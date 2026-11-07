from pathlib import Path
import json,subprocess,hashlib,tarfile,io
base=Path(__file__).parent;folder=base/'d04-currency-cloud-r2';proof=json.loads((base/'d04-currency-r2-owned-transfer-stop-r1/result.original.json').read_bytes())
assert proof['proof']['remote_runtime_never_started'];target=folder/'public-evidence.forensic.tar.gz';assert not target.exists()
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=12','ubuntu@43.172.70.182','sudo -n cat '+proof['evidence_path']]
r=subprocess.run(cmd,capture_output=True,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS);assert r.returncode==0 and hashlib.sha256(r.stdout).hexdigest()==proof['evidence_sha256'];target.write_bytes(r.stdout)
out=folder/'public-forensic';out.mkdir()
with tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz') as bundle:
 for member in bundle.getmembers():
  assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
  p=out/member.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(bundle.extractfile(member).read())
print(json.dumps(dict(collected_forensic_archive_SHA256=proof['evidence_sha256'],actual_tests_in_failed_transfer=0,other_projects_modified=False)))
