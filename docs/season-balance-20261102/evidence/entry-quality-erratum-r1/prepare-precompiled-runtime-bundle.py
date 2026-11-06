from pathlib import Path
import sys,json,hashlib,tarfile,io,subprocess
repo=Path.cwd();b=Path(__file__).parent;stage=sys.argv[1];build_name=sys.argv[2];assert stage.startswith('runtime-r') and stage[9:].isdigit()
out=b/stage;assert not out.exists();out.mkdir();build=b/'local-archive-pg-r2/build/bin/FantasyCard.Server.Tests/debug'
pin=json.loads((b/build_name/'source-pin.json').read_text(encoding='utf-8'))
for n,h in pin.items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h,n
files={'bin/'+p.relative_to(build).as_posix():p.read_bytes() for p in build.rglob('*') if p.is_file()}
for n in pin:
 if (not n.startswith('server/') or '/config/' in n) and Path(n).suffix not in ['.cs','.sql','.csproj','.props','.targets','.proto']:files[n]=(repo/n).read_bytes()
files['server/FantasyCard.Server.slnx']=(repo/'server/FantasyCard.Server.slnx').read_bytes();files['proof/source-pin.json']=json.dumps(pin,indent=2).encode();files['proof/build.original.log']=(b/build_name/'build.original.log').read_bytes();files['proof/server-global.original.json']=(repo/'server/global.json').read_bytes()
source=io.BytesIO()
with tarfile.open(fileobj=source,mode='w:gz') as tf:
 for n in sorted(pin):
  if n.startswith('server/') and Path(n).suffix in ['.cs','.sql','.csproj','.props','.targets','.proto']:
   data=(repo/n).read_bytes();m=tarfile.TarInfo(n);m.size=len(data);tf.addfile(m,io.BytesIO(data))
files['proof/source-snapshot.tar.gz']=source.getvalue()
with tarfile.open(out/'payload.tar.gz','w:gz') as tf:
 for n,data in sorted(files.items()):
  m=tarfile.TarInfo(n);m.size=len(data);m.mode=0o644;tf.addfile(m,io.BytesIO(data))
payload=out/'payload.tar.gz';manifest=dict(source_base=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),payload_sha256=hashlib.sha256(payload.read_bytes()).hexdigest(),payload_bytes=payload.stat().st_size,expanded_bytes=sum(map(len,files.values())),files={n:hashlib.sha256(data).hexdigest() for n,data in files.items()},image=json.loads((b/'runtime-r92/manifest.json').read_text())['image'],runtime_staging_margin=64*1024**2,cloud_SDK_started=False,production_database_used=False)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in manifest.items() if k!='files'}))
