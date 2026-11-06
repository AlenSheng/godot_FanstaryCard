from pathlib import Path
base=Path(__file__).parent
source=(base/'prepare-d04-room-events-cloud-r1.py').read_text(encoding='utf-8')
source=source.replace('d04-room-events-cloud-input-r1','d04-room-events-cloud-input-r2').replace('d04-room-events-server-r2','d04-room-events-build-r3')
source=source.replace('d04-room-events-cloud-r1','d04-room-events-cloud-r2').replace('d04-room-events-r1','d04-room-events-r2').replace('run-d04-room-events-file-r1','run-d04-room-events-file-r2')
lines=source.splitlines();matches=[i for i,line in enumerate(lines) if line.startswith('new=')];assert len(matches)==1
lines[matches[0]]="new=['FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts']"
source='\n'.join(lines)+'\n';source=source.replace(".replace('planned_report_cases=3','planned_report_cases=4')",".replace('planned_report_cases=3','planned_report_cases=1')").replace('prepared_cases=4','prepared_cases=1')
target=base/'prepare-d04-room-events-cloud-r2.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
print('Prepared one targeted nonempty checkpoint marker restart; original4case archive retained.')
