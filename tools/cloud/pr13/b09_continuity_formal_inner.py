"""Cloud SDK build and typed native natural-route matrix. No external restore."""
import hashlib,json,os,subprocess,time
from pathlib import Path
S=Path('/work');E=Path('/evidence');R=Path('/runtime')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs():return {str(p):digest(p) for root in (S,R) for p in sorted(root.rglob('*')) if p.is_file()}
before=inputs();source=os.environ['PR13_CONTINUITY_SOURCE_SHA'];mode=os.environ['PR13_CONTINUITY_MODE'];assert mode in ('development-smoke','formal')
result={'ok':False,'source_sha':source,'mode':mode,'whole_task_accepted':False,'formal_EXPERIMENT_accepted':False}
def run(name,args,deadline):
 start=time.monotonic()
 with (E/(name+'.log')).open('xb') as f:r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=deadline)
 return {'name':name,'exit_code':r.returncode,'wall_seconds':time.monotonic()-start}
try:
 result['build']=run('build',['dotnet','build','/work/ContinuityFormal.csproj','-c','Release','--artifacts-path','/evidence/artifacts','--configfile','/work/NuGet.Config','-p:Pr13RuntimeDirectory=/runtime','-p:RestorePackagesPath=/evidence/packages','-p:UseSharedCompilation=false','--disable-build-servers','-v','minimal'],300)
 if result['build']['exit_code']==0:
  executable=['dotnet','/evidence/artifacts/bin/ContinuityFormal/release/ContinuityFormal.dll']
  result['help']=run('help',executable+['--help'],30);assert result['help']['exit_code']==0
  cases=[(h,487001,3) for h in ('Mage','Priest','Guardian')] if mode=='development-smoke' else [(os.environ['PR13_CONTINUITY_HERO'],int(os.environ['PR13_CONTINUITY_SEED_START']),1000)]
  runs=[]
  for hero,start,count in cases:
   args=executable+['--output',str(E/'native'/hero),'--source',source,'--hero',hero,'--seed-start',str(start),'--seeds',str(count)]
   if mode=='development-smoke':args+=['--development-smoke']
   r=run('natural-'+hero,args,300 if mode=='development-smoke' else 1500);runs.append(r)
   if r['exit_code']!=0:break
   native=json.loads((E/'native'/hero/'result.json').read_text());assert native['ok'] and native['routes']==count*4 and native['typedRouterIntents'] and native['developmentSmoke']==(mode=='development-smoke')
  result.update(runs=runs,ok=len(runs)==len(cases) and all(r['exit_code']==0 for r in runs))
except Exception as error:result.update(error=type(error).__name__,detail=str(error))
finally:
 result['source_and_runtime_unchanged']=before==inputs();result['ok']=result['ok'] and result['source_and_runtime_unchanged'];(E/'inner-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result));raise SystemExit(0 if result['ok'] else 1)
