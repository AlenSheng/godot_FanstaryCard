from pathlib import Path
import base64,hashlib,io,json,tarfile

repo=Path.cwd();base=Path(__file__).parent;stage=base/'journey-native-cloud-r4';assert not stage.exists();stage.mkdir()
original=json.loads((base/'journey-client-cloud-r7/source-pin.json').read_text('utf-8'))
current={name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in original}
changed=[name for name in current if current[name]!=original[name]]
assert set(changed)=={'client/ui/reference_ui.gd','client/ui/season_journey_reward_controller.gd','client/ui/season_journey_reward_view.gd','client/tests/ui_visual_review.gd','client/tests/test_journey_reward_controller.gd'}
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
 for name in changed:archive.add(repo/name,arcname=name.removeprefix('client/'))
payload=buffer.getvalue();(stage/'delta.tar.gz').write_bytes(payload)
(stage/'source-pin.json').write_text(json.dumps(current,indent=2)+'\n',encoding='utf-8')
(stage/'manifest.json').write_text(json.dumps({'old':original,'current':current,'changed':changed,'delta_sha256':hashlib.sha256(payload).hexdigest(),'delta_bytes':len(payload)},indent=2)+'\n',encoding='utf-8')
root='/home/ubuntu/season-balance-20261102-journey-native-r4'
for index,offset in enumerate(range(0,len(payload),12000)):
 chunk=payload[offset:offset+12000]
 code="""from pathlib import Path
import base64,hashlib,json,shutil
root=Path(ROOT);root.mkdir(exist_ok=True)
d=shutil.disk_usage(root);assert d.free>=3*1024**3+8*1024**2 and d.free/d.total>=.05
p=root/NAME;assert not p.exists();data=base64.b64decode(DATA);assert hashlib.sha256(data).hexdigest()==SHA;p.write_bytes(data)
print(json.dumps({'name':p.name,'bytes':len(data),'sha256':SHA,'native_started':False}))
""".replace('ROOT',repr(root)).replace('NAME',repr(f'part-{index:03}.bin')).replace('DATA',repr(base64.b64encode(chunk).decode())).replace('SHA',repr(hashlib.sha256(chunk).hexdigest()))
 (stage/f'upload-{index:03}.py').write_text(code,encoding='utf-8')
print(json.dumps({'changed':changed,'delta_bytes':len(payload),'chunks':len(list(stage.glob('upload-*.py')))}))
