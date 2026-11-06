from pathlib import Path
import subprocess,json,hashlib,tarfile,io,struct,shutil,threading,time,secrets,os,sys,re
root=Path('/home/ubuntu/season-balance-20261106-f03-migration-rehearsal-r1')
upload=Path(str(root)+'-upload')
label='season-balance-20261106-f03-migration-rehearsal-r1'
production='e140d6f8ab9f'
pg_image='sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2'
runtime_image='sha256:b34b01ff381aa920264e3920d7a7a49e6c1056091999dfc6268107d07029b9f4'
def run(args,**kwargs):return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=30,**kwargs)
def sample():
    m=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());d=shutil.disk_usage('/home/ubuntu')
    r={'available_ram':int(m['MemAvailable'].split()[0])*1024,'free_disk':d.free,'disk_fraction':d.free/d.total}
    r['guard_ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05
    return r
assert not root.exists();admission=sample();assert admission['guard_ok'] and admission['available_ram']>=2048*1024**2
prod=json.loads(run(['docker','inspect',production]))[0];assert prod['State']['Running'] and prod['Config']['Labels']['com.docker.compose.project']=='fantasycard-cloud' and prod['Config']['Labels']['com.docker.compose.service']=='postgres'
assert run(['docker','exec',production,'id','-u','postgres'])==b'70\n'
for identity in [pg_image,runtime_image]:assert json.loads(run(['docker','image','inspect',identity]))[0]['Id']==identity
root.mkdir(mode=0o700);public=root/'public';public.mkdir();os.chown(public,1000,1000)
private=root/'private';private.mkdir();run(['mount','-t','tmpfs','-o','size=16m,nosuid,nodev,mode=0700','fc-f03-private',str(private)])
work=root/'input';work.mkdir();run(['mount','-t','tmpfs','-o','size=128m,nosuid,nodev','fc-f03-input',str(work)])
containers=[];stop=threading.Event();breach=threading.Event();job='fc-f03-rehearsal-'+secrets.token_hex(12);password=secrets.token_hex(24);dump_process=None
def owned_remove(cid):
    d=json.loads(run(['docker','inspect',cid]))[0]
    assert cid!=production and d['Config']['Labels']['com.fantasycard.task']==label
    if d['State']['Running']:subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['docker','rm',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
def watch():
    with (public/'resources.original.jsonl').open('x') as f:
        while not stop.wait(1):
            r=sample();f.write(json.dumps(r)+'\n');f.flush()
            if not r['guard_ok']:
                breach.set()
                for cid in list(containers):
                    d=json.loads(run(['docker','inspect',cid]))[0]
                    assert cid!=production and d['Config']['Labels']['com.fantasycard.task']==label
                    if d['State']['Running']:subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                sql="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='"+job+"' AND usename='fantasycard' AND datname='fantasycard' AND pid<>pg_backend_pid()"
                subprocess.run(['docker','exec',production,'psql','-U','fantasycard','-d','fantasycard','-X','-qAt','-c',sql],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return
thread=threading.Thread(target=watch,daemon=True);thread.start();code=90;manifest=None;backup=None
try:
    header=sys.stdin.buffer.read(4);assert len(header)==4;size=struct.unpack('!I',header)[0];assert size<1024**2
    manifest=json.loads(sys.stdin.buffer.read(size));body=sys.stdin.buffer.read(manifest['payload_bytes']);assert hashlib.sha256(body).hexdigest()==manifest['payload_sha256']
    assert manifest['expanded_bytes']<112*1024**2
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as bundle:
        for item in bundle.getmembers():
            assert item.isfile() and item.name in manifest['files'] and '..' not in Path(item.name).parts and not Path(item.name).is_absolute()
            data=bundle.extractfile(item).read();assert hashlib.sha256(data).hexdigest()==manifest['files'][item.name];p=work/item.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    cache=Path('/home/ubuntu/season-balance-20261102-dependency-cache-v1');assert manifest['cache_root']==str(cache) and cache.resolve()==cache and not cache.is_symlink()
    assert json.loads((cache/'ownership.original.json').read_text())=={'task':'season-balance-20261102','schema':1,'cap_bytes':64*1024**2}
    copied=0
    for name,digest in manifest['cached_files'].items():
        assert name.startswith('bin/') and name.endswith('.dll') and not Path(name).name.startswith(('FantasyCard.','F03')) and manifest['files'][name]==digest
        p=cache/digest;assert re.fullmatch('[0-9a-f]{64}',digest) and p.is_file() and not p.is_symlink() and p.stat().st_mode&0o222==0
        data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==digest;target=work/name;assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);copied+=len(data)
    assert all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items())
    (public/'dependency-cache-reuse.original.json').write_text(json.dumps({'files':len(manifest['cached_files']),'bytes':copied,'all_reused_hashes_verified':True,'task_assemblies_reused_from_cache':False,'private_data_cached':False})+'\n')
    env=private/'pg.env';env.write_text('POSTGRES_USER=f03_owner\nPOSTGRES_DB=fc_f03_rehearsal_r1\nPOSTGRES_PASSWORD='+password+'\n');env.chmod(0o600)
    pg=run(['docker','run','-d','--name','fc-f03-migration-pg-r1','--label','com.fantasycard.task='+label,'--network','none','--cpus','1','--memory','1024m','--memory-swap','1024m','--pids-limit','128','--user','70:70','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--tmpfs','/var/lib/postgresql:rw,noexec,nosuid,size=512m,uid=70,gid=70,mode=0700','--tmpfs','/var/run/postgresql:rw,noexec,nosuid,size=8m,uid=70,gid=70,mode=0775','--tmpfs','/tmp:rw,noexec,nosuid,size=16m,mode=1777','--env-file',str(env),pg_image,'postgres','-c','listen_addresses=127.0.0.1','-c','shared_buffers=16MB','-c','max_connections=12','-c','max_wal_size=64MB','-c','fsync=off','-c','synchronous_commit=off']).decode().strip();containers.append(pg);assert pg!=production
    for _ in range(60):
        ready=subprocess.run(['docker','exec',pg,'pg_isready','-U','f03_owner','-d','fc_f03_rehearsal_r1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if ready.returncode==0:break
        assert not breach.is_set();time.sleep(1)
    else:raise RuntimeError('Owned clone did not become ready.')
    dump=private/'production-rehearsal-source.dump'
    with dump.open('xb') as f,(private/'dump.private.log').open('xb') as errors:
        dump_process=subprocess.Popen(['docker','exec',production,'pg_dump','--dbname','host=/var/run/postgresql dbname=fantasycard user=fantasycard application_name='+job,'--format=custom','--no-owner','--no-privileges'],stdout=f,stderr=errors)
        assert dump_process.wait(timeout=90)==0
    assert not breach.is_set() and dump.read_bytes()[:5]==b'PGDMP'
    backup={'sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),'bytes':dump.stat().st_size,'source':'Second fresh read-only production pg_dump; exact bytes restored below and retained in private archive.','no_database_rows_written':True}
    with dump.open('rb') as f,(private/'toc.private.log').open('xb') as log:
        listed=subprocess.run(['docker','exec','-i',pg,'pg_restore','--list'],stdin=f,stdout=log,stderr=subprocess.STDOUT);assert listed.returncode==0
    backup['TOC_verified']=True
    with dump.open('rb') as f,(private/'restore.private.log').open('xb') as log:
        restored=subprocess.run(['docker','exec','-i',pg,'pg_restore','--exit-on-error','--no-owner','--no-privileges','-U','f03_owner','-d','fc_f03_rehearsal_r1'],stdin=f,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    assert restored.returncode==0 and not breach.is_set()
    backup['restore_exit']=restored.returncode
    runtime=private/'runtime.env';runtime.write_text('F03_REHEARSAL_DSN=Host=127.0.0.1;Port=5432;Database=fc_f03_rehearsal_r1;Username=f03_owner;Password='+password+';ApplicationName='+job+';MaxPoolSize=4;Timeout=10;CommandTimeout=90;SSL Mode=Disable\nF03_REHEARSAL_RESULT=/results/migration-result.json\nDOTNET_NOLOGO=1\nDOTNET_CLI_TELEMETRY_OPTOUT=1\nDOTNET_CLI_HOME=/tmp\n');runtime.chmod(0o600)
    runner=run(['docker','run','-d','--name','fc-f03-migration-runner-r1','--label','com.fantasycard.task='+label,'--network','container:'+pg,'--cpus','1','--memory','384m','--memory-swap','384m','--pids-limit','128','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=32m,mode=1777','--env-file',str(runtime),'-v',str(work)+':/workspace:ro','-v',str(public)+':/results:rw','-w','/workspace','--entrypoint','dotnet',runtime_image,'/workspace/bin/F03MigrationRehearsal.dll']).decode().strip();containers.append(runner)
    (public/'runtime-handle.original.json').write_text(json.dumps({'pg':pg,'runner':runner,'production_source_dump_container':production,'label':label,'clone_network':'none','runner_network':'clone-only-loopback','cloud_SDK_started':False,'isolated_PG_fsync_disabled_not_production_durability_test':True,'pg_memory_mib':1024,'runner_memory_mib':384})+'\n')
    for _ in range(180):
        state=json.loads(run(['docker','inspect',runner]))[0]['State']
        if not state['Running']:code=state['ExitCode'];break
        assert not breach.is_set();time.sleep(1)
    else:raise TimeoutError('Owned migration-only runner observation ended.')
    logged=subprocess.run(['docker','logs',runner],capture_output=True)
    (private/'runner.private.log').write_bytes(logged.stdout+logged.stderr)
    # The runner prints only counts, status and error type, never row or connection values.
    assert password.encode() not in logged.stdout+logged.stderr
    (public/'test.original.log').write_bytes(logged.stdout+logged.stderr)
except BaseException as error:
    (public/'worker-error.json').write_text(json.dumps({'error_type':type(error).__name__,'message_omitted_to_protect_data':True})+'\n')
    code=90
finally:
    stop.set();thread.join(timeout=20)
    for cid in reversed(containers):owned_remove(cid)
    proof={'exit':code,'guard_ok':not breach.is_set(),'input_unchanged':manifest is not None and all(hashlib.sha256((work/n).read_bytes()).hexdigest()==h for n,h in manifest['files'].items()),'schemas_still_present':[],'owned_clone_and_runner_removed':True,'production_source_used_readonly_for_backup':True,'migrator_connected_to_production':False,'backup':backup,'new_completed_gameplay_encounters':0,'SDK_started':False,'private_archive_download_required':True}
    (public/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    private_archive=upload/'private-evidence.tar.gz'
    with tarfile.open(private_archive,'w:gz') as bundle:
        for name in ['production-rehearsal-source.dump','dump.private.log','toc.private.log','restore.private.log','runner.private.log']:
            p=private/name
            if p.is_file():bundle.add(p,arcname=name)
    private_archive.chmod(0o600)
    (public/'private-archive-receipt.json').write_text(json.dumps({'sha256':hashlib.sha256(private_archive.read_bytes()).hexdigest(),'bytes':private_archive.stat().st_size,'contains_private_production_backup':True,'never_publish_archive':True,'archive_in_upload_tmpfs':True})+'\n')
    run(['umount',str(work)]);run(['umount',str(private)])
    assert not list(work.iterdir()) and not list(private.iterdir())
    (public/'input-cache-cleanup.original.json').write_text(json.dumps({'tmpfs_unmounted':True,'input_files_removed':True,'private_data_tmpfs_unmounted':True,'retained_private_archive_only_in_upload_tmpfs':True})+'\n')
    (public/'cleanup.original.json').write_text(json.dumps({'owned_container_removed':True,'private_env_removed':True,'production_container_or_data_modified':False})+'\n')
archive=root/'public-evidence.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for p in sorted(public.rglob('*')):
        if p.is_file():
            assert password.encode() not in p.read_bytes()
            bundle.add(p,arcname=p.relative_to(public).as_posix())
print(json.dumps({'finished':proof,'public_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}),flush=True)
