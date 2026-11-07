from pathlib import Path
import base64,hashlib,importlib.util,json,os,shlex,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-deployment-readiness-r2';assert not out.exists();out.mkdir()
source=(b/'f03-readiness-r1/cloud-readonly-source.original.py').read_text('utf-8')
needle="row['image_labels']={k:lab[k] for k in ['org.opencontainers.image.revision','fantasycard.config.sha256','fantasycard.config.version'] if k in lab}"
extra=needle+"""
  row['runtime_image']={'size':image.get('Size'),'architecture':image.get('Architecture'),'os':image.get('Os'),'repo_tags':image.get('RepoTags'),'layers':image.get('RootFS',{}).get('Layers'),'user':image.get('Config',{}).get('User'),'working_dir':image.get('Config',{}).get('WorkingDir'),'entrypoint':image.get('Config',{}).get('Entrypoint'),'cmd':image.get('Config',{}).get('Cmd')}
  row['public_host_settings']={k:d.get('HostConfig',{}).get(k) for k in ['ReadonlyRootfs','Memory','NanoCpus','CapDrop','SecurityOpt','LogConfig']}
  row['mounts_without_secret_contents']=[{k:m.get(k) for k in ['Type','Destination','RW']} for m in d.get('Mounts',[])]
  row['app_top_level_file_inventory']=command(['docker','exec',cid,'find','/app','-maxdepth','1','-type','f','-printf','%f %s\\n']).splitlines()
  row['app_project_DLL_hashes']=command(['docker','exec',cid,'sha256sum','/app/FantasyCard.Contracts.dll','/app/FantasyCard.Domain.dll','/app/FantasyCard.Server.dll']).splitlines()"""
assert needle in source;source=source.replace(needle,extra)
(out/'cloud-readonly-source.original.py').write_text(source,encoding='utf-8')
remote='sudo -n python3 -B -c '+shlex.quote('import base64;exec(base64.b64decode('+repr(base64.b64encode(source.encode()).decode())+'))')
command=['ssh','-n','-i',str(Path.home()/'.ssh/gpt-deploy-release.pem'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182',remote]
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=guard.guarded_run(command,env=dict(os.environ),timeout=60,wait_seconds=30)
(out/'stdout.original.log').write_text(r.stdout,encoding='utf-8');(out/'stderr.original.log').write_text(r.stderr,encoding='utf-8');(out/'terminal.original.json').write_text(json.dumps(dict(exit=r.returncode))+'\n');assert r.returncode==0,r.stderr[-1500:]
proof=json.loads(r.stdout);assert not proof['app_or_DB_writes'] and not proof['SDK_started'];(out/'readiness.original.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(resources=proof['resources'],protection_ok=proof['resource_protection_ok'],checkout=proof.get('checkout_head'),markers=proof.get('markers'),containers=proof['containers'],health=proof['health'])))
