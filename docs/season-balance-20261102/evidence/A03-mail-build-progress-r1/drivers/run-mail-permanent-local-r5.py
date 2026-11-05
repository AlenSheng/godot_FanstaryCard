from pathlib import Path
import json,hashlib,subprocess,sys,shutil,importlib.util,os
sys.stdout.reconfigure(encoding='utf-8');repo=Path.cwd();base=Path(__file__).parent;out=base/'mail-permanent-local-r5';assert not out.exists();out.mkdir()
names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','server','protocol','config/FantasyCard_Config.xlsx','client/data/catalog.json','client/data/locales','client/data/http_schema.json','client/data/http_endpoints.json','client/data/realtime_schema.json','tools/generate_network_protocol.py']).decode().split('\0');pins={n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in names if n and (repo/n).is_file()};(out/'source-pin.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
for name in pins:
    if name=='config/FantasyCard_Config.xlsx' or name=='client/data/catalog.json' or name.startswith('client/data/locales/') or name.startswith('server/config/') and name.endswith(('.bytes','.sha256','.version.txt')):
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,target)
reference=base/'mail-permanent-local-r3'
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
(out/'unchanged-dependency-reuse.json').write_text(json.dumps(dict(reference_stage=reference.name,production_source_bytes_unchanged=True,only_changed_test_source=changed,dependency_assemblies_sha256=dependencies,all_test_source_compiled=True,source_compile_flags_unchanged=True,guards_unchanged=True),indent=2)+'\n',encoding='utf-8')
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
cmd=['dotnet','test',str(repo/'server/tests/FantasyCard.Server.Tests/FantasyCard.Server.Tests.csproj'),'--artifacts-path',str(out/'build'),'--no-restore','-p:BuildProjectReferences=false','--filter','FullyQualifiedName~MailClaimContractTests|FullyQualifiedName~MailTemplateEncodingTests|FullyQualifiedName~SystemMailCatalogTests|FullyQualifiedName~JourneyRewardEncodingTests|FullyQualifiedName~SeasonShopEncodingTests','--logger','trx;LogFileName=mail-local.trx','--results-directory',str(out/'results'),'--verbosity','minimal','-m:1','-p:UseSharedCompilation=false']
try:r=guard.guarded_run(cmd,env=dict(os.environ,DOTNET_CLI_UI_LANGUAGE='en',DOTNET_CLI_TELEMETRY_OPTOUT='1',DOTNET_NOLOGO='1',FANTASYCARD_TEST_POSTGRES=''),timeout=240,wait_seconds=60)
except Exception as error:
    (out/'interrupted.original.json').write_text(json.dumps(dict(error_type=type(error).__name__,error=str(error),output=str(getattr(error,'output','')),command=cmd),indent=2)+'\n',encoding='utf-8');raise
(out/'build-and-tests.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');proof=dict(exit=r.returncode,source_unchanged=all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pins.items()),command=cmd,database_used=False,rendered_frames=False,new_full_routes=0,new_encounters=0);(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print((r.stdout+r.stderr)[-12000:]);print(json.dumps(proof));assert r.returncode==0 and proof['source_unchanged']
