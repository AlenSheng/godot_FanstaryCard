import hashlib,json,subprocess
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());project='/fixture/B08CoreRoomWitness.csproj';phases=[]
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,cwd='/fixture',stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version']
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 phase('native',['dotnet','run','--project',project,'-c','Release','--no-build','--no-restore','--artifacts-path','/artifacts','--',meta['implementation_source_sha'],'/evidence/native'],480)
 p=E/'native/summary.original.json';v=json.loads(p.read_bytes());assert v['ok'] and v['witnesses']==108 and v['heroes']==3 and v['weapon_levels']==6 and v['equipment_arms']==2 and v['case_count']==3 and v['actual_room_preview_play_equal'] and not v['candidate_activation'];result.update(ok=True,actual_sdk=sdk,native_summary=v,phases=phases,development_witness_only=True,formal_EXPERIMENT_accepted=False)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
(E/'inner-result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());raise SystemExit(0 if result['ok'] else 1)
