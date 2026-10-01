"""Bounded production CLI/GITHUB_OUTPUT/ZIP fixture; all data is synthetic."""
import hashlib,json,os,pathlib,subprocess,sys,zipfile
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';R=B/'release'
source=E/'numerical-source';source.mkdir();stage=E/'numerical-public';output=E/'numerical-github-output'
payloads={'version.txt':b'4.7.stable.fixture\n','import.log':'Original import fixture diagnostic\n完整诊断\n'.encode(),'numerics.log':b'{"ok":true,"fixture_only":true}\n'}
for name,data in payloads.items():(source/name).write_bytes(data)
for name in ['runtime/data/godot/keystores/debug.keystore','.env','.ssh/id_rsa','credentials.json']:
    p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'PRIVATE_SYNTHETIC_SENTINEL_DO_NOT_EXPORT')
def command(name,argv,env=None):
    run=subprocess.run(argv,cwd=R,env=env or dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=30)
    log=E/(name+'.log');log.write_text(run.stdout+run.stderr)
    return {'name':name,'argv':argv,'cwd':str(R),'exit_code':run.returncode,'log':str(log.relative_to(B)),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
cli=[sys.executable,str(R/'tools/cloud/export_evidence.py'),'--profile','numerical-client','--source',str(source),'--destination',str(stage)]
row=command('numerical-export',cli,dict(os.environ,PYTHONDONTWRITEBYTECODE='1',GITHUB_OUTPUT=str(output)));assert row['exit_code']==0
assert output.read_text()=='artifact_directory='+str(stage)+'\n'
inventory=json.loads((stage/'evidence-inventory.json').read_text())
assert {x['name'] for x in inventory['files']}==set(payloads) and inventory['rejected']==[]
missing=['preview-parity/'+x for x in ['input.json','results.json','manifest.json','server.log','client.log']]
assert inventory['missing']==missing
for name,data in payloads.items():assert (stage/name).read_bytes()==data
archive=E/'numerical-whitelist-fixture.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob('*')):
        if p.is_file():z.write(p,p.relative_to(stage))
with zipfile.ZipFile(archive) as z:
    assert set(z.namelist())==set(payloads)|{'evidence-inventory.json'}
    assert not any('debug.keystore' in x or 'runtime/' in x for x in z.namelist())
    for name,data in payloads.items():assert z.read(name)==data
    members=[{'name':name,'bytes':len(z.read(name)),'sha256':hashlib.sha256(z.read(name)).hexdigest()} for name in z.namelist()]
cli_missing=[]
for flag in ['--profile','--source','--destination']:
    args=cli.copy();at=args.index(flag);del args[at:at+2]
    receipt=command('missing-'+flag[2:],args);assert receipt['exit_code']==2
    cli_missing.append(receipt)
preflight=[]
for name in ['valid','PR_NUMBER','COMMIT_SHA','CONFIRM_SOURCE_SHA','CONFIRM_RESTART','ROLLBACK_BASELINE_SHA','CONFIRM_ROLLBACK_COMPATIBILITY']:
    folder=E/('preflight-'+name);folder.mkdir()
    args=[sys.executable,str(B/'probe_preflight.py'),'--directory',str(folder)]
    if name!='valid':args+=['--omit',name]
    receipt=command('preflight-'+name,args)
    assert receipt['exit_code']==(0 if name=='valid' else 1)
    if name!='valid':assert not (folder/'preflight.json').exists() and not (folder/'github-output').exists()
    preflight.append(receipt)
result={'status':'Passed','source_sha':'65361bcc27c51c28651c86c5dbba4f083a9b39e0','numerical_export':row,'GITHUB_OUTPUT':{'path':str(output.relative_to(B)),'value':output.read_text().strip(),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()},'ZIP':{'path':str(archive.relative_to(B)),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'members':members,'debug_keystore_or_runtime_member':False},'three_reports_byte_identical':True,'optional_missing':missing,'rejected':inventory['rejected'],'export_cli_missing_required':cli_missing,'controller_dispatch_missing_required':preflight,'scope':'Production exporter CLI executed. Six production preflight missing-input probes run in real child processes with fake API patched; no live API/SSH or deployment. Reports are synthetic fixtures, not Godot run evidence.'}
(E/'FIXTURES.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':'Passed','ZIP_members':[x['name'] for x in members],'optional_missing':len(missing),'CLI_missing_required_exit':2,'preflight_missing_inputs_exit':1,'preflight_missing_inputs':6,'live_API_calls':0}))
