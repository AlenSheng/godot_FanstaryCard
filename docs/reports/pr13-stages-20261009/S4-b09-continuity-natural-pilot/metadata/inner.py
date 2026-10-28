"""Cloud-only SDK compilation and natural route pilot; no external Nuget restore."""
import hashlib,json,os,subprocess,time
from pathlib import Path
S=Path('/work');E=Path('/evidence');R=Path('/runtime')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():return {str(p):digest(p) for root in (S,R) for p in sorted(root.rglob('*')) if p.is_file()}
before=inputs();source=os.environ['PR13_CONTINUITY_SOURCE_SHA'];result={'ok':False,'source_sha':source,'whole_task_accepted':False,'formal_EXPERIMENT_accepted':False}
def run(name,args,deadline):
 start=time.monotonic()
 with (E/(name+'.log')).open('xb') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=deadline)
 return {'name':name,'exit_code':r.returncode,'wall_seconds':time.monotonic()-start}
try:
 result['build']=run('build',['dotnet','build','/work/Continuity.csproj','-c','Release','--artifacts-path','/evidence/artifacts','--configfile','/work/NuGet.Config','-p:Pr13RuntimeDirectory=/runtime','-p:RestorePackagesPath=/evidence/packages','-p:UseSharedCompilation=false','--disable-build-servers','-v','minimal'],300)
 if result['build']['exit_code']==0:
  result['pilot']=run('natural-route',['dotnet','/evidence/artifacts/bin/Continuity/release/Continuity.dll','--output','/evidence/native',source],1500)
  if result['pilot']['exit_code']==0:
   native=json.loads((E/'native/result.json').read_text());assert native['ok'] and native['routes']==36 and native['productionChanged'] is False and native['stableBenefitEstablished'] is False
   result.update(ok=True,native=native)
except Exception as error:result.update(error=type(error).__name__,detail=str(error))
finally:
 result['source_and_runtime_unchanged']=before==inputs()
 result['ok']=result['ok'] and result['source_and_runtime_unchanged']
 (E/'inner-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
