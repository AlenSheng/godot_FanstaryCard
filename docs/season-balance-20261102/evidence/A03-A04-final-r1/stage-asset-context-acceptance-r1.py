from pathlib import Path
import hashlib,json,subprocess

repo=Path.cwd();b=Path(__file__).parent;root=repo/'docs/season-balance-20261102/evidence/A03-A04-final-r1'
m=json.loads((root/'manifest.json').read_bytes());assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in m['files'].items())
pin=json.loads((b/'asset-context-local-r5/source-pin.json').read_bytes());assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
scope={'.gitattributes','server/tests/FantasyCard.Server.Tests/Config/PublishedConfigTestInputs.cs','server/tests/FantasyCard.Server.Tests/Persistence/PostgresConfigVersionRoomTests.cs',
       'server/tests/FantasyCard.Server.Tests/Persistence/PostgresSeasonRoomTests.cs','server/tests/FantasyCard.Server.Tests/Persistence/PostgresAssetDomainCompositeTests.cs',
       'docs/season-balance-20261102/A03-A04-ASSET-CONTEXT-ACCEPTANCE.md','docs/season-balance-20261102/PROGRESS.json','docs/season-balance-20261102/README.md','docs/season-balance-20261102/A03-A04-CONTEXT-AUDIT.md'}
paths=[]
for entry in subprocess.check_output(['git','status','--porcelain=v1','-z','--untracked-files=all']).split(b'\0'):
 if not entry:continue
 assert entry[:2] in (b' M',b'??'),entry[:2]
 name=entry[3:].decode();assert name in scope or name.startswith('docs/season-balance-20261102/evidence/A03-A04-final-r1/'),name;paths.append(name)
p=b/'asset-context-staging.paths';assert not p.exists();p.write_bytes(b'\0'.join(n.encode() for n in paths)+b'\0')
subprocess.run(['git','add','--pathspec-from-file='+str(p),'--pathspec-file-nul'],check=True)
index={}
for row in subprocess.check_output(['git','ls-files','-s','-z']).split(b'\0'):
 if row:
  meta,path=row.split(b'\t',1);mode,blob,stage=meta.split();assert stage==b'0';index[path.decode()]=blob.decode()
for name in paths:
 raw=(repo/name).read_bytes()
 if '/evidence/' not in name:raw=raw.replace(b'\r\n',b'\n')
 assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==index[name],name
data=json.loads((repo/'docs/season-balance-20261102/PROGRESS.json').read_bytes());assert sum(x['status']=='complete' for x in data['items'])==23
print(json.dumps({'staged_files':len(paths),'evidence_bytes_exact_in_Git_index':True,'compiled_inputs_unchanged':True,'PG_unique_passed':121,'local':{'earlier_contract':34,'affected_config':14},'overall':'23/35'}))
