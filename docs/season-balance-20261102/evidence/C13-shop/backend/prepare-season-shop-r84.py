from pathlib import Path
import subprocess,tarfile,json,hashlib,io
base=Path(__file__).parent;stage='storage-r84';out=base/stage
assert not out.exists(),'Preserve any existing stage and inspect its handles before proceeding'
r=subprocess.run(['python',str(base/'pack-crafting-tests.py'),stage],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
(out/'pack.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
script=(base/'storage-r76/start-storage-tests.py').read_text(encoding='utf-8').replace('storage-r76',stage).replace('20261102-r76','20261102-r84')
server_filter='FullyQualifiedName~PostgresSeasonShopTests|FullyQualifiedName~SeasonShop_RealBinaryHttpKeepsScopedPricesCopiesAndFrozenReplayReceipts|FullyQualifiedName~SeasonShopEncodingTests|FullyQualifiedName~SeasonConfigCompilerTests'
domain_filter='FullyQualifiedName~FantasyCard.Domain.Tests.Configuration|FullyQualifiedName~PermanentCardCopyRulesTests|FullyQualifiedName~CardUpgradeTests|FullyQualifiedName~DeckRulesTests'
server='dotnet test tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj --filter "'+server_filter+'" --logger "trx;LogFileName=season-shop-server.trx" --results-directory /workspace/results --verbosity minimal -m:1 -p:UseSharedCompilation=false'
domain='dotnet test tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj --filter "'+domain_filter+'" --logger "trx;LogFileName=season-shop-domain.trx" --results-directory /workspace/results --verbosity minimal -m:1 -p:UseSharedCompilation=false'
start=script.index('server_command=');end=script.index('image=',start);script=script[:start]+'server_command='+repr(server)+'\ndomain_command='+repr(domain)+'\n'+script[end:];script=script.replace("'-e','DOTNET_CLI_TELEMETRY_OPTOUT=1'","'-e','FANTASYCARD_SHOP_INTEROP_DIR=/workspace/shop-wire','-e','DOTNET_CLI_TELEMETRY_OPTOUT=1'");compile(script,str(out/'start-storage-tests.py'),'exec');(out/'start-storage-tests.py').write_text(script,encoding='utf-8')
with tarfile.open(out/'source.tar.gz','r:gz') as tf:files={m.name:tf.extractfile(m).read() for m in tf if m.isfile()}
repo=Path.cwd()
for version in [4,5,6,7,8]:
 for name in ['fantasycard.config.bytes','fantasycard.config.sha256','fantasycard.config.version.txt']:
  n=f'server/config/archive/season-v1-config-{version}/{name}';data=(repo/n).read_bytes()
  if n in files:assert files[n]==data
  files[n]=data
with tarfile.open(out/'source.tar.gz','w:gz') as tf:
 for n,data in sorted(files.items()):
  m=tarfile.TarInfo(n);m.size=len(data);m.mode=0o644;tf.addfile(m,io.BytesIO(data))
manifest=json.loads((out/'input-manifest.json').read_text(encoding='utf-8'));manifest['files']={n:hashlib.sha256(data).hexdigest() for n,data in files.items()};manifest['archive_sha256']=hashlib.sha256((out/'source.tar.gz').read_bytes()).hexdigest();(out/'input-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
collector=(base/'storage-r76/collect-config-evidence.py').read_text(encoding='utf-8');collector=collector.replace('counts = {}',"for wire in sorted((root/'input/shop-wire').glob('*.bin')):\n    files['shop-wire/'+wire.name]=wire.read_bytes()\ncounts = {}")
(out/'collect-config-evidence.py').write_text(collector,encoding='utf-8')
with tarfile.open(out/'transfer.tar.gz','w:gz') as tf:
 for n in ['source.tar.gz','input-manifest.json','start-storage-tests.py','collect-config-evidence.py']:tf.add(out/n,arcname=n,recursive=False)
 tf.add(base/'cleanup-storage-sdk.py',arcname='cleanup-storage-sdk.py',recursive=False)
proof={'stage':stage,'transfer_sha256':hashlib.sha256((out/'transfer.tar.gz').read_bytes()).hexdigest(),'server_filter':server_filter,'domain_filter':domain_filter,'new_game_matches':0,'production_activated':False};(out/'transport-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
