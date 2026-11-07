from pathlib import Path
import hashlib,importlib.util,json,os,subprocess,tarfile

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-main-integration-r1';work=(b/'work/f03-main-integration-r1').resolve()
info=json.loads((out/'source.current.json').read_bytes());assert subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip()==info['head']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin=json.loads((out/'source-pin.original.json').read_bytes());assert all(sha(work/n)==h for n,h in pin.items())
build=json.loads((out/'build-result.json').read_bytes());native=json.loads((b/'f03-main-native-r1/result.json').read_bytes());render=json.loads((b/'f03-main-ui-r2/report.json').read_bytes());desktop=json.loads((b/'f03-main-ui-r2/terminal.original.json').read_bytes())
assert build['exit']==0 and native['ok'] and not native['errors'] and render['ok'] and render['screenshots']==33 and not render['layout_errors']
assert desktop['native_exit']==0 and desktop['all_checked_threads_private'] and desktop['input_desktop_unchanged'] and desktop['desktop_switch_calls']==0 and desktop['source_unchanged']
def tree(ref):
    raw=subprocess.check_output(['git','ls-tree','-rz',ref]);return {row.split(b'\t',1)[1].decode():row.split(b'\t',1)[0].decode() for row in raw.split(b'\0') if row}
target=tree(info['target']);common=tree(info['common']);current=tree(info['head']);source_audit=info['source_audit']
permitted={'client/ui/i18n.gd','client/tests/branch_sync_compatibility.gd','client/tests/ui_branch_sync_preview.gd','client/tests/ui_branch_sync_preview.tscn'}
assert all(current[n]==target[n] for n in source_audit['target_only_files'] if n not in permitted)
runtime_changes=[n for n in common if n.startswith(('server/src/','protocol/')) and current.get(n)!=common[n]];assert not runtime_changes
assert current['client/data/catalog.json']==common['client/data/catalog.json']
legacy_paths=['client/data/season_templates.json','client/data/season_transition_rules.json','config/season_templates.json','config/season_transition_rules.json']
assert all(current[n]==target[n] for n in legacy_paths)
consumers=[]
for p in (work/'client').rglob('*.gd'):
    if 'tests' in p.relative_to(work).parts:continue
    content=p.read_text('utf-8-sig')
    if any(term in content for term in ['season_templates','season_transition_rules','cleared_on_expedition']):consumers.append(p.relative_to(work).as_posix())
assert not consumers
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
for label,command in [('static-documents',['python',str(work/'tools/tests/test_branch_static_documents.py')]),('protocol',['python',str(work/'tools/generate_network_protocol.py'),'--check'])]:
    r=guard.guarded_run(command,env=dict(os.environ),timeout=30,wait_seconds=30);(out/(label+'.original.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
status=subprocess.check_output(['git','-C',str(work),'status','--porcelain','-z']).decode().split('\0');names=[s[3:] for s in status if s]
assert len(names)==840 and all(s.startswith(' M client/assets/') and s.endswith('.import') for s in status if s)
assert all((work/n).resolve().is_relative_to(work) for n in names)
hashes={n:sha(work/n) for n in names};archive=out/'generated-importer-metadata.original.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz') as tar:
    for n in names:tar.add(work/n,arcname=n,recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    assert len(tar.getmembers())==840
    for member in tar.getmembers():assert hashlib.sha256(tar.extractfile(member).read()).hexdigest()==hashes[member.name]
(out/'generated-importer-metadata.original.json').write_text(json.dumps(hashes,indent=2)+'\n')
spec_path=out/'generated-importer-paths.original.nul';spec_path.write_bytes(b'\0'.join(n.encode() for n in names)+b'\0')
subprocess.run(['git','-C',str(work),'restore','--worktree','--pathspec-from-file='+str(spec_path),'--pathspec-file-nul'],check=True)
assert not subprocess.check_output(['git','-C',str(work),'status','--porcelain'])
ref='refs/heads/codex/season-balance-main-candidate-20261107';assert not subprocess.check_output(['git','ls-remote','--heads','origin',ref],timeout=45)
r=guard.guarded_run(['git','push','origin',info['head']+':'+ref],env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),timeout=120,wait_seconds=30)
(out/'candidate-push.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
remote=subprocess.check_output(['git','ls-remote','--heads','origin',ref],timeout=45).decode().split()[0];assert remote==info['head']
proof=dict(common=info['common'],target=info['target'],candidate=info['head'],remote_ref=ref,remote_sha_verified=True,
    target_only_files_preserved_except_explicit_adapter_fixture_changes=True,server_and_protocol_changes_from_common=runtime_changes,
    legacy_season_documents_preserved=True,legacy_documents_active_client_consumers=consumers,current_typed_catalog_unchanged=True,
    static_document_tests=3,protocol_checked=True,full_solution_release_passed=True,build_source_entries=len(pin),build_source_unchanged=True,
    native_checks=native['checks'],native_product_inputs_unchanged_after_fixture_fix=True,
    render_frames=33,render_checks=len(render['checks']),layout_errors=0,representative_images_directly_reviewed=11,
    private_desktop_checks=desktop['private_desktop_checks'],desktop_switch_calls=0,render_r1_visual_rejected_and_retained=True,
    generated_importer_metadata_archived=840,worktree_clean=True,formal_main_updated=False,production_changed=False,
    F03_accepted=False,whole_progress='33/35',new_gameplay_cases=0,D03_used=308,F01_used=297,B05_used=330)
(out/'final-scope-audit.derived.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
