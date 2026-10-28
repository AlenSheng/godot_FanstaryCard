"""Verify native Guardian state ledgers before declaring any case coverage."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from pr13_raw_storage import open_raw, raw_input
from pr13_candidate_review import paired_clusters

STEPS = [1, 1, 2, 2, 3, 3]
FIVE = [5, 7, 9, 11, 13, 15]
BONUSES = [[1]*5, [1,1,2,1,2], [1,2,2,2,2], [2,2,2,2,3], [2,3,2,3,3], [3]*5]
REMAINDERS = [[0]*5, [4,8,2,6,0], [8,6,4,2,0], [2,4,6,8,0], [6,2,8,4,0], [0]*5]
CASE_SCENARIOS = {'PR13-B07.3-T01': {'preview-and-rejections'}, 'PR13-B07.3-T02': {'five-successful-plays','already-full','zero-empty','zero-full','exact-fill','overflow'}, 'PR13-B07.3-T03': {'json-pvp-restoration','legal-map-leave'}}


def require(ok, reason):
    if not ok: raise ValueError(reason)


def digest(raw): return hashlib.sha256(raw).hexdigest()


def validate_trace(row):
    require(row.get('Error') is None and row.get('Passed') is True, 'Native error/incomplete sequence retained')
    level=row['Level']; candidate=row['Candidate']; policy=2 if candidate else 1
    require(type(level) is int and 0<=level<=5 and type(candidate) is bool and row['Profile']==('Candidate' if candidate else 'Baseline'), 'Profile/level identity differs')
    states={}
    for identity,text in row['States'].items():
        require(isinstance(text,str) and digest(text.encode())==identity, 'Full original state hash differs')
        states[identity]=json.loads(text)
    require(row['NamedStates'] and all(h in states for h in row['NamedStates'].values()), 'Missing named full state')
    observations=row['Observations']; actual={}; found=defaultdict(set)
    require(len(observations)==9, 'Incomplete native scenarios')
    for observation in observations:
        cid=observation['case_id']; scenario=observation['scenario']
        require(cid in CASE_SCENARIOS and scenario in CASE_SCENARIOS[cid] and scenario not in actual and observation['passed'] is True, 'Unknown/duplicate/unpassed scenario')
        found[cid].add(scenario); actual[scenario]=observation['actual']
    require(dict(found)==CASE_SCENARIOS, 'Missing canonical case scenario')
    def state(identity):
        require(identity in states,'Missing actual state reference'); return states[identity]
    a=actual['preview-and-rejections']; before=state(a['before']); after=state(a['after'])
    require(a['previews']==10 and len(a['preview_state_sha256'])==10 and set(a['preview_state_sha256'])=={a['before']}, 'Preview full-state mutation or missing preview')
    require(len(a['rejects'])==4 and {r['fault'] for r in a['rejects']}=={'missing-target','future-revision','duplicate-instances','missing-instance'} and all(r['rejected'] is True and r['state_sha256']==a['before'] for r in a['rejects']), 'Missing rejection/full-state purity')
    old=before['Players'][0]['Combat']; new=after['Players'][0]['Combat']
    require(old['GuardianPolicy']==new['GuardianPolicy']==policy and old['GuardianShieldRemainderTenths']==(8 if candidate else 0), 'Frozen policy/remainder differs')
    expected_remainder=[8,2,6,0,4,8][level] if candidate else 0
    expected_gain=(7+[1,2,2,3,3,3][level]) if candidate else 7+STEPS[level]
    require(new['Shield']==a['resolution']['ShieldGain']==expected_gain and a['remainder']==new['GuardianShieldRemainderTenths']==expected_remainder, 'First play golden state differs')
    require(a['spent_instance_rejected'] is True and len(old['Deck']['Hand'])==1 and old['Deck']['Hand'][0]['InstanceId']==a['spent_instance'] and not new['Deck']['Hand'] and len(new['Deck']['Discard'])==1 and new['Deck']['Discard'][0]['InstanceId']==a['spent_instance'], 'Spent instance was not consumed exactly once')
    require(after['Revision']==before['Revision']+1 and a['resolution']['RoomRevision']==after['Revision'], 'Successful play revision differs')
    a=actual['five-successful-plays']; steps=a['steps']; total=0; ids=set()
    require(len(steps)==5, 'Five successful plays missing')
    for index,step in enumerate(steps):
        s=state(step['state']); gain=7+(BONUSES[level][index] if candidate else STEPS[level]); total+=gain
        require(step['play']==index and step['shield_gain']==gain and s['Shield']==total and s['GuardianPolicy']==policy and s['GuardianShieldRemainderTenths']==(REMAINDERS[level][index] if candidate else 0), 'Five-play trajectory golden state differs')
        require(step['instance_id'] not in ids and len(s['Deck']['Hand'])==4-index and len(s['Deck']['Discard'])==index+1 and s['Deck']['Discard'][-1]['InstanceId']==step['instance_id'], 'Five-play instances/counts differ'); ids.add(step['instance_id'])
    expected_weapon=FIVE[level] if candidate else STEPS[level]*5
    require(a['total']==a['expected']==total==35+expected_weapon and a['weapon_contribution']==row['FiveWeaponContribution']==expected_weapon, 'Five-play contribution differs')
    for scenario in ['already-full','zero-empty','zero-full','exact-fill','overflow']:
        a=actual[scenario]; old=state(a['before']); new=state(a['after'])
        initial=50 if scenario in ['already-full','zero-full'] else 50-(7+STEPS[level]) if scenario=='exact-fill' else 49 if scenario=='overflow' else 0
        gain=7+STEPS[level] if scenario=='exact-fill' else 1 if scenario=='overflow' else 0
        remainder=4 if candidate and scenario not in ['exact-fill','overflow'] else 0
        require(old['Shield']==initial and old['GuardianShieldRemainderTenths']==(4 if candidate else 0) and new['GuardianPolicy']==old['GuardianPolicy']==policy, 'Cap setup policy/remainder differs')
        require(a['ShieldGain']==a['expectedGain']==gain and a['expectedRemainder']==new['GuardianShieldRemainderTenths']==remainder and new['Shield']==initial+gain, 'Cap/zero golden outcome differs')
    a=actual['json-pvp-restoration']
    require(isinstance(a['saved_room_json'],str) and digest(a['saved_room_json'].encode())==a['saved_room_sha256'] and a['saved_room_json']==a['restored_room_json'], 'Whole room JSON restoration differs')
    require(a['frozen']==a['after'] and a['frozenPve']==a['after_pve_battle'] and a['during']!=a['frozen'], 'Frozen combat/PVE recovery differs')
    frozen=state(a['frozen']); during=state(a['during']); saved=json.loads(a['saved_room_json']); pvp=json.loads(a['pvp_room_json'])
    require(saved['Players'][0]['Combat']==frozen and pvp['Duels'] and any(p['Combat']==during for p in pvp['Players']), 'Actual saved/PVP room states missing')
    require(during['GuardianPolicy']==frozen['GuardianPolicy']==policy and a['pvp_resolution']['ShieldGain']>0, 'Actual PVP play or policy missing')
    a=actual['legal-map-leave']; old=state(a['beforeMove']); new=state(a['after'])
    require(a['target'] in a['legal_moves'] and a['target']==a['actual_position'] and a['target']!=a['from'] and a['generated_map_seed']==row['Seed'] and a['action_bar_phase_injected'] is True, 'Actual legal generated-map move missing')
    require(old['Shield']==9 and old['GuardianShieldRemainderTenths']==(4 if candidate else 0) and new['Shield']==new['GuardianShieldRemainderTenths']==0 and new['GuardianPolicy']==policy, 'Legal leave did not clear shield and remainder')
    return expected_weapon


def validate_block(directory, *, expected_source=None):
    directory=Path(directory); manifest=json.loads((directory/'manifest.json').read_text('utf8')); summary=json.loads((directory/'summary.json').read_text('utf8')); native=json.loads((directory/'summary.native.json').read_text('utf8'))
    require(manifest['Schema']=='guardian_authoritative_sequences_v1' and manifest['Profiles']==['Baseline','Candidate'] and manifest['WeaponLevels']==list(range(6)) and manifest['CardsPerSequence']==5, 'Frozen native schema differs')
    require(expected_source is None or manifest['SourceSha']==expected_source, 'Native source differs')
    n=manifest['Samples']; start=manifest['SeedStart']; require(type(n) is int and 1<=n<=1000 and type(start) is int and start>0, 'Bounded native block required')
    require(summary['Native']==native and native['Passed'] is True and native['ErrorCount']==0 and native['RowCount']==12*n and native['SourceSha']==manifest['SourceSha'] and native['Samples']==n and native['SeedStart']==start, 'Native completion/source/count differs')
    path,compressed,size=raw_input(directory,summary); require(size==native['RawBytes'],'Original native byte count differs')
    seen=set(); values=[]
    with open_raw(path,compressed) as stream:
        for line in stream:
            require(len(line)<=1024*1024,'Native row exceeds declared bound'); row=json.loads(line); key=(row['Seed'],row['Level'],row['Profile'])
            require(key not in seen and start<=row['Seed']<start+n,'Duplicate or outside frozen seed unit');seen.add(key)
            values.append({'seed':row['Seed'],'level':row['Level'],'profile':row['Profile'],'weapon_contribution':validate_trace(row)})
    required={(seed,level,profile) for seed in range(start,start+n) for level in range(6) for profile in ['Baseline','Candidate']}
    require(seen==required,'Incomplete paired level/seed coverage')
    return {'source_sha':manifest['SourceSha'],'seed_start':start,'samples':n,'rows':len(seen),'raw_bytes':size,'raw_sha256':native['RawSha256'],'stored_sha256':summary['RawStorage']['stored_sha256'],'stored_bytes':summary['RawStorage']['stored_bytes'],'values':values}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--source-sha',required=True);args=p.parse_args()
    blocks=[validate_block(d,expected_source=args.source_sha) for d in args.inputs];values=[v for b in blocks for v in b['values']]
    require(len({(r['seed'],r['level'],r['profile']) for r in values})==len(values),'Mixed/overlapping physical parts')
    required_seeds=set(range(200001,201001))|set(range(201001,202001))|set(range(202001,203001)); levels=[]
    for level in range(6):
        selected=[v for v in values if v['level']==level]
        require({v['seed'] for v in selected}==required_seeds and len(selected)==6000,'Three complete 1000-paired-seed blocks per level required')
        groups={profile:[{'seed':r['seed'],'battle':'five-successful-plays','value':r['weapon_contribution']} for r in selected if r['profile']==profile] for profile in ['Baseline','Candidate']}
        levels.append({'weapon_level':level,'five_play_weapon_contribution':paired_clusters(groups['Baseline'],groups['Candidate']),'golden_contract_violations':0})
    require(len(values)==36000,'Complete original primary budget required')
    report={'ok':True,'source_sha':args.source_sha,'canonical_cases_passed':3,'native_sequence_rows':len(values),'levels':levels,'parents':[{k:v for k,v in b.items() if k!='values'} for b in blocks],'production_activation':False,'accepted':False,'scope':'Injected boundary sequence contracts; descriptive seed-cluster intervals, no full expedition/PVP strength/capacity claim'}
    args.output.mkdir(parents=True,exist_ok=False);(args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in report.items() if k not in ['parents','levels']}))


if __name__=='__main__':main()
