from pathlib import Path

base=Path(__file__).parent;source=(base/'run-mail-permanent-local-r4.py').read_text('utf-8').replace('mail-permanent-local-r4','mail-permanent-local-r5')
needle="spec=importlib.util.spec_from_file_location('fixture_runtime'"
assert needle in source
addition='''reference=base/'mail-permanent-local-r3'
previous=json.loads((reference/'source-pin.json').read_text('utf-8'))
changed=[n for n,h in previous.items() if hashlib.sha256((repo/n).read_bytes()).hexdigest()!=h]
assert changed==['server/tests/FantasyCard.Server.Tests/Persistence/PostgresMailPermanentCopyTests.cs']
shutil.copytree(reference/'build',out/'build',copy_function=shutil.copy2)
components=['FantasyCard.Contracts','FantasyCard.Domain','FantasyCard.Server','FantasyCard.ConfigExporter']
dependencies={}
test_bin=out/'build/bin/FantasyCard.Server.Tests/debug';test_bin.mkdir(parents=True,exist_ok=True)
for component in components:
    root=reference/'build/bin'/component/'debug'
    assembly=root/(component+'.dll');assert assembly.exists()
    dependencies[component]=hashlib.sha256(assembly.read_bytes()).hexdigest()
    for p in root.iterdir():
        if p.is_file() and p.suffix in ('.dll','.pdb','.json','.exe'):
            target=test_bin/p.name
            if not target.exists():shutil.copy2(p,target)
(out/'unchanged-dependency-reuse.json').write_text(json.dumps(dict(reference_stage=reference.name,production_source_bytes_unchanged=True,only_changed_test_source=changed,dependency_assemblies_sha256=dependencies,all_test_source_compiled=True,source_compile_flags_unchanged=True,guards_unchanged=True),indent=2)+'\\n',encoding='utf-8')
'''
source=source.replace(needle,addition+needle)
source=source.replace("'--artifacts-path',str(out/'build'),", "'--artifacts-path',str(out/'build'),'--no-restore','-p:BuildProjectReferences=false',")
target=base/'run-mail-permanent-local-r5.py';assert not target.exists();target.write_text(source,encoding='utf-8');compile(source,str(target),'exec');print(str(target))
