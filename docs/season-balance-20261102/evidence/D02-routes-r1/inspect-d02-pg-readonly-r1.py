from pathlib import Path
import base64,json,shlex,subprocess

base=Path(__file__).parent;out=base/'d02-pg-readonly-r1';assert not out.exists();out.mkdir()
key=Path(r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem');assert key.is_file()
code="""from pathlib import Path
import json,shutil,subprocess
m=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines());disk=shutil.disk_usage('/home/ubuntu')
resource=dict(available_ram=int(m['MemAvailable'].split()[0])*1024,free_disk=disk.free,disk_fraction=disk.free/disk.total)
resource['guard_ok']=resource['available_ram']>=500*1024**2 and disk.free>=3*1024**3 and disk.free/disk.total>=.05
assert resource['guard_ok']
item=json.loads(subprocess.check_output(['docker','inspect','803968e390014540be88f60b9ac43203946d0145bf886fc61d9d9d4d04bc3b1a']))[0]
task=item['Config']['Labels'].get('com.fantasycard.task');assert task=='season-balance-20261102-a03-storage-r1'
print(json.dumps(dict(resource=resource,container_id=item['Id'],status=item['State']['Status'],task=task,ports=item['NetworkSettings']['Ports'],credentials_read=False,production_modified=False,cloud_SDK_started=False)))
"""
command='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',str(key),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','ubuntu@43.172.70.182',command],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS,timeout=40)
(out/'stderr.original.log').write_text(r.stderr,encoding='utf-8');(out/'stdout.original.json').write_text(r.stdout,encoding='utf-8');(out/'exit.original.json').write_text(json.dumps(dict(exit=r.returncode,readonly=True))+'\n')
assert r.returncode==0;result=json.loads(r.stdout);assert result['status']=='running' and result['resource']['guard_ok'];print(json.dumps(result))
