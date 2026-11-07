from pathlib import Path
import argparse,importlib.util,json

b=Path(__file__).parent
assert json.loads((b/'f03-main-import-r1/result.json').read_bytes())['exit']==0
info=json.loads((b/'f03-main-integration-r1/source.current.json').read_bytes());work=Path(info['worktree'])
spec=importlib.util.spec_from_file_location('validator',work/'tools/validate_ui_hidden.py');validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
options=argparse.Namespace(godot=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'),output=b/'f03-main-ui-r2',scripts_only=False,card_regression=False,locale='zh-CN',width=960,all_widths=True,all_locales=True,screens='retained-main-settings',scene='ui_branch_sync_preview',wait_seconds=0,render_timeout_seconds=300,verbose=False)
result=validator.run(options);print(json.dumps(dict(exit=result,expected_frames=33,source_candidate=info['head'],no_live_auth_or_matches=True,formal_main_updated=False)));raise SystemExit(result)

