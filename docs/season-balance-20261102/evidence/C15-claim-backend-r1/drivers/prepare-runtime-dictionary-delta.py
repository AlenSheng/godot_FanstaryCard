from pathlib import Path
import json,hashlib,tarfile,io,sys,re,importlib.util
b=Path(__file__).parent;stage,base_stage=sys.argv[1:3];assert re.fullmatch(r'runtime-r[1-9][0-9]*',stage) and re.fullmatch(r'runtime-r[1-9][0-9]*',base_stage)
o=b/stage;oldroot=b/base_stage;old=json.loads((oldroot/'manifest.json').read_text('utf-8'));new=json.loads((o/'manifest.json').read_text('utf-8'))
assert hashlib.sha256((oldroot/'payload.tar.gz').read_bytes()).hexdigest()==old['payload_sha256'];assert hashlib.sha256((o/'payload.tar.gz').read_bytes()).hexdigest()==new['payload_sha256']
spec=importlib.util.spec_from_file_location('codec',b/'runtime_dictionary_delta.py');codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
changed=[n for n,h in new['files'].items() if old['files'].get(n)!=h];removed=sorted(set(old['files'])-set(new['files']));target=o/'delta.tar.gz';assert not target.exists();details=[]
with tarfile.open(oldroot/'payload.tar.gz','r:gz') as before,tarfile.open(o/'payload.tar.gz','r:gz') as after,tarfile.open(target,'w:gz') as out:
    for name in changed:
        try:base=before.extractfile(name).read()
        except KeyError:base=b''
        raw=after.extractfile(name).read();assert hashlib.sha256(raw).hexdigest()==new['files'][name]
        patch=codec.encode(base,raw);assert codec.decode(base,patch)==raw
        member=tarfile.TarInfo(name);member.size=len(patch);member.mode=0o644;out.addfile(member,io.BytesIO(patch));details.append(dict(file=name,full_bytes=len(raw),encoded_bytes=len(patch),target_sha256=new['files'][name]))
manifest=dict(format='FCBDZ1',base_payload_sha256=old['payload_sha256'],target_payload_sha256=new['payload_sha256'],delta_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),delta_bytes=target.stat().st_size,changed_files=changed,removed_files=removed,codec_sha256=hashlib.sha256((b/'runtime_dictionary_delta.py').read_bytes()).hexdigest(),all_changed_members_roundtripped_byte_identical=True,application_bytes_changed=False,details=details)
(o/'delta-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in manifest.items() if k not in ['details','changed_files','removed_files']}));print('changed',len(changed),'removed',len(removed))
