from pathlib import Path
import collections,hashlib,json,statistics,xml.etree.ElementTree as ET

base=Path(__file__).parent;out=base/'d03-entry-calibration-inspection-r1.derived.json';assert not out.exists();summaries=[];source={}
stages=[('d03-support-r1',12),('d03-d0-candidates-r1',12),('d03-d0-holdout-r1',6),('d03-d0-holdout-control-r1',6),('d03-formal16-routes-r1',6)]
for name,n in stages:
    root=base/name;run=json.loads((root/'result.json').read_bytes());assert run['exit']==0 and run['actual_started']==n and all(run[k] for k in ['source_unchanged','binary_unchanged','workbook_unchanged','roster_identity_match'])
    p=root/'observations';rows=[json.loads(x) for x in (p/'routes.original.jsonl').read_text('utf-8').splitlines()];events=[json.loads(x) for x in (p/'events.original.jsonl').read_text('utf-8').splitlines()];assert len(rows)==n
    by_version=collections.defaultdict(list);casts=resources=0
    for row in rows:
        sc=row['scenario'];ee=[x for x in events if x.get('Id',x.get('scenario',x.get('result',{}).get('scenario',{})).get('Id'))==sc['Id']];start=ee[0];assert start['kind']=='start' and ee[-1]['result']==row and sc['Difficulty']==0
        assert start['player']['WornArmor']==[] and start['player']['Inventory']['Items']==[];assert sc['Loadout'] in ['support-mix','support-guard'];by_version[start['Version']].append(row)
        aa=[x for x in ee if x['kind']=='cast'];assert len(aa)==row['casts'];assert all(y['seconds']-x['seconds']>=1-1e-9 for x,y in zip(aa,aa[1:]));assert all(not x['resolution']['ActionReplayed'] and 1<=x['previews']<=3 for x in aa)
        starts=[x for x in ee if x['kind']=='encounter-start'];ends=[x for x in ee if x['kind']=='encounter-end'];assert len(starts)==len(ends)
        for a,b in zip(starts,ends,strict=True):
            assert a['pathIndex']==b['pathIndex'];cc=[x for x in aa if x['pathIndex']==a['pathIndex']];rr=[x for x in ee if x['kind']=='resource' and x['pathIndex']==a['pathIndex']]
            assert b['damage']==sum(x['resolution']['HpDamage']+x['resolution']['ShieldDamage'] for x in cc) and b['damage']==b['initialHp']+b['initialShield']+b['hpAdded']+b['shieldAdded']-b['hpOtherLoss']-b['shieldDiscarded']-b['remainingHp']-b['remainingShield'];resources+=len(rr)
        assert row['snapshot']['Map']==start['map'];actor=row['snapshot']['Players'][0]
        if row['outcome']=='Extracted':assert actor['Phase']==5 and actor['ExtractionCompletedAt']==row['expectedExtraction']
        else:assert row['outcome']=='Dead' and actor['Combat']['Hp']==0
        casts+=len(aa)
    summaries.append(dict(stage=name,cases=n,outcomes=dict(collections.Counter(x['outcome'] for x in rows)),versions={k:dict(collections.Counter(x['outcome'] for x in v)) for k,v in by_version.items()},casts=casts,resource_changes=resources))
    for file in [root/'result.json',p/'attempts.original.jsonl',p/'routes.original.jsonl',p/'events.original.jsonl']:source[file.relative_to(base).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
assert summaries[0]['outcomes']=={'Dead':12} and summaries[2]['outcomes']=={'Extracted':6} and summaries[3]['outcomes']=={'Dead':3,'Extracted':3}
formal=summaries[-1];assert formal['outcomes']=={'Extracted':6} and set(formal['versions'])=={'season-v1-config-16'}
budget=json.loads(Path('docs/season-balance-20261102/D03-BUDGET.json').read_bytes());assert budget['used']==114 and budget['remaining']==186 and budget['current_handle'] is None
result=dict(status='D03_entry_fix_observed_formal16_local_not_whole_acceptance',new_matches=42,stages=summaries,selected_D0_hp_shield_basis=5000,damage_interval_rewards_playerHP_unchanged=True,workbook_only2cells_changed=True,old15_retained=True,formal16_fresh6_extracted=True,
    source_sha256=source,D03_complete=False,D03_used=114,D03_remaining=186,population_P50_P90_and_class15_not_passed=True,branch_income_not_merged_into_observed_banks=True,production_not_activated=True)
out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
