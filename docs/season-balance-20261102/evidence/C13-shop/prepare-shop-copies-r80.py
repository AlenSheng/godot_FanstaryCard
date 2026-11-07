from pathlib import Path
import subprocess,tarfile,json,hashlib,io
base=Path(__file__).parent;stage='storage-r80';out=base/stage
assert not out.exists(),'Preserve any existing stage and inspect its handles before proceeding'
r=subprocess.run(['python',str(base/'pack-crafting-tests.py'),stage],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
(out/'pack.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
script=(base/'storage-r76/start-storage-tests.py').read_text(encoding='utf-8').replace('storage-r76',stage).replace('20261102-r76','20261102-r80')
server_filter='FullyQualifiedName~PostgresPermanentCardCopyTests|FullyQualifiedName~PostgresCardEconomyTests|FullyQualifiedName~PostgresCardUpgradeTests|FullyQualifiedName~PostgresMigrationTests|FullyQualifiedName~EconomyReconciliationReportTests'
domain_filter='FullyQualifiedName~PermanentCardCopyRulesTests|FullyQualifiedName~CardUpgradeTests|FullyQualifiedName~CardEconomyTests|FullyQualifiedName~DeckRulesTests'
server='dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter "'+server_filter+'" --logger "trx;LogFileName=shop-copies-server.trx" --results-directory /workspace/results --verbosity minimal -m:1 -p:UseSharedCompilation=false'
domain='dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj --filter "'+domain_filter+'" --logger "trx;LogFileName=shop-copies-domain.trx" --results-directory /workspace/results --verbosity minimal -m:1 -p:UseSharedCompilation=false'
start=script.index('server_command=');end=script.index('image=',start);script=script[:start]+'server_command='+repr(server)+'\ndomain_command='+repr(domain)+'\n'+script[end:];compile(script,str(out/'start-storage-tests.py'),'exec');(out/'start-storage-tests.py').write_text(script,encoding='utf-8')
with tarfile.open(out/'source.tar.gz','r:gz') as tf:files={m.name:tf.extractfile(m).read() for m in tf if m.isfile()}
repo=Path.cwd()
for version in [4,5,6,7]:
 for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
  n=f'server/config/archive/season-v1-config-{version}/{name}';data=(repo/n).read_bytes()
  if n in files:assert files[n]==data
  files[n]=data
with tarfile.open(out/'source.tar.gz','w:gz') as tf:
 for n,data in sorted(files.items()):
  m=tarfile.TarInfo(n);m.size=len(data);m.mode=0o644;tf.addfile(m,io.BytesIO(data))
manifest=json.loads((out/'input-manifest.json').read_text(encoding='utf-8'));manifest['files']={n:hashlib.sha256(data).hexdigest() for n,data in files.items()};manifest['archive_sha256']=hashlib.sha256((out/'source.tar.gz').read_bytes()).hexdigest();(out/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
collector=(base/'storage-r76/collect-config-evidence.py').read_bytes();(out/'collect-config-evidence.py').write_bytes(collector)
with tarfile.open(out/'transfer.tar.gz','w:gz') as tf:
 for n in ['source.tar.gz','input-manifest.json','start-storage-tests.py','collect-config-evidence.py']:tf.add(out/n,arcname=n,recursive=False)
 tf.add(base/'cleanup-storage-sdk.py',arcname='cleanup-storage-sdk.py',recursive=False)
proof={'stage':stage,'transfer_sha256':hashlib.sha256((out/'transfer.tar.gz').read_bytes()).hexdigest(),'server_filter':server_filter,'domain_filter':domain_filter,'new_game_matches':0,'production_activated':False};(out/'transport-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
