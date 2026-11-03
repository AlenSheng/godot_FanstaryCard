from pathlib import Path
import subprocess,json,hashlib,importlib.util,os,socket,time,xml.etree.ElementTree as ET
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-postgres-r2';assert not out.exists();out.mkdir()
key=Path(r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem');host='ubuntu@43.172.70.182'
ssh=['ssh','-i',str(key),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=1']
creation=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
remote='sudo -n python3 -c \'import base64;exec(base64.b64decode(\'"\'"\'aW1wb3J0IGpzb24sc2h1dGlsLHN1YnByb2Nlc3MKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCm09e2wuc3BsaXQoJzonKVswXTppbnQobC5zcGxpdCgpWzFdKSoxMDI0IGZvciBsIGluIFBhdGgoJy9wcm9jL21lbWluZm8nKS5yZWFkX3RleHQoKS5zcGxpdGxpbmVzKCkgaWYgbGVuKGwuc3BsaXQoKSk+MSBhbmQgbC5zcGxpdCgpWzFdLmlzZGlnaXQoKX0KZD1zaHV0aWwuZGlza191c2FnZSgnLycpO2Fzc2VydCBtWydNZW1BdmFpbGFibGUnXT49NTAwKjEwMjQqKjIgYW5kIGQuZnJlZT49MyoxMDI0KiozIGFuZCBkLmZyZWUvZC50b3RhbD49LjA1CnA9anNvbi5sb2FkcyhzdWJwcm9jZXNzLmNoZWNrX291dHB1dChbJ2RvY2tlcicsJ2luc3BlY3QnLCc4MDM5NjhlMzkwMDE0NTQwYmU4OGY2MGI5YWM0MzIwMzk0NmQwMTQ1YmY4ODZmYzYxZDlkOWQ0ZDA0YmMzYjFhJ10pKVswXQphc3NlcnQgcFsnU3RhdGUnXVsnU3RhdHVzJ109PSdydW5uaW5nJyBhbmQgcFsnQ29uZmlnJ11bJ0xhYmVscyddWydjb20uZmFudGFzeWNhcmQudGFzayddPT0nc2Vhc29uLWJhbGFuY2UtMjAyNjExMDItYTAzLXN0b3JhZ2UtcjEnCmM9anNvbi5sb2FkcyhQYXRoKCcvaG9tZS91YnVudHUvc2Vhc29uLWJhbGFuY2UtMjAyNjExMDItYTAzLXN0b3JhZ2UtcjEvdGVzdC1jb25uZWN0aW9uLnByaXZhdGUuanNvbicpLnJlYWRfdGV4dCgpKQpwcmludChqc29uLmR1bXBzKHsncmVzb3VyY2UnOnsnYXZhaWxhYmxlX3JhbSc6bVsnTWVtQXZhaWxhYmxlJ10sJ2ZyZWVfZGlzayc6ZC5mcmVlLCdTREtfb25fY2xvdWQnOkZhbHNlLCdvd25lZF9pc29sYXRlZF9QR192ZXJpZmllZCc6VHJ1ZX0sJ3Bhc3N3b3JkJzpjWydwYXNzd29yZCddfSkpCg==\'"\'"\'))\''
r=subprocess.run(ssh+[host,remote],capture_output=True,text=True,timeout=20,creationflags=creation);assert r.returncode==0,r.stderr
record=json.loads(r.stdout);password=record.pop("password");resource=record["resource"];del r
(out/"cloud-resource.json").write_text(json.dumps(resource,indent=2)+"\n")
with socket.socket() as sock:sock.bind(('127.0.0.1',55639))
tunnel=subprocess.Popen(ssh+['-o','ExitOnForwardFailure=yes','-N','-L','127.0.0.1:55639:127.0.0.1:55631',host],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=creation)
(out/'owned-tunnel-start.json').write_text(json.dumps({'pid':tunnel.pid,'local_bind':'127.0.0.1:55639','remote_test_bind':'127.0.0.1:55631','created_at':time.time(),'production_database_used':False},indent=2)+'\n')
try:
 for i in range(40):
  assert tunnel.poll() is None,'Owned SSH tunnel exited before test'
  try:
   with socket.create_connection(('127.0.0.1',55639),.25):break
  except OSError:time.sleep(.25)
 else:raise RuntimeError('Owned SSH tunnel did not become ready')
 spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
 pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
 (out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
 cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--filter','FullyQualifiedName~ActualScaledEliteVictoryResourcesReachTheOriginalSeasonWalletOnce','--logger','trx;LogFileName=base-drops-postgres.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
 env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',FANTASYCARD_TEST_POSTGRES='Host=127.0.0.1;Port=55639;Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30')
 print('Local SDK test using owned loopback SSH tunnel to isolated test PostgreSQL; no cloud SDK',flush=True)
 result=rt.guarded_run(cmd,env=env,timeout=240)
 text=result.stdout+result.stderr;assert password not in text,'Credential appeared in test output; original must remain private'
 (out/'test.original.log').write_text(text,encoding='utf-8')
 proof={'exit':result.returncode,'SDK':'10.0.400','production_database_used':False,'cloud_SDK_started':False,'new_game_matches':0,'B05_not_run':True,'command':cmd,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())}
 (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(text[-7000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged']
 tree=ET.parse(out/'results/base-drops-postgres.trx');counts=next(n.attrib for n in tree.iter() if n.tag.endswith('Counters'));assert counts['passed']=='1' and counts['notExecuted']=='0'
finally:
 tunnel.terminate();tunnel.wait(timeout=15)
 (out/'owned-tunnel-terminal.json').write_text(json.dumps({'pid':tunnel.pid,'exit_code':tunnel.returncode,'own_tunnel_only_stopped':True,'other_projects_modified':False},indent=2)+'\n')
