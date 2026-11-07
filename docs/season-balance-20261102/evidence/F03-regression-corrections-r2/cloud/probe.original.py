import json,pathlib,os,subprocess,datetime
run=lambda a:subprocess.check_output(a,text=True,timeout=15).strip()
mem={a:int(v.split()[0])*1024 for a,v in (line.split(':',1) for line in pathlib.Path('/proc/meminfo').read_text().splitlines()) if a in ['MemTotal','MemAvailable']}
s=os.statvfs('/');free=s.f_bavail*s.f_frsize;total=s.f_blocks*s.f_frsize
ids=run(['sudo','-n','docker','ps','-q','--filter','label=com.docker.compose.project=fantasycard-cloud']).splitlines();containers=[]
for cid in ids:
 value=run(['sudo','-n','docker','inspect','--format','{{.Id}}|{{.Image}}|{{.State.Status}}|{{.State.StartedAt}}',cid]).split('|');containers.append(dict(id=value[0],image=value[1],state=value[2],started_at=value[3]))
markers={}
for name in ['deployed-git-commit','deployed-runtime-commit']:
 p=pathlib.Path('/opt/fantasycard-app')/name;markers[name]=p.read_text().strip() if p.exists() else None
print(json.dumps(dict(readonly=True,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),memory=mem,disk=dict(free=free,total=total,free_percent=100*free/total),guards=dict(RAM=mem['MemAvailable']>=500*1024**2,disk_bytes=free>=3*1024**3,disk_percent=free/total>=.05),production_containers=containers,markers=markers,git_head=run(['git','-C','/opt/fantasycard-github','rev-parse','HEAD']),git_status=run(['git','-C','/opt/fantasycard-github','status','--porcelain']),production_modified=False)))
