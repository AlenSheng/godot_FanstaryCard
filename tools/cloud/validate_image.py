"""Run the existing validator against final image DLLs, with private evidence local."""
import argparse
import importlib.util
import json
import pathlib
import re
import sys
from deployment import sha, validate_image_proof


def export_diagnostics(evidence, destination):
    """Publish only disposable test logs/results, never DLLs, mappings or dumps."""
    destination.mkdir(parents=True, exist_ok=True)
    paths = [evidence / name for name in ('tests.log', 'smoke-build.log',
             'smoke-before.log', 'smoke-after.log', 'test-dependency-hashes.txt')]
    paths += sorted((evidence / 'results').glob('*.trx'))
    inventory = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        # These files come from a credential-free, disposable test stack. Still
        # scrub bearer/JWT text and explicit credential assignments if a failing
        # test prints them. No container logs or runtime state files are exported.
        value = path.read_text(encoding='utf-8', errors='replace')
        value = re.sub(r'(?i)Bearer\s+[^\s"<>]+', 'Bearer [redacted]', value)
        value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b', '[redacted JWT]', value)
        value = re.sub(r'(?im)^.*(?:TEST_SERVER_SSH_KEY|GH_TOKEN|accessToken|access_token|api[_-]?key|password)\s*[:=].*$', '[redacted credential assignment]', value)
        target = destination / ('results' if path.suffix == '.trx' else '') / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8')
        inventory.append({'name': str(target.relative_to(destination)), 'bytes': target.stat().st_size})
    (destination / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')


def validate(source, image, builder, source_sha, output, diagnostics=None):
    source = pathlib.Path(source).resolve(strict=True)
    sha(source_sha)
    # Never inspect a real release key. Check existence only and stop safely.
    if (source / 'release-encryption.key').exists():
        raise ValueError('Image validation requires a credential-free source checkout')
    trusted_tools = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(trusted_tools))
    spec = importlib.util.spec_from_file_location('trusted_image_validator', trusted_tools / 'validate_docker_server.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.ROOT = source
    validator.PRIVATE = output.parent / 'private-image-validation'
    # Disposable fixture value, never a server credential or uploaded secret.
    validator.secrets.token_hex = lambda count: '0' * (count * 2)
    validator.PRIVATE.mkdir(parents=True, exist_ok=True)
    before = set(validator.PRIVATE.iterdir())
    try:
        ok = validator.validate(image, builder)
    finally:
        created = set(validator.PRIVATE.iterdir()) - before
        if len(created) == 1:
            export_diagnostics(next(iter(created)), diagnostics or output.parent / 'diagnostics')
    if len(created) != 1:
        raise ValueError('Ambiguous final-image evidence')
    report = json.loads((created.pop() / 'verification.json').read_text())
    proof = {'ok': ok, 'source_sha': source_sha, 'image_id': report.get('image'),
             'assemblies': report.get('assemblies'), 'tests': report.get('tests'),
             'runtime_uid': report.get('runtime_uid'),
             'restart_test_passed': report.get('smoke_before', {}).get('ok') is True and report.get('smoke_after', {}).get('ok') is True,
             'database_outage': report.get('database_outage'),
             'production_local_auth_status': report.get('production_local_auth_status'),
             'cleanup_ok': report.get('cleanup', {}).get('ok') is True}
    output.write_text(json.dumps(proof, indent=2) + '\n')
    if not ok:
        raise ValueError('Final-image validation failed; private local evidence retained')
    validate_image_proof(proof, proof['image_id'], source_sha)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--builder', required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--diagnostics', type=pathlib.Path)
    args = parser.parse_args()
    validate(args.source, args.image, args.builder, args.source_sha, args.output, args.diagnostics)
