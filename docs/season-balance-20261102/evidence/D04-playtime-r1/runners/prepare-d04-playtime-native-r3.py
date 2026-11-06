from pathlib import Path
base=Path(__file__).parent;source=(base/'run-d04-playtime-native-r2.py').read_text(encoding='utf-8')
for group,project,filter in [('domain','FantasyCard.Domain.Tests','FullyQualifiedName~RoomPlaytimeObservationTests'),('server','FantasyCard.Server.Tests','FullyQualifiedName~PlaytimeStatisticsTests')]:
 p=base/('run-d04-playtime-'+group+'-r3.py');assert not p.exists()
 text=source.replace("out=base/'d04-playtime-native-r2'","out=base/'d04-playtime-"+group+"-r3'")
 text=text.replace("repo/'server/FantasyCard.Server.slnx'","repo/'server/tests/"+project+"/"+project+".csproj'")
 text=text.replace('FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~PlaytimeStatisticsTests',filter).replace('LogFileName=contracts.trx','LogFileName='+group+'.trx')
 p.write_text(text,encoding='utf-8')
print('Two sequential guarded project runners prepared, separate immutable outputs/TRX.')
