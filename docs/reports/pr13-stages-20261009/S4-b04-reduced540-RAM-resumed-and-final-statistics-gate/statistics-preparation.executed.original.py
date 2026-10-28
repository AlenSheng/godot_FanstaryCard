import hashlib,json,runpy,subprocess
from pathlib import Path
R='/opt/fantasycard-github';B=Path('/home/ubuntu/pr13-acceptance-20261009');S='docs/reports/pr13-stages-20261009/S0-b04-final540-statistics-current-RAM-study';E=B/'evidence/B04-reduced-final-statistics-r2-20261014';STUDY=B/'evidence/B04-single-factor-reduced-ram-r3-20261014'
def git(*a):return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*a])
head=git('rev-parse','HEAD').decode().strip();assert head=='c4aa31d52ecb3e8dc9c0da56807c20d21551caf9'
def blob(name):return git('show',head+':'+S+'/'+name)
assert not E.exists();plan=json.loads(blob('analysis-plan.original.json'));assert plan['required_parts']==540 and plan['required_encounters']==21600;raws={r['path']:blob(r['path']) for r in plan['control_files']}
for row in plan['control_files']:
 data=raws[row['path']];assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
assert json.loads(raws['study-plan.original.json'])==json.loads((STUDY/'plan.original.json').read_bytes()) and raws['config-reference.original.json']==(STUDY/'config-reference.original.json').read_bytes();E.mkdir();(E/'analysis-plan.original.json').write_bytes(blob('analysis-plan.original.json'))
for name,data in raws.items():(E/name).write_bytes(data)
n=runpy.run_path(str(E/'controller.original.py'));n['frozen']();st=json.loads(subprocess.check_output(['python3',str(STUDY/'controller.original.py'),'status']));assert st['completed_G_verified_parts']<540
try:n['complete_inputs']();raise RuntimeError('Unexpected incomplete quota acceptance')
except AssertionError as error:assert str(error)=='Revised 540 native and G closures required';rejected=str(error)
v={'ok':True,'current_cloud_release_sha':head,'required_parts':540,'required_encounters':21600,'current_G_closed_parts':st['completed_G_verified_parts'],'actual_control_files_byte_verified':len(plan['control_files']),'active_study_plan_and_reference_exact_equal':True,'incomplete_primary_quota_rejected':True,'rejection':rejected,'statistics_jobs_started':0,'MAIN_accepted':False};(E/'prepared.original.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
