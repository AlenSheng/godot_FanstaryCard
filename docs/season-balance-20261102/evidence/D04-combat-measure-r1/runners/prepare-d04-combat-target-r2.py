from pathlib import Path
base=Path(__file__).parent
source=(base/'prepare-d04-combat-cloud-r1.py').read_text(encoding='utf-8')
source=source.replace('d04-combat-measure-cloud-input-r1','d04-combat-measure-cloud-input-r2').replace('d04-combat-measure-server-r2','d04-combat-measure-build-r3')
source=source.replace('d04-combat-measure-cloud-r1-file','d04-combat-measure-cloud-r2-file').replace('d04-combat-measure-r1','d04-combat-measure-r2').replace('start-d04-combat-cloud-r1.py','start-d04-combat-cloud-r2.py').replace('run-d04-combat-cloud-r1.py','run-d04-combat-cloud-r2.py')
source=source.replace('d04-combat-cache-readback-before-r1.derived.json','d04-combat-cache-readback-before-r2.derived.json')
lines=source.splitlines();at=[i for i,line in enumerate(lines) if line.startswith('new=')];assert len(at)==1
lines[at[0]]="new=['FantasyCard.Server.Tests.Persistence.PostgresCombatMeasurementTelemetryTests.ActualCheckpointKeepsPveAndPvpCountersSeparateAndPrivateReadProjectionDoesNotChangeAssets']"
source='\n'.join(lines)+'\n'
needle="source=source.replace(needle,','.join(\"'-method',\"+repr(x) for x in new))";assert source.count(needle)==1
source=source.replace(needle,needle+".replace('planned_report_cases=4','planned_report_cases=1')")
source=source.replace('dict(cases=4,','dict(cases=1,')
target=base/'prepare-d04-combat-cloud-r2.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
p=base/'verify-d04-combat-cache-before-r2.py';assert not p.exists();text=(base/'verify-d04-combat-cache-before-r1.py').read_text(encoding='utf-8').replace('d04-combat-cache-before-r1','d04-combat-cache-before-r2').replace('d04-combat-cache-readback-before-r1.derived.json','d04-combat-cache-readback-before-r2.derived.json');p.write_text(text,encoding='utf-8')
print('Prepared only checkpoint-cadence recheck; original3passes retained and product sources unchanged.')
