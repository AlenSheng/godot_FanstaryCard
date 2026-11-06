from pathlib import Path
import copy,hashlib,json,struct

repo=Path.cwd();base=Path(__file__).parent;proof=base/'journey-cosmetic-registration-r1.json';assert not proof.exists()
path=repo/'client/assets/imported/manifest.json';raw=path.read_bytes();original=json.loads(raw);updated=copy.deepcopy(original)
assets=json.loads((repo/'docs/season-balance-20261102/C15-ASSET-PROVENANCE.json').read_text('utf-8'))['assets']
added={}
for row in assets:
    image=repo/row['file'];data=image.read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
    size=list(struct.unpack('>II',data[16:24]));digest=hashlib.sha256(data).hexdigest();assert size==row['size'] and digest==row['sha256']
    key=image.relative_to(repo/'client/assets/imported').as_posix();assert key not in updated['files']
    entry={'path':'res://'+image.relative_to(repo/'client').as_posix(),'source_path':row['source'],'source_sha256':digest,'imported_sha256':digest,'source_size':size,'imported_size':size}
    updated['files'][key]=entry;added[key]=entry
assert len(added)==7 and len(updated['files'])==len(original['files'])+7
assert all(updated['files'][key]==value for key,value in original['files'].items())
assert all(updated[key]==value for key,value in original.items() if key!='files')
path.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
proof.write_text(json.dumps({'before_sha256':hashlib.sha256(raw).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_entries_preserved':len(original['files']),'added':added,'all_other_sections_unchanged':True,'scope':'registration and source bytes only; rendered art remains pending'},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'original_entries':len(original['files']),'added':len(added)}))
