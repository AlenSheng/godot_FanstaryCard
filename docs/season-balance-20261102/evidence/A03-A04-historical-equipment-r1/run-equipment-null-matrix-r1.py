from pathlib import Path
import subprocess,json,os,time
repo=Path.cwd();b=Path(__file__).parent;out=b/'equipment-null-matrix-r1';assert not out.exists();out.mkdir()
scenes=[['historical_gear_none'],['ready_removed_equipment'],['ready_removed_timeout']]
(out/'plan.json').write_text(json.dumps({'groups':scenes,'widths':[960,1280,1920],'locales':11,'expected_final_frames':99,'reserve_GiB':6,'startup_GiB':1,'renderer_deadline_seconds':180,'resource_protections_unchanged':True},indent=2)+'\n')
with (out/'handles.original.jsonl').open('x',encoding='utf-8') as handles:
 for number,group in enumerate(scenes,1):
  target=b/('equipment-null-ui-group'+str(number)+'-r1');assert not target.exists()
  args=['python','tools/validate_ui_hidden.py','--godot',r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe','--output',str(target),'--all-locales','--all-widths','--screens',','.join('='+s for s in group)]
  print('Starting exact group'+str(number)+' '+','.join(group),flush=True)
  with (out/('group'+str(number)+'.driver.original.log')).open('xb') as log:
   child=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
   handle={'pid':child.pid,'group':number,'output':str(target),'command':args,'started_at':time.time()};handles.write(json.dumps(handle)+'\n');handles.flush();(out/'current-child.json').write_text(json.dumps(handle,indent=2)+'\n')
   code=child.wait()
  terminal=json.loads((target/'terminal.original.json').read_text(encoding='utf-8'));print(json.dumps({'group':number,'driver_exit':code,'terminal':terminal}),flush=True)
  if code!=0:
   (out/'terminal.original.json').write_text(json.dumps({'state':'GroupFailed','group':number,'driver_exit':code,'remaining_not_started':list(range(number+1,4))},indent=2)+'\n');raise SystemExit(code)
  review=json.loads((target/'review.json').read_text(encoding='utf-8'));assert review['screenshots']==33 and not review['legacy_layout_observations'] and all(review['checks'].values())
(out/'terminal.original.json').write_text(json.dumps({'state':'Complete','groups':3,'final_frames':99,'actual_full_game_matches':0},indent=2)+'\n')
print('All3 groups complete;99 unique actual frames; manual review still required',flush=True)
