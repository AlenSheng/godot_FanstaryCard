from pathlib import Path
import datetime, json

b=Path(__file__).parent
# Keep a single heavy validation lane. The candidate builds must all be terminal first.
builds=json.loads((b/'f03-platform-refresh-r1/builds.result.json').read_bytes());assert builds['ok']
transfer=json.loads((b/'f03-fixed-app-transfer-resume-r1/result.json').read_bytes());assert transfer['exit']==0
verified=json.loads((b/'f03-fixed-app-reconcile-r2/result.original.json').read_bytes())
assert not verified['root_exists'] and not verified['launch_exists']
original=(b/'run-f03-fixed-app-cloud-r1.py').read_text('utf-8')
prefix=original.split("prepared=remote(setup,'setup')",1)[0].replace("out=b/'f03-fixed-app-cloud-r1'","out=b/'f03-fixed-app-cloud-resume-r1'")
assert prefix!=original
namespace={'__file__':str(Path(__file__)),'__name__':'__main__'}
exec(compile(prefix,str(Path(__file__)),'exec'),namespace)
out=namespace['out'];remote=namespace['remote'];upload=namespace['upload'];root=namespace['root'];transport=namespace['transport']
preflight=f'''from pathlib import Path
import hashlib,json,shutil,subprocess
u=Path({upload!r});r=Path({root!r});p=u/'stream.bin.part'
assert not r.exists() and not (u/'launch.original.json').exists() and p.is_file() and not p.is_symlink()
assert p.stat().st_size=={transport['bytes']} and hashlib.sha256(p.read_bytes()).hexdigest()=={transport['sha256']!r}
assert json.loads((u/'ownership.original.json').read_text())['sha256']=={transport['sha256']!r}
assert not subprocess.check_output(['docker','ps','-a','-q','--filter','label=com.fantasycard.task=season-balance-20261107-f03-fixed-app-r1'],timeout=15).strip()
d=shutil.disk_usage('/home/ubuntu');m=dict(s.split(':',1) for s in Path('/proc/meminfo').read_text().splitlines())
assert d.free>=3*1024**3+64*1024**2 and d.free/d.total>=.05 and int(m['MemAvailable'].split()[0])*1024>=700*1024**2
print(json.dumps(dict(same_complete_upload=True,sha256={transport['sha256']!r},no_existing_worker=True,resources_passed=True)))
'''
proof=remote(preflight,'same-upload-admission')
(out/'same-upload-admission.original.json').write_text(json.dumps(proof,indent=2)+'\n')
(out/'launch-attempt-started.original.json').write_text(json.dumps(dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),same_root=root,same_upload=upload,
    rule='If SSH observation fails, inspect remote launch.original.json and same worker; never duplicate'),indent=2)+'\n')
tail="launch=f'''"+original.split("launch=f'''",1)[1]
exec(compile(tail,str(Path(__file__)),'exec'),namespace)
