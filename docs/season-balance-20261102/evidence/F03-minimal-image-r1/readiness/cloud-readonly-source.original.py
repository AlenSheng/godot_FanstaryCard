from pathlib import Path
import subprocess,json,re,shutil,datetime
def command(args):
 return subprocess.check_output(args,stderr=subprocess.PIPE,timeout=12).decode().strip()
disk=shutil.disk_usage('/home/ubuntu');memory=dict(l.split(':',1) for l in Path('/proc/meminfo').read_text().splitlines());available=int(memory['MemAvailable'].split()[0])*1024
out={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'resources':{'available_ram':available,'free_disk':disk.free,'disk_fraction':disk.free/disk.total},'resource_protection_ok':available>=500*1024**2 and disk.free>=3*1024**3 and disk.free/disk.total>=.05,'app_or_DB_writes':False,'SDK_started':False}
repo=Path('/opt/fantasycard-github')
if repo.is_dir():
 out['checkout_head']=command(['git','-c','safe.directory='+str(repo),'-C',str(repo),'rev-parse','HEAD'])
 out['checkout_dirty_entry_count']=len(command(['git','-c','safe.directory='+str(repo),'-C',str(repo),'status','--porcelain']).splitlines())
markers={}
for name in ['deployed-git-commit','deployed-runtime-commit']:
 p=Path('/opt/fantasycard-app')/name
 if p.is_file():
  text=p.read_text().strip();markers[name]=text if re.fullmatch('[0-9a-f]{40}',text) else 'PresentNonCanonicalValue'
out['markers']=markers
containers=[]
for cid in command(['docker','ps','-q','--filter','label=com.docker.compose.project=fantasycard-cloud']).splitlines():
 d=json.loads(command(['docker','inspect',cid]))[0];labels=d['Config'].get('Labels') or {};service=labels.get('com.docker.compose.service')
 if service not in ['server','postgres','caddy']:continue
 row={'id':cid,'service':service,'running':d['State']['Running'],'health':d['State'].get('Health',{}).get('Status'),'started_at':d['State']['StartedAt'],'image_id':d['Image']}
 if service=='server':
  image=json.loads(command(['docker','image','inspect',d['Image']]))[0];lab=image['Config'].get('Labels') or {};row['image_labels']={k:lab[k] for k in ['org.opencontainers.image.revision','fantasycard.config.sha256','fantasycard.config.version'] if k in lab}
  row['runtime_image']={'size':image.get('Size'),'architecture':image.get('Architecture'),'os':image.get('Os'),'repo_tags':image.get('RepoTags'),'layers':image.get('RootFS',{}).get('Layers'),'user':image.get('Config',{}).get('User'),'working_dir':image.get('Config',{}).get('WorkingDir'),'entrypoint':image.get('Config',{}).get('Entrypoint'),'cmd':image.get('Config',{}).get('Cmd')}
  row['public_host_settings']={k:d.get('HostConfig',{}).get(k) for k in ['ReadonlyRootfs','Memory','NanoCpus','CapDrop','SecurityOpt','LogConfig']}
  row['mounts_without_secret_contents']=[{k:m.get(k) for k in ['Type','Destination','RW']} for m in d.get('Mounts',[])]
  row['app_top_level_file_inventory']=command(['docker','exec',cid,'find','/app','-maxdepth','1','-type','f','-printf','%f %s\n']).splitlines()
  row['app_project_DLL_hashes']=command(['docker','exec',cid,'sha256sum','/app/FantasyCard.Contracts.dll','/app/FantasyCard.Domain.dll','/app/FantasyCard.Server.dll']).splitlines()
 if service=='postgres' and out['resource_protection_ok']:
  value=command(['docker','exec',cid,'psql','-U','fantasycard','-d','fantasycard','-X','-qAt','-c',"BEGIN READ ONLY;SELECT coalesce(max(version),0),count(*) FROM schema_migrations;SELECT pg_database_size(current_database());ROLLBACK;"])
  row['read_only_migration_and_size_result']=value.splitlines()
 containers.append(row)
out['containers']=containers
backups=Path('/opt/fantasycard-app/backups')
if backups.is_dir():
 files=[p for p in backups.iterdir() if p.is_file()];out['backup_inventory']={'file_count':len(files),'total_bytes':sum(p.stat().st_size for p in files),'newest_mtime_epoch':max((p.stat().st_mtime for p in files),default=None),'contents_read':False}
health=[]
for url in ['http://127.0.0.1:8080/health/ready','https://www.relicbound.cn/health/ready','https://www.relicbound.cn/admin']:
 try:
  result=command(['curl','--silent','--show-error','--max-time','8','--output','/dev/null','--write-out','%{http_code}',url]);health.append({'url':url,'status':int(result)})
 except subprocess.SubprocessError as e:health.append({'url':url,'error_type':type(e).__name__})
out['health']=health;print(json.dumps(out))
