from pathlib import Path
import json,shutil

b=Path(__file__).parent;old=b/'f03-protected-snapshot-r2';out=b/'f03-protected-snapshot-r4';assert not out.exists();out.mkdir();(out/'inputs').mkdir()
info=json.loads((old/'prepared.original.json').read_bytes());previous=Path(info['private']);private=previous.with_name('f03-snapshot-probe-r4');assert not private.exists();private.mkdir()
source=(old/'Program.cs').read_text('utf-8')
needle='''if(!JsonNode.DeepEquals(JsonNode.Parse(typed),JsonNode.Parse(json))) throw new InvalidOperationException("Restored capture differs from original snapshot");'''
replacement='''var left=JsonNode.Parse(typed)!;
        var right=JsonNode.Parse(json)!;
        var inactiveTimerNormalizations=0;
        var activeBotTimersPreserved=0;
        for(var index=0;index<snapshot.Players.Count;index++)
        {
            var before=snapshot.Players[index];
            var after=restored.Players[index];
            if(before.PlayerId!=after.PlayerId) throw new InvalidOperationException("Player ordering/identity changed");
            if(before.IsBot && before.Phase is RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted && before.BotPveRemaining is not null)
            {
                if(!after.IsBot || after.Phase!=before.Phase || after.BotPveRemaining is not null) throw new InvalidOperationException("Unexpected terminal bot timer change");
                left["Players"]![index]!["BotPveRemaining"]=null;
                right["Players"]![index]!["BotPveRemaining"]=null;
                inactiveTimerNormalizations++;
            }
            else if(before.IsBot && before.Phase==RoomPlayerPhase.Pve && before.Pve?.Phase==PveBattlePhase.Active && before.BotPveRemaining>TimeSpan.Zero)
            {
                if(after.BotPveRemaining!=before.BotPveRemaining) throw new InvalidOperationException("Active bot PVE timer changed");
                activeBotTimersPreserved++;
            }
        }
        if(!JsonNode.DeepEquals(left,right)) throw new InvalidOperationException("Restored capture differs outside the explicitly verified terminal-bot timer normalization");'''
assert needle in source;source=source.replace(needle,replacement)
source=source.replace('results.Add(new{id,ok=true,revision=room.Revision,elapsed=room.Elapsed,canonical_sha256=', 'results.Add(new{id,ok=true,inactiveTimerNormalizations,activeBotTimersPreserved,revision=room.Revision,elapsed=room.Elapsed,canonical_sha256=')
(out/'Program.cs').write_text(source,encoding='utf-8')
for mode in ['original','protected']:
    project=private/mode;project.mkdir();(project/'Program.cs').write_text(source,encoding='utf-8');shutil.copyfile(previous/mode/'Probe.csproj',project/'Probe.csproj')
manifest=json.loads((old/'inputs.original.json').read_bytes())
for row in manifest:
    original=Path(row['path']);target=out/'inputs'/original.name;shutil.copyfile(original,target);row['path']=str(target)
(out/'inputs.original.json').write_text(json.dumps(manifest,indent=2)+'\n')
info.update(private=str(private),same50_input_bytes_as_r2=True,product_source_unchanged=True,
    semantic_oracle='Only terminal IsBot+Dead/Extracted BotPveRemaining may normalize to null, exactly as BattleRoom.Restore:778-782. Everything else remains deep-equal; active bot PVE timers must remain exact.')
(out/'prepared.original.json').write_text(json.dumps(info,indent=2)+'\n')
runner=(b/'run-protected-snapshot-probe-r1.py').read_text('utf-8').replace('f03-protected-snapshot-r1','f03-protected-snapshot-r4')
(b/'run-protected-snapshot-probe-r4.py').write_text(runner,encoding='utf-8');print(json.dumps(dict(samples=50,new_gameplay_starts=0,product_source_changed=False,normalization_scope='terminal bot timer only')))
