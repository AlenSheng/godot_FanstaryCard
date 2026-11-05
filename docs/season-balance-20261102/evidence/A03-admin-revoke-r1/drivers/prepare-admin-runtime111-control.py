from pathlib import Path

base=Path(__file__).parent;source=(base/'prepare-runtime110-tmpfs-control.py').read_text('utf-8').replace('runtime-r110','runtime-r111')
source=source.replace("filters=['FantasyCard.Server.Tests.Persistence.PostgresMailPermanentCopyTests.*'", "filters=['FantasyCard.Server.Tests.Persistence.PostgresAdminRevokeContextTests.*','FantasyCard.Server.Tests.Persistence.PostgresMailPermanentCopyTests.*'")
p=base/'prepare-runtime111-tmpfs-control.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
source=(base/'collect-mail-resource-r110.py').read_text('utf-8').replace('runtime-r110','runtime-r111').replace("passed']=='25'", "passed']=='33'").replace('declared_twenty_five_checks_accepted','declared_thirty_three_checks_accepted')
source=source.replace('next_base_runtime109_retained=True','next_base_runtime109_retained=True')
p=base/'collect-admin-revoke-r111.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
print(str(base/'prepare-runtime111-tmpfs-control.py'))
