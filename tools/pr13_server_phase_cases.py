"""Export exact server replay/STOP, measured runtime phases and bounded sends."""
import argparse
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from pr13_render_cases import ROOT,sha,write

MAPPING={
 'PR13-B04.1-T01':('Persistence.PostgresRuntimeIntegrationTests.Actual_starter_deck_matches_published_twenty_white_level_zero_cards',['OFFLINE','POSTGRES']),
 'LOAD-09.1-T01':('Persistence.PostgresRuntimeIntegrationTests.Four_humans_enqueue_ready_and_launch_one_persisted_room',['OFFLINE','POSTGRES']),
 'LOAD-09.1-T02':('Persistence.PostgresRuntimeIntegrationTests.Four_humans_enqueue_ready_and_launch_one_persisted_room',['OFFLINE','POSTGRES']),
 'LOAD-09.1-T03':('Persistence.PostgresRuntimeIntegrationTests.Four_humans_enqueue_ready_and_launch_one_persisted_room',['OFFLINE','POSTGRES']),
 'PR13-A02.4-T01':('Persistence.PostgresRuntimeIntegrationTests.Queued_STOP_cancellation_releases_assets_once_and_allows_next_preparation',['OFFLINE','POSTGRES']),
 'PR13-A02.4-T02':('Persistence.PostgresRuntimeIntegrationTests.Match_timeout_removes_unready_human_and_fills_room_with_bots',['OFFLINE','POSTGRES']),
 'LOAD-09.3-T01':('Matchmaking.ReadySendIsolationTests.One_slow_player_cannot_hold_three_ready_notifications_and_each_player_replay_stays_ordered',['OFFLINE']),
 'LOAD-09.3-T03':('Matchmaking.ReadySendIsolationTests.One_slow_player_cannot_hold_three_ready_notifications_and_each_player_replay_stays_ordered',['OFFLINE']),
 'LOAD-09.4-T02':('Rooms.RoomActorTests.Concurrent_commands_are_serialized_by_single_reader',['OFFLINE']),
}
PHASES={
 'PR13-B01.1-T03':('Thousands_of_business_ids_never_create_metric_identity_labels',['OFFLINE']),
 'LOAD-06.3-T01':('Actual_pool_acquisition_wait_is_separate_from_replay_SQL_execution',['OFFLINE','POSTGRES']),
 'LOAD-06.3-T02':('Blocked_socket_send_keeps_actor_execution_separate_in_the_same_request_trace',['OFFLINE']),
 'LOAD-06.3-T03':('Thousands_of_business_ids_never_create_metric_identity_labels',['OFFLINE']),
}


def assertions(trx):
    doc=ET.parse(trx);counters={k:int(v) for k,v in doc.find('.//{*}Counters').attrib.items()}
    if counters['total']!=counters['passed'] or counters['total']!=counters['executed'] or counters.get('notExecuted',0):raise ValueError('Every native assertion must pass with zero skips')
    definitions={r.attrib['id']:r.find('{*}TestMethod').attrib for r in doc.findall('.//{*}UnitTest')};rows=[]
    for r in doc.findall('.//{*}UnitTestResult'):
        method=definitions[r.attrib['testId']];output=r.findtext('.//{*}StdOut') or ''
        rows.append(dict(method=method['className'].split(',')[0]+'.'+method['name'],case=r.attrib['testName'],outcome=r.attrib['outcome'],measurements=[json.loads(line.split('PR13_RUNTIME ',1)[1]) for line in output.splitlines() if line.startswith('PR13_RUNTIME ')]))
    return counters,rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--native',type=Path,required=True);p.add_argument('--phases',type=Path,required=True);p.add_argument('--outbound',type=Path,required=True);p.add_argument('--outbound-source-sha',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';contracts={c['id']:c for pkg in json.loads(plan.read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']}
    def export(label,source,native_rows,mapping,parents):
        dst=out/label;dst.mkdir();records=[]
        for cid,(method,profiles) in mapping.items():
            selected=[r for r in native_rows if r['method']=='FantasyCard.Server.Tests.'+method]
            expected_count=3 if method.endswith('Actual_starter_deck_matches_published_twenty_white_level_zero_cards') else 1
            if len(selected)!=expected_count or any(r['outcome']!='Passed' for r in selected):raise ValueError('Exact assertion absent: '+method)
            records.append(dict(case_id=cid,executed=True,status='Passed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=profiles,actual=dict(native_assertions=selected),scope='Actual named native production components; PostgreSQL where declared, controlled stalled sockets and in-process actual trace/meter listeners. Full LIVE/capacity/performance review and human evidence separate.'))
        (dst/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records).encode());write(dst/'report.json',dict(source_sha=source,plan_sha256=sha(plan),source=dict(scope=label,input_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in parents}),executed=len(records),passed=len(records),accepted=False))
        return len(records)
    n=args.native.resolve();report=json.loads((n/'report.json').read_text(encoding='utf8'))
    if report['exit_code']!=0 or report['owned_databases_removed'] is not True or report['source_changed_during_execution']:raise ValueError('Owned current suite failed or changed')
    counters,native=assertions(n/'native.trx');count=export('replay-stop-isolation',report['source_sha'],native,MAPPING,[n/'report.json',n/'native.trx'])
    f=args.phases.resolve();meta=json.loads((f/'report.json').read_text(encoding='utf8'))
    if meta['exit_code']!=0 or meta['owned_databases_removed'] is not True:raise ValueError('Measured PG phase run incomplete')
    _,phase_rows=assertions(f/'native.trx');count+=export('runtime-phases',meta['source_sha'],phase_rows,{'%s'%cid:('Common.RuntimeTimingTests.'+method,profiles) for cid,(method,profiles) in PHASES.items()},[f/'report.json',f/'native.trx'])
    guard=args.outbound.resolve();_,guards=assertions(guard/'outbound.trx');pending=[r for r in guards if r['method'].endswith('.PendingSendLimitAbortsSlowPeer')];size=[r for r in guards if r['method'].endswith('.Exactly_16KiB_sends_but_one_byte_more_closes_before_socket_write')]
    if len(pending)!=1 or len(size)!=1:raise ValueError('Both original pending-32 and actual outbound 16KiB/+1 guards required')
    source_sha=subprocess.check_output(['git','rev-parse',args.outbound_source_sha+'^{commit}'],cwd=ROOT,text=True).strip()
    paths=['server/src/FantasyCard.Server/Realtime/RealtimeConnection.cs','server/tests/FantasyCard.Server.Tests/Realtime/OutboundSizeBoundaryTests.cs','server/tests/FantasyCard.Server.Tests/Realtime/ProtobufTicketTests.cs']
    if subprocess.check_output(['git','diff',source_sha,'--',*paths],cwd=ROOT):raise ValueError('Outbound implementation/tests differ from the actual declared tested commit')
    dst=out/'outbound-guards';dst.mkdir();cid='LOAD-09.3-T02';record=dict(case_id=cid,executed=True,status='Passed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE'],actual=dict(native_assertions=pending+size,maximum_pending_sends=32,maximum_outbound_bytes=16384),scope='Actual native binary connection guard boundaries; controlled socket, no network capacity claim');(dst/'cases.jsonl').write_bytes((json.dumps(record,ensure_ascii=False)+'\n').encode());write(dst/'report.json',dict(source_sha=source_sha,plan_sha256=sha(plan),source=dict(scope='exact pending and outbound guard assertions',input_hashes={'native_trx':sha(guard/'outbound.trx'),**{path:sha(ROOT/path) for path in paths}}),executed=1,passed=1,accepted=False))
    print(json.dumps(dict(executed=count+1,passed=count+1,native_current_counters=counters)))
    return 0


if __name__=='__main__':raise SystemExit(main())
