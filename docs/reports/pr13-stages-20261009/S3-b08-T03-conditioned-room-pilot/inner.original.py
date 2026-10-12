import hashlib,json,subprocess
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());project='/fixture/T03ConditionedRoomBoundary.csproj';phases=[]
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,cwd='/fixture',stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version']
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 phase('native',['dotnet','run','--project',project,'-c','Release','--no-build','--no-restore','--artifacts-path','/artifacts','--',meta['implementation_source_sha'],'/evidence/pilot','3','0'],480)
 p=E/'pilot/summary.original.json';v=json.loads(p.read_bytes());assert v['passed'] and v['witnesses']==v['expected_witnesses']==2880 and v['samples']==3 and v['block']==0 and v['strata']==120 and not v['candidate_activation'];result.update(ok=True,actual_sdk=sdk,native_summary=v,phases=phases,pilot_only=True,formal_EXPERIMENT_accepted=False)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
(E/'inner-result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());raise SystemExit(0 if result['ok'] else 1)
