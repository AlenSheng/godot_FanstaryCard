import hashlib,json,shutil,subprocess
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());project='/fixture/B12EffectivePolicy.csproj';phases=[]
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,cwd='/fixture',stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 assert subprocess.check_output(['dotnet','--version'],text=True).strip()=='10.0.400'
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:NuGetAudit=false','--ignore-failed-sources'],90)
 phase('build',['dotnet','build',project,'--no-restore','--artifacts-path','/artifacts','-c','Release','-p:UseSharedCompilation=false','-maxcpucount:1'],180)
 out=Path('/artifacts/bin/B12EffectivePolicy/release');assert (out/'B12EffectivePolicy.dll').is_file()
 for row in meta['runtime_files']:
  p=Path('/runtime')/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];target=out/row['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 phase('native',['dotnet',str(out/'B12EffectivePolicy.dll')],150)
 v=json.loads((E/'native/summary.original.json').read_bytes());assert v['passed'] and v['executed']==72 and v['ownSchemaRemoved'];result.update(ok=True,executed=72,native=v,phases=phases)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases)
(E/'inner-result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({'ok':result['ok'],'executed':result.get('executed',0)}));raise SystemExit(0 if result['ok'] else 1)
