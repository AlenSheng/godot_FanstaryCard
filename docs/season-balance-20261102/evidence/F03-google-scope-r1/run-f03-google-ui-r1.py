from pathlib import Path
import importlib.util,json,argparse
b=Path(__file__).parent;assert json.loads((b/'f03-google-import-r1/result.json').read_bytes())['exit']==0
info=json.loads((b/'f03-google-integration-r1/source.original.json').read_bytes());work=Path(info['worktree'])
spec=importlib.util.spec_from_file_location('validator',work/'tools/validate_ui_hidden.py');validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
options=argparse.Namespace(godot=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'),output=b/'f03-google-ui-r1',scripts_only=False,card_regression=False,locale='zh-CN',width=960,all_widths=True,all_locales=True,screens='google-specific-five-states',scene='ui_google_branch_review',wait_seconds=0,render_timeout_seconds=600,verbose=False)
result=validator.run(options);print(json.dumps({'exit':result,'expected_frames':165,'custom_scene_fixture':'ui_google_branch_review','no_real_Google_SDK':True,'actual_remote_branch_updated':False}));raise SystemExit(result)
