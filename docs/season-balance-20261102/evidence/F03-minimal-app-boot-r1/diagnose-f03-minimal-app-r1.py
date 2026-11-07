from pathlib import Path
import base64,json,re,shlex,subprocess

b=Path(__file__).parent;out=b/'f03-minimal-app-cloud-resume-r1'
code='''from pathlib import Path
import json,re,subprocess
root=Path('/home/ubuntu/season-balance-20261107-f03-minimal-app-r1')
password=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r1/test-connection.private.json').read_text())['password']
text=(root/'application.private.log').read_text().replace(password,'[REDACTED]')
text=re.sub(r'[0-9a-fA-F]{64}','[REDACTED-HEX]',text)
assert password not in text
print(json.dumps(dict(redacted_application_log=text[-18000:],task_containers=subprocess.check_output(['docker','ps','-a','-q','--filter','label=com.fantasycard.task=season-balance-20261107-f03-minimal-app-r1']).decode().split(),read_only=True)))
'''
remote='sudo -n python3 -B -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
command=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','ubuntu@43.172.70.182',remote]
r=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=35,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS);assert r.returncode==0,r.stderr[-1000:]
(out/'redacted-application-diagnostic.original.json').write_text(r.stdout,encoding='utf-8');print(r.stdout)
