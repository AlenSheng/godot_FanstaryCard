"""Read native suite identities; zero exit alone never establishes matrix coverage."""
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

def assess_trx(path,required_methods):
    tree=ET.parse(Path(path));counters=tree.find('.//{*}Counters')
    if counters is None:return {'state':'Blocked','reason':'native_counters_missing','acceptance':False}
    counts={k:int(v) for k,v in counters.attrib.items()}
    methods={n.attrib['id']:n.find('{*}TestMethod').attrib['name'] for n in tree.findall('.//{*}UnitTest')}
    results=tree.findall('.//{*}UnitTestResult');passed=Counter(methods[r.attrib['testId']] for r in results if r.attrib.get('outcome')=='Passed')
    missing={name:n-passed[name] for name,n in required_methods.items() if passed[name]<n}
    failed=[r.attrib['testName'] for r in results if r.attrib.get('outcome') not in ('Passed','NotExecuted')]
    skipped=[r.attrib['testName'] for r in results if r.attrib.get('outcome')=='NotExecuted']
    state='Failed' if failed or counts.get('failed',0) else 'Blocked' if missing or skipped or counts.get('notExecuted',0) or counts.get('executed')!=counts.get('total') else 'CoveredForMainReview'
    return {'state':state,'missing_assertion_rows':missing,'failed_cases':failed,'skipped_cases':skipped,'counters':counts,'acceptance':False}

def assess_gate(suites,required_names,*,expected_source_sha,baseline_compile_exit=0):
    missing=[name for name in required_names if name not in suites]
    stale=[name for name in required_names if name in suites and suites[name].get('source_sha')!=expected_source_sha]
    failed=[name for name in required_names if name in suites and suites[name].get('state')=='Failed']
    blocked=[name for name in required_names if name in suites and suites[name].get('state')!='CoveredForMainReview']
    state='Failed' if failed else 'Blocked' if baseline_compile_exit!=0 or missing or stale or blocked else 'ReadyForMainReview'
    return {'state':state,'missing_suites':missing,'stale_source_suites':stale,'failed_suites':failed,'incomplete_suites':blocked,'baseline_compile_exit':baseline_compile_exit,'acceptance':False}
