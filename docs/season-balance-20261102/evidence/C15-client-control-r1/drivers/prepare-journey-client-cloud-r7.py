from pathlib import Path
import base64,hashlib,io,json,re,tarfile

base=Path(__file__).parent;stage=base/'journey-client-cloud-r7';assert not stage.exists();stage.mkdir();previous=base/'journey-client-cloud-r6'
pins=json.loads((previous/'source-pin.json').read_text('utf-8'));assert all(hashlib.sha256(Path(n).read_bytes()).hexdigest()==h for n,h in pins.items())
matches=json.loads(json.loads((base/'client-assets-match-r1.original.json').read_text('utf-8'))['stdout'])
asset_pins={name:pins['client/'+name] for name in matches['matched']}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
 for p in sorted((previous/'project').rglob('*')):
  if p.is_file() and p.relative_to(previous/'project').as_posix() not in asset_pins:archive.add(p,arcname=p.relative_to(previous/'project').as_posix())
raw=buffer.getvalue();digest=hashlib.sha256(raw).hexdigest();(stage/'input.tar.gz').write_bytes(raw)
(stage/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
source=(previous/'remote.original.py').read_text('utf-8').replace('season-balance-20261102-journey-client-r6','season-balance-20261102-journey-client-r7')
old_payload=re.search(r"^payload=base64.b64decode\([^\n]+",source,re.M).group(0)
source=source.replace(old_payload,"payload=Path('/home/ubuntu/season-balance-20261102-journey-client-r7-transfer/input.tar.gz.part').read_bytes();assert hashlib.sha256(payload).hexdigest()=="+repr(digest))
old_pins=re.search(r'^asset_pins=[^\n]+',source,re.M).group(0);source=source.replace(old_pins,'asset_pins='+repr(asset_pins))
source=re.sub(r"'payload_sha256': '[a-f0-9]{64}'", "'payload_sha256': "+repr(digest),source)
source=source.replace(hashlib.sha256((previous/'input.tar.gz').read_bytes()).hexdigest(),digest)
(stage/'remote.original.py').write_text(source,encoding='utf-8');compile(source,str(stage/'remote.original.py'),'exec')
(stage/'manifest.json').write_text(json.dumps({'payload_sha256':digest,'payload_bytes':len(raw),'reused_assets':asset_pins,'transport':'SFTP serialized8KiB; verify complete bytes before any native start'},indent=2)+'\n',encoding='utf-8')
(stage/'sftp-put.batch').write_text('put "'+(stage/'input.tar.gz').as_posix()+'" "/home/ubuntu/season-balance-20261102-journey-client-r7-transfer/input.tar.gz.part"\n',encoding='utf-8')
print(json.dumps({'payload_bytes':len(raw),'reused_assets':len(asset_pins),'shipped_changed_png':list(matches['missing'])}))
