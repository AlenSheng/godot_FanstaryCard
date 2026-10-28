
import hashlib,importlib.util,json,os,random,shutil,sys,time
from pathlib import Path
assert sys.platform.startswith('linux')
OUT=Path('/evidence');ROOT=Path('/inputs');SOURCE='0d56ceccf526f6ae8973f57da152d67faf93a5d5'
spec=importlib.util.spec_from_file_location('frozen_preregistered_statistics','/frozen_analysis.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
receipts=[]
def rejected(name,root,source):
 try:m.analyze(root,source,10000)
 except (ValueError,KeyError) as e:receipts.append({'control':name,'rejected':True,'error':type(e).__name__,'detail':str(e)})
 else:raise AssertionError('Invalid formal evidence accepted: '+name)
empty=OUT/'empty-negative-input';empty.mkdir();rejected('missing_all_nine_formal_units',empty,SOURCE)
rejected('wrong_frozen_source',ROOT,'0'*40)
smoke=OUT/'smoke-negative-input';d=smoke/'Mage-479001';d.mkdir(parents=True)
shutil.copyfile('/smoke/result.json',d/'result.json');(d/'routes.jsonl').write_text('')
rejected('actual_development_smoke_cannot_count_as_formal',smoke,SOURCE)
duplicate=OUT/'duplicate-negative-input';duplicate.mkdir()
# The duplicate is rejected while reading the first unit; no additional unit
# materialization or links to transient container mount paths are required.
original=ROOT/'Mage-479001';dest=duplicate/'Mage-479001';dest.mkdir()
for name in ('result.json','render-vectors.jsonl'):shutil.copyfile(original/name,dest/name)
p=dest/'routes.jsonl'
with (original/'routes.jsonl').open('rb') as f,p.open('xb') as out:
 first=f.readline();out.write(first);out.write(first)
 shutil.copyfileobj(f,out,65536)
rejected('duplicate_seed_capacity_row',duplicate,SOURCE)
z=m.paired_binary_bootstrap([0]*3000,10000,random.Random(482999));assert z['precision_insufficient'] and z['empirical_degenerate_interval_is_not_proof_of_zero_population_effect'] and z['discordant_seed_pairs']==0
receipts.append({'control':'zero_discordance_is_Inconclusive_not_zero_population_effect','rejected':True,'interval':z})
(OUT/'negative-controls.json').write_text(json.dumps({'ok':True,'controls':receipts,'native_formal_samples_added':0,'controls_not_game_results':True},indent=2)+'\n')
began=time.monotonic();result=m.analyze(ROOT,SOURCE,10000);assert result['ok'] and result['formal_native_units']==9 and result['formal_routes']==36000
(OUT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
completion={'ok':True,'frozen_native_source_sha':SOURCE,'statistics_sha256':hashlib.sha256(Path('/frozen_analysis.py').read_bytes()).hexdigest(),'formal_routes':36000,'formal_units':9,'bootstrap_resamples_per_primary':10000,'validity_negative_controls_passed':len(receipts),'analysis_wall_seconds':time.monotonic()-began,'decision':result['decision'],'MAIN_accepted':False,'current_Godot_RENDER_pending':True,'cloud_only_execution':True}
(OUT/'inner-result.json').write_text(json.dumps(completion,indent=2)+'\n');print(json.dumps(completion))
