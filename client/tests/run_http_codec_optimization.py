"""Compare a committed baseline and current codec on exactly the same real bootstrap bytes."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--godot',required=True)
p.add_argument('--baseline-ref',required=True)
p.add_argument('--sample',required=True)
p.add_argument('--work-dir',default='work/client-opt/benchmark')
a=p.parse_args(); repo=Path(__file__).resolve().parents[2]; work=(repo/a.work_dir).resolve()
for folder in ['baseline','network','data','tests']: (work/folder).mkdir(parents=True,exist_ok=True)
for name in ['protobuf.gd','http_protocol.gd']:
    text=subprocess.check_output(['git','show',a.baseline_ref+':client/network/'+name],cwd=repo).decode('utf-8-sig')
    if name=='http_protocol.gd': text=text.replace('res://network/protobuf.gd','res://baseline/protobuf.gd')
    (work/'baseline'/name).write_text(text,encoding='utf-8')
for name in ['gateway.gd','protobuf.gd','http_protocol.gd']: shutil.copyfile(repo/'client/network'/name,work/'network'/name)
for name in ['realtime_schema.json','http_schema.json','http_endpoints.json']: shutil.copyfile(repo/'client/data'/name,work/'data'/name)
shutil.copyfile(a.sample,work/'data/bootstrap-real.pb')
shutil.copyfile(repo/'client/tests/test_http_codec_optimization.gd',work/'tests/test_http_codec_optimization.gd')
(work/'project.godot').write_text('[application]\nconfig/name="Codec optimization isolated benchmark"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
env=dict(os.environ,FANTASYCARD_SERVER_URL='http://127.0.0.1:38971')
records=[]
for label,extra in [('import',['--editor','--import','--quit']),('benchmark',['--script','res://tests/test_http_codec_optimization.gd'])]:
    command=[a.godot,'--headless','--language','en','--path',str(work)]+extra
    r=subprocess.run(command,env=env,capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=(r.stdout+r.stderr).decode('utf-8',errors='replace'); (work/(label+'.log')).write_text(output,encoding='utf-8')
    passed=r.returncode==0 and 'ERROR:' not in output
    records.append({'step':label,'exit_code':r.returncode,'passed':passed})
    if label=='benchmark': print(output)
(work/'results.json').write_text(json.dumps({'baseline_ref':a.baseline_ref,'sample_sha256':hashlib.sha256(Path(a.sample).read_bytes()).hexdigest(),'runs':records},indent=2),encoding='utf-8')
raise SystemExit(0 if all(row['passed'] for row in records) else 1)
