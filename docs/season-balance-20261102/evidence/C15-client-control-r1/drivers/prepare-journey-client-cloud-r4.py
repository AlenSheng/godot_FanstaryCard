from pathlib import Path

base=Path(__file__).parent;source=(base/'run-journey-controller-cloud-r3.py').read_text('utf-8')
source=source.replace('journey-controller-cloud-r3','journey-client-cloud-r4').replace('season-balance-20261102-journey-controller-r3','season-balance-20261102-journey-client-r4')
old="pending=['tests/test_journey_reward_controller.gd']"
new="pending=['tests/test_journey_reward_controller.gd','ui/main.gd','tests/ui_visual_review.gd','audio/sound_service.gd'] + [p.relative_to(repo/'client').as_posix() for p in (repo/'client/assets/audio').glob('*.wav')]"
assert old in source;source=source.replace(old,new)
old="    if target.suffix=='.gd':pending+="
assert old in source
source=source.replace(old,"    if target.suffix=='.tscn':pending+=re.findall(r'path=\"res://([^\"]+)\"',raw.decode('utf-8-sig'))\n"+old)
old="Game=\"*res://state/game_store.gd\"\\n[rendering]"
assert old in source;source=source.replace(old,"Game=\"*res://state/game_store.gd\"\\nSound=\"*res://audio/sound_service.gd\"\\n[rendering]")
old="shutil.copyfile(base/'journey-controller-native-r2/run.gd',project/'run.gd')"
assert old in source
replacement=old+'''
runner=(project/'run.gd').read_text('utf-8')
runner=runner.replace('    var script = load', '    var ui_scripts = ["res://ui/main.gd", "res://ui/reference_ui.gd", "res://ui/season_journey_reward_view.gd", "res://ui/season_cosmetic_art.gd", "res://tests/ui_visual_review.gd"]\\n    for path in ui_scripts:\\n        var candidate = load(path)\\n        if candidate == null or not candidate.can_instantiate():\\n            quit(3)\\n            return\\n    var script = load')
(project/'run.gd').write_text(runner,encoding='utf-8')
'''
source=source.replace(old,replacement).replace('len(payload)<2*1024**2','len(payload)<16*1024**2')
source=source.replace("os.chmod(output,0o777)","os.chmod(output,0o777)\ncurrent=resources();assert current['available_ram']>=admission and current['disk_free']>=disk_floor+8*1024**2 and current['disk_ratio']>=.05")
source=source.replace('timeout=270)','timeout=600)')
target=base/'run-journey-client-cloud-r4.py';assert not target.exists();target.write_text(source,encoding='utf-8')
compile(source,str(target),'exec')
print(str(target))
