"""Compile unchanged current release in RAM with existing release protection rules."""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
C=Path('/controls');O=Path('/publish-output');W=Path('/work');P=json.loads((C/'plan.original.json').read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def phase(name,args,env=None,timeout=600):
 with (O/(name+'.stdout.original.log')).open('xb') as out,(O/(name+'.stderr.original.log')).open('xb') as err:
  r=subprocess.run(args,cwd=W/'source/server',env=env,stdout=out,stderr=err,timeout=timeout)
 phases.append({'name':name,'arguments':args,'exit_code':r.returncode});assert r.returncode==0,name
 return r.returncode
for row in P['source_files']:
 p=Path('/source')/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
assert sha(C/'obfuscar.xml')==P['obfuscar_xml_sha256']
phases=[];shutil.copytree('/source',W/'source')
env=dict(os.environ,NUGET_PACKAGES='/packages',DOTNET_CLI_HOME='/work/dotnet-home',HOME='/work/home')
phase('actual-current-restore',['dotnet','restore','src/FantasyCard.Server/FantasyCard.Server.csproj','--ignore-failed-sources','--artifacts-path','/work/artifacts'],env)
phase('actual-current-publish',['dotnet','publish','src/FantasyCard.Server/FantasyCard.Server.csproj','-c','Release','-o','/input','--no-restore','--artifacts-path','/work/artifacts','-m:1','-p:UseSharedCompilation=false','-p:DebugType=None','-p:DebugSymbols=false','-p:UseAppHost=false'],env)
private=O/'private';private.mkdir();unprotected=private/'unprotected';unprotected.mkdir()
assemblies=['FantasyCard.Contracts.dll','FantasyCard.Domain.dll','FantasyCard.Server.dll']
unprotected_hashes={}
for name in assemblies:shutil.copyfile(Path('/input')/name,unprotected/name);unprotected_hashes[name]=sha(unprotected/name)
toolenv=dict(env,NUGET_PACKAGES='/work/tool-packages')
phase('actual-pinned-protection-tool-install',['dotnet','tool','install','Obfuscar.GlobalTool','--version','2.2.50','--tool-path','/work/tools'],toolenv)
for folder in ['/usr/share/dotnet/shared/Microsoft.NETCore.App','/usr/share/dotnet/shared/Microsoft.AspNetCore.App']:
 roots=list(Path(folder).glob('10.*'));assert len(roots)==1
 for p in roots[0].glob('*.dll'):shutil.copyfile(p,Path('/framework')/p.name)
phase('actual-current-obfuscar',['/work/tools/obfuscar.console','/controls/obfuscar.xml'],toolenv)
assert Path('/private/mapping.xml').stat().st_size>0
shutil.copyfile('/private/mapping.xml',private/'protection-mapping.original.xml')
protected_hashes={}
for name in assemblies:
 p=Path('/output')/name;assert p.stat().st_size>0;protected_hashes[name]=sha(p);assert protected_hashes[name]!=unprotected_hashes[name]
 shutil.copyfile(p,Path('/input')/name)
for p in Path('/input').glob('*'):
 if p.suffix in ['.pdb','.xml'] or p.name=='appsettings.Development.json':p.unlink()
for p in Path('/input').rglob('*'):
 if p.is_file():assert p.suffix not in ['.pdb','.cs','.key','.dpapi']
runtime=O/'runtime';shutil.copytree('/input',runtime)
for p in runtime.rglob('*'):
 if p.is_dir():p.chmod(0o755)
 else:p.chmod(0o644)
rows=[{'path':p.relative_to(runtime).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(runtime.rglob('*')) if p.is_file()]
result={'ok':True,'source_sha':P['source_sha'],'compiled_unchanged_current_source':True,'protected_with_original_obfuscar_XML':True,
 'unprotected_assembly_SHA256':unprotected_hashes,'protected_assembly_SHA256':protected_hashes,
 'private_mapping_bytes':(private/'protection-mapping.original.xml').stat().st_size,'private_mapping_sha256':sha(private/'protection-mapping.original.xml'),
 'runtime_files':rows,'actual_native_phases':phases,'production_changed':False,'MAIN_accepted':False}
(O/'actual-protected-current-publish.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in result.items() if k not in ['runtime_files','actual_native_phases']}))
