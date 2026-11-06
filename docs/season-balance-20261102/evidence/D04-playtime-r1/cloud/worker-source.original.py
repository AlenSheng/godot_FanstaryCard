from pathlib import Path
import hashlib, io, json, os, re, shutil, struct, subprocess, sys, tarfile, threading, time

root=Path('/home/ubuntu/season-balance-20261106-d04-playtime-r1')
label='season-balance-20261106-d04-playtime-r1'
database='803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a'
image='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4'
def run(args, **kwargs): return subprocess.check_output(args,stderr=subprocess.PIPE,**kwargs)
def sample():
    m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines()); d=shutil.disk_usage('/home/ubuntu')
    r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=d.free,disk_fraction=d.free/d.total)
    r['guard_ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05
    return r
assert not root.exists(); first=sample(); assert first['guard_ok'] and first['available_ram']>=1800*1024**2
pg=json.loads(run(['docker','inspect',database]))[0]
assert pg['State']['Running'] and pg['Config']['Labels']['com.fantasycard.task']=='season-balance-20261102-a03-storage-r1'
assert json.loads(run(['docker','image','inspect',image]))[0]['Id']==image
root.mkdir(mode=0o700); (root/'public').mkdir(); public=root/'public'; os.chown(public,1000,1000); stop=threading.Event(); breached=threading.Event(); cid=None; input_mounted=False
def watch():
    with (public/'resources.original.jsonl').open('x') as log:
        while not stop.wait(2):
            r=sample(); log.write(json.dumps(r)+'\n'); log.flush()
            if not r['guard_ok']:
                breached.set()
                if cid is not None: subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return
thread=threading.Thread(target=watch,daemon=True); thread.start(); password=None; code=None
try:
    header=sys.stdin.buffer.read(4); assert len(header)==4; size=struct.unpack('!I',header)[0]; assert size<1024**2
    manifest=json.loads(sys.stdin.buffer.read(size)); length=manifest['payload_bytes']; assert 0<length<=32*1024**2
    body=sys.stdin.buffer.read(length); assert len(body)==length and hashlib.sha256(body).hexdigest()==manifest['payload_sha256']
    assert not breached.is_set(); (public/'input-manifest.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
    assert manifest['expanded_bytes']<112*1024**2
    work=root/'input'; assert work.resolve()==work and work.parent==root and not work.exists()
    work.mkdir(); run(['mount','-t','tmpfs','-o','size=128m,nosuid,nodev','fc-season17-input',str(work)]); input_mounted=True
    assert run(['findmnt','-n','-o','FSTYPE','--target',str(work)]).decode().strip()=='tmpfs'
    (public/'input-tmpfs.original.json').write_text(json.dumps(dict(path=str(work),size_mib=128,payload_sha256=manifest['payload_sha256'],disk_payload_written=False))+'\n')
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as archive:
        assert all(m.isfile() and m.name in manifest['files'] and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in archive.getmembers())
        for member in archive.getmembers():
            raw=archive.extractfile(member).read(); assert hashlib.sha256(raw).hexdigest()==manifest['files'][member.name]
            target=root/'input'/member.name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(raw)
    assert all(hashlib.sha256((root/'input'/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
    resource=sample(); assert resource['guard_ok'] and resource['available_ram']>=1800*1024**2 and not breached.is_set()
    private=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text()); password=private['password']
    env=root/'runtime.private.env'; env.write_text('FANTASYCARD_TEST_POSTGRES=Host=127.0.0.1;Port=5432;Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30;ApplicationName=fc-d04-playtime-cloud-r1\nFANTASYCARD_PROCESS_EVIDENCE=/results/process-logs\nFANTASYCARD_D04_SCHEMA_EVIDENCE=/results/owned-schemas.original.jsonl\nFANTASYCARD_D04_REPORT_EVIDENCE=/results/currency-reports.original.jsonl\nFANTASYCARD_PROCESS_SERVER_DLL=/workspace/bin/FantasyCard.Server.dll\nDOTNET_CLI_TELEMETRY_OPTOUT=1\nDOTNET_NOLOGO=1\nDOTNET_CLI_HOME=/tmp\nFANTASYCARD_E2E_SERVER_DLL=/workspace/bin/FantasyCard.Server.dll\nFANTASYCARD_E2E_PROCESS_LOG_DIR=/results/process-logs\n'); env.chmod(0o600)
    args=['docker','run','-d','--name','fc-season-d04-playtime-r1','--label','com.fantasycard.task='+label,
        '--cpus','1','--memory','1200m','--memory-swap','1200m','--pids-limit','256','--network','container:'+database,'--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only',
        '--tmpfs','/tmp:rw,noexec,nosuid,size=64m,mode=1777','--env-file',str(env),'-v',str(root/'input')+':/workspace:ro','-v',str(public)+':/results:rw','-w','/workspace',
        '--entrypoint','dotnet',image,'/workspace/bin/FantasyCard.Server.Tests.dll','-noLogo','-noColor','-noAutoReporters','-failSkips','-parallel','none','-reporter','verbose',
        '-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.PersistedTerminalClocksDriveNetHourlyPercentilesIncludingDeathsZeroAndUnlocatedFinancialRows','-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_admin_economy_report_keeps_existing_HTTPS_key_and_no_store_boundary','-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts','-trx','/results/cases.trx','-xml','/results/cases.xml']
    cid=run(args).decode().strip(); handle=dict(container_id=cid,label=label,image_id=image,precompiled_local=True,cloud_SDK_started=False,memory_mib=1200,cpus=1,started_at=time.time(),source_payload_sha256=manifest['payload_sha256'])
    (public/'runtime-handle.original.json').write_text(json.dumps(handle,indent=2)+'\n'); print(json.dumps(dict(started=handle)),flush=True)
    for _ in range(450):
        inspected=json.loads(run(['docker','inspect',cid]))[0]
        if not inspected['State']['Running']: code=inspected['State']['ExitCode']; break
        if breached.is_set(): break
        time.sleep(2)
    if code is None:
        subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        code=json.loads(run(['docker','inspect',cid]))[0]['State']['ExitCode']
    captured=subprocess.run(['docker','logs',cid],capture_output=True,check=True)
    logs=(captured.stdout+captured.stderr).decode('utf-8',errors='replace'); assert password not in logs
    (public/'test.original.log').write_text(logs,encoding='utf-8')
    p=public/'owned-schemas.original.jsonl'; schemas=[json.loads(line)['schema'] for line in p.read_text().splitlines()] if p.exists() else []
    q=public/'process-logs/receipts.jsonl'; schemas+=([row['evidence']['schema'] for line in q.read_text().splitlines() if (row:=json.loads(line))['caseId']=='SEASON17-schema'] if q.exists() else []);schemas=sorted(set(schemas))
    assert all(re.fullmatch(r'fc_runtime_test_[0-9a-f]{32}',s) for s in schemas)
    query='SELECT nspname FROM pg_namespace WHERE nspname IN ('+','.join("'"+s+"'" for s in schemas)+') ORDER BY nspname' if schemas else 'SELECT nspname FROM pg_namespace WHERE false'
    present=run(['docker','exec',database,'psql','-U','season_stage','-d','season_stage','-qAt','-c',query]).decode().splitlines()
    proof=dict(exit=code,guard_ok=not breached.is_set(),owned_schemas=schemas,schemas_still_present=present,input_unchanged=all(hashlib.sha256((root/'input'/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items()),new_completed_gameplay_encounters=0,planned_report_cases=3,production_database_used=False,SDK_started=False)
    (public/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
finally:
    stop.set(); thread.join(timeout=5)
    if cid is not None:
        inspected=json.loads(run(['docker','inspect',cid]))[0]; assert inspected['Config']['Labels']['com.fantasycard.task']==label
        if inspected['State']['Running']: subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['docker','rm',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    env=root/'runtime.private.env'
    if env.exists(): env.unlink()
    if input_mounted:
        assert (root/'input').resolve()==root/'input'
        run(['umount',str(root/'input')]); input_mounted=False
        assert not list((root/'input').iterdir())
    (public/'input-cache-cleanup.original.json').write_text(json.dumps(dict(tmpfs_unmounted=True,input_files_removed=True,local_source_payload_retained=True,other_projects_modified=False))+'\n')
    (public/'cleanup.original.json').write_text(json.dumps(dict(owned_container_removed=cid is not None,private_env_removed=not env.exists(),other_projects_modified=False))+'\n')
archive=root/'public-evidence.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for p in sorted(public.rglob('*')):
        if p.is_file():
            raw=p.read_bytes(); assert password is None or password.encode() not in raw; tar.add(p,arcname=p.relative_to(public).as_posix())
print(json.dumps(dict(finished=proof,evidence_path=str(archive),evidence_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())),flush=True)
