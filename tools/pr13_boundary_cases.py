"""Explicit OFFLINE/AUDIT cases for clocks, FPS profiles and public evidence."""
import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'client/tests'))
from fixture_runtime import isolated_environment
from tools.tests.test_gameplay_load_sampling_contract import CoordinatorSamplingContractTests
from tools.gameplay_load_validation import aggregate_window,provenance
from tools.pr13_audit_replay import replay
from tools.pr13_public_evidence import inspect_public,validated_files,derived_identity
from tools.pr13_ci_evidence import classify_runs


def write(path,value): path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def native_fps(output,godot):
    results=[]
    for cap in (None,30):
        directory=output/('native-default' if cap is None else 'native-fps-30'); directory.mkdir()
        report=directory/'result.json'
        env=isolated_environment(directory,FANTASYCARD_SERVER_URL='http://127.0.0.1:1',FANTASYCARD_LOAD_RUN_ID='fps-profile-probe',PR13_FPS_REPORT=str(report))
        command=[godot,'--headless','--audio-driver','Dummy','--path',str(ROOT/'client')]
        if cap is not None: command+=['--max-fps',str(cap)]
        command+=['--script','res://tests/pr13_fps_probe.gd']
        with (directory/'engine.log').open('wb') as log:
            child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
            try: code=child.wait(timeout=15)
            finally:
                if child.poll() is None: child.kill();child.wait(timeout=5)
        if code: raise AssertionError('Native FPS probe failed')
        data=json.loads(report.read_text(encoding='utf8'))
        if data['pid']!=child.pid or any(t<0 for t in data['intervals_usec']): raise AssertionError('Invalid native clock observation')
        if cap is not None and data['configured_max_fps']!=cap: raise AssertionError('Engine did not receive FPS override')
        results.append({'actual':data,'command':command,'exit_code':code,'kind':'actual engine; no gameplay/capacity claim'})
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--godot',required=True)
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    private=output/'controlled-fixtures';private.mkdir()
    plan_path=ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json';plan=json.loads(plan_path.read_text(encoding='utf8'))
    contracts={c['id']:c for p in plan['packages'] for s in p['subtasks'] for c in s['test_cases']}
    sampler=CoordinatorSamplingContractTests();cache={};native=native_fps(output,args.godot)

    def clock():
        code,report=sampler.run_fixture(wall_jump=True,max_groups=2)
        groups=report['group_launches']
        interval=groups[1]['started_monotonic_ms']-groups[0]['started_monotonic_ms']
        rates=[s['command_rate'] for s in report['samples'][1:]]
        cutoffs=report['request_distributions']; final=cutoffs['final']
        # An unqualified coordinator clock invalidates partition/rate claims;
        # caller-owned final counts remain available for audit.
        clock_rejected=(not report['cutoff_clock_quality']['qualified'] and
                        'cutoff_clock_unqualified' in cutoffs['evidence_errors'] and
                        cutoffs['running'] is None and cutoffs['drain'] is None and
                        final is not None and final['logical_request_count']>0 and
                        final['observed_window_seconds'] is None and
                        final['logical_requests_per_second'] is None and
                        final['completed_requests_per_second'] is None and
                        final['throughput_missing_reason']=='coordinator_cutoff_clock_unqualified' and
                        not report['acceptance_passed'])
        return {'exit_code':code,'group_interval_ms':interval,'command_rates':rates,'report':report,'native_clock':native}, code==3 and interval==120000 and all(r in (2,4) for r in rates) and clock_rejected

    def memory():
        code,report=sampler.run_fixture(generator_observation={'available':True,'host_memory_available_bytes':1024**3})
        return {'exit_code':code,'report':report,'observation':'controlled generator metric; not observed host capacity'},code==3 and 'generator_memory_low' in report['all_triggers'] and not report['acceptance_passed']

    def fps():
        _,baseline=sampler.run_fixture();code,candidate=sampler.run_fixture(client_max_fps=30)
        data={'baseline':baseline['load_contract'],'candidate':candidate['load_contract'],'candidate_launch':candidate['launch_receipts'],'native':native,'same_capacity_profile':False}
        return data,code==0 and baseline['load_contract']!=candidate['load_contract'] and native[1]['actual']['configured_max_fps']==30

    def missing_tls():
        result=aggregate_window([{'operations':[],'telemetry':[{'type':'http_attempt','duration_ms':10,'status':200}]}])
        tls=result['transport_phase_timings']['tls_handshake_ms']
        return result,tls['p95_ms'] is None and tls['quality']=='unavailable' and bool(tls['missing_reason'])

    def sensitive():
        rejected=[]
        for n,data in enumerate(({'access_token':'private-fixture-value'},{'request':{'ticket_body':{'status':'Ready'}}},{'authorization':'Bearer private-fixture-value'})):
            path=private/('sensitive-'+str(n)+'.json');write(path,data)
            try: inspect_public(path)
            except ValueError as error: rejected.append(str(error))
        return {'rejected_count':len(rejected),'reasons':rejected,'values_echoed':False},len(rejected)==3 and all('private-fixture-value' not in reason for reason in rejected)

    def overwritten():
        path=private/'overwritten.json';write(path,{'version':1})
        entry={'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path)};validated_files(private,[entry]);write(path,{'version':2})
        try: validated_files(private,[entry])
        except ValueError as error: return {'before_sha256':entry['sha256'],'after_sha256':sha(path),'rejected':str(error)},entry['sha256']!=sha(path)
        return {'rejected':False},False

    def lineage():
        parent=private/'raw.jsonl';derived=private/'derived.json';parent.write_bytes(b'{"event_seq":1}\n');write(derived,{'count':1})
        data=derived_identity(parent,derived)
        return data,data['parent']['sha256']!=data['derived']['sha256'] and data['original_overwritten'] is False

    def missing_raw():
        result=replay(private,{'files':[{'path':'deleted-history.jsonl','bytes':1,'sha256':'a'*64}]},stop_ms=100,final_ms=200)
        return result,result['status']=='Blocked' and result['raw_read'] is False and result['derived'] is None

    def trigger():
        source=(ROOT/'.github/workflows/gameplay-load.yml').read_text(encoding='utf8')
        events={};section=None
        for line in source.splitlines():
            if line in ('  pull_request:','  push:'): section=line.strip(': ');events[section]=[]
            elif line=='  workflow_dispatch:': section=None
            elif section and line.startswith("      - '"): events[section].append(line.split("'")[1])
        filename='client/tests/pr13_fps_probe.gd'
        matched={event:[p for p in patterns if fnmatch.fnmatchcase(filename,p)] for event,patterns in events.items()}
        return {'actual_new_file':filename,'configured_event_paths':matched,'workflow_sha256':sha(ROOT/'.github/workflows/gameplay-load.yml'),'remote_ci_pass_claim':False}, all(matched.get(k) for k in ('push','pull_request'))

    def stale_ci():
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        old=subprocess.check_output(['git','rev-parse','HEAD~1'],cwd=ROOT,text=True).strip()
        data=classify_runs(head,[{'head_sha':old,'status':'completed','conclusion':'success'}])
        return {'controlled_old_success':True,'head':head,'old_sha':old,'classification':data}, not data['all_returned_workflows_passed'] and data['historical_workflow_count']==1

    actions={
        'LOAD-06.4-T01':('wall-jump',clock),'LOAD-06.4-T02':('missing-tls-hook',missing_tls),
        'LOAD-06.4-T03':('sensitive-public-rejection',sensitive),'LOAD-07.1-T03':('wall-jump',clock),
        'LOAD-07.2-T01':('generator-memory-stop',memory),'LOAD-07.2-T03':('actual-fps-profile',fps),
        'LOAD-11.1-T02':('missing-original-raw',missing_raw),'LOAD-11.2-T01':('overwritten-manifest',overwritten),
        'LOAD-11.2-T02':('sensitive-public-rejection',sensitive),'LOAD-11.2-T03':('parent-derived-lineage',lineage),
        'LOAD-11.3-T01':('configured-new-file-ci-paths',trigger),'LOAD-11.3-T03':('stale-ci-source',stale_ci)}
    records=[]
    for case_id,(name,action) in actions.items():
        if name not in cache:
            actual,passed=action();cache[name]=(actual,passed);write(output/(name+'.json'),{'actual':actual,'passed':passed})
        actual,passed=cache[name];contract=contracts[case_id]
        records.append({'case_id':case_id,'executed':True,'status':'Passed' if passed else 'Failed','setup':contract['setup_and_injection'],'expected':contract['expected'],'actual':actual,'artifact':name+'.json','profiles_executed':['OFFLINE']})
    (output/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
    paths=('tools/pr13_boundary_cases.py','tools/pr13_public_evidence.py','tools/pr13_ci_evidence.py','tools/pr13_evidence_bundle.py','tools/gameplay_load_test.py','tools/gameplay_load_validation.py','tools/tests/test_gameplay_load_sampling_contract.py','client/tests/pr13_fps_probe.gd','.github/workflows/gameplay-load.yml')
    source=provenance(ROOT,paths)
    report={'source_sha':source['git_commit'],'source':source,'plan_sha256':sha(plan_path),'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'kind':'explicit_offline_audit_boundary_cases','runtime_accepted':False,'scope':'Real coordinator with controlled clock/metrics; real native FPS probes; public-file validation. No service capacity or historical recovery claim.'}
    write(output/'report.json',report)
    files=[p for p in output.rglob('*') if p.is_file() and 'controlled-fixtures' not in p.relative_to(output).parts and 'runtime' not in p.relative_to(output).parts]
    write(output/'manifest.json',{'files':[{'path':p.relative_to(output).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)]})
    print(json.dumps({'executed':report['executed'],'passed':report['passed'],'source_sha':report['source_sha']}))
    return 0 if report['executed']==report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
