"""Verify the declared native PostgreSQL CI artifact, independently of job exit0.

This gate covers the explicit required-method manifest, not every CI step or
the project's runtime acceptance. Source references and dirty input manifests
remain distinct. It never reads or records credential values.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
try:
    from .pr13_suite_coverage import assess_trx
except ImportError:
    from pr13_suite_coverage import assess_trx

def assess(trx, required_file, source_file, expected_source, native_exit_file, source_manifest=None):
    required = json.loads(required_file.read_bytes())
    methods = required.get('required_methods')
    if not isinstance(methods, dict) or not methods or any(
            not isinstance(k, str) or not k or type(v) is not int or v < 1 for k, v in methods.items()):
        raise ValueError('A nonempty explicit required-method manifest is required')
    if not re.fullmatch('[0-9a-f]{40}', expected_source):
        raise ValueError('An exact expected source reference is required')
    actual_source = source_file.read_text(encoding='utf8').strip() if source_file.is_file() else None
    native_exit = None
    if native_exit_file.is_file():
        text = native_exit_file.read_text(encoding='utf8').strip()
        if not re.fullmatch('-?[0-9]+', text):
            raise ValueError('Native exit file must contain the actual integer exit')
        native_exit = int(text)
    if actual_source != expected_source:
        result = {'state': 'Blocked', 'reason': 'source_reference_missing_or_mismatched', 'acceptance': False}
    elif native_exit is None or not trx.is_file():
        result = {'state': 'Blocked', 'reason': 'native_exit_or_TRX_missing', 'acceptance': False}
    elif native_exit != 0:
        result = {'state': 'Failed', 'reason': 'native_exit_nonzero', 'acceptance': False}
    else:
        try:
            tree = ET.parse(trx)
            counter = tree.find('.//{*}Counters')
            if counter is None:
                raise ValueError('Native counters are missing')
            counts = {k: int(v) for k, v in counter.attrib.items()}
            rows = tree.findall('.//{*}UnitTestResult')
            outcomes = Counter(row.attrib.get('outcome') for row in rows)
            execution_ids = [row.attrib['executionId'] for row in rows if row.attrib.get('executionId')]
            if (any(v < 0 for v in counts.values()) or
                    counts.get('total') != len(rows) or
                    counts.get('executed') != len(rows) - outcomes['NotExecuted'] or
                    counts.get('passed', 0) != outcomes['Passed'] or
                    counts.get('failed', 0) != outcomes['Failed'] or
                    counts.get('notExecuted', 0) != outcomes['NotExecuted'] or
                    len(execution_ids) != len(set(execution_ids))):
                raise ValueError('Native counters or execution identities contradict result rows')
            result = assess_trx(trx, methods)
        except (ET.ParseError, KeyError, TypeError, ValueError, OSError) as error:
            result = {'state': 'Blocked', 'reason': 'native_TRX_invalid_or_inconsistent',
                      'error_type': type(error).__name__, 'acceptance': False}
    code = 0 if result['state'] == 'CoveredForMainReview' else 1 if result['state'] == 'Failed' else 3
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return {'state': result['state'], 'pipeline_exit': code, 'native_exit': native_exit,
            'source_reference': actual_source, 'expected_source_reference': expected_source,
            'source_is_reference_not_clean_build_claim': True,
            'actual_input_manifest_SHA': digest(source_manifest) if source_manifest else None,
            'TRX_SHA': digest(trx), 'required_manifest_SHA': digest(required_file),
            'required_methods': methods, 'coverage': result, 'task_or_project_acceptance': False,
            'scope': 'Declared native PG method coverage and source reference only; not full hosted workflow or deployment'}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trx', type=Path, required=True)
    parser.add_argument('--required-methods', type=Path, required=True)
    parser.add_argument('--source-file', type=Path, required=True)
    parser.add_argument('--expected-source', required=True)
    parser.add_argument('--native-exit-file', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = assess(args.trx, args.required_methods, args.source_file, args.expected_source,
                    args.native_exit_file, args.source_manifest)
    result['guard_source_SHA'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['coverage_helper_source_SHA'] = hashlib.sha256(Path(__file__).with_name('pr13_suite_coverage.py').read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k: result[k] for k in ('state', 'pipeline_exit', 'native_exit', 'task_or_project_acceptance')}))
    return result['pipeline_exit']

if __name__ == '__main__':
    raise SystemExit(main())
