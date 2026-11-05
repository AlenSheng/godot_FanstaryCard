from pathlib import Path
import hashlib,json,re,subprocess

repo=Path.cwd();base=Path(__file__).parent;target=base/'journey-client-static-audit-r1.json';assert not target.exists()
files=['client/ui/season_journey_reward_controller.gd','client/ui/season_journey_reward_view.gd','client/ui/season_cosmetic_art.gd']
keys=set()
for name in files:keys.update(re.findall(r'P\.localized\("([a-z0-9_]+)"\)',(repo/name).read_text('utf-8')))
languages={};additions=None
for path in (repo/'client/data/locales').glob('*.json'):
    name=path.relative_to(repo).as_posix();raw=path.read_bytes();current=json.loads(raw)
    original=json.loads(subprocess.check_output(['git','show','HEAD:'+name]))
    assert all(current['strings'][k]==v for k,v in original['strings'].items())
    assert all(current[k]==v for k,v in original.items() if k!='strings')
    added=set(current['strings'])-set(original['strings']);assert len(added)==26
    if additions is None:additions=added
    else:assert added==additions
    assert all(key in current['strings'] and current['strings'][key].strip() for key in keys)
    for key in added:
        assert sorted(re.findall(r'%[sd]',current['strings'][key]))==sorted(re.findall(r'%[sd]',json.loads((repo/'client/data/locales/en.json').read_text('utf-8'))['strings'][key]))
    languages[path.stem]={'strings':len(current['strings']),'old_strings_preserved':len(original['strings']),'added':len(added),'sha256':hashlib.sha256(raw).hexdigest()}
assert len(languages)==11
manifest=json.loads((repo/'client/assets/imported/manifest.json').read_text('utf-8'));original=json.loads(subprocess.check_output(['git','show','HEAD:client/assets/imported/manifest.json']))
assert all(manifest['files'][k]==v for k,v in original['files'].items())
assert all(manifest[k]==v for k,v in original.items() if k!='files')
assets=[]
for row in json.loads((repo/'docs/season-balance-20261102/C15-ASSET-PROVENANCE.json').read_text('utf-8'))['assets']:
    path=repo/row['file'];key=path.relative_to(repo/'client/assets/imported').as_posix();entry=manifest['files'][key]
    assert entry['path']=='res://'+path.relative_to(repo/'client').as_posix()
    assert entry['imported_sha256']==row['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assets.append(key)
report={'ok':True,'languages':languages,'literal_ui_keys':sorted(keys),'added_keys':sorted(additions),'registered_assets':assets,'old_manifest_entries_preserved':len(original['files']),'rendered':False,'engine_compiled':False}
target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'ok':True,'languages':len(languages),'added_keys_each':26,'registered_assets':len(assets),'rendered':False}))
