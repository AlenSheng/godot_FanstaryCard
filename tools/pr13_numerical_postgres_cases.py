"""Validate and export the nine remaining B02 persisted contract cases."""
import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

IDS = {f'PR13-B02.{task}-T0{case}' for task in (1, 2, 4) for case in (1, 2, 3)}


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def require_equal_hash(row, before, after):
    if not re.fullmatch('[0-9a-f]{64}', row.get(before, '')) or row[before] != row.get(after):
        raise ValueError('Observed state/database mutation: ' + before)


def require_trx(path, expected=None):
    root = ET.parse(path).getroot(); counters = root.find('.//{*}Counters'); rows = root.findall('.//{*}UnitTestResult')
    if (counters is None or not rows or int(counters.get('total', 0)) != len(rows)
            or int(counters.get('executed', 0)) != len(rows) or int(counters.get('passed', 0)) != len(rows)
            or int(counters.get('notExecuted', 1)) != 0 or any(row.get('outcome') != 'Passed' for row in rows)
            or (expected is not None and len(rows) != expected)):
        raise ValueError('Actual complete unskipped native TRX required')
    return len(rows)


def validate(directory):
    result = read(directory / 'result.json')
    if (result.get('ok') is not True or result.get('remaining_schemas') != '0'
            or result.get('source_inputs_unchanged') is not True or result.get('client_inputs_unchanged') is not True
            or len(result.get('cleanup', {})) != 6 or any(value is not True for value in result['cleanup'].values())
            or len(result.get('phases', {})) != 4
            or any(p['exit_code'] != 0 or p['oom_killed'] for p in result['phases'].values())):
        raise ValueError('Clean actual native phases, source invariance and owned cleanup required')
    require_trx(directory / 'numerical-postgres.trx', 9)
    domain_count = require_trx(directory / 'domain.trx', 338)
    if result['numerical_client'].get('suite') != 'numerical-integration' or result['numerical_client'].get('ok') is not True or result['numerical_client'].get('failures'):
        raise ValueError('Actual Godot numerical scene required')
    client = read(directory / 'client-result.json')
    if client.get('ok') is not True or len(client.get('checks', [])) != 2 or any(r.get('passed') is not True for r in client['checks']):
        raise ValueError('Actual client codec and preview regression required')
    receipts = [read(p) for p in sorted((directory / 'receipts').glob('*.json'))]
    if len(receipts) != 9 or {r['caseId'] for r in receipts} != IDS or any(r['status'] != 'Passed' for r in receipts):
        raise ValueError('All nine exact native PostgreSQL receipts required')
    cases = {row['caseId']: row['actual'] for row in receipts}
    obsolete = cases['PR13-B02.1-T01']
    if (obsolete['compilerExitCode'] == 0 or set(obsolete['diagnostics']) != {'CS1739', 'CS1061'}
            or any(term not in obsolete['compilerLog'] for term in ['CS1739', 'CS1061', 'useConsumptionBasedFenxian', 'GuardianShieldRemainder'])
            or not re.fullmatch('[0-9a-f]{64}', obsolete.get('domainAssemblyHash', ''))):
        raise ValueError('Actual obsolete API compiler failure and reference hash required')
    require_equal_hash(obsolete, 'databaseBeforeHash', 'databaseAfterHash')
    defaults = cases['PR13-B02.1-T02']['rows']
    if len(defaults) != 2 or any(row['FenxianDrawPolicy'] != 1 or row['GuardianShieldPolicy'] != 1 for row in defaults):
        raise ValueError('Default current policies changed')
    if defaults[0]['observations'] != [0, 0, 1, 1, 2] or defaults[1]['observations'] != [2, 2, 2, 2, 2]:
        raise ValueError('Default policy behavior changed')
    candidates = cases['PR13-B02.1-T03']['rows']
    if (len(candidates) != 9 or {r.get('count') for r in candidates if r['hero'] == 'Mage'} != {1, 3, 5}
            or {r.get('level') for r in candidates if r['hero'] == 'Guardian'} != set(range(6))):
        raise ValueError('All candidate card counts and guardian levels required')
    for row in candidates:
        if row['hero'] == 'Mage':
            if row['FenxianDrawPolicy'] != 2 or row['draws'] != [0 if row['count'] == 1 else 1 if row['count'] == 3 else 2] * 8:
                raise ValueError('Candidate mage assertion differs')
        elif row['hero'] != 'Guardian' or row['GuardianShieldPolicy'] != 2 or row['totalWeaponBonus'] != 5 + 2 * row['level'] or row['GuardianShieldRemainderTenths'] != 0:
            raise ValueError('Candidate guardian assertion differs')
    order = cases['PR13-B02.2-T01']['rows']; gold = cases['PR13-B02.2-T02']['rows']; healing = cases['PR13-B02.2-T03']
    if len(order) != 7 or {r['name'] for r in order} != {'fire-first', 'water-first', 'per-card-floor', 'tuning-core', 'tuning-no-conflict', 'dual-no-core', 'dual-with-core'}:
        raise ValueError('Missing order, floor, tuning or dual element vector')
    if [r['actual']['Damage'] for r in gold] != [46, 72, 113] or [len(r['selectedInstances']) for r in gold] != [3, 4, 5]:
        raise ValueError('Exact GDD vectors changed')
    for row in [*order, *gold, healing['recovery'], healing['cardOnly'], healing['combined']]:
        expected = row['expected']; actual = row['actual']
        for e, a in [('damage', 'Damage'), ('heal', 'Heal'), ('core', 'CoreElement'), ('coreCount', 'CoreCount'), ('pairs', 'ConflictPairCount'), ('cancellation', 'ConflictCancellation'), ('resonance', 'ResonanceMultiplier')]:
            if expected[e] != actual[a]:
                raise ValueError('Actual persisted Resolver vector differs: ' + row['name'])
        if any(card['Level'] != 0 for card in row['selectedInstances']) or row['ConfigVersion'] != 'b02-vector-' + row['contextHash'][:12]:
            raise ValueError('Frozen full vector context required')
        require_equal_hash(row, 'snapshotBeforeHash', 'snapshotAfterHash'); require_equal_hash(row, 'databaseBeforeHash', 'databaseAfterHash')
    if [healing[k]['actual']['Heal'] for k in ['recovery', 'cardOnly', 'combined']] != [2, 13, 18]:
        raise ValueError('Priest ordinary healing and conflict E0 were conflated')
    policy = cases['PR13-B02.4-T01']; require_equal_hash(policy, 'oldBeforeHash', 'oldAfterHash'); require_equal_hash(policy, 'databaseBeforeHash', 'databaseAfterHash')
    if not all(policy.get(k) is True for k in ['candidateFrozen', 'newRoomCandidateEnabled', 'rollbackNewRoomDefaults']) or policy['oldSourceHash'] != policy['rollbackSourceHash'] or policy['oldSourceHash'] == policy['candidateSourceHash']:
        raise ValueError('Old/candidate/rollback room source differs')
    duel = cases['PR13-B02.4-T02']; require_equal_hash(duel, 'beforeHash', 'afterHash'); require_equal_hash(duel, 'beforeHash', 'restoredAgainHash')
    if duel['pvpWorkingRemainder'] != 8 or duel['restoredPveRemainder'] != 4 or duel['frozenPveVerified'] is not True:
        raise ValueError('Persisted PVP did not restore original PVE')
    legacy = cases['PR13-B02.4-T03']
    if legacy['restoredFenxian'] != 1 or legacy['restoredGuardian'] != 1 or len(legacy['faults']) != 3:
        raise ValueError('Legacy defaults or faults missing')
    for row in legacy['faults']:
        if row['rejected'] is not True: raise ValueError('Invalid snapshot was restored')
        require_equal_hash(row, 'liveBeforeHash', 'liveAfterHash'); require_equal_hash(row, 'injectedDatabaseHash', 'databaseAfterRejectionHash')
    return result, receipts, domain_count


def export(directory, source_sha, evidence_prefix):
    if not re.fullmatch('[0-9a-f]{40}', source_sha): raise ValueError('Exact implementation source SHA required')
    result, receipts, domain_count = validate(directory)
    return [{'case_id': r['caseId'], 'executed': True, 'status': 'Passed', 'source_sha': source_sha,
             'profiles_executed': ['OFFLINE', 'POSTGRES'], 'actual': {'native_receipt': r['actual'], 'domain_rows_passed': domain_count,
             'execution_source_base_sha': result['source_base_sha'], 'native_postgres_rows': 9, 'skipped': 0, 'godot_numerical_scene_passed': True, 'client_codec_preview_suites_passed': 2},
             'evidence': [evidence_prefix + '/' + name for name in ['native-result.json', 'source-hashes.json', 'numerical-postgres.trx', 'domain.trx', 'client-result.json']]}
            for r in receipts]


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--native', type=Path, required=True); parser.add_argument('--source-sha', required=True)
    parser.add_argument('--evidence-prefix', required=True); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    records = export(args.native, args.source_sha, args.evidence_prefix)
    if args.output.exists(): raise ValueError('Immutable case output already exists')
    args.output.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records), encoding='utf8'); print(json.dumps({'executed': len(records), 'passed': len(records), 'skipped': 0}))


if __name__ == '__main__': main()
