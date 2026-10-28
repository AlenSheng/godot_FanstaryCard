"""One sealed, guarded Windows producer for the registered three-host100 study.

This runs real native clients. It cannot declare joint capacity acceptance.
It never accepts remote commands, arbitrary executables or another study's PIDs.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def save(path, value):
    raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as out: out.write(raw)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--host-id',choices=('windows','sjh'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dependency-path',type=Path)
    args=parser.parse_args(argv)
    if args.dependency_path: sys.path.insert(0,str(args.dependency_path.resolve(strict=True)))
    import psutil
    from pr13_native_capture import observe_processes,observe_software
    from pr13_distributed_capacity import (canonical,load_git_reference,OFFICIAL_ENGINE,
        ENGINE_VERSION,THREE_HOST100_INITIAL_MEMORY,_client_inputs_match)
    from pr13_distributed_load import THREE_HOST100_PROFILE,THREE_HOST100_PARTITIONS

    assert os.name=='nt'
    spec=json.loads(args.spec.read_text(encoding='utf-8'))
    assert spec['workload_profile']==THREE_HOST100_PROFILE and spec['target_clients']==100
    part=next(p for p in spec['partitions'] if p['host_id']==args.host_id)
    count=THREE_HOST100_PARTITIONS[args.host_id][0]
    assert part['platform']=='windows' and part['clients']==count
    assert os.environ['COMPUTERNAME']==part['machine_name']
    assert (args.host_id=='sjh')==(part['machine_name']=='SJH')
    floor=6442450944;assert part['memory_floor_bytes']==floor
    P=Path(part['project_path']).resolve(strict=True).parent
    assert Path(__file__).resolve().is_relative_to(P/'tools')
    reference=load_git_reference(P,spec['source_head'],workload_profile=spec['workload_profile'])
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=P,text=True).strip()==reference['head']
    controller_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    assert reference['controllers']['tools/pr13_three_host_windows.py']==controller_sha
    J=args.output.resolve();J.mkdir(parents=True,exist_ok=False)
    save(J/'supervisor-started.original.json',dict(PID=os.getpid(),create_time=psutil.Process().create_time(),
        host_id=args.host_id,machine_name=part['machine_name'],spec_sha256=hashlib.sha256(canonical(spec)).hexdigest(),
        controller_sha256=controller_sha,at_ns=time.time_ns()))
    ctypes.WinDLL('kernel32').SetPriorityClass(ctypes.c_void_p(-1),0x4000)
    affinity=part['cpu_affinity'];psutil.Process().cpu_affinity(affinity)
    before=observe_software(P,Path(part['engine_path']),list(reference['controls']))
    save(J/'software-before.original.json',before)
    assert before['source_head']==reference['head'] and before['source_controls']==reference['controls']
    assert before['engine_sha256']==OFFICIAL_ENGINE['windows'] and before['engine_version']==ENGINE_VERSION
    _client_inputs_match(before['client_inputs'],reference['client'])
    resources=[];guard=None;inspection=False;forced=[]
    def resource():
        row=dict(at_unix_ms=time.time_ns()/1e6,monotonic_ms=time.monotonic_ns()/1e6,
            memory_available_bytes=psutil.virtual_memory().available)
        resources.append(row);return row
    assert resource()['memory_available_bytes']>=THREE_HOST100_INITIAL_MEMORY[args.host_id]
    driver=[sys.executable,'-B',str(P/'tools/gameplay_load_test.py'),'--godot',part['engine_path'],
        '--server-url',part['server_url'],'--prometheus',part['prometheus_url'],'--client-project',str(P/'client'),
        '--run','--max-groups','1','--group-size',str(count),'--group-interval','1','--max-seconds','960',
        '--load-profile','active-hold','--hold-seconds','720','--target-online',str(count),'--target-active',str(count),
        '--authority-transition-policy','capacity-budgeted-authority-recovery-v2',
        '--minimum-continuous-seconds','120','--minimum-coverage','0.95','--maximum-sample-gap','20',
        '--minimum-command-rate','1','--hero-class','Guardian','--strategy','baseline_all_hand',
        '--strategy-seed',str(part['seed_start']),'--cycle-limit-seconds','240','--http-p95-limit-ms','5000',
        '--command-p95-limit-ms','8000','--health-limit-ms','10000','--monitor-timeout-seconds','10',
        '--minimum-generator-memory-bytes',str(floor),'--minimum-cloud-memory-bytes','500000000',
        '--minimum-cloud-disk-percent','5','--client-memory-start-budget-mib','256',
        '--launch-interval-seconds','1','--stop-file',str(J/'STOP'),'--output',str(J/'coordinator')]
    env=dict(os.environ,FANTASYCARD_SERVER_URL=part['server_url'],APPDATA=str(J/'userdata'),LOCALAPPDATA=str(J/'localdata'))
    if args.dependency_path: env['PYTHONPATH']=str(args.dependency_path.resolve())
    launch_manifest={}
    def owned_native(launch):
        child=psutil.Process(launch['pid']);owned=child.environ();cmd=child.cmdline()
        assert '--headless' in cmd and str(P/'client') in cmd
        assert owned.get('FANTASYCARD_LOAD_RUN_ID')==launch['run_id']
        assert owned.get('FANTASYCARD_LOAD_PROCESS_EPOCH')==launch['process_epoch']
        assert child.exe().lower()==str(Path(part['engine_path']).resolve()).lower()
        return child
    with (J/'stdout.original.log').open('xb') as out,(J/'stderr.original.log').open('xb') as err:
        process=subprocess.Popen(driver,cwd=P,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        save(J/'coordinator-started.original.json',dict(PID=process.pid,argv=driver,create_time=psutil.Process(process.pid).create_time()))
        started=time.monotonic()
        while process.poll() is None:
            if resource()['memory_available_bytes']<floor: guard='Windows_memory_below6GiB'
            if time.monotonic()-started>1140: guard='Windows_owned_stage_deadline'
            if (J.parent/'STOP-STUDY').exists(): guard='peer_or_parent_stop'
            manifests=list((J/'coordinator').glob('*/launch-manifest.json'))
            if len(manifests)==1:
                try: launch_manifest=json.loads(manifests[0].read_text(encoding='utf-8'))
                except (OSError,ValueError): pass
                if len(launch_manifest.get('launches',[]))==count and not inspection:
                    try:
                        for launch in launch_manifest['launches']:
                            child=owned_native(launch);child.cpu_affinity(affinity);child.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                        save(J/'processes.original.json',observe_processes(launch_manifest,count));inspection=True
                    except (psutil.Error,ValueError,AssertionError): guard='Windows_native_process_inspection_failed'
            if guard:
                save(J/'STOP',dict(reason=guard,at_ns=time.time_ns()))
                deadline=time.monotonic()+60
                while time.monotonic()<deadline and process.poll() is None: resource();time.sleep(.5)
                if process.poll() is None:
                    for launch in launch_manifest.get('launches',[]):
                        try:
                            child=owned_native(launch);child.terminate();forced.append(child.pid)
                        except psutil.NoSuchProcess: pass
                    save(J/'forced-own-native-processes.original.json',dict(PIDs=forced))
                    process.terminate()
                break
            time.sleep(.5)
        rc=process.wait(timeout=20)
    resource();save(J/'resources.original.json',resources)
    after=observe_software(P,Path(part['engine_path']),list(reference['controls']));save(J/'software-after.original.json',after)
    # observe_software includes observation timestamps; compare only source/engine inputs.
    source_unchanged=all(before.get(k)==after.get(k) for k in
        ('source_head','source_controls','engine_sha256','engine_version','client_inputs'))
    source_unchanged=source_unchanged and hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==controller_sha
    terminal=dict(ok=rc==0 and guard is None and inspection and source_unchanged and not forced,
        exit=rc,guard_stop=guard,native_process_inspection=inspection,source_unchanged=source_unchanged,
        controller_sha256=controller_sha,machine_name=part['machine_name'],at_ns=time.time_ns())
    save(J/'terminal.original.json',terminal);print(json.dumps(terminal),flush=True)
    return 0 if terminal['ok'] else 3


if __name__=='__main__': raise SystemExit(main())
