from pathlib import Path
import json

base=Path(__file__).parent;root=base/'runtime-r109';delta=json.loads((root/'delta-manifest.json').read_text('utf-8'));manifest=json.loads((root/'manifest.json').read_text('utf-8'))
delta.update(staging_method='hardlink_readonly_base_unlink_changed_before_write',staging_allocation_bytes=sum(row['full_bytes'] for row in delta['details'])+len(manifest['files'])*4096)
(root/'delta-manifest.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
source=(base/'runtime-r108/start-delta-runtime.py').read_text('utf-8').replace('runtime-r108','runtime-r109').replace('runtime-r107','runtime-r108')
start=source.index('filters=[');end=source.index('\ncommand=',start)
filters=['FantasyCard.Server.Tests.Persistence.PostgresMailPermanentCopyTests.*','FantasyCard.Server.Tests.Persistence.PostgresAdminPermanentCopyTests.*','FantasyCard.Server.Tests.Persistence.PostgresSeasonShopTests.*','FantasyCard.Server.Tests.Persistence.PostgresJourneyRewardClaimTests.*','FantasyCard.Server.Tests.Persistence.PostgresJourneyRewardEntitlementTests.*','FantasyCard.Server.Tests.Persistence.PostgresSystemMailLocalizationTests.*','FantasyCard.Server.Tests.Persistence.PostgresMailReaderLifetimeTests.*','FantasyCard.Server.Tests.Persistence.PostgresMigrationTests.*','FantasyCard.Server.Tests.Progression.EconomyReconciliationReportTests.*','FantasyCard.Server.Tests.EndToEnd.RealNetworkEndToEndTests.JourneyRewards_ActualBinaryHttpClaimsFrozenCopiesAndSelectsOwnedCosmetics']
source=source[:start]+'filters='+repr(filters)+source[end:]
p=root/'start-delta-runtime.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
source=(base/'setup-journey-claims-r108-file-transfer.py').read_text('utf-8').replace('runtime-r108','runtime-r109').replace('runtime-r107','runtime-r108')
p=base/'setup-mail-runtime109-file-transfer.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
print(json.dumps({'target_files':len(manifest['files']),'staging_allocation':delta['staging_allocation_bytes'],'delta_bytes':delta['delta_bytes'],'filters':len(filters)}))
