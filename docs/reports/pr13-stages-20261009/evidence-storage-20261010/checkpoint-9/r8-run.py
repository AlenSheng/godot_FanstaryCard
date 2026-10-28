import hashlib,json,os,subprocess,time
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');S=B/'source-cleanup-ticket-authority-r1';E=B/'evidence/cleanup-ticket-authority-r8'
metadata=json.loads((E/'preregistration.json').read_text());results=[]
environment=dict(os.environ,FANTASYCARD_LOAD_RUN_ID='pr13-offline-cleanup-ticket-authority-r8',FANTASYCARD_SERVER_URL='http://127.0.0.1:9')
engine=str(B/'cache/cleanup-authority-godot/Godot_v4.7.2-stable_linux.x86_64')
commands=[('parse',[engine,'--headless','--audio-driver','Dummy','--path',str(S/'client'),'--script','res://tests/run_gameplay_load_parse.gd']),
          ('authority',[engine,'--headless','--audio-driver','Dummy','--path',str(S/'client'),'--script','res://tests/test_cleanup_ticket_authority.gd']),
          ('coordinator',['python3','-m','unittest','-v','tools.tests.test_gameplay_load_sampling_contract','tools.tests.test_gameplay_load_finalization','tools.tests.test_pr13_resource_policy'])]
for label,command in commands:
    started=time.time()
    try:
        process=subprocess.run(command,cwd=S,capture_output=True,env=environment,timeout=120)
        raw=process.stdout+process.stderr;code=process.returncode
    except subprocess.TimeoutExpired as error:
        raw=(error.stdout or b'')+(error.stderr or b'')+bytes([10])+b'Explicit contract-test deadline exceeded'+bytes([10]);code=124
    (E/(label+'.private.log')).write_bytes(raw)
    item={'label':label,'exit_code':code,'elapsed_seconds':time.time()-started,'log_sha256':hashlib.sha256(raw).hexdigest()}
    if label=='authority':
        lines=[line.split('CLEANUP_TICKET_AUTHORITY ',1)[1] for line in raw.decode(errors='replace').splitlines() if line.startswith('CLEANUP_TICKET_AUTHORITY ')]
        if lines:
            evidence=json.loads(lines[-1]);(E/'checks.json').write_text(json.dumps(evidence,indent=2)+chr(10));item['checks']=len(evidence['checks']);item['passed_checks']=sum(bool(row['passed']) for row in evidence['checks']);item['ok']=evidence['ok']
    results.append(item)
    if code:break
proof={'source_sha':metadata['source_sha'],'execution_host':'Tencent cloud','scope':metadata['scope'],'git_dirty':True,
       'ok':len(results)==3 and all(item['exit_code']==0 for item in results) and results[1].get('ok') is True,
       'results':results,'whole_scope_accepted':False,'production_code_modified':False,'metadata':metadata}
(E/'result.json').write_text(json.dumps(proof,indent=2)+chr(10))
