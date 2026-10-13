import hashlib,json,shutil,subprocess,time
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());phases=[]
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,cwd='/fixture',stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 assert subprocess.check_output(['dotnet','--version'],text=True).strip()=='10.0.400'
 project='/fixture/FantasyCard.GuardianProbe.csproj';phase('restore',['dotnet','restore',project,'--artifacts-path','/artifacts','--source','/packages','-p:NuGetAudit=false','--ignore-failed-sources'],90);phase('build',['dotnet','build',project,'--no-restore','--artifacts-path','/artifacts','-c','Release','-p:UseSharedCompilation=false','-maxcpucount:1'],180);rt=Path('/artifacts/bin/FantasyCard.GuardianProbe/release');p=Path('/runtime/FantasyCard.Domain.dll');shutil.copyfile(p,rt/p.name);assert hashlib.sha256((rt/p.name).read_bytes()).hexdigest()==meta['Domain_DLL_SHA256'];(E/'native').mkdir();full_start=time.monotonic();block=None;execution=[]
 for j in meta['jobs']:
  if block!=j['logical_block_start']:block=j['logical_block_start'];block_start=time.monotonic()
  remain=min(1260-(time.monotonic()-full_start),420-(time.monotonic()-block_start));assert remain>0
  phase('native-'+str(j['seed_start']),['dotnet',str(rt/'FantasyCard.GuardianProbe.dll'),'--output','/evidence/native/'+str(j['seed_start']),'--source-sha',meta['implementation_source_sha'],'--seed-start',str(j['seed_start']),'--samples','200'],remain)
  summary=json.loads((E/'native'/str(j['seed_start'])/'summary.native.json').read_bytes());assert summary['Passed'] and summary['RowCount']==2400 and summary['ErrorCount']==0;assert time.monotonic()-full_start<=1260 and time.monotonic()-block_start<=420;execution.append({**j,'native_rows':2400,'native_exit_code':0,'logical_elapsed_seconds':time.monotonic()-block_start,'full_native_elapsed_seconds':time.monotonic()-full_start});(E/'execution.original.json').write_bytes((json.dumps(execution,indent=2)+'\n').encode())
 result['full_native_seconds']=time.monotonic()-full_start;phase('independent-analysis',['python3','/fixture/tools/analysis.py'],900);report=json.loads((E/'analysis/report.original.json').read_bytes());assert report['ok'] and report['native_sequence_rows']==36000;result.update(ok=True,native_rows=36000,native_parts=15,report=report,phases=phases)
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
(E/'inner-result.original.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({'ok':result['ok'],'native_rows':result.get('native_rows',0)}));raise SystemExit(0 if result['ok'] else 1)
