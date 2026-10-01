"""Read-only byte/object/config and report-contract verification."""
import hashlib,json,pathlib,subprocess
B=pathlib.Path(__file__).resolve().parent;repo='/workspace/godot_FanstaryCard';out=[]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
specs=[('a05-source','packets/a05/source-green2-fixed.json'),('load02-source','packets/load02/source-dfb3f88a73ef-fixed.json'),('red-source','red-source/FIXED_SOURCE.json')]
for directory,filename in specs:
    manifest=json.loads((B/filename).read_text());root=B/directory;entries=manifest['files']+manifest.get('harness_files',[]);bad=[]
    raw_tree=subprocess.check_output(['git','-C',repo,'ls-tree','-r','-z',manifest['integration_sha']]);tree={}
    for line in raw_tree.split(b'\0'):
        if line:
            meta,name=line.split(b'\t',1);tree[name.decode()]=meta.split()[2].decode()
    overlay_paths={e['path'] for e in manifest.get('harness_files',[])}
    for e in entries:
        p=root/e['path']
        if not p.is_file() or p.stat().st_size!=e['bytes'] or digest(p)!=e['sha256']:bad.append(e['path']);continue
        if e['path'] not in overlay_paths:
            data=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            assert tree.get(e['path'])==blob,(directory,e['path'],'exact Git blob differs')
            if e.get('git_blob'):assert e['git_blob']==blob
        else:assert e['path'] not in tree
    assert not bad,(directory,bad)
    binaries=[]
    for name in ['FantasyCard.Server.dll','FantasyCard.Server.Tests.dll']:
        project='src/FantasyCard.Server' if name=='FantasyCard.Server.dll' else 'tests/FantasyCard.Server.Tests'
        p=root/'server'/project/'bin/Release/net10.0'/name
        binaries.append({'path':str(p.relative_to(B)),'bytes':p.stat().st_size,'sha256':digest(p)})
    out.append({'directory':directory,'source_sha':manifest['integration_sha'],'verified_declared_paths':len(entries),'declared_bytes':sum(e['bytes'] for e in entries),'source_byte_mismatches':0,'actual_fixed_Git_tree_blob_mismatches':0,'native_Git_HEAD':subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip() if (root/'.git').exists() else None,'source_checkout_dirty':None,'missing_reasons':{'source_checkout_dirty':'Exact declared partial source, not full checkout; historical tracked files outside replay manifest absent. Do not claim clean full worktree.','native_Git_HEAD':'Original RED has no Git metadata; source paths from exact Git objects and nine original declared overlay hashes are verified.'} if not (root/'.git').exists() else {'source_checkout_dirty':'Exact declared partial source, not full checkout; historical tracked files outside replay manifest absent. Do not claim clean full worktree.'},'fresh_internal_build_artifacts':binaries,'assertions_or_implementation_modified':False})
plan_path=pathlib.Path('/workspace/pr13-main-bounded-seal/docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json');plan=json.loads(plan_path.read_text());fields=plan['evidence_contract']['report_fields'];metadata=[]
for group in ['a05','load02']:
    root=B/'packets'/group;r=json.loads((root/'report.json').read_text());nulls=[x for x in fields if r.get(x) is None];missing=[x for x in fields if x not in r];reasons=r.get('missing_reasons',{})
    assert not missing and all(x in reasons for x in nulls),(group,missing,nulls,reasons)
    sha=r['integration_sha'];source=B/('a05-source' if group=='a05' else 'load02-source')
    candidates=list(source.rglob('fantasycard.config.bytes'));hashes={digest(x) for x in candidates};assert r['config_bytes_hash'] in hashes
    workbook=source/'config/FantasyCard_Config.xlsx';assert digest(workbook)==r['config_source_hash']
    metadata.append({'group':group,'integration_sha':sha,'required_fields':len(fields),'missing_fields':missing,'null_fields':nulls,'missing_reasons':reasons,'profile_hash':r['profile_hash'],'algorithm_version':r['algorithm_version'],'config_source_hash':digest(workbook),'config_bytes_hash':r['config_bytes_hash'],'all_config_byte_copy_hashes':sorted(hashes),'exact_required_config_found':True,'report_sha256':digest(root/'report.json')})
original={'HEAD':subprocess.check_output(['git','-C',repo,'rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','-C',repo,'branch','--show-current'],text=True).strip(),'status':subprocess.check_output(['git','-C',repo,'status','--porcelain'],text=True),'modified_by_review':False}
(B/'SOURCE_METADATA_CHECKS.json').write_text(json.dumps({'plan_sha256':digest(plan_path),'sources':out,'metadata':metadata,'original_checkout':original},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verified_source_paths':[x['verified_declared_paths'] for x in out],'metadata_fields_each':len(fields),'source_config_mismatches':0,'original_checkout':original},ensure_ascii=False))
