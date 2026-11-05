from pathlib import Path
import importlib.util,argparse,os,sys,json
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');stage=sys.argv[1];locales=sys.argv[2]
assert stage.startswith('preparation-source-ui-') and not (b/stage).exists()
allowed=json.loads((repo/'client/data/localization_registry.json').read_text(encoding='utf-8'))['languages']
assert len(locales.split(','))==len(set(locales.split(','))) and all(n in allowed for n in locales.split(','))
spec=importlib.util.spec_from_file_location('hidden_validator',repo/'tools/validate_ui_hidden.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
os.environ['FANTASYCARD_PREPARATION_REVIEW_INPUT']=str(b/'preparation-client-http-r1')
args=argparse.Namespace(output=b/stage,godot=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'),scripts_only=False,card_regression=False,locale=locales,width=960,all_widths=(len(sys.argv)<4 or sys.argv[3]=='all'),all_locales=False,screens='=prep_source_owned,=prep_source_borrowed,=prep_source_locked,=prep_source_unavailable,=prep_source_deck,=prep_source_deck_bottom,=prep_source_menu,=prep_current_d1',scene='ui_visual_review',wait_seconds=0,verbose=False)
code=m.run(args);print(json.dumps(dict(stage=stage,code=code,locales=locales)));raise SystemExit(code)
