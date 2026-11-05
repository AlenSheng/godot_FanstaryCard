from pathlib import Path
import argparse,importlib.util,json,os,sys

repo=Path.cwd();base=Path(__file__).parent;stage=sys.argv[1];locales=sys.argv[2]
assert stage.startswith('journey-client-ui-') and not (base/stage).exists()
allowed=json.loads((repo/'client/data/localization_registry.json').read_text('utf-8'))['languages']
assert len(locales.split(','))==len(set(locales.split(','))) and all(n in allowed for n in locales.split(','))
spec=importlib.util.spec_from_file_location('hidden_validator',repo/'tools/validate_ui_hidden.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
os.environ['FANTASYCARD_JOURNEY_REWARD_REVIEW_INPUT']=str(base/'runtime-r108/public/results/journey-reward-client')
screens='claim_rewards_pending,claim_rewards_class_menu,claim_rewards_confirm,claim_rewards_claimed,claim_rewards_unavailable,claim_rewards_tail,claim_cosmetics_empty,claim_cosmetics_owned,claim_cosmetics_tail,claim_deck_equipped,claim_hall_equipped'
args=argparse.Namespace(output=base/stage,godot=Path(r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'),scripts_only=False,card_regression=False,locale=locales,width=960,all_widths=len(sys.argv)<4 or sys.argv[3]=='all',all_locales=False,screens=','.join('='+name for name in screens.split(',')),scene='ui_visual_review',wait_seconds=0,verbose=False)
result=module.run(args);print(json.dumps({'stage':stage,'returncode':result,'languages':locales,'actual_frames_required':11*len(locales.split(','))*(3 if args.all_widths else 1)}));raise SystemExit(result)
