from pathlib import Path
import subprocess,json,hashlib
repo=Path.cwd();base=Path(__file__).parent;out=base/'f02-composite-dependency-audit-r2';assert not out.exists();out.mkdir()
source=repo/'docs/season-balance-20261102/evidence/A03-A04-final-r1/asset-context-matrix-r1.original.json';matrix=json.loads(source.read_bytes());expected={n:h for f in matrix['families'] for n,h in f['source_sha256'].items()};unchanged=[];changed=[]
for name,digest in expected.items():
 actual=hashlib.sha256((repo/name).read_bytes()).hexdigest()
 if actual==digest:unchanged.append(dict(path=name,sha256=actual));continue
 commits=subprocess.check_output(['git','log','-n','50','--format=%H','--',name]).decode().splitlines();found=None
 for commit in commits:
  raw=subprocess.check_output(['git','show',commit+':'+name])
  if digest in [hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(bytes([13,10]),bytes([10])).replace(bytes([10]),bytes([13,10]))).hexdigest()]:found=commit;break
 assert found is not None,name
 patch=subprocess.check_output(['git','diff',found,'HEAD','--',name]);p=out/(Path(name).name+'.scope.derived.diff');p.write_bytes(patch)
 changed.append(dict(path=name,prior_source_sha256=digest,current_sha256=actual,matching_prior_commit=found,diff=str(p),diff_sha256=hashlib.sha256(patch).hexdigest()))
assert len(expected)==22 and len(unchanged)==20 and {x['path'] for x in changed}=={'server/src/FantasyCard.Server/Progression/ProgressionRepository.cs','server/src/FantasyCard.Server/Matchmaking/RoomReadyCoordinator.cs'}
proof=dict(kind='dependency and scope comparison, not fresh runtime execution',source_matrix_SHA256=hashlib.sha256(source.read_bytes()).hexdigest(),families=[f['id'] for f in matrix['families']],unique_direct_sources=22,unchanged_sources=unchanged,changed_sources=changed,indirect_configuration_and_room_changes_require_current_C01_and_F02_proofs=True,F02_complete=False)
(out/'result.derived.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(families=9,direct_sources=22,unchanged=20,changes=changed)))
