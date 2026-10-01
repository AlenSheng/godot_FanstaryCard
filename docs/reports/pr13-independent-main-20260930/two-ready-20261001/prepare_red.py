"""Exact 2dda runtime and original declared nine-file harness; no assertion edit."""
import hashlib,json,pathlib,subprocess
B=pathlib.Path(__file__).resolve().parent;repo='/workspace/godot_FanstaryCard';sha='2dda41b32ba89f06d5ea722ae8b9469004940c22';R=B/'red-source';R.mkdir()
spec=json.loads((B/'packets/a05/source-green2-fixed.json').read_text())
paths=set(subprocess.check_output(['git','-C',repo,'ls-tree','-r','--name-only',sha],text=True).splitlines())
entries=[];omitted=[]
for e in spec['files']:
    name=e['path']
    if name not in paths:omitted.append(name);continue
    data=subprocess.check_output(['git','-C',repo,'show',sha+':'+name]);p=R/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
packet=pathlib.Path('/workspace/pr13-main-bounded-20261001/a05');old=json.loads((packet/'source-final.json').read_text())
overlays=[]
for e in old['harness_files']:
    data=(packet/'harness'/e['path']).read_bytes();assert len(data)==e['bytes'] and hashlib.sha256(data).hexdigest()==e['sha256']
    assert e['path'] not in paths,'Original declared test overlay unexpectedly overwrites tracked implementation'
    p=R/e['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);overlays.append(e)
assert len(overlays)==9
proof={'integration_sha':sha,'business_source_sha':'f812879e4518fd09bf22656451cb563d62940298','copy_scope':'Exact partial 2dda source and original 80687833 nine-file declared causal test overlay; no production or assertion modifications','files':entries,'harness_files':overlays,'harness_report_commit':'8068783331da07ec68354c1874eb0d65adea632f','post_fix_only_paths_absent_from_baseline':omitted,'tests_executed':0}
(R/'FIXED_SOURCE.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'integration_sha':sha,'files':len(entries),'overlays':9,'post_fix_only_omitted':len(omitted)}))
