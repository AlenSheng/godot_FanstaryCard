from pathlib import Path
import subprocess,os,sys,json,hashlib,datetime,importlib.util,shutil,types
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');public=b/'f03-protected-build-r1';private=Path(r'G:\PR13Evidence\private\season-balance-20261102-f03-protected-r1')
assert not public.exists() and not private.exists();public.mkdir();private.mkdir(parents=True)
flags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS
sid=subprocess.check_output(['powershell','-NoProfile','-Command','[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],creationflags=flags).decode().strip()
r=subprocess.run(['icacls',str(private),'/inheritance:r','/grant:r','*'+sid+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],capture_output=True,creationflags=flags);(private/'ACL.private.log').write_bytes(r.stdout+r.stderr);assert r.returncode==0
(private/'ownership.original.json').write_text(json.dumps({'task':'season-balance-20261102','scope':'protected candidate build and private mapping, no database copies','do_not_publish_mapping_or_unprotected_assemblies':True})+'\n')
spec=importlib.util.spec_from_file_location('runtime',repo/'client/tests/fixture_runtime.py');runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
sys.path.insert(0,str(repo/'tools'));spec=importlib.util.spec_from_file_location('exporter',repo/'tools/export_protected_server.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
tool=Path(r'G:\Program Files\GodotFiles\godot_FanstaryCard\tools\engine-local\protected\dotnet-tools\obfuscar.console.exe');assert tool.is_file()
head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();assert head=='daeb8701ba03abeb7b40abcf96fe019568eb6729'
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','tools/export_protected_server.py','tools/release_protection.py']).decode().split('\0')
pin={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in names if n and (repo/n).is_file()};(public/'source-pin.json').write_text(json.dumps(pin,indent=2)+'\n')
def command(cmd,name,timeout=240):
 print(json.dumps({'stage':name,'started':True}),flush=True)
 env=dict(os.environ,DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',DOTNET_CLI_UI_LANGUAGE='en',FANTASYCARD_TEST_POSTGRES='')
 result=runtime.guarded_run([str(c) for c in cmd],env=env,timeout=timeout,wait_seconds=30)
 log=private/(name+'.private.log');log.write_text(result.stdout+result.stderr,encoding='utf-8')
 (public/(name+'.terminal.json')).write_text(json.dumps({'exit':result.returncode,'private_log_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'source_unchanged':all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items()),'new_gameplay_cases':0},indent=2)+'\n')
 assert result.returncode==0,name
 return result.stdout
version=command([tool,'--version'],'tool-version',30);assert exporter.TOOL_VERSION in version
build=private/'build';publish=private/'publish';protected=private/'obfuscated'
command(['dotnet','build',repo/'server/FantasyCard.Server.slnx','-c','Release','--artifacts-path',build,'-m:1','-p:UseSharedCompilation=false','--verbosity','minimal'],'solution-release-build',300)
command(['dotnet','publish',repo/'server/src/FantasyCard.Server/FantasyCard.Server.csproj','-c','Release','--no-restore','--artifacts-path',build,'-m:1','-p:DebugType=None','-p:DebugSymbols=false','-p:UseAppHost=false','-p:UseSharedCompilation=false','-o',publish,'--verbosity','minimal'],'publish',180)
test_dirs=[build/'bin'/suite/'release' for suite in exporter.SUITES]
# Reuse the repository's exact protection configuration builder with a guarded runtime query.
exporter.subprocess=types.SimpleNamespace(check_output=lambda cmd,**kw:command(cmd,'runtime-framework-discovery',30))
config=private/'obfuscar.xml';exporter.configuration(publish,protected,private/'mapping.xml',test_dirs).write(config,encoding='utf-8',xml_declaration=True)
(public/'protection-config.original.xml').write_bytes(config.read_bytes())
command([tool,config],'obfuscation',240)
destination=repo/'builds/server-protected/f03-daeb8701-r1';assert not destination.exists()
assert subprocess.run(['git','check-ignore','--quiet',str(destination/'CANDIDATE-NOT-YET-VALIDATED.txt')]).returncode==0
destination.mkdir(parents=True);assemblies={}
for assembly in exporter.ASSEMBLIES:
 name=assembly+'.dll';a=publish/name;z=protected/name;assert z.is_file() and hashlib.sha256(a.read_bytes()).hexdigest()!=hashlib.sha256(z.read_bytes()).hexdigest()
 assemblies[name]={'original_sha256':hashlib.sha256(a.read_bytes()).hexdigest(),'protected_sha256':hashlib.sha256(z.read_bytes()).hexdigest()}
excluded=[]
for source in publish.rglob('*'):
 if not source.is_file():continue
 relative=source.relative_to(publish)
 if source.suffix.lower() in ['.cs','.pdb','.key','.dpapi','.xml'] or source.name=='appsettings.Development.json':excluded.append(relative.as_posix());continue
 target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);copy=protected/source.name if source.parent==publish and source.name in assemblies else source;shutil.copyfile(copy,target)
protected_suites=[]
for test_dir in test_dirs:
 suite=test_dir.parent.name;target=private/'protected-tests/bin'/suite/'release';shutil.copytree(test_dir,target)
 shutil.copyfile(protected/(suite+'.dll'),target/(suite+'.dll'))
 for name in assemblies:
  if (target/name).is_file():shutil.copyfile(destination/name,target/name)
 protected_suites.append(str(target/(suite+'.dll')))
(destination/'CANDIDATE-NOT-YET-VALIDATED.txt').write_text('Current fixed-source protected candidate only. D03/F01 gates, packaged runtime validation and final release approval remain incomplete. Do not deploy.\n')
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
package_files={p.relative_to(destination).as_posix():{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in destination.rglob('*') if p.is_file()}
report={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exported':True,'tested':False,'source_commit':head,'source_unchanged':True,'output':str(destination),'obfuscator':'Obfuscar '+exporter.TOOL_VERSION,'tool_executable_sha256':hashlib.sha256(tool.read_bytes()).hexdigest(),'assemblies':assemblies,'test_assemblies':protected_suites,'private_mapping':str(private/'mapping.xml'),'private_report':str(private/'report.json'),'excluded_from_package':excluded,'package_files':package_files,'private_ACL_applied':True,'new_gameplay_cases':0,'cloud_SDK_started':False,'deployment_performed':False,'D03_F01_gates_passed':False,'F03_complete':False}
(private/'report.json').write_text(json.dumps(report,indent=2)+'\n');(public/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'protected_candidate_built':True,'files':len(package_files),'tested':False,'deployed':False,'assemblies':assemblies}),flush=True)
assert not subprocess.check_output(['git','status','--porcelain'])
