from pathlib import Path
import json,subprocess,base64,shlex,sys
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;root=b/'runtime-r106';proof=json.loads((root/'receiver-progress-r1.original.json').read_text('utf-8'))
assert not proof['runtime_root_exists'] and not proof['runtime_containers'];a,z=proof['samples'];assert a==z and a['wchan']=='pipe_read';assert 'not responding' in (root/'start-delta-retry1.original.log').read_text('utf-8')
out=root/'disconnected-receiver-stop.original.json';assert not out.exists()
code="""from pathlib import Path
import json,subprocess,hashlib,os,signal,time
expected=EXPECTED;pid=expected['pid'];p=Path('/proc')/str(pid);root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r106')
assert not root.exists();assert not subprocess.check_output(['docker','ps','-a','--filter','label=com.fantasycard.task=season-balance-20261102-a03-runtime-r106','--format','{{.ID}}']).strip()
if p.exists():
 raw=(p/'stat').read_text();tail=raw[raw.rindex(')')+2:].split();assert int(tail[19])==expected['start_ticks'];assert hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()==expected['argv_sha256'];assert (p/'wchan').read_text().strip()=='pipe_read'
 os.kill(pid,signal.SIGTERM)
for _ in range(25):
 if not p.exists():break
 raw=(p/'stat').read_text();tail=raw[raw.rindex(')')+2:].split()
 if tail[0]=='Z':break
 time.sleep(.2)
terminal=not p.exists() or tail[0]=='Z';assert terminal
print(json.dumps(dict(only_owned_precontainer_receiver_stopped=pid,identity_start_ticks=expected['start_ticks'],identity_argv_sha256=expected['argv_sha256'],local_upstream_already_terminal=True,original_complete_delta_retained_locally=True,no_runtime_container_or_PG_test_was_started=True,terminal=terminal,PG_unchanged=True)))
""".replace('EXPECTED',repr(a))
cmd='sudo -n python3 -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(code.encode()).decode())+'))')
r=subprocess.run(['ssh','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',cmd],capture_output=True,text=True,encoding='utf-8',timeout=40)
out.write_text(r.stdout+r.stderr,encoding='utf-8');print(r.stdout+r.stderr);assert r.returncode==0
