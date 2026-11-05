from pathlib import Path
import json,hashlib,shutil
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');stage=b/'runtime-r105';source=stage/'public/results/preparation-client';target=b/'preparation-client-http-r1';assert not target.exists()
a=json.loads((stage/'collection-audit.json').read_text(encoding='utf-8'));assert a['exit_code']==0 and a['counts']['passed']=='1' and a['counts']['failed']=='0' and a['counts']['notExecuted']=='0'
assert hashlib.sha256((stage/'public-evidence.tar.gz').read_bytes()).hexdigest()==a['public_archive_sha256']
files=list(source.iterdir());assert len(files)==10 and all(p.is_file() for p in files)
for p in files:assert hashlib.sha256(p.read_bytes()).hexdigest()==a['files']['results/preparation-client/'+p.name]
m=json.loads((source/'input-manifest.json').read_text(encoding='utf-8'));assert len(m)==9
for n,h in m.items():assert hashlib.sha256((source/n).read_bytes()).hexdigest()==h
assert len(json.loads((source/'cases.json').read_text(encoding='utf-8')))==2
target.mkdir()
for p in files:shutil.copyfile(p,target/p.name)
print('Copied10 exact real-PG response files, including9 declared input hashes.')
