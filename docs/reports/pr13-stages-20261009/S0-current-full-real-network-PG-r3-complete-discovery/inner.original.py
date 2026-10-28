import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

W=Path('/work');O=Path('/output');R=Path('/runtime')
plan=json.loads((W/'plan.original.json').read_bytes())
selector=plan['selector']
assembly=R/'FantasyCard.Server.Tests.dll'
assert hashlib.sha256(assembly.read_bytes()).hexdigest()==plan['test_assembly_sha256']
phases=[]
def phase(name,args,timeout):
    with (O/(name+'.stdout.original.log')).open('xb') as stdout,(O/(name+'.stderr.original.log')).open('xb') as stderr:
        result=subprocess.run(args,cwd=str(R),stdout=stdout,stderr=stderr,timeout=timeout)
    phases.append({'name':name,'arguments':args,'exit_code':result.returncode})
    return result.returncode
listing=phase('actual-discovery',['dotnet','test',str(assembly),'--list-tests','--filter',selector],120)
assert listing==0
raw=(O/'actual-discovery.stdout.original.log').read_text()
names=[line.strip() for line in raw.splitlines() if line.strip().startswith('FantasyCard.Server.Tests.EndToEnd.RealNetwork')]
assert names and len(names)==len(set(names))
assert set(names)==set(plan['required_source_method_names']) and len(names)==10
frozen={'ok':True,'selector':selector,'actual_discovered_names':names,'expected_native_rows':len(names),
    'actual_test_assembly_sha256':plan['test_assembly_sha256'],
    'discovered_before_execution':True,'post_execution_target_changes_allowed':False,'MAIN_accepted':False}
(O/'actual-discovered-required-tests.original.json').write_bytes((json.dumps(frozen,indent=2)+'\n').encode())
code=phase('actual-full-real-network',['dotnet','test',str(assembly),'--filter',selector,
    '--results-directory','/output/results','--logger','trx;LogFileName=all-real-network.original.trx'],1800)
tree=ET.parse(O/'results/all-real-network.original.trx')
counts={k:int(v) for k,v in tree.find('.//{*}Counters').attrib.items()}
results=tree.findall('.//{*}UnitTestResult')
actual_names=[row.attrib['testName'] for row in results]
missing=sorted(set(names)-set(actual_names));unexpected=sorted(set(actual_names)-set(names))
ok=code==0 and not missing and not unexpected and counts['total']==counts['executed']==counts['passed']==len(names) and counts['failed']==counts['notExecuted']==0
report={'ok':ok,'actual_native_job_exit_code':code,'actual_native_rows':counts.get('executed'),
    'actual_required_discovered_rows':len(names),'native_counters':counts,'missing_actual_names':missing,
    'unexpected_actual_names':unexpected,'all_selected_rows_unskipped_passed':ok,'phases':phases,
    'scope':'All ten current RealNetworkEndToEndTests native methods against isolated PostgreSQL and actual Program HTTP/WebSocket loopback processes; no Godot client, WAN, full solution, statistical or canonical profile acceptance claim',
    'MAIN_accepted':False}
(O/'full-real-network-result.original.json').write_bytes((json.dumps(report,indent=2)+'\n').encode())
print(json.dumps({k:v for k,v in report.items() if k!='phases'}))
assert ok,'Full discovered suite did not pass; original output retained'
