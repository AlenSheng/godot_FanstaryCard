from pathlib import Path
import hashlib,json,os,subprocess,sys

sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent
locales=list(json.loads((repo/'client/data/localization_registry.json').read_bytes())['languages'])
plan=base/'e01-archive-ui-matrix-r1.plan.original.json';assert not plan.exists()
groups=[dict(locale=locale,output=str(base/('e01-archive-ui-r1-'+locale))) for locale in locales]
plan.write_text(json.dumps(dict(frames=297,states=9,widths=[960,1280,1920],per_renderer_window=180,groups=groups),indent=2)+'\n')
original=repo/'server/config/archive/season-v1-config-15/fantasycard.config.bytes';digest=hashlib.sha256(original.read_bytes()).hexdigest()
env=dict(os.environ,FANTASYCARD_ARCHIVE_CONFIG15_BYTES=str(original),FANTASYCARD_ARCHIVE_CONFIG15_HASH=(original.parent/'fantasycard.config.sha256').read_text().strip())
for group in groups:
    print('ArchiveUI starting',group['locale'],flush=True)
    result=subprocess.run([sys.executable,str(repo/'tools/validate_ui_hidden.py'),'--godot',r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe','--output',group['output'],'--screens','archive','--locale',group['locale'],'--all-widths','--wait-seconds','180'],env=env)
    terminal=json.loads((Path(group['output'])/'terminal.original.json').read_bytes())
    print(json.dumps(dict(locale=group['locale'],exit=result.returncode,PNGs=terminal.get('PNGs'),stop_reason=terminal.get('stop_reason'))),flush=True)
    assert result.returncode==0 and terminal['native_exit']==0 and terminal['source_unchanged']
assert hashlib.sha256(original.read_bytes()).hexdigest()==digest
print('297 archiveframes complete; no game matches.',flush=True)
