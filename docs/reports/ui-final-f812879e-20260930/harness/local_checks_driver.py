from pathlib import Path
import os,json,subprocess,time
repo=Path.cwd();out=repo/'artifacts/ui-final-f812879e-20260930'
source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
godot=os.environ['A3GAME_GODOT_EXECUTABLE']
commands=[]
def run(label,cmd,timeout,extra=None):
 env=dict(os.environ,FANTASYCARD_SOURCE_SHA=source,
   XDG_DATA_HOME=str(out/(label+'-user/data')),XDG_CONFIG_HOME=str(out/(label+'-user/config')))
 if extra:env.update(extra)
 start=time.monotonic();print('START',label,flush=True)
 with (out/'logs'/f'{label}.log').open('wb') as log:
  try:r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 record={'label':label,'command':cmd,'cwd':str(repo),'source_sha':source,'exit_code':code,'duration_seconds':round(time.monotonic()-start,3),'deadline_seconds':timeout,'log':f'logs/{label}.log'}
 commands.append(record);(out/'local-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
 print('DONE',label,code,flush=True)
 return code
run('callback',['python3','tools/pr13_callback_isolation.py','--output',str(out/'callback')],75)
run('http-codec',['python3','client/tests/run_http_protobuf_client.py','--godot',godot,'--work-dir',str(out/'http-codec')],200)
run('http-boundary',['python3','client/tests/run_http_boundary.py','--godot',godot,'--output',str(out/'http-boundary')],90)
run('ui-modules',[godot,'--headless','--path','client','--script','res://tests/run_ui_style_checks.gd'],90,{'FANTASYCARD_UI_CHECKS':str(out/'ui-modules.json')})
run('new-session-modules',[godot,'--headless','--path','client','--script',str(out/'harness/new_session_modules.gd')],90,{'FANTASYCARD_SESSION_RESULTS':str(out/'new-session-modules.json')})
run('load-parse',[godot,'--headless','--path','client','--script','res://tests/run_gameplay_load_parse.gd'],45)
print(json.dumps({'ok':all(r['exit_code']==0 for r in commands),'checks':len(commands),'source_sha':source}),flush=True)
raise SystemExit(0 if all(r['exit_code']==0 for r in commands) else 1)
