from pathlib import Path
import base64,hashlib,io,json,subprocess,tarfile

base=Path(__file__).parent;stage=base/'journey-controller-cloud-r3';repo=Path.cwd()
assert json.loads((stage/'observation-r1.original.json').read_text('utf-8'))['stdout'].find('"root_exists": false')>=0
pins=json.loads((stage/'source-pin.json').read_text('utf-8'));assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())
source=(stage/'remote.original.py').read_text('utf-8');out=stage/'transport-retry1.stdout.original.log';err=stage/'transport-retry1.stderr.original.log';assert not out.exists() and not err.exists()
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182','sudo -n python3 -'],input=source,capture_output=True,text=True,timeout=270)
out.write_text(r.stdout,encoding='utf-8');err.write_text(r.stderr,encoding='utf-8');assert r.returncode==0,(r.returncode,r.stderr[-2000:])
data=json.loads(r.stdout);raw=base64.b64decode(data['archive_base64']);assert hashlib.sha256(raw).hexdigest()==data['sha256'];(stage/'public.tar.gz').write_bytes(raw)
public=stage/'public';assert not public.exists();public.mkdir()
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
 for item in archive.getmembers():
  assert item.isfile() and Path(item.name).name==item.name
  (public/item.name).write_bytes(archive.extractfile(item).read())
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())
for name in ['terminal.original.json','case-results.json','test.stderr.original.log']:
 if (public/name).exists():print(name,(public/name).read_text('utf-8')[-6000:])
