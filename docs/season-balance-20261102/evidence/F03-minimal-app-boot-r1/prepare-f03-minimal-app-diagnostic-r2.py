from pathlib import Path

b=Path(__file__).parent;source=(b/'f03-minimal-app-worker-r1.py').read_text('utf-8')
source=source.replace('season-balance-20261107-f03-minimal-app-r1','season-balance-20261107-f03-minimal-app-r2').replace('fc-f03-app-','fc-f03-app2-').replace('app-candidate-r1','app-candidate-r2')
old="logs=run(['docker','logs',app]).decode(errors='replace');(root/'application.private.log').write_text(logs);(root/'application.private.log').chmod(0o600)"
new="""state=inspect(app);(public/'application-state.original.json').write_text(json.dumps({k:state['State'].get(k) for k in ['Status','Running','Pid','ExitCode','Error','OOMKilled','StartedAt','FinishedAt']},indent=2)+'\\n')
    captured=subprocess.run(['docker','logs',app],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    logs=(captured.stdout+captured.stderr).decode(errors='replace');(root/'application.private.log').write_text(logs);(root/'application.private.log').chmod(0o600)
    safe_logs=logs.replace(password,'[REDACTED]').replace(admin,'[REDACTED]')
    assert password not in safe_logs and admin not in safe_logs
    (public/'application-redacted.original.log').write_text(safe_logs)
    (public/'application-log-capture.original.json').write_text(json.dumps(dict(stdout_bytes=len(captured.stdout),stderr_bytes=len(captured.stderr),both_streams_collected=True,raw_log_private=True))+'\\n')"""
assert old in source;source=source.replace(old,new)
target=b/'f03-minimal-app-worker-r2.py';compile(source,str(target),'exec');assert not target.exists();target.write_text(source,encoding='utf-8')
prepare=(b/'prepare-f03-minimal-app-input-r1.py').read_text('utf-8').replace('f03-minimal-app-input-r1','f03-minimal-app-input-r2').replace('season-balance-20261107-f03-minimal-app-r1','season-balance-20261107-f03-minimal-app-r2')
(b/'prepare-f03-minimal-app-input-r2.py').write_text(prepare,encoding='utf-8')
runner=(b/'run-f03-minimal-app-cloud-r1.py').read_text('utf-8').replace('f03-minimal-app-cloud-r1','f03-minimal-app-cloud-r2').replace('f03-minimal-app-input-r1','f03-minimal-app-input-r2').replace('f03-minimal-app-worker-r1.py','f03-minimal-app-worker-r2.py').replace('season-balance-20261107-f03-minimal-app-r1','season-balance-20261107-f03-minimal-app-r2')
runner=runner.replace("'-o','ConnectTimeout=12','-b'","'-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','-b'")
(b/'run-f03-minimal-app-cloud-r2.py').write_text(runner,encoding='utf-8')
print(str(target))
