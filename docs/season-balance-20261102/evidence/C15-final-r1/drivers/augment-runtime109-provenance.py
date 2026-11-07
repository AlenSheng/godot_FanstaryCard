from pathlib import Path
import hashlib,io,json,tarfile

base=Path(__file__).parent;root=base/'runtime-r109';p=root/'payload.tar.gz';m=root/'manifest.json'
assert not (root/'payload.initial.original.tar.gz').exists()
old=json.loads(m.read_text('utf-8'));raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==old['payload_sha256']
files={}
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
 for member in archive.getmembers():files[member.name]=archive.extractfile(member).read()
assert all(hashlib.sha256(data).hexdigest()==old['files'][name] for name,data in files.items())
files['proof/production-components-build.original.log']=(base/'mail-permanent-local-r3/build-and-tests.original.log').read_bytes()
files['proof/unchanged-dependency-reuse.json']=(base/'mail-permanent-local-r6/unchanged-dependency-reuse.json').read_bytes()
reuse=json.loads(files['proof/unchanged-dependency-reuse.json'])
for name,digest in reuse['dependency_assemblies_sha256'].items():assert hashlib.sha256(files['bin/'+name+'.dll']).hexdigest()==digest
(root/'payload.initial.original.tar.gz').write_bytes(raw);(root/'manifest.initial.original.json').write_bytes(m.read_bytes())
with tarfile.open(p,'w:gz') as archive:
 for name,data in sorted(files.items()):
  member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644;archive.addfile(member,io.BytesIO(data))
old.update(payload_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),payload_bytes=p.stat().st_size,expanded_bytes=sum(map(len,files.values())),files={n:hashlib.sha256(data).hexdigest() for n,data in files.items()})
m.write_text(json.dumps(old,indent=2)+'\n',encoding='utf-8');print(json.dumps({'files':len(files),'payload_bytes':old['payload_bytes'],'expanded_bytes':old['expanded_bytes']}))
