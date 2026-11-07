from pathlib import Path
import hashlib,json,tarfile,io

repo=Path.cwd();base=Path(__file__).parent;name='server/tests/FantasyCard.Domain.Tests/Combat/SeasonResourceLoopTargetedTests.cs'
current=(repo/name).read_text('utf-8');variants={}
old=current.replace('using System.Globalization;\n','')
old=old.replace('        var skip=int.Parse(Environment.GetEnvironmentVariable("FANTASYCARD_B05_SKIP_FIRST")??"0",CultureInfo.InvariantCulture);Assert.InRange(skip,0,8);var number=0;\n','')
old=old.replace('            number++;if(number<=skip)continue;\n','')
anchor='            var deck=Deck(hero,build);SeasonFenxianTests.ValidateDeck(hero,deck);\n';assert anchor in old
old=old.replace(anchor,anchor+'            var number=rows.Count+1;\n').replace('previousBudget=291+skip','previousBudget=291').replace('Assert.Equal(9-skip,rows.Count)','Assert.Equal(9,rows.Count)')
begin=old.index('                if(player.PendingRedEvaluation is {} pending)');end=old.index('                var kind=player.Combat.Hp',begin);old=old[:begin]+old[end:]
variants['b05-final-local-build-r1']=old.encode()
variants['b05-final-local-build-r2']=current.replace('using System.Globalization;\n','').replace('??"0",CultureInfo.InvariantCulture)','??"0")').encode()
variants['b05-final-local-build-r3']=(repo/name).read_bytes()
proof=[]
for stage,recovered in variants.items():
 root=base/stage;pin=json.loads((root/'source-pin.json').read_bytes());assert hashlib.sha256(recovered).hexdigest()==pin[name],stage
 inputs={n:recovered if n==name else (repo/n).read_bytes() for n in pin if Path(n).suffix in ['.cs','.sql','.csproj','.props','.targets','.proto']}
 assert all(hashlib.sha256(data).hexdigest()==pin[n] for n,data in inputs.items())
 target=root/'source-snapshot.verified-pinned-bytes.tar.gz';assert not target.exists()
 with tarfile.open(target,'w:gz') as tf:
  for n,data in sorted(inputs.items()):
   info=tarfile.TarInfo(n);info.size=len(data);tf.addfile(info,io.BytesIO(data))
 proof.append(dict(stage=stage,files=len(inputs),archive_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),recovered_test_source_sha256=pin[name],
                   provenance='Captured after execution; previous fixture bytes recovered by reversing recorded edits and verified against the original frozen source-pin. No original logs or results changed.'))
out=base/'b05-frozen-input-capture.derived.json';assert not out.exists();out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'archives':3,'all_members_match_original_input_pins':True,'historical_fixture_bytes_recovered':True}))
