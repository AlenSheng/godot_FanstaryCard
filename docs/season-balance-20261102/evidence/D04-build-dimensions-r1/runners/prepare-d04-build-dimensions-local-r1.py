from pathlib import Path
base=Path(__file__).parent
source=(base/'run-d04-room-events-domain-r2.py').read_text(encoding='utf-8').replace('d04-room-events-domain-r2','d04-build-dimensions-domain-r1')
source=source.replace('FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~RoomEventObservationTests','FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~RoomEventObservationTests|FullyQualifiedName~RoomBuildProfileTests')
path=base/'run-d04-build-dimensions-domain-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
source=(base/'run-d04-room-events-server-r2.py').read_text(encoding='utf-8').replace('d04-room-events-server-r2','d04-build-dimensions-server-r1')
source=source.replace('FullyQualifiedName~RoomObservationCoalescingTests','FullyQualifiedName~RoomObservationCoalescingTests|FullyQualifiedName~SeasonEventDimensionTests')
path=base/'run-d04-build-dimensions-server-r1.py';assert not path.exists();compile(source,str(path),'exec');path.write_text(source,encoding='utf-8')
print('Prepared sequential domain32 and server5 scoped runs. No campaign replay.')
