"""Export the same-trial ACK response loss/restart and owner/hold assertions."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from pr13_render_cases import ROOT, sha, write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(); native = args.native.resolve(); out = args.output.resolve()
    report = json.loads((native / 'report.json').read_text(encoding='utf8'))
    trx = native / 'combined.trx'; doc = ET.parse(trx)
    counts = {k: int(v) for k, v in doc.find('.//{*}Counters').attrib.items()}
    if (report['exit_code'] != 0 or report['owned_databases_removed'] is not True or
            counts['total'] != 5 or counts['passed'] != 5 or counts['executed'] != 5):
        raise ValueError('All five unskipped owned native assertions required')
    rows = [dict(case=r.attrib['testName'], outcome=r.attrib['outcome']) for r in doc.findall('.//{*}UnitTestResult')]
    combined = [r for r in rows if 'drop-first-committed-restart' in r['case']]
    owner = [r for r in rows if 'Extraction_settlement_commits_all_assets_once_and_releases_notification' in r['case']]
    receipts = native / 'process-evidence/receipts.jsonl'
    raw = [json.loads(line) for line in receipts.read_text(encoding='utf8').splitlines()]
    restart = [r['evidence'] for r in raw if r['caseId'] == 'ACK-FAULT-combined-restart']
    committed = [r['evidence'] for r in raw if r['caseId'] == 'ACK-FAULT-drop-first-committed-restart']
    if (len(combined) != 1 or len(owner) != 1 or len(restart) != 1 or len(committed) != 1 or
            restart[0]['oldProcessId'] == restart[0]['newProcessId'] or restart[0]['acknowledgedRows'] != 1 or
            committed[0]['assetsOnce'] is not True or committed[0]['acknowledged'] is not True):
        raise ValueError('Same-trial committed response loss, changed OS PID and once-only assets required')
    attempts = committed[0]['attempts']
    if (len(attempts) != 2 or not attempts[0]['Dropped'] or attempts[1]['Dropped'] or
            len({r['KeySha256'] for r in attempts}) != 1 or any(r['BackendStatus'] != 200 for r in attempts)):
        raise ValueError('Original production client must retry the same ACK key after restart')
    plan = ROOT / 'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'
    contracts = {c['id']: c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages']
                 for task in pkg['subtasks'] for c in task['test_cases']}
    records = []
    for cid, selected, actual in [
        ('LOAD-10.3-T02', combined, dict(restart=restart[0], attempts=attempts, assets_once=True)),
        ('PR13-A09.3-T01', combined, dict(restart=restart[0], attempts=attempts, assets_once=True)),
        ('LOAD-08.4-T02', owner, dict(other_player_receipt_and_match_rejected=True, wrong_match_rejected=True, wallet_unchanged=True)),
        ('PR13-B11.3-T03', owner, dict(pending_hold_ack_rejected=True, pending_notification_withheld=True,
                                      owner_receipt_readable=True, committed_owner_receipt_preserved=True, foreign_ack_rejected=True))]:
        records.append(dict(case_id=cid, executed=True, status='Passed', setup=contracts[cid]['setup_and_injection'],
                            expected=contracts[cid]['expected'], profiles_executed=['OFFLINE', 'POSTGRES'],
                            actual=dict(native_assertions=selected, **actual),
                            scope='Actual owned PG and full Program/production Godot for combined ACK fault; repository identity/hold assertions where named. Seeded terminal route; natural exploration, capacity and human evidence separate.'))
    out.mkdir(parents=True, exist_ok=False)
    (out / 'cases.jsonl').write_bytes(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records).encode())
    write(out / 'report.json', dict(source_sha=report['source_sha'], plan_sha256=sha(plan),
                                   source=dict(scope='exact same-trial combined fault and native owner guards',
                                               input_hashes={str(f.relative_to(ROOT)).replace('\\', '/'): sha(f)
                                                             for f in (trx, native / 'report.json', receipts)}),
                                   executed=4, passed=4, native_counters=counts, accepted=False))
    print(json.dumps(dict(executed=4, passed=4))); return 0


if __name__ == '__main__': raise SystemExit(main())
