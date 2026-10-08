"""Export permanent notification-loss cases from actual PB/PG route proofs."""
import argparse
import json
from pathlib import Path
from pr13_render_cases import ROOT,sha,write


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();native=args.native.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    report=json.loads((native/'report.json').read_text(encoding='utf8'))
    if report['ok'] is not True or report['case_count']!=3 or report['passed_case_count']!=3 or report['owned_fixture_databases_removed'] is not True or report['owned_server_stopped'] is not True:raise ValueError('Complete owned three-scenario actual network/PG matrix required')
    cases={r['case']:r for r in report['cases']}
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']};rows=[]
    for cid,name in [('LOAD-04.3-T01','ready_required_all_lost_ticket'),('PR13-A04.1-T01','ready_required_all_lost_ticket'),('LOAD-04.3-T02','ready_started_all_lost_snapshot'),('LOAD-10.3-T01','ready_started_all_lost_snapshot')]:
        r=cases[name];client=r['actual'];transport=[json.loads(line) for line in (native/name/'transport/trace.jsonl').read_text(encoding='utf8').splitlines()];dropped=[e for e in transport if e['event']=='frame_dropped'];forwarded=[e for e in transport if e['event']=='frame_forwarded']
        lost='room.ready_required' if name=='ready_required_all_lost_ticket' else 'room.started'
        if not r['postgres_passed'] or not r['transport_passed'] or not client['passed'] or not dropped or any(e['kind']!=lost for e in dropped) or any(e['kind']==lost for e in forwarded):raise ValueError('Permanent loss predicate absent')
        rows.append(dict(case_id=cid,executed=True,status='Passed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE','POSTGRES'],actual=dict(permanently_missing_kind=lost,actual_dropped_frames=len(dropped),missing_kind_forwarded=0,ready_send_count=client['ready_send_count'],authoritative_ticket_reads=client['ticket_reads'],actual_snapshot_frames=sum(e['kind']=='room.snapshot' for e in forwarded),same_authoritative_match=client['observed_match_id']==client['expected_match_id'],same_authoritative_room=client['observed_room_id']==client['expected_room_id'],business_cleanup=client['cleanup'],local_terminal=client['local_terminal'],route_clear=client['route_probe_clear'],postgres_postconditions=r['postgres']),scope='Actual production decoder/store/load client, full Program and PostgreSQL; owned relay discards original PB frames and all replay of the chosen kind. Legal abandon in cleanup is not a natural gameplay cycle. LIVE/capacity/human separate.'))
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows).encode());write(out/'report.json',dict(source_sha=report['source_sha'],plan_sha256=sha(plan),source=dict(scope='actual permanent notification loss and authority recovery',input_hashes=report['cases'][0]['input_hashes'],native_report_sha256=sha(native/'report.json')),executed=len(rows),passed=len(rows),accepted=False));print(json.dumps(dict(executed=len(rows),passed=len(rows))))
    return 0


if __name__=='__main__':raise SystemExit(main())
