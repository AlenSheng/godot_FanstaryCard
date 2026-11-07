from pathlib import Path
base=Path(__file__).parent
p=base/'start-f02-season-credit-cloud-r2.py';assert not p.exists()
s=(base/'start-f02-season-credit-cloud-r1.py').read_text(encoding='utf-8').replace('f02-season-credit-r1','f02-season-credit-r2')
needle="'-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_original16_and_current17_credit_survive_abrupt_restart_and_bad_archive_isolation'"
assert s.count(needle)==1
s=s.replace(needle,needle+",'-method','FantasyCard.Server.Tests.EndToEnd.ProcessLifecycleRecoveryTests.Full_host_actual17_preparation_READY_and_active_credit_resume_after_abrupt_restart_without_player_casts'")
s=s.replace('ApplicationName=fc-e01-discard-cloud-r1','ApplicationName=fc-f02-season-credit-cloud-r2')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=base/'run-f02-season-credit-cloud-r2.py';assert not p.exists()
s=(base/'run-f02-season-credit-cloud-r1.py').read_text(encoding='utf-8').replace('f02-season-credit-cloud-r1','f02-season-credit-cloud-r2').replace('f02-season-credit-r1','f02-season-credit-r2').replace('f02-season-credit-build-r1','f02-season-credit-build-r3')
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Prepared four exact new F02 cases from buildr3; originalr1 fully retained, no capacity or B05 methods selected.')
