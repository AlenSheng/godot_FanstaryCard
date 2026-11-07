from pathlib import Path
base=Path(__file__).parent
source=(base/'run-d04-combat-server-r2.py').read_text(encoding='utf-8').replace('d04-combat-measure-server-r2','d04-physical-flow-server-r1')
source=source.replace('FullyQualifiedName~RoomObservationCoalescingTests|FullyQualifiedName~SeasonEventDimensionTests|FullyQualifiedName~CombatMeasurementProjectionTests','FullyQualifiedName~RoomObservationCoalescingTests|FullyQualifiedName~SeasonEventDimensionTests|FullyQualifiedName~CombatMeasurementProjectionTests|FullyQualifiedName~PhysicalEquipmentFlowTests')
target=base/'run-d04-physical-server-r1.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared guarded server26 physical classification/common projection checks; no campaign replay.')
