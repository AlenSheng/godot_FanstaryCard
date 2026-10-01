"""Independent local command receipt. Never writes tested implementation."""
import argparse,datetime,hashlib,json,os,pathlib,platform,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--id',required=True);p.add_argument('--cwd',required=True);p.add_argument('--timeout',type=int,default=120);p.add_argument('argv',nargs=argparse.REMAINDER)
a=p.parse_args();argv=a.argv[1:] if a.argv[:1]==['--'] else a.argv
B=pathlib.Path(__file__).resolve().parent;log=B/'evidence'/(a.id+'.log')
sha=subprocess.check_output(['git','-C',a.cwd,'rev-parse','HEAD'],text=True).strip()
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
with log.open('w') as stream:r=subprocess.run(argv,cwd=a.cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=a.timeout)
record=dict(id=a.id,argv=argv,cwd=a.cwd,source_sha=sha,started_at_utc=start,elapsed_seconds=time.monotonic()-t,exit_code=r.returncode,python=sys.version,python_executable=sys.executable,platform=platform.platform(),environment={'PYTHONDONTWRITEBYTECODE':'1'},log=str(log.relative_to(B)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
(B/'evidence'/(a.id+'.command.json')).write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record));print(log.read_text()[-1500:]);raise SystemExit(r.returncode)
