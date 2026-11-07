from pathlib import Path
import subprocess,base64,shlex,json,os
b=Path(__file__).parent;out=b/'f03-readiness-r1';code=(out/'cloud-readonly-source.original.py').read_bytes()
remote='sudo -n python3 -B -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code).decode())+'))')
cmd=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',remote]
r=subprocess.run(cmd,capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
(out/'cloud-readonly.stdout.original.log').write_bytes(r.stdout);(out/'cloud-readonly.stderr.original.log').write_bytes(r.stderr);(out/'cloud-readonly-terminal.original.json').write_text(json.dumps({'exit':r.returncode})+'\n');assert r.returncode==0,r.stderr.decode(errors='replace')
proof=json.loads(r.stdout);assert not proof['app_or_DB_writes'] and not proof['SDK_started'];(out/'cloud-readiness.derived.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
