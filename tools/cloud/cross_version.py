"""Bounded, sequential source-rebuild compatibility probes on one private PG.

No deployment guard is changed. Negative old-version observations remain unsafe,
even when the reproduction itself meets its expected outcome.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

OLD = '8489fe97c7da71e1a5bfe1a860faf86fd4e0a4af'
NEW = 'cc6da2e7b8a2c7ba46d867af74ce28a58ccfeac3'
CONTROLLER = '262390134e98f169899d076e6fa21926d44ba1aa'
ACTUAL_OLD_IMAGE = 'sha256:e7defa05caeb1188afb4cfc4390d96900bfc10afb4996ced23a042fb09132697'


def command(args, *, env=None, log=None, timeout=120, check=True):
    result = subprocess.run([str(x) for x in args], env=env, capture_output=True,
                            text=True, timeout=timeout)
    if log:
        Path(log).write_text(result.stdout + result.stderr)
    if check and result.returncode:
        raise RuntimeError(f'{Path(str(args[0])).name} failed ({result.returncode}); {log}')
    return result


def run(args):
    for executable in [args.dotnet, args.postgres_bin / 'initdb', args.postgres_bin / 'pg_ctl', args.postgres_bin / 'pg_dump', args.postgres_bin / 'pg_restore']:
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f'Missing executable: {executable}')
    # Verify app sources before creating a database; labels alone cannot bind a rebuild.
    source_proof = {}
    for label, source, sha in [('old', args.old_source.resolve(), OLD), ('new', args.new_source.resolve(), NEW)]:
        head = command(['git', '-C', source, 'rev-parse', 'HEAD']).stdout.strip()
        command(['git', '-C', source, 'diff', '--exit-code', sha, '--', 'server'])
        untracked = command(['git', '-C', source, 'ls-files', '--others', '--exclude-standard', '--', 'server']).stdout.strip()
        if untracked:
            raise ValueError('Untracked server sources cannot be used for a fixed rebuild')
        source_proof[label] = {'checkout_head': head, 'expected_source_sha': sha,
                              'server_tree': command(['git', '-C', source, 'rev-parse', sha + ':server']).stdout.strip(),
                              'working_server_sources_exact': True}
    root = args.work.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    pg = args.postgres_bin.resolve()
    data, socket, logs = root / 'data', root / 'socket', root / 'logs'
    socket.mkdir(mode=0o700); logs.mkdir()
    database = 'fc_compat_' + uuid.uuid4().hex[:12]
    result = {'source_old_sha': OLD, 'source_new_sha': NEW, 'controller_sha': CONTROLLER,
              'actual_old_image_id': ACTUAL_OLD_IMAGE,
              'old_image_evidence': 'source rebuild surrogate; actual online image unavailable',
              'online_server_used': False, 'simultaneous_versions': False,
              'database_restore_used': False, 'historical_fixture_data_deleted': False,
              'health_scope': 'Actual version RoomRecoveryWorker/RoomRegistry and RoomRecoveryHealthCheck in a loopback ASP.NET health fixture; not full Program readiness',
              'clock_scope': 'Fixed clock and dormant tick timer isolate recovery/routing; not elapsed gameplay/load evidence',
              'ddl_scope': 'App columns/constraints/indexes/functions/triggers; excludes only explicit compat_fail fault-injection function/trigger',
              'source_proof': source_proof,
              'cases': [], 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    for label, build in [('old', args.old_build), ('new', args.new_build)]:
        directory = build.resolve() / 'bin/CrossVersion/release'
        result[label + '_rebuilt_dlls'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.glob('FantasyCard.*.dll')}
    started = False
    output = root / 'report.json'
    port = 55438
    try:
        command([pg/'initdb', '-D', data, '--auth-local=trust', '--auth-host=reject', '--username=postgres', '--no-locale', '--encoding=UTF8'], log=logs/'initdb.log')
        command([pg/'pg_ctl', '-D', data, '-l', root/'postgres.log', '-o', f"-h '' -k {socket} -p {port}", '-w', 'start'], log=logs/'start.log')
        started = True
        command([pg/'createdb', '-h',socket,'-p',str(port),'-U','postgres',database])

        def sql(text):
            return command([pg/'psql','-h',socket,'-p',str(port),'-U','postgres','-d',database,'-v','ON_ERROR_STOP=1','-Atc',text]).stdout.strip()

        def case(name, phases, expectations):
            schema = 'fc_compat_' + uuid.uuid4().hex[:12]
            assert re.fullmatch(r'fc_compat_[a-f0-9]{12}', schema)
            sql(f'CREATE SCHEMA {schema}')
            fixture = root / (name + '-fixture.json')
            item = {'name': name, 'schema': schema, 'observations': [], 'unexpected_failures': [],
                    'unsafe_observed': False, 'fixture_data_retained': True}
            baseline_migrations = baseline_ddl = None
            dependency_failed = False
            for index, ((version, action), expected) in enumerate(zip(phases, expectations, strict=True)):
                env = dict(os.environ, FANTASYCARD_COMPAT_POSTGRES=f'Host={socket};Port={port};Username=postgres;Database={database};Search Path={schema};Pooling=false;Timeout=3;Command Timeout=10',
                           FANTASYCARD_COMPAT_VERSION=OLD if version == 'old' else NEW)
                build = args.old_build if version == 'old' else args.new_build
                log = logs/f'{name}-{index:02d}-{version}-{action}.log'
                entry = {'version': version, 'source_sha': OLD if version=='old' else NEW,
                         'action': action, 'log': str(log.relative_to(root))}
                if dependency_failed:
                    entry.update(not_executed=True, reason='Earlier fixture/probe failed; no valid state for dependent phase')
                    item['observations'].append(entry)
                    continue
                try:
                    completed = command([args.dotnet, build/'bin/CrossVersion/release/FantasyCard.Server.Tests.dll',action,fixture],env=env,log=log,timeout=115,check=False)
                    lines=[line for line in completed.stdout.splitlines() if line.startswith('{')]
                    proof=json.loads(lines[-1]) if lines else {}
                    entry.update(exit_code=completed.returncode,proof=proof)
                    if completed.returncode or not proof.get('probe_completed'):
                        dependency_failed = True
                        raise RuntimeError('Probe did not complete')
                    if baseline_migrations is None:
                        baseline_migrations=proof['migration_rows']; baseline_ddl=proof['app_ddl_hash']
                    entry['migrations_unchanged']=proof['migration_rows']==baseline_migrations
                    entry['app_ddl_unchanged']=proof['app_ddl_hash']==baseline_ddl
                    if not entry['migrations_unchanged'] or not entry['app_ddl_unchanged']:
                        raise RuntimeError('Migration checksum or application DDL changed across switch')
                    current=json.loads(fixture.read_text())
                    for key,value in expected.items():
                        if key=='unsafe':
                            item['unsafe_observed'] |= value
                            continue
                        if isinstance(value,str) and value.startswith('@'):
                            value=current[value[1:]]
                        if proof.get(key)!=value:
                            raise RuntimeError(f'{key}: expected {value!r}, observed {proof.get(key)!r}')
                    entry['expected_observation_verified']=True
                except Exception as error:
                    dependency_failed = True
                    entry['expected_observation_verified']=False; entry['error']=str(error)
                    item['unexpected_failures'].append({'phase':index,'error':str(error)})
                item['observations'].append(entry)
                output.write_text(json.dumps(result | {'in_progress_case':item},indent=2)+'\n')
            item['probe_expectations_passed']=not item['unexpected_failures']
            item['rollback_safety']='unsafe' if item['unsafe_observed'] else 'bounded observations only'
            result['cases'].append(item)
            output.write_text(json.dumps(result,indent=2)+'\n')

        case('checkpoint-old-new-old', [('old','seed-checkpoint'),('new','roundtrip'),('old','roundtrip')], [{},{'checkpoint_revision':21,'equipment_location':'InMatchEquipped','relic_equipment_location':'RelicPile','victim_state':'Settled'},{'checkpoint_revision':31,'equipment_location':'InMatchEquipped','relic_equipment_location':'RelicPile','victim_state':'Settled'}])
        for first,second in [('old','new'),('new','old')]:
            case('claim-loss-'+first+'-'+second,[ (first,'seed-launch'),(first,'claim-drop'),(second,'launch-retry'),(first,'recover'),(second,'drain') ],[{}, {'committed_response_dropped':True,'asset_reservation_count':1,'match_status':'Launching'}, {'asset_reservation_count':1,'match_status':'Running'}, {'ready_http_status':200,'primary_route_room':'@room','asset_reservation_count':1},{'drain_allowed':False}])
            case('mark-loss-'+first+'-'+second,[(first,'seed-launch'),(first,'mark-drop'),(second,'recover'),(first,'recover'),(first,'mark-replay')],[{}, {'committed_response_dropped':True,'match_status':'Running'}, {'ready_http_status':200,'primary_route_room':'@room','asset_reservation_count':1},{'ready_http_status':200,'primary_route_room':'@room','asset_reservation_count':1},{'committed_running_replay_accepted':first=='new','unsafe':first=='old'}])
            case('settlement-loss-'+first+'-'+second,[(first,'seed-settlement'),(first,'settlement-drop'),(second,'settlement-replay'),(first,'settlement-replay')],[{}, {'committed_response_dropped':True},{'receipt_count':1,'hold_count':1,'ledger_count':1,'holds_committed_this_attempt':1},{'receipt_count':1,'hold_count':1,'ledger_count':1,'holds_committed_this_attempt':0}])
        case('new-terminal-write-failure',[('old','seed-terminal'),('new','terminal-fail'),('old','recover'),('new','drain')],[{}, {'memory_phase':'Dead','snapshot_failure_observed':True,'durable_player_state':'Active','settlements':0,'durable_snapshot_phase':'ActionBar'}, {'durable_player_state':'Active','ready_http_status':200}, {'drain_allowed':False}])
        case('old-terminal-write-failure',[('old','seed-terminal'),('old','terminal-fail'),('new','recover'),('old','recover')],[{}, {'memory_phase':'Dead','snapshot_failure_observed':True,'durable_player_state':'Settled','settlements':1,'durable_snapshot_phase':'ActionBar','unsafe':True}, {'ready_http_status':503,'primary_route_room':None}, {'ready_http_status':200,'primary_recovered_phase':'ActionBar','durable_player_state':'Settled','unsafe':True}])
        case('stale-settled-player',[('old','seed-stale'),('new','recover'),('old','recover'),('new','drain')],[{}, {'ready_http_status':503,'primary_route_room':None}, {'ready_http_status':200,'primary_recovered_phase':'ActionBar','durable_player_state':'Settled','unsafe':True}, {'drain_allowed':False}])
        case('stale-old-room-steals-next-route',[('old','seed-stale-next'),('new','recover'),('old','recover')],[{}, {'ready_http_status':503,'primary_route_room':'@next_room'}, {'ready_http_status':503,'primary_route_room':'@room','primary_recovered_phase':'ActionBar','unsafe':True}])
        case('drain-launching',[('old','seed-launch'),('old','claim-drop'),('new','drain')],[{}, {'match_status':'Launching'}, {'drain_allowed':False,'active_match_count':1}])
        case('drain-pending-hold',[('old','seed-pending'),('new','drain'),('old','drain')],[{}, {'drain_allowed':False,'active_match_count':0,'pending_hold_count':1,'contradictory_snapshot_count':0},{'drain_allowed':False,'active_match_count':0,'pending_hold_count':1,'contradictory_snapshot_count':0}])
        case('drain-completed-contradiction',[('old','seed-drain-stale'),('new','drain'),('old','drain')],[{}, {'drain_allowed':False,'active_match_count':0,'pending_hold_count':0,'contradictory_snapshot_count':1},{'drain_allowed':False,'contradictory_snapshot_count':1}])
        for name,action in [('settled-missing-snapshot','seed-drain-missing'),('receipt-player-state-mismatch','seed-drain-receipt-state'),('receipt-pointer-mismatch','seed-drain-receipt-pointer')]:
            case('drain-'+name,[('old',action),('new','drain'),('old','drain')],[{}, {'drain_allowed':False,'active_match_count':0,'pending_hold_count':0,'contradictory_snapshot_count':1,'legacy_drain_allowed':True},{'drain_allowed':False,'contradictory_snapshot_count':1,'legacy_drain_allowed':True}])
        for name,action,field in [('orphan-receipt','seed-drain-orphan-receipt','settlement_association_error_count'),('orphan-snapshot-member','seed-drain-orphan-member','orphan_snapshot_member_count'),('wrong-hold-owner','seed-drain-wrong-hold-owner','wrong_hold_owner_count')]:
            case('drain-'+name,[('old',action),('new','drain'),('old','drain')],[{}, {'drain_allowed':False,'active_match_count':0,'pending_hold_count':0,'contradictory_snapshot_count':1,'legacy_drain_allowed':True,field:1},{'drain_allowed':False,'contradictory_snapshot_count':1,'legacy_drain_allowed':True,field:1}])
        case('drain-consistent-terminal-control',[('old','seed-drain-consistent'),('new','drain'),('old','drain')],[{}, {'drain_allowed':True,'active_match_count':0,'pending_hold_count':0,'contradictory_snapshot_count':0},{'drain_allowed':True,'contradictory_snapshot_count':0}])
        case('drain-empty-control',[('old','migrate'),('new','drain'),('old','drain')],[{}, {'drain_allowed':True,'active_match_count':0,'pending_hold_count':0,'contradictory_snapshot_count':0},{'drain_allowed':True}])
        result['all_probe_expectations_passed']=all(c['probe_expectations_passed'] for c in result['cases'])
        result['unconditional_application_rollback_safe']=False
        result['drain_guard_completeness_proven']=False
        result['proposed_path']='Review a drained window only; never override existing Rooms guards automatically'
        dump=root/'fixture-private.dump'
        descriptor=os.open(dump,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
        command([pg/'pg_dump','-h',socket,'-p',str(port),'-U','postgres','-d',database,'-Fc','-f',dump],log=logs/'dump.log')
        command([pg/'pg_restore','--list',dump],log=logs/'dump-list-private.log')
        result['private_fixture_dump']={'file':dump.name,'mode':oct(dump.stat().st_mode&0o777),'bytes':dump.stat().st_size,'sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'list_verified':True,'uploaded':False}
    finally:
        result['completed_at']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        if started:
            stopped=command([pg/'pg_ctl','-D',data,'-m','fast','-w','stop'],log=logs/'stop.log',check=False)
            result['private_pg_stopped']=stopped.returncode==0
        output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'report':str(output),'cases':len(result['cases']),
                      'expectations_passed':result.get('all_probe_expectations_passed'),
                      'unsafe_cases':[c['name'] for c in result['cases'] if c['unsafe_observed']],
                      'online_server_used':False,'private_pg_stopped':result.get('private_pg_stopped')},indent=2))
    return 0 if result.get('all_probe_expectations_passed') and result.get('private_pg_stopped') else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--dotnet',type=Path,required=True)
    parser.add_argument('--postgres-bin',type=Path,required=True)
    parser.add_argument('--old-build',type=Path,required=True)
    parser.add_argument('--new-build',type=Path,required=True)
    parser.add_argument('--old-source',type=Path,required=True)
    parser.add_argument('--new-source',type=Path,required=True)
    raise SystemExit(run(parser.parse_args()))
