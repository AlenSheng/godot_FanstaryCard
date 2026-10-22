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


def main(argv=None):
    """Run one declared native suite and propagate its actual coverage gate.

    The command is an argument array, not a shell string. Use ``{trx}`` for
    the native runner's report path. Credentials remain in the environment;
    only the presence of explicitly named variables is recorded.
    """
    import argparse
    import hashlib
    import json
    import math
    import os
    import re
    import subprocess
    import time

    parser=argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--command-json',type=Path,required=True)
    parser.add_argument('--required-methods',type=Path,required=True)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--expected-source-sha',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=float,default=180)
    parser.add_argument('--observe-env',action='append',default=[])
    args=parser.parse_args(argv)
    command=json.loads(args.command_json.read_text(encoding='utf8'))
    required=json.loads(args.required_methods.read_text(encoding='utf8'))
    if (not isinstance(command,list) or not 1<=len(command)<=128 or
            any(not isinstance(v,str) or not v or len(v)>8192 for v in command) or
            not any('{trx}' in v for v in command)):
        raise ValueError('A bounded native argument array with a {trx} path is required')
    if (not isinstance(required,dict) or not required or
            any(not isinstance(k,str) or not k or type(v) is not int or not 1<=v<=1000000
                for k,v in required.items())):
        raise ValueError('Explicit nonempty required native method counts are required')
    if any(not re.fullmatch('[0-9a-f]{40}',v) for v in (args.source_sha,args.expected_source_sha)):
        raise ValueError('Exact source references are required')
    if not math.isfinite(args.timeout_seconds) or not 0<args.timeout_seconds<=3600:
        raise ValueError('Native execution deadline must be in (0, 3600] seconds')
    if any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',v) for v in args.observe_env):
        raise ValueError('Environment observation accepts names only')
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    trx=output/'native.original.trx'
    command=[v.replace('{trx}',str(trx)) for v in command]
    def save(name,value):
        (output/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
    save('native-command.original.json',command)
    metadata={'source_sha':args.source_sha,'expected_source_sha':args.expected_source_sha,
              'source_is_reference_not_clean_build_claim':True,
              'command_input_sha256':hashlib.sha256(args.command_json.read_bytes()).hexdigest(),
              'required_methods_input_sha256':hashlib.sha256(args.required_methods.read_bytes()).hexdigest(),
              'gate_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'environment_presence':{k:bool(os.environ.get(k)) for k in args.observe_env},
              'native_execution_deadline_seconds':args.timeout_seconds}
    native_exit=None;timed_out=False;launch_error=None;started=time.monotonic()
    with (output/'native.stdout.original.log').open('xb') as stdout,(output/'native.stderr.original.log').open('xb') as stderr:
        try:
            child=subprocess.Popen(command,stdout=stdout,stderr=stderr,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
            save('native-started.original.json',{'PID':child.pid,'started_unix_ms':int(time.time()*1000)})
            try:native_exit=child.wait(timeout=args.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out=True
                child.terminate()
                try:native_exit=child.wait(timeout=10)
                except subprocess.TimeoutExpired:child.kill();native_exit=child.wait(timeout=10)
        except OSError as error:launch_error=type(error).__name__
    save('native-terminal.original.json',{'actual_exit':native_exit,'execution_deadline_exhausted':timed_out,
                                        'launch_error':launch_error,'elapsed_seconds':time.monotonic()-started})
    if launch_error or timed_out or not trx.is_file():
        suite={'state':'Blocked','acceptance':False,'reason':'native_unavailable_or_incomplete',
               'launch_error':launch_error,'execution_deadline_exhausted':timed_out,'TRX_present':trx.is_file()}
    else:
        try:suite=assess_trx(trx,required)
        except (ET.ParseError,KeyError,TypeError,ValueError,OSError) as error:
            suite={'state':'Blocked','reason':'native_TRX_invalid','error_type':type(error).__name__,'acceptance':False}
    if native_exit not in (None,0) and not timed_out:
        suite=dict(suite,state='Failed',reason='native_exit_nonzero',native_exit=native_exit,acceptance=False)
    suite=dict(suite,source_sha=args.source_sha)
    gate=assess_gate({'native':suite},['native'],expected_source_sha=args.expected_source_sha)
    code=0 if gate['state']=='ReadyForMainReview' else 3 if gate['state']=='Blocked' else 1
    result={'state':gate['state'],'native_exit':native_exit,'suite':suite,'gate':gate,
            'pipeline_exit':code,'acceptance':False,'metadata':metadata,
            'TRX_sha256':hashlib.sha256(trx.read_bytes()).hexdigest() if trx.is_file() else None,
            'scope':'Observed native suite and its coverage gate only; no task/project acceptance'}
    save('report.json',result)
    print(json.dumps({'state':result['state'],'native_exit':native_exit,'pipeline_exit':code,'acceptance':False}))
    return code


if __name__=='__main__':raise SystemExit(main())
