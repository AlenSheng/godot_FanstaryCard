from pathlib import Path
import os,json,subprocess,time
repo=Path.cwd();out=repo/'artifacts/ui-final-f812879e-20260930'
source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();godot=os.environ['A3GAME_GODOT_EXECUTABLE'];records=[]
for label,scene in [('monster-titles','res://tests/ui_monster_title_review.tscn'),('representatives',str(out/'harness/ui_representatives.tscn')),('mail',str(out/'harness/ui_style_mail_labels.tscn')),('codex',str(out/'harness/ui_style_codex_review.tscn'))]:
 env=dict(os.environ,DISPLAY=':93',FANTASYCARD_SOURCE_SHA=source,FANTASYCARD_TITLE_PHASE='final-combination',FANTASYCARD_ART_EVIDENCE=str(out/label),FANTASYCARD_UI_EVIDENCE=str(out/label),FANTASYCARD_UI_ASSERT_FIXES='1',XDG_DATA_HOME=str(out/(label+'-user/data')),XDG_CONFIG_HOME=str(out/(label+'-user/config')))
 cmd=[godot,'--path','client','--rendering-method','gl_compatibility','--audio-driver','Dummy',scene]
 print('START',label,flush=True);start=time.monotonic()
 with (out/'logs'/f'{label}.log').open('wb') as log:
  try:r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180);code=r.returncode
  except subprocess.TimeoutExpired:code=124
 report=json.loads((out/label/'report.json').read_text()) if (out/label/'report.json').exists() else {}
 records.append({'label':label,'command':cmd,'source_sha':source,'cwd':str(repo),'exit_code':code,'report_ok':report.get('ok',False),'screenshots':report.get('screenshots',0),'duration_seconds':round(time.monotonic()-start,3),'deadline_seconds':180,'log':f'logs/{label}.log'})
 (out/'native-commands.json').write_text(json.dumps(records,indent=2)+'\n')
 print('DONE',label,code,report.get('ok'),report.get('screenshots'),flush=True)
print(json.dumps({'ok':all(r['exit_code']==0 and r['report_ok'] for r in records),'source_sha':source,'screenshots':sum(r['screenshots'] for r in records)}),flush=True)
raise SystemExit(0 if all(r['exit_code']==0 and r['report_ok'] for r in records) else 1)
