from pathlib import Path
import json

base=Path(__file__).parent;root=base/'runtime-r110';delta=json.loads((root/'delta-manifest.json').read_text('utf-8'));manifest=json.loads((root/'manifest.json').read_text('utf-8'))
delta.update(staging_method='tmpfs_byte_verified_full_copy',staging_allocation_bytes=len(manifest['files'])*4096,tmpfs_allocation_bytes=64*1024**2)
(root/'delta-manifest.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
source=(base/'runtime-r109/start-delta-runtime.py').read_text('utf-8').replace('runtime-r109','runtime-r110').replace('runtime-r108','runtime-r109')
source=source.replace("r['available_ram']>=1800*1024**2", "r['available_ram']>=(1800+64)*1024**2")
source=source.replace("delta['staging_method']=='hardlink_readonly_base_unlink_changed_before_write'", "delta['staging_method']=='tmpfs_byte_verified_full_copy' and delta['tmpfs_allocation_bytes']==64*1024**2")
needle="root.mkdir(mode=0o700);work=root/'input';shutil.copytree(source,work,copy_function=os.link)"
assert needle in source
source=source.replace(needle,"root.mkdir(mode=0o700);work=root/'input';work.mkdir()\nsubprocess.run(['mount','-t','tmpfs','-o','size=67108864,nosuid,nodev,mode=0755','season-runtime110-input',str(work)],check=True)\nshutil.copytree(source,work,dirs_exist_ok=True,copy_function=shutil.copy2)")
start=source.index('filters=[');end=source.index('\ncommand=',start)
filters=['FantasyCard.Server.Tests.Persistence.PostgresMailPermanentCopyTests.*','FantasyCard.Server.Tests.Persistence.PostgresAdminPermanentCopyTests.*','FantasyCard.Server.Tests.Persistence.PostgresSystemMailLocalizationTests.*','FantasyCard.Server.Tests.Persistence.PostgresMailReaderLifetimeTests.*','FantasyCard.Server.Tests.Persistence.PostgresMigrationTests.*','FantasyCard.Server.Tests.Progression.EconomyReconciliationReportTests.*']
source=source[:start]+'filters='+repr(filters)+source[end:]
p=root/'start-delta-runtime.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
for old,new in [('setup-mail-runtime109-file-transfer.py','setup-mail-runtime110-file-transfer.py'),('transfer-r109-stream-sftp.py','transfer-r110-stream-sftp.py'),('verify-r109-complete-stream.py','verify-r110-complete-stream.py'),('start-r109-from-verified-file.py','start-r110-from-verified-file.py'),('observe-mail-runtime-r109.py','observe-mail-resource-r110.py')]:
 source=(base/old).read_text('utf-8').replace('runtime-r109','runtime-r110').replace('runtime-r108','runtime-r109');p=base/new;assert not p.exists();p.write_text(source,encoding='utf-8')
print(json.dumps({'target_files':len(manifest['files']),'disk_metadata_budget':delta['staging_allocation_bytes'],'tmpfs_max_bytes':delta['tmpfs_allocation_bytes'],'full_input_bytes':manifest['expanded_bytes'],'runtime_initial_RAM_admission_MiB':1864,'cloud_reserve_unchanged':True,'filters':len(filters)}))
