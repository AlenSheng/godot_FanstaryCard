from pathlib import Path
import gzip,hashlib,io,json,os,shutil,struct,subprocess,sys,tarfile,threading,time

label='season-balance-20261107-f03-minimal-image-r1'
root=Path('/home/ubuntu')/label;upload=Path('/home/ubuntu')/(label+'-upload')
assert not root.exists();root.mkdir(mode=0o700);public=root/'public';public.mkdir()
created=[];new_image=None;new_tag='fantasycard-f03-minimal:candidate-r1';stop=threading.Event();breach=threading.Event()
def run(args,**kwargs):return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=40,**kwargs)
def resources():
    m=dict(x.split(':',1) for x in Path('/proc/meminfo').read_text().splitlines());disk=shutil.disk_usage(root)
    r=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=disk.free,disk_fraction=disk.free/disk.total)
    r['ok']=r['available_ram']>=500*1024**2 and r['free_disk']>=3*1024**3 and r['disk_fraction']>=.05;return r
def guard(extra=0):
    r=resources();assert r['ok'] and r['free_disk']>=3*1024**3+extra and not breach.is_set();return r
def inspect(cid):return json.loads(run(['docker','inspect',cid]))[0]
def production_state():
    rows=[]
    for cid in run(['docker','ps','-q','--filter','label=com.docker.compose.project=fantasycard-cloud']).decode().split():
        item=inspect(cid);service=(item['Config'].get('Labels') or {}).get('com.docker.compose.service')
        rows.append(dict(id=cid,service=service,image=item['Image'],started=item['State']['StartedAt'],running=item['State']['Running']))
    return sorted(rows,key=lambda r:r['id'])
def watcher():
    with (public/'resources.original.jsonl').open('x') as log:
        while not stop.wait(.5):
            r=resources();log.write(json.dumps(r)+'\n');log.flush()
            if not r['ok']:
                breach.set()
                for cid in list(created):
                    try:
                        item=inspect(cid)
                        if item['Config']['Labels'].get('com.fantasycard.task')==label and item['State']['Running']:
                            subprocess.run(['docker','kill',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                    except Exception:pass
                return
before=production_state();(public/'production-before.original.json').write_text(json.dumps(before,indent=2)+'\n')
thread=threading.Thread(target=watcher,daemon=True);thread.start();result=None
try:
    first=guard(64*1024**2);assert first['available_ram']>=700*1024**2
    assert not run(['docker','ps','-a','-q','--filter','label=com.fantasycard.task='+label]).strip()
    assert subprocess.run(['docker','image','inspect',new_tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
    assert run(['findmnt','-n','-o','FSTYPE','--target',str(upload)]).decode().strip()=='tmpfs'
    raw=(upload/'stream.bin').read_bytes();length=struct.unpack('!I',raw[:4])[0];manifest=json.loads(raw[4:4+length]);payload=raw[4+length:]
    assert manifest['task']==label and len(payload)==manifest['payload_bytes'] and hashlib.sha256(payload).hexdigest()==manifest['payload_sha256']
    body=gzip.decompress(payload);assert len(body)==manifest['tar_bytes'] and manifest['expanded_bytes']<16*1024**2
    files=manifest['payload_files'];assert len(files)==18 and 'CANDIDATE-NOT-YET-VALIDATED.txt' in files
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:') as archive:
        assert len(archive.getmembers())==18
        for member in archive.getmembers():
            assert member.isfile() and member.name in files and '/' not in member.name and member.mode==0o644 and member.uid==member.gid==1654
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest()==files[member.name]
    base=manifest['base_image'];base_info=json.loads(run(['docker','image','inspect',base]))[0]
    assert base_info['Id']==base and not base_info['Config'].get('Volumes') and base_info['Config'].get('User')=='1654'
    assert base_info['Config']['WorkingDir']=='/app' and base_info['Config']['Entrypoint']==['dotnet','FantasyCard.Server.dll']
    env_names=[v.split('=',1)[0].upper() for v in base_info['Config'].get('Env',[])]
    assert not any(any(term in name for term in ['PASSWORD','APIKEY','API_KEY','SECRET','TOKEN','CONNECTIONSTRING']) for name in env_names)
    (public/'input-manifest.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cid=run(['docker','create','--name','fc-f03-minimal-builder-r1','--label','com.fantasycard.task='+label,'--network','none',base]).decode().strip();created.append(cid)
    guard();run(['docker','cp','-',cid+':/app/'],input=body)
    guard();new_image=run(['docker','commit','--change','LABEL org.opencontainers.image.revision='+manifest['compiled_source'],
        '--change','LABEL com.fantasycard.task='+label,'--change','LABEL fantasycard.candidate=true',cid,new_tag]).decode().strip()
    image=json.loads(run(['docker','image','inspect',new_image]))[0]
    assert image['Id']!=base and image['Config']['User']=='1654' and image['RootFS']['Layers'][:-1]==base_info['RootFS']['Layers']
    (public/'candidate-image.original.json').write_text(json.dumps(dict(id=new_image,base=base,size=image['Size'],user=image['Config']['User'],working_dir=image['Config']['WorkingDir'],entrypoint=image['Config']['Entrypoint'],layers=image['RootFS']['Layers'],revision=image['Config']['Labels']['org.opencontainers.image.revision']),indent=2)+'\n')
    outputs={}
    commands={
        'hashes':['sha256sum',*['/app/'+name for name in sorted(files)]],
        'inventory':['find','/app','-type','f','-printf','%P\n'],
        'runtimes':['dotnet','--list-runtimes'],
        'sdks':['dotnet','--list-sdks'],
    }
    for name,command in commands.items():
        guard();args=['docker','create','--name','fc-f03-minimal-'+name+'-r1','--label','com.fantasycard.task='+label,
            '--read-only','--network','none','--user','1654:1654','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--cpus','1','--memory','128m','--memory-swap','128m','--pids-limit','64','--entrypoint',command[0],new_image,*command[1:]]
        utility=run(args).decode().strip();created.append(utility);output=run(['docker','start','-a',utility]).decode();item=inspect(utility)
        assert item['State']['ExitCode']==0 and not item['State']['Running']
        assert item['HostConfig']['ReadonlyRootfs'] and item['HostConfig']['NetworkMode']=='none' and item['Config']['User']=='1654:1654'
        outputs[name]=output;(public/(name+'.stdout.original.log')).write_text(output)
    actual={line.split('  ',1)[1].removeprefix('/app/'):line.split('  ',1)[0] for line in outputs['hashes'].splitlines()}
    assert actual==files and set(outputs['inventory'].splitlines())==set(files)
    assert 'Microsoft.NETCore.App 10.' in outputs['runtimes'] and 'Microsoft.AspNetCore.App 10.' in outputs['runtimes'] and not outputs['sdks'].strip()
    after=production_state();assert before==after and not breach.is_set();guard()
    result=dict(ok=True,exact18_files_and_SHA=True,UID1654_can_read_all_files=True,read_only_rootfs=True,no_network=True,no_SDK_present=True,no_SDK_started=True,
        no_game_program_started=True,no_DB_access=True,new_gameplay_starts=0,production_containers_unchanged=True,production_deployment=False,
        candidate_marker_retained=True,not_a_full_release_verification=True,candidate_image=new_image,payload_sha256=manifest['payload_sha256'])
except Exception as error:
    result=dict(ok=False,type=type(error).__name__,error=str(error),new_gameplay_starts=0,production_deployment=False)
finally:
    cleanup=[]
    for cid in reversed(created):
        try:
            item=inspect(cid);assert item['Config']['Labels'].get('com.fantasycard.task')==label
            subprocess.run(['docker','rm','-f',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20);cleanup.append(cid)
        except Exception as error:cleanup.append(dict(id=cid,error_type=type(error).__name__))
    image_removed=False
    if new_image is not None:
        item=json.loads(run(['docker','image','inspect',new_image]))[0];assert item['Config']['Labels'].get('com.fantasycard.task')==label
        assert not run(['docker','ps','-a','-q','--filter','ancestor='+new_image]).strip()
        subprocess.run(['docker','image','rm',new_tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20);image_removed=True
    after=production_state();assert before==after
    stop.set();thread.join(timeout=5)
    (public/'cleanup.original.json').write_text(json.dumps(dict(owned_containers_removed=cleanup,owned_candidate_image_removed=image_removed,production_state_unchanged=before==after,resources=resources()),indent=2)+'\n')
    (public/'result.json').write_text(json.dumps(result,indent=2)+'\n')
with tarfile.open(root/'public-evidence.tar.gz','w:gz') as tar:
    for p in sorted(public.iterdir()):
        if p.is_file():tar.add(p,arcname=p.name,recursive=False)
print(json.dumps(result),flush=True)
