from pathlib import Path
base=Path(__file__).parent
source=(base/'run-d04-playtime-server-r5.py').read_text(encoding='utf-8')
text=source.replace("out=base/'d04-playtime-server-r5'","out=base/'d04-crafting-build-r1'")
text=text.replace("'test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj')","'build',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj')")
text=text.replace(",'--filter','FullyQualifiedName~PlaytimeStatisticsTests','--logger','trx;LogFileName=server.trx','--results-directory',str(out/'results')",'')
target=base/'build-d04-crafting-r1.py'
assert not target.exists()
compile(text,str(target),'exec')
target.write_text(text,encoding='utf-8')
print('Prepared guarded compile only; no battle or PG execution.')
