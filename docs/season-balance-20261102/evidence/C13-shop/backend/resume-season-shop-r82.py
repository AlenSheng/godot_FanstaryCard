from pathlib import Path
import subprocess,json
b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');stage=b/'storage-r82';ship=b/'ship-season-shop-r82.py';script=ship.read_text(encoding='utf-8')
record=json.loads((stage/'after-scp-timeout.original.log').read_text(encoding='utf-8'));assert not record['handle_exists'] and not record['containers'] and not record['input_exists']
batch=stage/'resume-put.sftp';batch.write_text('reput "'+(stage/'transfer.tar.gz').as_posix()+'" "/home/ubuntu/season-season-shop-r82-transfer.tar.gz"\nquit\n')
r=subprocess.run(['sftp','-i',r'C:\Users\SHENGJIAHAO\.ssh\gpt-deploy-release.pem','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-b',str(batch),'ubuntu@43.172.70.182'],capture_output=True,text=True,timeout=90);(stage/'resume-put.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
context={'__file__':str(ship),'__name__':'resume_existing_r82'};exec(script[:script.index('remote_py("""from pathlib')],context)
exec(script[script.index("proof=json.loads"):],context)
