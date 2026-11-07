from pathlib import Path
import json,tarfile,hashlib,io
b=Path(__file__).parent;old=json.loads((b/'runtime-r106/manifest.json').read_text('utf-8'));root=b/'runtime-r107';new=json.loads((root/'manifest.json').read_text('utf-8'))
assert hashlib.sha256((b/'runtime-r106/payload.tar.gz').read_bytes()).hexdigest()==old['payload_sha256']
assert hashlib.sha256((root/'payload.tar.gz').read_bytes()).hexdigest()==new['payload_sha256']
changed=[n for n,h in new['files'].items() if old['files'].get(n)!=h];removed=sorted(set(old['files'])-set(new['files']));target=root/'delta.tar.gz';assert not target.exists()
with tarfile.open(root/'payload.tar.gz','r:gz') as source,tarfile.open(target,'w:gz') as out:
    for entry in source:
        if entry.name not in changed:continue
        assert entry.isfile();raw=source.extractfile(entry).read();assert hashlib.sha256(raw).hexdigest()==new['files'][entry.name]
        member=tarfile.TarInfo(entry.name);member.size=len(raw);member.mode=0o644;out.addfile(member,io.BytesIO(raw))
result=dict(base_payload_sha256=old['payload_sha256'],target_payload_sha256=new['payload_sha256'],delta_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),delta_bytes=target.stat().st_size,changed_files=changed,removed_files=removed)
(root/'delta-manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ['changed_files','removed_files']}));print('changed',len(changed),'removed',len(removed))
