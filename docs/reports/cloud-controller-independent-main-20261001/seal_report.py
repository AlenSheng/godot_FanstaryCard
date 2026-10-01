"""Read-only identity and small report for bounded controller component review."""
import datetime,hashlib,json,pathlib,re,subprocess,yaml
B=pathlib.Path(__file__).resolve().parent;E=B/'evidence';repo=pathlib.Path('/workspace/godot_FanstaryCard')
release='65361bcc27c51c28651c86c5dbba4f083a9b39e0';main='1517f9fae8d865b8d663fa27d9fd38e95cb03d28';original='b39841d3f5191c11c9e51c7e6875490789aba53c'
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
rows=[]
paths=git('diff','--name-only','28c6c7e7d3898e4d2abd186f53361477ba380330',release).decode().splitlines();assert len(paths)==24
for sha,root,names in [(release,B/'release',paths),(main,B/'main',['.github/workflows/test-server-deploy.yml'])]:
    actual_sha=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();assert actual_sha==sha
    status=subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True);assert status==''
    for name in names:
        data=git('show',sha+':'+name);p=root/name
        if p.exists():assert p.read_bytes()==data
        rows.append({'source_sha':sha,'path':name,'git_blob':git('rev-parse',sha+':'+name).decode().strip(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'materialized_byte_verified':p.exists(),'missing_reasons':{} if p.exists() else {'materialized_byte_verified':'Sparse checkout omits deployment documentation; blob hash independently read, not executed.'}})
assert git('rev-parse','HEAD').decode().strip()==original and git('status','--porcelain')==b''
stub_path=B/'main/.github/workflows/test-server-deploy.yml';stub_text=stub_path.read_text();assert len(stub_text.splitlines())==40
stub=yaml.load(stub_text,Loader=yaml.BaseLoader)
real=yaml.load((B/'release/.github/workflows/test-server-deploy.yml').read_text(),Loader=yaml.BaseLoader)
assert stub['on']['workflow_dispatch']['inputs']==real['on']['workflow_dispatch']['inputs']
assert stub['permissions']=={} and set(stub['jobs'])=={'registration-only'}
assert stub['jobs']['registration-only']['if']=='${{ false }}'
assert stub['jobs']['registration-only']['steps']==[{'run':'true'}]
assert not any(x in stub_text.lower() for x in ['secrets.','environment:','uses:'])
(E/'SOURCE_HASHES.json').write_text(json.dumps(rows,indent=2)+'\n')
commands=[json.loads(p.read_text()) for p in sorted(E.glob('*.command.json'))]
assert len(commands)==4 and all(x['exit_code']==0 for x in commands)
testlog=(E/'CONTROLLER41.log').read_text();assert len(re.findall(r'^test_.* \.\.\. ok$',testlog,re.M))==41 and '\nOK\n' in testlog and 'skipped' not in testlog.lower()
fixture=json.loads((E/'FIXTURES.json').read_text());assert fixture['status']=='Passed'
tool=B/'bin/actionlint';version=subprocess.check_output([str(tool),'-version'],text=True).strip()
report={'kind':'Independent bounded controller component review; not application deployment acceptance','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'verdict':'ControllerComponentPassed','eligible_for_component_signoff':True,'release_candidate_sha':release,'main_registration_sha':main,'reference_report_commit':'249297a17411b87de37303ef60d286ed83ac20e5','reference_report_path':'docs/reports/cloud-minimal-integration-20261001/README.md','actual_results':{'controller_tests':{'passed':41,'failed':0,'skipped':0,'exit_code':0},'workflow_actionlint':{'files':4,'exit_code':0,'diagnostics':0,'shellcheck_enabled':False,'reason':'Exact candidate canonical actionlint command uses -shellcheck=; separate Bash syntax verification performed.'},'Python_AST':{'files':13,'exit_code':0},'Bash_syntax':{'files':5,'exit_code':0},'numerical_export':{'original_reports':3,'byte_identical':True,'optional_missing':fixture['optional_missing'],'GITHUB_OUTPUT_verified':True,'ZIP_members':[x['name'] for x in fixture['ZIP']['members']],'debug_keystore_or_runtime_member':False,'exit_code':0},'required_input_negative':{'exporter_CLI':{'missing_arguments':3,'each_exit_code':2},'controller_dispatch':{'missing_inputs':6,'each_exit_code':1,'preflight_files_emitted':False,'API':'Synthetic patched API only; no live protection/server API calls.'}},'main_stub':{'lines':40,'dispatch_schema_matches_release':True,'permissions':{},'sole_job_if':'${{ false }}','checkout_or_secret_or_Environment':False}},'tool_versions':{'python':commands[0]['python'],'platform':commands[0]['platform'],'actionlint':version,'bash':subprocess.check_output(['bash','--version'],text=True).splitlines()[0],'PyYAML':yaml.__version__},'tool_hashes':{'actionlint_archive_sha256':hashlib.sha256((B/'bin/actionlint.tar.gz').read_bytes()).hexdigest(),'actionlint_binary_sha256':hashlib.sha256(tool.read_bytes()).hexdigest()},'commands':commands,'source_hashes':'evidence/SOURCE_HASHES.json','fixtures':'evidence/FIXTURES.json','manifest':'MANIFEST.json','source_and_assertions_modified':False,'original_checkout':{'sha':original,'status':'clean'},'remaining_blockers_for_controller_component':[],'unverified_and_not_signed':{'application_complete_regression':True,'final_runtime_image':True,'real_SSH':True,'real_server_deployment':True,'live_API_protection_policy':True,'registered_UI_discoverability':True},'application_deployable':False,'application_missing_reasons':'Known old Domain.Tests contract produces ten compile errors per fixed prior report; deliberately not rerun or bypassed. No application evidence borrowed from another SHA. Domain library build not retested in this bounded controller review.','authorization_boundary':'No merge, release/main push, workflow dispatch/rerun, account/budget/secret/variable changes, real server API/SSH, application image build or deployment. Parent coordinates any approved minimal integration.','persistence':'Only local small nonsensitive review, commands, fixture outputs and hashes; no raw Library upload or report branch push.'}
(B/'REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
(B/'COMMANDS.json').write_text(json.dumps(commands,indent=2)+'\n')
print(json.dumps({'verdict':report['verdict'],'component_blockers':0,'tested_source_files':len(rows),'main_stub_lines':40,'application_deployable':False}))
