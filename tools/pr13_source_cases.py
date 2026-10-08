"""Actual SDK/source/config rejection fixtures and readonly current export parity."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import pr13_stages as stages
from tools.gameplay_load_validation import provenance

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--config-export',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    plan_path=ROOT/stages.PLAN;contracts={c['id']:c for pkg in json.loads(plan_path.read_text(encoding='utf8'))['packages'] for task in pkg['subtasks'] for c in task['test_cases']};records=[]
    def record(cid,actual,passed,profiles=None):records.append({'case_id':cid,'executed':True,'status':'Passed' if passed else 'Failed','setup':contracts[cid]['setup_and_injection'],'expected':contracts[cid]['expected'],'actual':actual,'profiles_executed':profiles or ['OFFLINE'],'scope':'Actual isolated source/SDK/config compiler/filesystem entries and readonly recorded inputs; no historical runtime recovery, PG rollback or production health claim'})
    required_sha=sha(ROOT/'server/global.json')
    unavailable=stages.sdk_info(executable=out/'missing-sdk/dotnet.exe')
    with patch.object(stages,'sdk_info',return_value=unavailable):
        summary=stages.freeze(out/'sdk-missing-stage',config_export=args.config_export.resolve())
    missing=stages.read(out/'sdk-missing-stage/LOAD-11.1/report.json')
    record('LOAD-11.1-T03',{'native_sdk_lookup':unavailable,'frozen_task_state':missing['status'],'required_version':missing['tool_versions']['dotnet_required'],'global_json_unchanged':sha(ROOT/'server/global.json')==required_sha},not unavailable['available'] and missing['status']=='Blocked' and missing['tool_versions']['dotnet_required']=='10.0.400' and sha(ROOT/'server/global.json')==required_sha)
    refs=stages.source_references('a33f58f','cb96d16')
    record('LOAD-11.1-T01',refs,refs['different_sources'] is True and not refs['runtime_execution_verified'],['OFFLINE','AUDIT'])
    advanced=stages.source_references('HEAD','086e083')
    record('PR13-A08.1-T01',advanced,advanced['different_sources'] is True and not advanced['runtime_execution_verified'],['OFFLINE','AUDIT'])
    with tempfile.TemporaryDirectory(dir=out) as directory:
        repo=Path(directory);(repo/'hooks').mkdir();(repo/'fixture.py').write_bytes(b'value=1\n')
        def git(*argv):return subprocess.run(['git','-c','core.hooksPath='+str(repo/'hooks'),*argv],cwd=repo,capture_output=True,text=True,encoding='utf8',timeout=10,check=True)
        git('init','--quiet');git('add','fixture.py');git('-c','user.name=PR13 Fixture','-c','user.email=fixture@invalid.local','commit','--quiet','-m','owned source fixture')
        before=provenance(repo,('fixture.py',));(repo/'fixture.py').write_bytes(b'value=2\n');after=provenance(repo,('fixture.py',))
        record('PR13-A08.1-T02',{'before':before,'after':after},before['git_dirty'] is False and after['git_dirty'] is True and before['git_commit']==after['git_commit'] and before['sha256']!=after['sha256'],['OFFLINE','AUDIT'])
    policy=stages.default_policy(ROOT/'client/data/catalog.json');catalog=json.loads((ROOT/'client/data/catalog.json').read_text(encoding='utf8'));catalog['tables']['NumericalRules'][0]['cards_spent_draw']=True
    candidate=out/'controlled-on-catalog.json';write(candidate,catalog);rejected=False
    try:stages.default_policy(candidate)
    except ValueError:rejected=True
    record('PR13-B12.3-T03',{'formal_default':policy,'isolated_on_input_rejected':rejected,'formal_source_unchanged':sha(ROOT/'server/global.json')==required_sha},rejected and policy['cards_spent_draw'] is False)
    exported=args.config_export.resolve();identity=stages.config_identity();pairs=[]
    for sub,published in [('server','server/config/generated'),('client','client/data/generated')]:
        file=exported/sub/'fantasycard.config.bytes';target=ROOT/published/'fantasycard.config.bytes'
        pairs.append({'side':sub,'actual_export_sha256':sha(file),'published_sha256':sha(target),'equal':file.read_bytes()==target.read_bytes()})
    record('PR13-B12.3-T01',{'pairs':pairs,'current_workbook_sha256':identity['source_sha256'],'native_compiler_export':True},all(p['equal'] for p in pairs),['OFFLINE','AUDIT'])
    bad=out/'altered-export';(bad/'server').mkdir(parents=True);(bad/'client').mkdir()
    for sub in ('server','client'):
        source=exported/sub/'fantasycard.config.bytes';(bad/sub/source.name).write_bytes(source.read_bytes()+b'X')
    refused=False
    try:stages.freeze(out/'inconsistent-export-stage',config_export=bad)
    except ValueError as error:refused='re-export differs' in str(error)
    record('PR13-B12.1-T01',{'source_export_mismatch_rejected':refused,'runtime_stage_created':(out/'inconsistent-export-stage').exists(),'published_package_hashes_unchanged':all(p['published_sha256']==identity['bytes_sha256'] for p in pairs)},refused and not (out/'inconsistent-export-stage').exists(),['OFFLINE','AUDIT'])
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in records).encode())
    write(out/'report.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'plan_sha256':sha(plan_path),'source':{'scope':'actual SDK/Git/config filesystem source contracts','input_hashes':{p:sha(ROOT/p) for p in ('tools/pr13_source_cases.py','tools/pr13_stages.py','tools/gameplay_load_validation.py','server/global.json','client/data/catalog.json','config/FantasyCard_Config.xlsx')}},'executed':len(records),'passed':sum(r['status']=='Passed' for r in records),'accepted':False})
    print(json.dumps({'executed':len(records),'passed':sum(r['status']=='Passed' for r in records)}));return 0 if all(r['status']=='Passed' for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
