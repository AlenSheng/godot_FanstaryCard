from pathlib import Path

base=Path(__file__).parent
pairs=[('setup-mail-runtime110-file-transfer.py','setup-mail-runtime111-file-transfer.py'),('transfer-r110-stream-sftp.py','transfer-r111-stream-sftp.py'),('verify-r110-complete-stream.py','verify-r111-complete-stream.py'),('start-r110-from-verified-file.py','start-r111-from-verified-file.py'),('observe-mail-resource-r110.py','observe-admin-revoke-r111.py')]
for old,new in pairs:
 p=base/new;assert not p.exists();source=(base/old).read_text('utf-8').replace('runtime-r110','runtime-r111');p.write_text(source,encoding='utf-8');compile(source,str(p),'exec')
print('Fresh runtime111 control files prepared; base remains runtime109.')
