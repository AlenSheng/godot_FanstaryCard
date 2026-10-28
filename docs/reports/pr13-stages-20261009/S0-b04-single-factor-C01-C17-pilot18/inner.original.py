import hashlib,json,shutil,subprocess
from pathlib import Path
E=Path('/evidence');phases=[]
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,cwd='/fixture',stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'pilot_only':True,'formal_acceptance':False,'MAIN_accepted':False}
try:
 assert subprocess.check_output(['dotnet','--version'],text=True).strip()=='10.0.400';project='/fixture/B04SingleFactor.csproj';phase('restore',['dotnet','restore',project,'--artifacts-path','/artifacts','--source','/packages','-p:NuGetAudit=false','--ignore-failed-sources'],90);phase('build',['dotnet','build',project,'--no-restore','--artifacts-path','/artifacts','-c','Release','-p:UseSharedCompilation=false','-maxcpucount:1'],180);rt=Path('/artifacts/bin/B04SingleFactor/release');shutil.copyfile('/runtime/FantasyCard.Domain.dll',rt/'FantasyCard.Domain.dll');meta=json.loads(Path('/meta.json').read_bytes());assert hashlib.sha256((rt/'FantasyCard.Domain.dll').read_bytes()).hexdigest()==next(r['sha256'] for r in meta['runtime_files'] if r['path']=='FantasyCard.Domain.dll');completed=[]
 for hero in ['Mage','Priest','Guardian']:
  for strategy in ['baseline_all_hand','basic','build']:
   name=hero+'-'+strategy;out=E/'native'/name;phase('native-'+name,['dotnet',str(rt/'B04SingleFactor.dll'),'--source-sha',meta['source_sha'],'--hero',hero,'--group','O1','--strategy',strategy,'--block','0','--offset','0','--samples','1','--output',str(out)],120);v=json.loads((out/'summary.original.json').read_bytes());assert v['passed'] and v['actual_encounters']==2 and v['actual_errors']==0;completed.append({'hero':hero,'strategy':strategy,'actual_encounters':2,'outcomes':v['outcomes'],'diagnostic_events':v['observer_events']});(E/'pilot-execution.original.json').write_bytes((json.dumps(completed,indent=2)+'\n').encode())
 result.update(ok=True,pilot_encounters=18,completed=completed,phases=phases)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
(E/'inner-result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({'ok':result['ok'],'pilot_encounters':result.get('pilot_encounters',0),'formal_acceptance':False}));raise SystemExit(0 if result['ok'] else 1)
