from pathlib import Path
import json,subprocess,re,hashlib,datetime,ast,sys
base=Path(__file__).parent;stage=base/'f03-readiness-r1';info=json.loads((stage/'branch-readiness-deltas.derived.json').read_bytes());entry=next(r for r in info['branches'] if r['branch']=='release_google');goal=info['goal_head'];target=entry['remote_sha'];common=entry['merge_base'];tree=entry['merge_tree_sha'];out=stage/'google-conflict-draft-r1';assert not out.exists();out.mkdir();root=out/'root';root.mkdir();source_manifest={}
def read(rev,path):
    raw=subprocess.check_output(['git','show',rev+':'+path]);name=rev[:12]+'/'+path;dst=out/'inputs'/name;dst.parent.mkdir(parents=True,exist_ok=True)
    if not dst.exists():dst.write_bytes(raw)
    source_manifest[name]={'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)};return raw
def write(path,raw):
    dst=root/path;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
def parse(rev,path):return json.loads(read(rev,path))
missing=object();unresolved=[]
def merge(b,t,g,path):
    if t==g:return t
    if t==b:return g
    if g==b:return t
    if isinstance(t,dict) and isinstance(g,dict) and (isinstance(b,dict) or b is missing):
        b={} if b is missing else b;result={}
        for k in sorted(set(b)|set(t)|set(g)):
            v=merge(b.get(k,missing),t.get(k,missing),g.get(k,missing),path+'/'+k)
            if v is not missing:result[k]=v
        return result
    unresolved.append(path);return g
paths=[m.split('Merge conflict in ',1)[1] for m in entry['conflict_messages']];assert len(paths)==16
for path in paths:
    if path.startswith('client/data/locales/'):
        result=merge(parse(common,path),parse(target,path),parse(goal,path),path);write(path,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
assert not unresolved,unresolved
path='protocol/http/v1/game.proto';g=read(goal,path).decode();t=read(target,path).decode();added=[]
for name in ['GoogleSignInRequest','AccountDeletionStatus']:
    assert re.search(r'\bmessage\s+'+name+r'\s*\{',g) is None
    m=re.search(r'\bmessage\s+'+name+r'\s*\{[^}]*\}',t,re.S);assert m;added.append(m.group())
text=g.rstrip()+'\n\n// Retained release_google identity contracts.\n'+'\n\n'.join(added)+'\n';names=re.findall(r'\bmessage\s+(\w+)\s*\{',text);assert len(names)==len(set(names));write(path,text.encode())
path='protocol/http/v1/endpoints.json';g=parse(goal,path);t=parse(target,path);assert g['protocol_version']==t['protocol_version'] and g['media_type']==t['media_type'] and g['error']==t['error']
key=lambda r:(r['method'],r['path']);endpoints={key(r):r for r in g['endpoints']};added_routes=[]
for route in t['endpoints']:
    k=key(route)
    if k in endpoints:assert {a:v for a,v in endpoints[k].items() if a!='source'}=={a:v for a,v in route.items() if a!='source'},k
    else:endpoints[k]=route;added_routes.append(k)
g['endpoints']=list(endpoints.values());write(path,(json.dumps(g,indent=2)+'\n').encode())
path='tools/validate_ui_hidden.py';merged=read(tree,path).decode();pattern=r'<<<<<<<[^\n]*\n.*?=======\n.*?>>>>>>>[^\n]*\n';assert len(re.findall(pattern,merged,re.S))==1
replacement='''                "FANTASYCARD_REVIEW_WIDTHS": "960,1280,1920" if getattr(args, "all_widths", False) else str(args.width),
                "FANTASYCARD_REVIEW_LOCALES": ",".join(json.loads((root / "client/data/localization_registry.json").read_text(encoding="utf-8"))["languages"]) if getattr(args, "all_locales", False) else args.locale,
'''
merged=re.sub(pattern,lambda _:replacement,merged,flags=re.S);ast.parse(merged);assert 'RESERVE = 2 * GIB' in merged and 'START_BUDGET = GIB' in merged;write(path,merged.encode())
generator=read(goal,'tools/generate_network_protocol.py');write('tools/generate_network_protocol.py',generator);write('protocol/realtime/v1/realtime.proto',read(tree,'protocol/realtime/v1/realtime.proto'))
for check in [False,True]:
    cmd=[sys.executable,str(root/'tools/generate_network_protocol.py')]+(['--check'] if check else []);r=subprocess.run(cmd,capture_output=True)
    (out/('generator-check.original.log' if check else 'generator.original.log')).write_bytes(r.stdout+r.stderr);assert r.returncode==0
schema=json.loads((root/'client/data/http_schema.json').read_bytes());parent_counts={}
for label,rev in [('goal',goal),('google',target)]:
    parent=parse(rev,'client/data/http_schema.json')['messages'];count=0
    for name,fields in parent.items():
        assert name in schema['messages']
        for tag,field in fields.items():assert schema['messages'][name].get(tag)==field,(label,name,tag);count+=1
    parent_counts[label]={'messages_preserved':len(parent),'exact_fields_preserved':count}
for path in paths:
    raw=(root/path).read_bytes();assert b'<<<<<<<' not in raw and b'>>>>>>>' not in raw,path
for path in [p for p in paths if p.startswith('client/data/locales/')]:
    result=json.loads((root/path).read_bytes())
    for label,rev in [('goal',goal),('google',target)]:
        parent=parse(rev,path)['strings'];assert all(result['strings'].get(k)==v for k,v in parent.items()),(path,label)
goal_flags=set(re.findall(r'parser\.add_argument\("([^"]+)"',read(goal,'tools/validate_ui_hidden.py').decode()));target_flags=set(re.findall(r'parser\.add_argument\("([^"]+)"',read(target,'tools/validate_ui_hidden.py').decode()));draft_flags=set(re.findall(r'parser\.add_argument\("([^"]+)"',(root/'tools/validate_ui_hidden.py').read_text()))
assert goal_flags|target_flags <= draft_flags
resolved={p:{'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest(),'size':(root/p).stat().st_size} for p in paths}
(out/'source-manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n')
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'goal_sha':goal,'google_sha':target,'merge_base':common,'auto_merge_tree':tree,'resolved_conflict_files':resolved,'unresolved_scalar_JSON_conflicts':unresolved,'parent_contract_preservation':parent_counts,'added_google_routes':added_routes,'source_proto_messages_appended':2,'canonical_generator_check_passed':True,'locale_existing_values_both_parents_preserved':True,'UI_validation_flags_both_parents_preserved':True,'memory_reserve_GiB':2,'startup_budget_GiB':1,'draft_only':True,'actual_branch_or_index_changes':False,'runtime_or_UI_validation':False,'production_modified':False,'F03_complete':False,'warning':'A conflict-free generated draft is not a compiled, runtime-tested platform integration. Revalidate exact parent heads and migrate/backup/package gates after D03/F01.'}
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'draft_conflicts_resolved':len(resolved),'parent_contract_preservation':parent_counts,'added_google_routes':added_routes,'generator_check':True,'runtime_checked':False,'branch_changed':False}))
assert subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()==goal and not subprocess.check_output(['git','status','--porcelain'])
