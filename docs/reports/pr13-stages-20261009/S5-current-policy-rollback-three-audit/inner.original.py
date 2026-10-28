import hashlib,json,os,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
E=Path('/evidence');project='/work/server/tests/FantasyCard.Domain.Tests/FantasyCard.Domain.Tests.csproj';required=['New_source_policy_does_not_change_a_live_default_room_or_its_saved_instances','Rolling_source_back_changes_new_rooms_and_preserves_existing_candidate_room_instances'];phases=[]
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,cwd='/work/server',timeout=timeout)
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 assert 'FANTASYCARD_TEST_POSTGRES' not in os.environ;sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version'];write(E/'sdk.original.json',{'actual_sdk':sdk,'required_methods':required,'test_database_environment_present':False})
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 phase('native',['dotnet','test',project,'-c','Release','--no-build','--no-restore','--artifacts-path','/artifacts','--filter','|'.join('FullyQualifiedName~'+m for m in required),'--results-directory','/evidence/results','--logger','trx;LogFileName=policy-rollback.original.trx'],180)
 trx=E/'results/policy-rollback.original.trx';tree=ET.parse(trx);counts={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()};definitions={r.attrib['id']:r.find('{*}TestMethod').attrib['name'] for r in tree.findall('.//{*}UnitTest')};rows=tree.findall('.//{*}UnitTestResult');assert counts['total']==counts['executed']==counts['passed']==2 and counts['failed']==counts['notExecuted']==0 and len(rows)==2;assert {definitions[r.attrib['testId']] for r in rows}==set(required) and all(r.attrib['outcome']=='Passed' for r in rows);result.update(ok=True,counts=counts,passed_methods=required,actual_native_rows=2,phases=phases,original_TRX_sha256=hashlib.sha256(trx.read_bytes()).hexdigest())
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
write(E/'inner-result.original.json',result);raise SystemExit(0 if result['ok'] else 1)
