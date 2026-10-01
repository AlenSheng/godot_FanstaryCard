"""Independent unrelated-to-coordinator sentinel; unchanged 35s hang mode."""
import json,pathlib,subprocess,sys,time
B=pathlib.Path(__file__).resolve().parent/'load02'
sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'])
out=B/'evidence/hang-with-sentinel'
command=[sys.executable,str(B/'harness/coordinator_case.py'),'hang',str(out)]
started=time.monotonic()
try:
    result=subprocess.run(command,cwd=B,capture_output=True,text=True,timeout=60)
    (out/'stdout.log').write_text(result.stdout)
    (out/'stderr.log').write_text(result.stderr)
    cleanup=json.loads((out/'cleanup-real-time.json').read_text())
    report=json.loads(next((out/'runs').glob('*/report.json')).read_text())
    alive=sentinel.poll() is None
    assert result.returncode==3 and alive
    assert cleanup['grace_seconds']==35 and cleanup['real_elapsed_seconds']>=35
    assert len(cleanup['forced_pids'])==1 and sentinel.pid not in cleanup['forced_pids']
    assert cleanup['forced_pids']==report['forced_termination_pids']
    row=dict(command=command,exit_code=result.returncode,elapsed_seconds=time.monotonic()-started,sentinel_pid=sentinel.pid,external_sentinel_alive_after_coordinator=alive,cleanup=cleanup,forced_record_visible=True)
finally:
    if sentinel.poll() is None:sentinel.terminate()
    sentinel.wait(timeout=5)
row['sentinel_reaped_by_review_owner']=True
(out/'ownership-receipt.json').write_text(json.dumps(row,indent=2)+'\n')
print(json.dumps(row))
