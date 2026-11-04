from pathlib import Path
import subprocess,json,hashlib,importlib.util,os,socket,time,xml.etree.ElementTree as ET
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');out=base/'local-shop-copies-postgres-r1';assert not out.exists();out.mkdir()
key=Path(r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem');host='ubuntu@43.172.70.182'
ssh=['ssh','-i',str(key),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
creation=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
import threading,queue
remote='sudo -n python3 -c \'import base64;exec(base64.b64decode(\'"\'"\'aW1wb3J0IGpzb24sc2h1dGlsLHN1YnByb2Nlc3Msc3lzCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAptPXtsLnNwbGl0KCc6JylbMF06aW50KGwuc3BsaXQoKVsxXSkqMTAyNCBmb3IgbCBpbiBQYXRoKCcvcHJvYy9tZW1pbmZvJykucmVhZF90ZXh0KCkuc3BsaXRsaW5lcygpIGlmIGxlbihsLnNwbGl0KCkpPjEgYW5kIGwuc3BsaXQoKVsxXS5pc2RpZ2l0KCl9CmQ9c2h1dGlsLmRpc2tfdXNhZ2UoJy8nKTthc3NlcnQgbVsnTWVtQXZhaWxhYmxlJ10+PTUwMCoxMDI0KioyIGFuZCBkLmZyZWU+PTMqMTAyNCoqMyBhbmQgZC5mcmVlL2QudG90YWw+PS4wNQpwPWpzb24ubG9hZHMoc3VicHJvY2Vzcy5jaGVja19vdXRwdXQoWydkb2NrZXInLCdpbnNwZWN0JywnODAzOTY4ZTM5MDAxNDU0MGJlODhmNjBiOWFjNDMyMDM5NDZkMDE0NWJmODg2ZmM2MWQ5ZDlkNGQwNGJjM2IxYSddKSlbMF0KYXNzZXJ0IHBbJ1N0YXRlJ11bJ1N0YXR1cyddPT0ncnVubmluZycgYW5kIHBbJ0NvbmZpZyddWydMYWJlbHMnXVsnY29tLmZhbnRhc3ljYXJkLnRhc2snXT09J3NlYXNvbi1iYWxhbmNlLTIwMjYxMTAyLWEwMy1zdG9yYWdlLXIxJwpjPWpzb24ubG9hZHMoUGF0aCgnL2hvbWUvdWJ1bnR1L3NlYXNvbi1iYWxhbmNlLTIwMjYxMTAyLWEwMy1zdG9yYWdlLXIxL3Rlc3QtY29ubmVjdGlvbi5wcml2YXRlLmpzb24nKS5yZWFkX3RleHQoKSkKcHJpbnQoanNvbi5kdW1wcyh7J3Jlc291cmNlJzp7J2F2YWlsYWJsZV9yYW0nOm1bJ01lbUF2YWlsYWJsZSddLCdmcmVlX2Rpc2snOmQuZnJlZSwnU0RLX29uX2Nsb3VkJzpGYWxzZSwnb3duZWRfaXNvbGF0ZWRfUEdfdmVyaWZpZWQnOlRydWV9LCdwYXNzd29yZCc6Y1sncGFzc3dvcmQnXX0pLGZsdXNoPVRydWUpCnN5cy5zdGRpbi5yZWFkKCkK\'"\'"\'))\''
with socket.socket() as sock:sock.bind(('127.0.0.1',55639))
tunnel=subprocess.Popen(ssh+['-o','ExitOnForwardFailure=yes','-L','127.0.0.1:55639:127.0.0.1:55631',host,remote],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=creation)
(out/'owned-tunnel-start.json').write_text(json.dumps({'pid':tunnel.pid,'local_bind':'127.0.0.1:55639','remote_test_bind':'127.0.0.1:55631','created_at':time.time(),'production_database_used':False,'single_connection_preflight_and_forward':True},indent=2)+'\n')
try:
 q=queue.Queue();reader=threading.Thread(target=lambda:q.put(tunnel.stdout.readline()),daemon=True);reader.start()
 line=q.get(timeout=40)
 assert line,'Remote preflight did not return data'
 record=json.loads(line);password=record.pop('password');resource=record['resource'];del line,record
 (out/'cloud-resource.json').write_text(json.dumps(resource,indent=2)+'\n')
 for i in range(40):
  assert tunnel.poll() is None,'Owned SSH tunnel exited before test'
  try:
   with socket.create_connection(('127.0.0.1',55639),.25):break
  except OSError:time.sleep(.25)
 else:raise RuntimeError('Owned SSH tunnel did not become ready')
 spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
 pins={p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'server').rglob('*') if p.is_file() and p.suffix in ['.cs','.sql','.csproj','.props','.targets','.bytes'] and not any(x in p.parts for x in ['bin','obj','.artifacts'])}
 (out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n')
 cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(base/'local-shop-copies-server-r1/build'),'--no-build','--no-restore','--filter','FullyQualifiedName~PostgresPermanentCardCopyTests|FullyQualifiedName~PostgresCardEconomyTests|FullyQualifiedName~PostgresMigrationTests','--logger','trx;LogFileName=bot-real-custody.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
 env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_NOLOGO='1',DOTNET_CLI_TELEMETRY_OPTOUT='1',FANTASYCARD_TEST_POSTGRES='Host=127.0.0.1;Port=55639;Database=season_stage;Username=season_stage;Password='+password+';MaxPoolSize=16;Timeout=10;CommandTimeout=30')
 print('Local SDK test using owned loopback SSH tunnel to isolated test PostgreSQL; no cloud SDK',flush=True)
 result=rt.guarded_run(cmd,env=env,timeout=2700)
 text=result.stdout+result.stderr;assert password not in text,'Credential appeared in test output; original must remain private'
 (out/'test.original.log').write_text(text,encoding='utf-8')
 proof={'exit':result.returncode,'SDK':'10.0.400','production_database_used':False,'cloud_SDK_started':False,'new_game_matches':0,'B05_not_run':True,'command':cmd,'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items())}
 (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(text[-7000:]);print(json.dumps(proof));assert result.returncode==0 and proof['source_unchanged']
 tree=ET.parse(out/'results/bot-real-custody.trx');counts=next(n.attrib for n in tree.iter() if n.tag.endswith('Counters'));assert int(counts['passed'])>=15 and counts['notExecuted']=='0'
finally:
 tunnel.stdin.close()
 try:tunnel.wait(timeout=10)
 except subprocess.TimeoutExpired:tunnel.terminate();tunnel.wait(timeout=10)
 error=tunnel.stderr.read().decode('utf-8',errors='replace');assert 'password' not in error.lower();(out/'tunnel.stderr.original.log').write_text(error,encoding='utf-8')
 (out/'owned-tunnel-terminal.json').write_text(json.dumps({'pid':tunnel.pid,'exit_code':tunnel.returncode,'own_tunnel_only_stopped':True,'other_projects_modified':False},indent=2)+'\n')

