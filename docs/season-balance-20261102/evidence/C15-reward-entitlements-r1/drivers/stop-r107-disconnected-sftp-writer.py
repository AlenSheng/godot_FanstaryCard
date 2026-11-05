from pathlib import Path
import json,subprocess,base64,shlex,sys
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r107';proof=json.loads((o/'file-prefix-r3.original.json').read_text('utf-8'));assert proof['local_prefix_identical'] and not proof['complete'] and not proof['runtime_root_exists'] and not proof['runtime_containers'];assert json.loads((o/'sftp-r1.original.json').read_text('utf-8'))['exit']==255;assert len(proof['open_transfer_writers'])==1
out=o/'sftp-writer-stop-r1.original.json';assert not out.exists();control=dict(worker=proof['open_transfer_writers'][0],prefix_bytes=proof['bytes'],prefix_sha256=proof['sha256'])
code=r"""from pathlib import Path
import json,time,os,signal,hashlib,subprocess
v=CONTROL;w=v['worker'];p=Path('/proc')/str(w['pid']);target=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107-upload/stream-r1.bin.part')
assert not Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107').exists();assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r107','--format','{{.ID}}']).strip()
def inspect():
 assert target.stat().st_size==v['prefix_bytes'] and hashlib.sha256(target.read_bytes()).hexdigest()==v['prefix_sha256']
 if not p.exists():return False
 raw=(p/'stat').read_text();tail=raw[raw.rindex(')')+2:].split();assert int(tail[19])==w['start_ticks'];assert hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()==w['argv_sha256'];assert (p/'fd'/w['fd']).readlink()==target
 return True
live=inspect();time.sleep(5);live=inspect()
if live:os.kill(w['pid'],signal.SIGTERM)
for _ in range(25):
 if not p.exists():break
 raw=(p/'stat').read_text();tail=raw[raw.rindex(')')+2:].split()
 if tail[0]=='Z':break
 time.sleep(.2)
assert not p.exists() or tail[0]=='Z'
assert target.stat().st_size==v['prefix_bytes'] and hashlib.sha256(target.read_bytes()).hexdigest()==v['prefix_sha256']
print(json.dumps(dict(only_owned_disconnected_sftp_writer_stopped=w['pid'],identity_start_ticks=w['start_ticks'],identity_argv_sha256=w['argv_sha256'],verified_partial_file_preserved=True,prefix_bytes=v['prefix_bytes'],prefix_sha256=v['prefix_sha256'],terminal=True,no_runtime_or_PG_test_started=True)))
""".replace('CONTROL',repr(control))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=45)
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
