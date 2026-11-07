from pathlib import Path
import json,shutil

b=Path(__file__).parent;old=b/'f03-protected-snapshot-r1';out=b/'f03-protected-snapshot-r2';assert not out.exists();out.mkdir();(out/'inputs').mkdir()
(old/'result.json').write_text(json.dumps(dict(stage='compile',exit=1,errors=['Missing Combat namespace for CombatCardCatalog and BattleRoomSnapshot'],actual_snapshot_executions=0,new_gameplay_starts=0,product_source_modified=False),indent=2)+'\n')
info=json.loads((old/'prepared.original.json').read_bytes());previous=Path(info['private']);private=previous.with_name('f03-snapshot-probe-r2');assert not private.exists();private.mkdir()
source=(old/'Program.cs').read_text('utf-8').replace('using FantasyCard.Domain.Cards;','using FantasyCard.Domain.Cards;\nusing FantasyCard.Domain.Combat;')
(out/'Program.cs').write_text(source,encoding='utf-8')
for mode in ['original','protected']:
    p=private/mode;p.mkdir();(p/'Program.cs').write_text(source,encoding='utf-8');shutil.copyfile(previous/mode/'Probe.csproj',p/'Probe.csproj')
manifest=json.loads((old/'inputs.original.json').read_bytes())
for row in manifest:
    original=Path(row['path']);target=out/'inputs'/original.name;shutil.copyfile(original,target);row['path']=str(target)
(out/'inputs.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
info.update(private=str(private),same50_input_bytes_as_r1=True,only_namespace_import_corrected=True)
(out/'prepared.original.json').write_text(json.dumps(info,indent=2)+'\n')
runner=(b/'run-protected-snapshot-probe-r1.py').read_text('utf-8').replace('f03-protected-snapshot-r1','f03-protected-snapshot-r2')
(b/'run-protected-snapshot-probe-r2.py').write_text(runner,encoding='utf-8');print(json.dumps(dict(same_inputs=50,private=str(private),new_gameplay_starts=0)))
