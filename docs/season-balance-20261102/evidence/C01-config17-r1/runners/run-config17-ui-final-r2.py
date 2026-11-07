from pathlib import Path
import json,hashlib,subprocess,sys,os,datetime
repo=Path.cwd();base=Path(__file__).parent;codes=list(json.loads((repo/'client/data/localization_registry.json').read_bytes())['languages'])
plan=base/'config17-ui-final-r2.plan.original.json';assert not plan.exists();groups=[dict(locale=code,output=str(base/('config17-ui-final-r2-'+code))) for code in codes if code in ['ar','ja','ko','ru']]
plan.write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),states=7,frames=84,widths=[960,1280,1920],groups=groups,render_window_seconds=180,new_game_matches=0),indent=2)+'\n')
archive=repo/'server/config/archive/season-v1-config-16/fantasycard.config.bytes';digest=hashlib.sha256(archive.read_bytes()).hexdigest()
env=dict(os.environ,FANTASYCARD_ARCHIVE_CONFIG16_BYTES=str(archive),FANTASYCARD_ARCHIVE_CONFIG16_HASH=(archive.parent/'fantasycard.config.sha256').read_text().strip())
for group in groups:
 print('Starting affected UI',group['locale'],flush=True)
 r=subprocess.run([sys.executable,str(repo/'tools/validate_ui_hidden.py'),'--godot',r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe','--output',group['output'],'--screens','sustain','--locale',group['locale'],'--all-widths','--wait-seconds','30'],env=env)
 terminal=json.loads((Path(group['output'])/'terminal.original.json').read_bytes());review=json.loads((Path(group['output'])/'review.json').read_bytes());failed=[k for k,v in review['checks'].items() if v is not True]
 print(json.dumps(dict(locale=group['locale'],exit=r.returncode,frames=review['screenshots'],checks=len(review['checks']),failed=failed[:12],terminal=terminal['native_exit']),ensure_ascii=True),flush=True)
 assert r.returncode==0 and terminal['native_exit']==0 and terminal['source_unchanged'] and not failed and review['screenshots']==21
assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
print('84 affected frames complete; representative direct review still required.',flush=True)
