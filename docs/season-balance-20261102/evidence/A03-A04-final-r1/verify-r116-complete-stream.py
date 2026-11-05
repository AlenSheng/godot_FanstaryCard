from pathlib import Path
import json,subprocess,shlex,hashlib,sys
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r116';assert json.loads((o/'sftp-r1.original.json').read_text('utf-8'))['exit']==0;out=o/'file-prefix-r2.original.json';assert not out.exists()
code="""from pathlib import Path
import json,hashlib
root=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r116-upload');p=root/'stream-r1.bin.part';assert root.resolve().parent==Path('/home/ubuntu') and not root.is_symlink();assert p.is_file() and not p.is_symlink() and p.resolve().parent==root.resolve();raw=p.read_bytes()
print(json.dumps(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),runtime_root_exists=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r116').exists(),runtime_containers=None,runtime_container_check_deferred_to_original_start_admission=True,sftp_completed_with_exit_zero=True)))
"""
try:r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182','python3 -c '+shlex.quote(code)],capture_output=True,text=True,encoding='utf-8',timeout=40)
except subprocess.TimeoutExpired:
    (o/'file-complete-verification-observation-timeout.original.json').write_text(json.dumps(dict(timeout_seconds=40,remote_outcome_unknown=True,not_a_test_failure=True))+'\n',encoding='utf-8');raise
(o/'file-complete-verification.transport.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr;proof=json.loads(r.stdout);local=(o/'transport-stream-file-r1.bin').read_bytes();proof['local_prefix_identical']=proof['bytes']<=len(local) and hashlib.sha256(local[:proof['bytes']]).hexdigest()==proof['sha256'];proof['complete']=proof['bytes']==len(local) and proof['local_prefix_identical'];out.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof));assert proof['complete']
