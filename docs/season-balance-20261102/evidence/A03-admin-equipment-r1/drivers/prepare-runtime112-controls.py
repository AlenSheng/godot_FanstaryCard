from pathlib import Path
import json

base=Path(__file__).parent;root=base/'runtime-r112';delta=json.loads((root/'delta-manifest.json').read_bytes());manifest=json.loads((root/'manifest.json').read_bytes())
delta.update(staging_method='tmpfs_byte_verified_full_copy',staging_allocation_bytes=len(manifest['files'])*4096,tmpfs_allocation_bytes=64*1024**2)
(root/'delta-manifest.json').write_text(json.dumps(delta,indent=2)+'\n',encoding='utf-8')
source=(base/'runtime-r111/start-delta-runtime.py').read_text('utf-8').replace('runtime-r111','runtime-r112')
source=source.replace("filters=['FantasyCard.Server.Tests.Persistence.PostgresAdminRevokeContextTests.*'", "filters=['FantasyCard.Server.Tests.Persistence.PostgresAdminEquipmentProvenanceTests.*','FantasyCard.Server.Tests.Persistence.PostgresAdminRevokeContextTests.*'")
p=root/'start-delta-runtime.py';assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
for old,new in [('setup-mail-runtime111-file-transfer.py','setup-mail-runtime112-file-transfer.py'),('transfer-r111-stream-sftp.py','transfer-r112-stream-sftp.py'),('verify-r111-complete-stream.py','verify-r112-complete-stream.py'),('start-r111-from-verified-file.py','start-r112-from-verified-file.py'),('observe-admin-revoke-r111.py','observe-admin-equipment-r112.py'),('collect-admin-revoke-r111.py','collect-admin-equipment-r112.py')]:
 source=(base/old).read_text('utf-8').replace('runtime-r111','runtime-r112').replace("passed']=='33'", "passed']=='36'").replace('declared_thirty_three_checks_accepted','declared_thirty_six_checks_accepted')
 p=base/new;assert not p.exists();p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
print(json.dumps({'files':len(manifest['files']),'staging':'64MiB tmpfs','base':'runtime109','expected_checks':36}))
