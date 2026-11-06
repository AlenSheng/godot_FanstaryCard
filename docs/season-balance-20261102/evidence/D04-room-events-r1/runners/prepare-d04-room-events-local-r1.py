from pathlib import Path
base=Path(__file__).parent
source=(base/'run-d04-playtime-domain-r3.py').read_text(encoding='utf-8').replace("out=base/'d04-playtime-domain-r3'","out=base/'d04-room-events-domain-r1'")
source=source.replace('FullyQualifiedName~RoomPlaytimeObservationTests','FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~RoomEventObservationTests')
target=base/'run-d04-room-events-domain-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
source=(base/'run-d04-playtime-server-r5.py').read_text(encoding='utf-8').replace("out=base/'d04-playtime-server-r5'","out=base/'d04-room-events-server-r1'")
source=source.replace('FullyQualifiedName~PlaytimeStatisticsTests','FullyQualifiedName~RoomObservationCoalescingTests')
target=base/'run-d04-room-events-server-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared sequential guarded domain19 and server1 runs, no campaign matrices.')
