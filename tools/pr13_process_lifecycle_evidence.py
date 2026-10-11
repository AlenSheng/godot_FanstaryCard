"""Verify cloud process lifecycle evidence bytes; executes no native game code."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


EXPECTED = {
    'A05_healthy_teammate_old_room_and_new_room_survive_real_callbacks_and_OS_restart': 1,
    'A05_actual_settlement_transaction_fault_recovers_without_duplicate_assets': 2,
    'A05_actual_runtime_pending_holds_survive_OS_restart_without_early_completion': 1,
    'Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt': 1,
    'A05_guard_preserves_ordinary_context_and_authoritative_ACK_recovery': 3,
    'Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth': 4,
    'Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes': 4,
    'Real_LOAD02_timeout_STOP_preserves_original_business_truth': 3,
    'Full_host_Running_room_resumes_after_abrupt_OS_process_restart': 1,
    'Full_host_extraction_then_two_restarts_preserve_assets_and_duplicate_ACK': 1,
    'Full_host_cold_start_commits_durable_pending_holds_once': 1,
    'Full_host_quarantines_contradictory_terminal_checkpoint_but_recovers_next_room': 1,
    'Full_host_three_entry_cycles_duplicate_READY_and_ACK_release_owned_locks': 1,
    'Full_host_MarkRunning_committed_response_loss_recovers_one_room_and_actual_client_routes': 1,
    'SupportOnly_actual_Register_conflict_retries_same_launch_without_partial_room_or_second_reservation': 2,
    'Actual_default_single_IP_auth_limit_is_separate_from_capacity': 1,
    'Actual_prelogged_account_still_observes_default_economy_write_limit': 1,
}
VARIANTS = {
    'A05_actual_settlement_transaction_fault_recovers_without_duplicate_assets': [('precommit',), ('committed-response-loss',)],
    'A05_guard_preserves_ordinary_context_and_authoritative_ACK_recovery': [('ordinary', 'success'), ('recovered', 'uncommitted-loss'), ('recovered', 'committed-loss')],
    'Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth': [(x,) for x in ('drop-first-committed', 'drop-first-committed-restart', 'drop-all-committed', 'drop-all-uncommitted')],
    'Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes': [(x,) for x in ('cycles-middle-response-loss', 'cycles-middle-uncommitted-loss', 'stop-before-commit', 'stop-after-commit')],
    'Real_LOAD02_timeout_STOP_preserves_original_business_truth': [('timeout-before-stop', 'LOAD-02.2-T01'), ('normal-wait-stop', 'LOAD-02.2-T02'), ('committed-unknown-stop', 'LOAD-02.2-T03')],
    'SupportOnly_actual_Register_conflict_retries_same_launch_without_partial_room_or_second_reservation': [('player-route',), ('room-id',)],
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def original_path(root, name):
    path = root / name
    # Godot font metadata has names exceeding Windows MAX_PATH.
    if __import__('os').name == 'nt':
        path = Path('\\\\?\\' + str(path.resolve()))
    return path


def verify(root, backup):
    root, backup = Path(root), Path(backup)
    proof = json.loads((backup / 'local-backup-receipt.json').read_bytes())
    assert proof['ok'] and proof['all_original_members_SHA_verified'] and proof['archive_gzip_CRC_verified']
    raw = (backup / 'delivery-manifest.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == proof['manifest_sha256']
    manifest = json.loads(raw)
    seen = set()
    for row in manifest['files']:
        name = row['path']
        assert name not in seen and not Path(name).is_absolute() and '..' not in Path(name).parts
        seen.add(name)
        path = original_path(root, name)
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    assert len(seen) == proof['members_verified']
    trx = ET.parse(root / 'native-output/results/native-process27.trx')
    counters = trx.find('.//{*}Counters').attrib
    assert all(int(counters[k]) == 29 for k in ('total', 'executed', 'passed'))
    assert all(int(v) == 0 for k, v in counters.items() if k not in ('total', 'executed', 'passed'))
    definitions = {x.attrib['id']: x.find('./{*}TestMethod').attrib for x in trx.findall('.//{*}UnitTest')}
    rows = trx.findall('.//{*}UnitTestResult')
    assert len(rows) == 29 and len({x.attrib['executionId'] for x in rows}) == 29
    methods = Counter()
    variants = {k: [] for k in VARIANTS}
    actual = []
    for row in rows:
        assert row.attrib['outcome'] == 'Passed'
        method = definitions[row.attrib['testId']]
        assert method['className'].split(',')[0] == 'FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests'
        name = method['name']
        assert row.attrib['testName'].split('(', 1)[0].rsplit('.', 1)[-1] == name
        methods[name] += 1
        arguments = tuple(re.findall(r'"([^"\n]*)"', row.attrib['testName']))
        if name in variants:
            variants[name].append(arguments)
        else:
            assert not arguments
        actual.append({**row.attrib, 'method': name})
    assert methods == Counter(EXPECTED)
    assert all(Counter(variants[k]) == Counter(v) for k, v in VARIANTS.items())
    outer = json.loads((root / 'metadata/run-result.json').read_bytes())
    assert not outer['ok'] and not outer['oom_killed']
    assert outer['inner']['error'] == 'AssertionError'
    assert outer['inner']['phases'] == [{'name': k, 'exit_code': 0} for k in ('restore', 'build', 'native')]
    assert outer['remaining_owned_fixture_schemas'] == 0
    assert outer['owned_containers_removed'] and outer['frozen_source_and_package_bytes_unchanged']
    resources = [json.loads(x) for x in (root / 'metadata/resources.jsonl').read_text().splitlines()]
    assert resources and all(x['memory_available_bytes'] >= 500000000 and x['production_health_status'] == 200 for x in resources)
    for x in resources:
        events = dict((k, int(v)) for k, v in (line.split() for line in x['owned_SDK_memory_events'].splitlines()))
        assert events.get('oom') == events.get('oom_kill') == 0
    return {
        'ok': True, 'native_rows_passed': 29, 'native_distinct_methods': 17, 'native_skipped': 0,
        'native_exit_code': 0, 'wrapper_original_failed': True,
        'wrapper_failure_reason': 'Frozen wrapper expected 27 rows, omitted two current default-limit methods; its display-name split also split dotted theory argument strings.',
        'original_failed_wrapper_preserved': True,
        'method_names_derived_from_TRX_TestDefinitions': True,
        'complete_original_G_members_reverified': len(seen), 'owned_containers_removed': True,
        'remaining_owned_fixture_schemas': 0, 'cgroup_oom_and_oom_kill': 0,
        'cgroup_observed_peak_bytes': max(x['owned_SDK_memory_current_bytes'] for x in resources),
        'host_observed_minimum_available_bytes': min(x['memory_available_bytes'] for x in resources),
        'actual_case_rows': actual, 'MAIN_accepted': False,
    }


def verify_pending(root):
    root = Path(root) / 'native-output/process-evidence'
    receipts = [json.loads(x) for x in (root / 'receipts.jsonl').read_text().splitlines()]
    passed = [x for x in receipts if x['caseId'] == 'A05-runtime-passed']
    assert len(passed) == 1
    evidence = passed[0]['evidence']
    assert evidence['pendingBefore'] == evidence['committedAfter'] == 4
    assert len(evidence['pids']) == len(set(evidence['pids'])) == 2
    controls = list(root.glob('ack-client-a05-pending-*/control'))
    assert len(controls) == 1
    control = controls[0]
    result = json.loads((control / 'result.json').read_bytes())
    assert result['ok'] and not result['failures'] and result['observations']
    assert all(x['passed'] for x in result['observations'])
    for phase in ('pending-before-restart', 'pending-after-restart'):
        state = json.loads((control / (phase + '.json')).read_bytes())
        assert state['phase'] == phase and state['match_id'] == evidence['matchId']
        assert not state['settlement'] and state['lobby_unfinished_settlement'] is None
        for label in ('original recovery match retained', 'no premature client completion', 'actual pending ACK rejected 409', 'actual next preparation rejected'):
            assert any(x['check'] == phase + ' ' + label for x in result['observations'])
    ready = json.loads((control / 'ready.json').read_bytes())
    assert ready['settlement']['matchId'] == evidence['matchId']
    assert ready['settlement']['settlementId'] == evidence['receiptId']
    completed = json.loads((control / 'completed.json').read_bytes())
    assert not completed['match_id'] and not completed['settlement'] and not completed['busy']
    before, after = evidence['before'], evidence['after']
    assert before['Owner'] == after['Owner'] == evidence['playerId']
    assert after['Gold'] == before['Gold'] + 23 and after['Potions'] == before['Potions'] + 2
    assert after['GoldLedger'] == after['Movements'] == 1
    assert after['Location'] == 'Equipped'
    return {'original_receipt': passed[0], 'control_directory': str(control), 'observations': result['observations'], 'POSTGRES_only': True, 'WAN_LIVE_claimed': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('backup')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = verify(args.root, args.backup)
    Path(args.output).write_bytes((json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps({k: v for k, v in result.items() if k != 'actual_case_rows'}))
