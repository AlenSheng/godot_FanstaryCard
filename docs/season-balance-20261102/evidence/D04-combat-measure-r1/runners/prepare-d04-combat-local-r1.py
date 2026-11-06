from pathlib import Path
base=Path(__file__).parent
source=(base/'run-d04-build-dimensions-domain-r4.py').read_text(encoding='utf-8').replace('d04-build-dimensions-domain-r4','d04-combat-measure-domain-r1')
source=source.replace('FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~RoomEventObservationTests|FullyQualifiedName~RoomBuildProfileTests','FullyQualifiedName~RoomPlaytimeObservationTests|FullyQualifiedName~RoomEventObservationTests|FullyQualifiedName~RoomBuildProfileTests|FullyQualifiedName~RoomCombatMeasurementTests')
target=base/'run-d04-combat-domain-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
source=(base/'run-d04-build-dimensions-server-r2.py').read_text(encoding='utf-8').replace('d04-build-dimensions-server-r2','d04-combat-measure-server-r1')
source=source.replace('FullyQualifiedName~RoomObservationCoalescingTests|FullyQualifiedName~SeasonEventDimensionTests','FullyQualifiedName~RoomObservationCoalescingTests|FullyQualifiedName~SeasonEventDimensionTests|FullyQualifiedName~CombatMeasurementProjectionTests')
target=base/'run-d04-combat-server-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared sequential guarded domain45/server8; campaign matrices disabled.')
