from pathlib import Path

base=Path(__file__).parent;source=(base/'run-journey-client-cloud-r5.py').read_text('utf-8')
source=source.replace('journey-client-cloud-r5','journey-client-cloud-r6').replace('season-balance-20261102-journey-client-r5','season-balance-20261102-journey-client-r6')
source=source.replace('buffer=io.BytesIO()',"external_assets={n.removeprefix('client/'):h for n,h in pins.items() if Path(n).suffix in ('.png','.wav')}\nbuffer=io.BytesIO()",1)
source=source.replace("if source.is_file():archive.add(source,arcname=source.relative_to(project).as_posix())", "if source.is_file() and source.relative_to(project).as_posix() not in external_assets:archive.add(source,arcname=source.relative_to(project).as_posix())")
needle="runner=input_dir/'runner.py'"
replacement="""asset_base=Path('/home/ubuntu/pr13-acceptance-20261009/work/cap-RENDER-r7-inputs/client')
asset_pins=ASSET_PINS
reused=[]
for name,digest in asset_pins.items():
 p=asset_base/name;assert p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==digest,('existing asset mismatch',name)
 target=input_dir/name;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();os.link(p,target);reused.append({'name':name,'sha256':digest})
record('existing-assets-before.original.json',{'base':str(asset_base),'assets':reused,'method':'hard links read-only mounted; Godot imports a separate tmpfs copy'})
"""+needle
assert needle in source;source=source.replace(needle,replacement)
needle="record('cleanup.original.json',{'container_removed':True,'input_retained':True})"
assert needle in source;source=source.replace(needle,needle+"\nassert all(hashlib.sha256((asset_base/n).read_bytes()).hexdigest()==h for n,h in asset_pins.items())\nrecord('existing-assets-after.original.json',{'all_original_bytes_unchanged':True,'asset_count':len(asset_pins)})")
needle="remote=remote.replace('PAYLOAD_SHA'"
assert needle in source;source=source.replace(needle,"remote=remote.replace('ASSET_PINS',repr(external_assets))\n"+needle)
target=base/'run-journey-client-cloud-r6.py';assert not target.exists();target.write_text(source,encoding='utf-8');compile(source,str(target),'exec')
print(str(target))
