from pathlib import Path
import json,subprocess,shlex,hashlib,sys,re
sys.stdout.reconfigure(encoding='utf-8');b=Path(__file__).parent;o=b/'runtime-r107';index=sys.argv[1];assert re.fullmatch(r'r[1-9][0-9]*',index);out=o/('file-prefix-'+index+'.original.json');assert not out.exists();stop=json.loads((o/'sftp-writer-stop-r1.original.json').read_text('utf-8'));assert stop['terminal']
code="""from pathlib import Path
import json,hashlib
p=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107-upload/stream-r1.bin.part');assert p.is_file() and not p.is_symlink();raw=p.read_bytes();print(json.dumps(dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),runtime_root_exists=Path('/home/ubuntu/season-balance-20261102-a03-runtime-r107').exists(),runtime_containers=None,runtime_container_check_deferred_to_original_start_admission=True)))
"""
try:r=subprocess.run(['ssh','-n','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','ubuntu@43.172.70.182','python3 -c '+shlex.quote(code)],capture_output=True,text=True,encoding='utf-8',timeout=40)
except subprocess.TimeoutExpired:
    (o/('file-prefix-'+index+'-observation-timeout.original.json')).write_text(json.dumps(dict(timeout_seconds=40,remote_outcome_unknown=True,not_a_test_failure=True))+'\n',encoding='utf-8');raise
(o/('file-prefix-'+index+'.transport.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stderr;proof=json.loads(r.stdout);local=(o/'transport-stream-file-r1.bin').read_bytes();assert 0<=proof['bytes']<=len(local);proof['local_prefix_identical']=hashlib.sha256(local[:proof['bytes']]).hexdigest()==proof['sha256'];proof['complete']=proof['bytes']==len(local) and proof['local_prefix_identical'];proof['prior_owned_writer_terminal_verified']=stop;out.write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof));assert proof['local_prefix_identical'] and not proof['runtime_root_exists']
