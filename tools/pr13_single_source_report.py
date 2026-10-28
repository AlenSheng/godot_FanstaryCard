"""Generate and verify immutable report views from one qualified raw replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

try:
    from . import pr13_audit_replay as audit
except ImportError:
    import pr13_audit_replay as audit

VERSION = 'pr13-single-source-report-v1'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _source_code():
    paths = [Path(__file__), Path(audit.__file__),
             Path(audit.reconcile_cycles.__code__.co_filename), Path(audit.aggregate_recent.__code__.co_filename)]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def build_model(root, manifest, *, run_id, stop_ms, final_ms, algorithm='current'):
    root = Path(root).resolve()
    if not isinstance(run_id, str) or not run_id or len(run_id) > 256 or any(c in run_id for c in '\r\n\x00'):
        raise ValueError('One explicit bounded original run ID is required')
    result = audit.replay(root, manifest, stop_ms=stop_ms, final_ms=final_ms, algorithm=algorithm)
    if result['status'] != 'Derived':
        raise ValueError('Original source replay is not qualified: ' + result['status'])
    contexts = set()
    for item in result['files']:
        if not item['path'].endswith('.jsonl'):
            continue
        with (root / item['path']).open(encoding='utf-8') as stream:
            for line in stream:
                event = json.loads(line)
                contexts.add(tuple(event[key] for key in ('run_id', 'client_id', 'process_epoch')))
    if not contexts or {c[0] for c in contexts} != {run_id}:
        raise ValueError('Declared run ID differs from the actual raw event contexts')
    # The second read supplies identities only. It cannot authorize changed raw.
    if any(row['state'] != 'Matching' for row in audit.check_files(root, manifest)):
        raise ValueError('Original sources changed while generating report identities')
    return dict(schema_version=1, generator=VERSION, source_code_sha256=_source_code(),
                run_id=run_id, contexts=[dict(run_id=r, client_id=c, process_epoch=p) for r,c,p in sorted(contexts)],
                cutoff_basis='Explicit frozen original STOP/final values; no new clock qualification inferred',
                original_runtime_source_not_inferred_from_replay_code=True,
                check_denominator_scope='No separate check records supplied; zero check denominators do not prove no business failures',
                audit=result)


def _views(model):
    summaries, distribution = [], []
    for cutoff in ('running', 'drain', 'final'):
        data = model['audit']['derived'][cutoff]
        summaries.append(dict(cutoff=cutoff, **{key: value for key, value in data.items() if type(value) is int}))
        clients = set(data['cycles_by_client']) | set(data['acknowledgements_by_client'])
        for client in sorted(clients):
            distribution.append(dict(cutoff=cutoff, client_id=client,
                                     completed_cycles=data['cycles_by_client'].get(client, 0),
                                     acknowledgements=data['acknowledgements_by_client'].get(client, 0)))
    def cell(value):
        return str(value).replace('\\', '\\\\').replace('|', '\\|').replace('\r', '\\r').replace('\n', '\\n').replace('`', '\\`')
    derived = model['audit']['derived']
    lines = ['# PR13 single-source report', '',
             'Run: `' + cell(model['run_id']) + '`',
             'Generator: `' + model['generator'] + '`; replay: `' + model['audit']['algorithm'] + '`',
             'Cutoffs (Unix ms): STOP=' + str(derived['stop_ms']) + ', final=' + str(derived['final_ms']), '',
             '| Cutoff | Acknowledgements | Completed cycles |', '| --- | ---: | ---: |']
    lines += ['| {cutoff} | {acknowledgements} | {completed_cycles} |'.format(**row) for row in summaries]
    lines += ['', '| Cutoff | Client | Acknowledgements | Completed cycles |', '| --- | --- | ---: | ---: |']
    lines += ['| ' + ' | '.join(cell(row[key]) for key in ('cutoff','client_id','acknowledgements','completed_cycles')) + ' |' for row in distribution]
    lines += ['', 'Client distribution covers recorded events; zero-cycle clients require a launch manifest.',
              model['check_denominator_scope'] + '.',
              'This derivation grants no runtime, capacity, historical recovery or whole-project acceptance.', '', '## Source identities', '']
    lines += ['- ' + cell(row['path']) + ': ' + str(row['bytes']) + ' bytes, SHA256 `' + row['sha256'] + '`' for row in model['audit']['files']]
    lines += ['', '## Algorithm source identities', '']
    lines += ['- ' + name + ': `' + digest + '`' for name,digest in sorted(model['source_code_sha256'].items())]
    if model['audit']['legacy_redlines'] is not None:
        lines += ['', '## Retained legacy redlines', '', '```json',
                  json.dumps(model['audit']['legacy_redlines'], sort_keys=True, indent=2), '```']
    payloads = dict(model_json=encoded(model), summary_json=encoded(summaries), distribution_json=encoded(distribution),
                    report_md=('\n'.join(lines) + '\n').encode('utf-8'))
    return {name.replace('_', '.'): payload for name,payload in payloads.items()}


def bundle_payloads(model):
    payloads = _views(model)
    manifest = dict(generator=VERSION, run_id=model['run_id'], files=[
        dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()) for name,data in sorted(payloads.items())])
    return dict(payloads, **{'manifest.json': encoded(manifest)})


def create_bundle(root, manifest, output, **options):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('Refusing to overwrite an archived report bundle')
    if output.is_relative_to(root):
        raise ValueError('Generated report views must be outside the original source root')
    payloads = bundle_payloads(build_model(root, manifest, **options))
    output.mkdir(parents=True, exist_ok=False)
    for name,data in payloads.items():
        with (output / name).open('xb') as stream:
            stream.write(data)
    return payloads


def validate_bundle(root, manifest, bundle, **options):
    # Recompute from original raw, never trust a possibly edited model.json.
    expected = bundle_payloads(build_model(root, manifest, **options))
    bundle = Path(bundle)
    if not bundle.is_dir() or {p.name for p in bundle.iterdir()} != set(expected):
        raise ValueError('Derived report bundle entries differ from the qualified model')
    for name,data in expected.items():
        path = bundle / name
        if not path.is_file() or path.stat().st_size != len(data) or path.read_bytes() != data:
            raise ValueError('Derived report view differs from the same raw and algorithm: ' + name)
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--stop-ms', type=int, required=True)
    parser.add_argument('--final-ms', type=int, required=True)
    parser.add_argument('--algorithm', choices=('current','legacy-accounting'), default='current')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--output', type=Path)
    action.add_argument('--check', type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        options = dict(run_id=args.run_id, stop_ms=args.stop_ms, final_ms=args.final_ms, algorithm=args.algorithm)
        if args.output is not None: create_bundle(args.input, manifest, args.output, **options)
        else: validate_bundle(args.input, manifest, args.check, **options)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps(dict(state='Rejected', error_type=type(error).__name__, acceptance=False)))
        return 3
    print(json.dumps(dict(state='Generated' if args.output is not None else 'Verified', generator=VERSION, acceptance=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
