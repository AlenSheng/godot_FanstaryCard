from pathlib import Path
import ast,base64,hashlib,json,shutil

base=Path(__file__).parent;source=base/'admin-card-ledger-sql-r1';target=Path('docs/season-balance-20261102/evidence/C15-native17-admin-sql-r1')
tree=ast.parse((source/'remote.original.py').read_text('utf-8'))
calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='b64decode' and isinstance(node.args[0],ast.Constant)]
assert len(calls)==1;raw=base64.b64decode(calls[0].args[0].value)
preview=(source/'fixture.original.sql').read_bytes();assert preview==raw.replace(b'\n',b'\r\n')
p=source/'executed.original.sql';assert not p.exists();p.write_bytes(raw)
note={'executed_sql_sha256':hashlib.sha256(raw).hexdigest(),'local_preview_sha256':hashlib.sha256(preview).hexdigest(),'executed_SQL_extracted_losslessly_from_recorded_remote_payload':True,'local_preview_had_Windows_newline_expansion_on_original_mixed_newlines':True,'original_preview_and_payload_retained':True,'meaning':'fixture.original.sql is the local text export; executed.original.sql is the exact psql input payload. Differences are newline serialization only.'}
(source/'serialization-note.json').write_text(json.dumps(note,indent=2)+'\n',encoding='utf-8')
for name in ['executed.original.sql','serialization-note.json']:
 p=target/'admin-card-ledger-sql-r1'/name;assert not p.exists();p.write_bytes((source/name).read_bytes())
shutil.copyfile(Path(__file__),target/'drivers'/Path(__file__).name)
p=target/'manifest.json';manifest=json.loads(p.read_text('utf-8'))
for name in ['admin-card-ledger-sql-r1/executed.original.sql','admin-card-ledger-sql-r1/serialization-note.json','drivers/'+Path(__file__).name]:manifest['files'][name]=hashlib.sha256((target/name).read_bytes()).hexdigest()
p.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps(note))
