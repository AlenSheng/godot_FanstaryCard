"""Expose only one exact owned PG container and native backup commands to a test."""
import hashlib,json,os,re,socket,struct,subprocess,sys,threading
from pathlib import Path
ROOT=Path(sys.argv[1]);OWNER=sys.argv[2];CID=sys.argv[3];NAME=sys.argv[4];BASEDB=sys.argv[5];SOCKET=ROOT/'owned-postgres.sock';LOG=ROOT/'bridge-operations.original.jsonl';MAX=64*1024**2;lock=threading.Lock()
def exact():
 v=json.loads(subprocess.check_output(['docker','inspect',CID],timeout=15))[0];assert v['Id']==CID and v['Name']=='/'+NAME and v['Config']['Labels'].get('codex.owner')==OWNER and v['Config']['Labels'].get('codex.scope')=='disposable-local' and v['Config']['Labels'].get('codex.task')=='pr13-stages-20261008';return v
def recv(s,n):
 out=bytearray()
 while len(out)<n:
  block=s.recv(n-len(out));assert block;out.extend(block)
 return bytes(out)
def database(value):assert value==BASEDB or re.fullmatch(r'ready_stop_[0-9a-f]{32}',value)
def approved(args,stdin):
 exact();assert isinstance(args,list) and all(isinstance(a,str) for a in args)
 if args==['inspect',NAME]:assert not stdin;return ['docker','inspect',CID]
 assert args and args[0]=='exec';tail=args[1:];interactive=tail[0]=='-i'
 if interactive:tail=tail[1:]
 assert tail[0]==NAME;command=tail[1:];assert command
 if command[0]=='pg_dump':
  assert not interactive and not stdin and len(command)==10 and command[1:3]==['-U','fantasycard'] and command[3]=='-d' and command[5]=='--schema' and re.fullmatch(r'fc_runtime_test_[0-9a-f]+',command[6]) and command[7:]==['--format=custom','--no-owner','--no-acl']
  database(command[4])
 elif command[0]=='createdb':assert not interactive and not stdin and len(command)==4 and command[1:3]==['-U','fantasycard'];database(command[3])
 elif command[0]=='dropdb':assert not interactive and not stdin and len(command)==5 and command[1:4]==['--force','-U','fantasycard'];database(command[4]);assert command[4]!=BASEDB
 elif command[0]=='pg_restore':assert interactive and len(command)==8 and command[1:3]==['-U','fantasycard'] and command[3]=='-d' and command[5:]==['--exit-on-error','--no-owner','--no-acl'];database(command[4]);assert command[4]!=BASEDB and stdin.startswith(b'PGDMP')
 else:raise ValueError('Command outside exact owned native backup boundary')
 return ['docker','exec',*(['-i'] if interactive else []),CID,*command]
def client(s):
 try:
  s.settimeout(35);hsize=struct.unpack('!I',recv(s,4))[0];assert hsize<16384;header=json.loads(recv(s,hsize));n=header['stdin_bytes'];assert type(n)==int and 0<=n<=MAX;stdin=recv(s,n);args=header['args']
  # pg_dump's original fixed lock-wait option is part of the declared command.
  patched=args
  if args[:2]==['exec',NAME] and len(args)>2 and args[2]=='pg_dump':
   assert args[-1]=='--lock-wait-timeout=10s';patched=args[:-1]
  command=approved(patched,stdin);r=subprocess.run(command,input=stdin,capture_output=True,timeout=30);assert len(r.stdout)<=MAX and len(r.stderr)<=128*1024;response={'exit_code':r.returncode,'stdout_bytes':len(r.stdout),'stderr_bytes':len(r.stderr)}
  with lock:
   with LOG.open('a') as f:f.write(json.dumps({'args':args,'stdin_bytes':len(stdin),'stdin_sha256':hashlib.sha256(stdin).hexdigest(),'stdout_bytes':len(r.stdout),'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_bytes':len(r.stderr),'exit_code':r.returncode,'actual_owned_container_id':CID})+'\n')
  raw=json.dumps(response).encode();s.sendall(struct.pack('!I',len(raw))+raw+r.stdout+r.stderr)
 except Exception as error:
  message=(type(error).__name__+': owned bridge rejected or failed').encode();raw=json.dumps({'exit_code':125,'stdout_bytes':0,'stderr_bytes':len(message)}).encode();s.sendall(struct.pack('!I',len(raw))+raw+message)
 finally:s.close()
assert not SOCKET.exists();exact();server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(SOCKET));SOCKET.chmod(0o666);server.listen(8)
try:
 while True:s,_=server.accept();threading.Thread(target=client,args=(s,),daemon=True).start()
finally:server.close()
