import hashlib,json,os,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
E=Path('/evidence');meta=json.loads(Path('/meta.json').read_bytes());project='/work/server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj';phases=[]
def write(p,v):assert not p.exists();p.write_bytes((json.dumps(v,indent=2)+'\n').encode())
def phase(name,args,timeout):
 with (E/(name+'.original.log')).open('xb') as log:r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,cwd='/work/server')
 phases.append({'name':name,'exit_code':r.returncode});assert r.returncode==0,name+' failed'
result={'ok':False,'MAIN_accepted':False}
try:
 assert 'FANTASYCARD_TEST_POSTGRES' not in os.environ;required={'Concurrent_deck_writes_allow_one_version_winner_and_replay_its_response':1,'Preparation_create_replay_conflict_and_cancel_release_are_atomic':1};sdk=subprocess.check_output(['dotnet','--version'],cwd='/work/server',text=True).strip();assert sdk==json.loads(Path('/work/server/global.json').read_bytes())['sdk']['version'];write(E/'sdk.original.json',{'actual_sdk':sdk,'test_database_environment_key_present':False,'required_method_rows':required})
 phase('restore',['dotnet','restore',project,'--source','/packages','--artifacts-path','/artifacts','-p:RestorePackagesPath=/packages','-p:UseSharedCompilation=false','-maxcpucount:1'],480)
 phase('build',['dotnet','build',project,'-c','Release','--no-restore','--artifacts-path','/artifacts','-p:UseSharedCompilation=false','-maxcpucount:1'],600)
 filter='|'.join('FullyQualifiedName~'+name for name in required);phase('native',['dotnet','test',project,'-c','Release','--no-build','--no-restore','--artifacts-path','/artifacts','--filter',filter,'--results-directory','/evidence/results','--logger','trx;LogFileName=actual-missing-DB.trx'],180)
 trx=E/'results/actual-missing-DB.trx';tree=ET.parse(trx);counts={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()};rows=tree.findall('.//{*}UnitTestResult');assert counts['total']==2 and counts['notExecuted']==2 and counts['executed']==counts['passed']==counts['failed']==0;assert len(rows)==2 and all(r.attrib['outcome']=='NotExecuted' for r in rows)
 sys.path.insert(0,'/control');from pr13_suite_coverage import assess_trx
 actual=assess_trx(trx,required);assert actual['state']=='Blocked' and len(actual['skipped_cases'])==2 and actual['missing_assertion_rows']==required and actual['acceptance'] is False
 record={'case_id':'LOAD-11.3-T02','executed':True,'status':'Passed','source_sha':meta['production_source_sha'],'profiles_executed':['AUDIT'],'actual':{'actual_dotnet_test_exit_code':0,'actual_test_database_environment_key_present':False,'actual_native_counters':counts,'actual_native_skipped_case_names':actual['skipped_cases'],'actual_current_caller_verdict':actual,'original_TRX_sha256':hashlib.sha256(trx.read_bytes()).hexdigest()},'scope':'Actual full current-equivalent C# test assembly on Tencent with no PostgreSQL connection string; the test checks skip/Blocked classification. It does not execute or accept either skipped database case.'};(E/'cases.original.jsonl').write_bytes((json.dumps(record)+'\n').encode());result.update(ok=True,native_clean=True,actual_db_tests_executed=0,actual_db_tests_skipped=2,actual_missing_DB_caller_state='Blocked',original_TRX_sha256=record['actual']['original_TRX_sha256'],phases=phases,production_source_sha=meta['production_source_sha'])
except Exception as error:result.update(error=type(error).__name__,detail=str(error),phases=phases,failed_originals_retained=True)
write(E/'inner-result.original.json',result);raise SystemExit(0 if result['ok'] else 1)
