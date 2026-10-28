"""Independent scalar/event reconciliation for actual advancing cap encounters."""
import argparse
from collections import Counter,defaultdict
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

TICKS=10_000_000
ARMS=('BaselinePurple','SingleOrangeHead')
ELEMENTS={'Fire':1,'Wood':2,'Earth':3,'Metal':4,'Water':5}
COMMON=('C01','C02','C03','C04','C05','C06','C07','C17','C18','C20','C25','C26','C27','C29')
BUSINESS_SOURCE_SHA='b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
COLLECTOR_REVISION='cap-effective-raw-budget-v2'
DEFAULT_RAW_UNIT_LIMIT=2*1024**3
RAW_PART_LIMIT=128*1024**2
MAX_RAW_UNIT_LIMIT=32*1024**3
COLLECTOR_FIELDS=('business_source_sha','instrumentation_source_sha','mixed_input_manifest_sha256','collector_revision','raw_unit_limit_bytes',
                  'raw_unit_limit_explicit','event_raw_bytes','collection_complete')
def require(ok,message):
    if not ok:raise ValueError(message)
def near(a,b):return math.isfinite(a) and math.isfinite(b) and abs(a-b)<1e-8
def clamp(value,lo,hi):return max(lo,min(value,hi))

def collection_contract(manifest,summary,source,raw_unit_limit=None,business_source=None,collector_revision=None,
                        instrumentation_source=None,mixed_input_manifest=None):
    """Reconcile collector metadata only; this function executes no combat oracle."""
    require(re.fullmatch('[0-9a-f]{40}',source or '') is not None and
            manifest.get('source_sha')==summary.get('source_sha')==source,'Exact collector source differs')
    schema=manifest.get('schema')
    if schema=='actual_cap_effective_experiment_v2':
        require(type(raw_unit_limit) is int and RAW_PART_LIMIT<=raw_unit_limit<=MAX_RAW_UNIT_LIMIT,
                'New collector requires an explicit expected raw budget')
        require(business_source==BUSINESS_SOURCE_SHA and source!=business_source and
                collector_revision==COLLECTOR_REVISION,'New collector business/source/revision anchor differs')
        require(re.fullmatch('[0-9a-f]{40}',instrumentation_source or '') is not None
                and instrumentation_source!=business_source
                and re.fullmatch('[0-9a-f]{64}',mixed_input_manifest or '') is not None,
                'New collector published code/mixed input anchors are required')
        require(all(key in manifest and key in summary and type(manifest[key]) is type(summary[key])
                    and manifest[key]==summary[key] for key in COLLECTOR_FIELDS),
                'Manifest and summary collector metadata differ')
        require(manifest['business_source_sha']==business_source and manifest['collector_revision']==collector_revision
                and manifest['instrumentation_source_sha']==instrumentation_source
                and manifest['mixed_input_manifest_sha256']==mixed_input_manifest
                and type(manifest['raw_unit_limit_bytes']) is int and manifest['raw_unit_limit_bytes']==raw_unit_limit,
                'Declared collector budget/provenance differs from preregistration')
        require(type(manifest['raw_unit_limit_explicit']) is bool and
                (manifest['raw_unit_limit_explicit'] or raw_unit_limit==DEFAULT_RAW_UNIT_LIMIT),
                'Omitted native budget option must retain the original two GiB default')
        require(manifest['collection_complete'] is True and type(manifest['event_raw_bytes']) is int
                and 0<=manifest['event_raw_bytes']<=raw_unit_limit,'Collector is incomplete or over its cumulative raw budget')
        revision=collector_revision;business=business_source
    else:
        require(schema=='actual_cap_effective_experiment_v1' and
                not any(key in manifest or key in summary for key in COLLECTOR_FIELDS),'Legacy collector schema was mixed or relabeled')
        require(raw_unit_limit in (None,DEFAULT_RAW_UNIT_LIMIT) and business_source in (None,source)
                and collector_revision in (None,'legacy-v1') and instrumentation_source is None
                and mixed_input_manifest is None,'Legacy originals retain their original two GiB contract')
        raw_unit_limit=DEFAULT_RAW_UNIT_LIMIT;revision='legacy-v1';business=source
    parts=summary.get('event_parts')
    require(isinstance(parts,list) and parts,'Original event parts are missing')
    total_raw=total_events=0
    for index,part in enumerate(parts):
        require(isinstance(part,dict) and part.get('path')==f'cap-events-{index:03}.jsonl.gz',
                'Event part sequence contains a gap, duplicate or unsafe path')
        require(type(part.get('raw_bytes')) is int and 0<part['raw_bytes']<=RAW_PART_LIMIT
                and type(part.get('events')) is int and part['events']>0,'Original per-part raw budget/count differs')
        total_raw+=part['raw_bytes'];total_events+=part['events']
    require(total_raw<=raw_unit_limit,'Original event parts exceed the cumulative raw budget')
    require(type(summary.get('actual_casts')) is int and summary['actual_casts']>=0
            and type(summary.get('actual_ticks')) is int and summary['actual_ticks']>=0
            and total_events==summary['actual_casts']+summary['actual_ticks'],'Complete original part/event count differs')
    require(type(summary.get('raw_bytes')) is int and 0<summary['raw_bytes']<=RAW_PART_LIMIT,
            'Original encounter JSONL exceeds its unchanged raw budget')
    if schema=='actual_cap_effective_experiment_v2':
        require(total_raw==manifest['event_raw_bytes']==summary['event_raw_bytes'],
                'Original event raw total differs from complete part metadata')
    return {'collector_revision':revision,'business_source_sha':business,
            **({'instrumentation_source_sha':instrumentation_source,'mixed_input_manifest_sha256':mixed_input_manifest}
               if schema=='actual_cap_effective_experiment_v2' else {}),
            'raw_unit_limit_bytes':raw_unit_limit,'event_raw_bytes':total_raw,
            'original_two_GiB_budget_satisfied':total_raw<=DEFAULT_RAW_UNIT_LIMIT,
            'collector_metadata_complete':True}

def collection_negative_controls(manifest,summary,source,raw_unit_limit=None,business_source=None,collector_revision=None,
                                 instrumentation_source=None,mixed_input_manifest=None):
    """Reject corrupt metadata while preserving the originals and event oracle."""
    rejected=[]
    for name in ('collector-declared-budget-tampered','collector-event-part-missing','collector-cumulative-budget-exceeded'):
        m,s=copy.deepcopy(manifest),copy.deepcopy(summary)
        if name=='collector-declared-budget-tampered':
            m['raw_unit_limit_bytes']=s['raw_unit_limit_bytes']=(raw_unit_limit or DEFAULT_RAW_UNIT_LIMIT)+1
        elif name=='collector-event-part-missing':
            s['event_parts'].pop()
        else:
            limit=raw_unit_limit or DEFAULT_RAW_UNIT_LIMIT
            count=limit//RAW_PART_LIMIT+1
            template=copy.deepcopy(s['event_parts'][0])
            s['event_parts']=[dict(template,path=f'cap-events-{index:03}.jsonl.gz',
                                  raw_bytes=RAW_PART_LIMIT,events=1) for index in range(count)]
            s['actual_casts']=0;s['actual_ticks']=count
            if m['schema']=='actual_cap_effective_experiment_v2':
                m['event_raw_bytes']=s['event_raw_bytes']=count*RAW_PART_LIMIT
        try:collection_contract(m,s,source,raw_unit_limit,business_source,collector_revision,instrumentation_source,mixed_input_manifest)
        except ValueError:rejected.append({'name':name,'rejected':True})
        else:raise ValueError('Corrupt collector metadata accepted: '+name)
    return rejected

def event_contract(row):
    require(row['passed'] is True,'Native cap event failed')
    before=row['before'];after=row['after'];equipment=row['equipment']
    require(before['FenxianPolicy']==after['FenxianPolicy']=='CurrentRhythm' and before['ShieldPolicy']==after['ShieldPolicy']=='CurrentSteps','Candidate policy differs')
    require(0<=before['Shield']<=before['MaximumHp']//2 and 0<=after['Shield']<=before['MaximumHp']//2,'Shield cap differs')
    if row['kind']=='cast':
        cards=row['selected'];ids=[c['InstanceId'] for c in cards];require(1<=len(cards)<=5 and len(ids)==len(set(ids)) and all(c['Level']==0 for c in cards),'Owned ordered card selection differs')
        base=sum(c['shield'] for c in cards);require(base==row['card_shield'] and not row['candidate_activation'],'Original shield basis/candidate differs')
        multiplier=1+.45*clamp(max(1,before['Hp']-row['health_cost'])/before['MaximumHp'],0,1) if row['Hero']=='Guardian' else 1
        # This experiment freezes weapon level to declared equipment endpoint.
        level=row['weapon_level'];flat=(3 if level>=4 else 2 if level>=2 else 1) if row['Hero']=='Guardian' else 0
        requested=math.floor(base*multiplier*(1+equipment['BulwarkShieldBonus']))+flat if base>0 else 0
        effective=min(requested,before['MaximumHp']//2-before['Shield'])
        require(requested==row['requested']==row['independent_requested'] and effective==row['effective']==row['independent_effective'] and row['overflow']==requested-effective and after['Shield']==before['Shield']+effective,'Independent requested/effective/overflow differs')
        return
    require(row['kind']=='tick' and not equipment['HasRapidDraw'],'Declared tick/current equipment differs')
    resistance=equipment['Elements'][row['element']+'Resistance'];require(near(resistance,min(.6,row['raw_resistance'])) and near(resistance,row['effective_resistance']),'Independent resistance cap differs')
    if row['raw_resistance']>=.6:require(near(row['effective_marginal'],0),'Above-cap marginal differs')
    delta=TICKS//10;charge=before['Charge'];hand=before['Hand'];available=before['AvailableCards']
    boundaries=sorted({0,delta}|{before[key] for key in ['SpeedTicks','ConversionTicks','StunTicks','BlockTicks'] if 0<=before[key]<=delta})
    for start,end in zip(boundaries,boundaries[1:]):
        if not row['draw_enabled'] or start<before['StunTicks'] or start<before['BlockTicks']:continue
        speed=before['SpeedModifier'] if start<before['SpeedTicks'] else 0
        rate=2 if start<before['ConversionTicks'] else 1
        charge+=(end-start)/TICKS/clamp(4*(1+equipment['DrawIntervalModifier'])*(1+speed),1.8,6)*rate
        while charge>=1:
            if hand>=5:charge=0;break
            charge-=1
            if available>0:hand+=1;available-=1
    interval=clamp(4*(1+equipment['DrawIntervalModifier'])*(1+before['SpeedModifier']),1.8,6)/(2 if before['ConversionTicks']>0 else 1)
    require(near(interval,before['Interval']) and near(interval,row['independent_interval']) and near(charge,after['Charge']) and near(charge,row['independent_charge_after']) and hand==after['Hand']==row['independent_hand_after'],'Independent staged draw/hand-full accounting differs')
    for key in ['SpeedTicks','ConversionTicks','StunTicks','BlockTicks']:require(after[key]==max(0,before[key]-delta),'Status expiry differs')

def stream(path,summary,callback):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size==summary['stored_bytes'],'Stored hash/bytes differs')
    stored_hash=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):stored_hash.update(block)
    require(stored_hash.hexdigest()==summary['stored_sha256'],'Stored hash/bytes differs')
    h=hashlib.sha256();size=count=0
    with gzip.open(path,'rb') as f:
        while True:
            raw=f.readline(2*1024**2+1)
            if not raw:break
            require(len(raw)<=2*1024**2 and raw.endswith(b'\n'),'Original JSONL line exceeds the bounded collector contract')
            h.update(raw);size+=len(raw);count+=1;callback(json.loads(raw))
    require(size==summary['raw_bytes'] and h.hexdigest()==summary['raw_sha256'],'Original raw CRC/hash/bytes differs')
    return count

def validate(directory,source,controls=False,raw_unit_limit=None,business_source=None,collector_revision=None,
             instrumentation_source=None,mixed_input_manifest=None):
    directory=Path(directory);m=json.loads((directory/'manifest.json').read_text());s=json.loads((directory/'summary.json').read_text())
    collection=collection_contract(m,s,source,raw_unit_limit,business_source,collector_revision,instrumentation_source,mixed_input_manifest)
    require(s.get('passed') is True and type(s.get('errors')) is int and s['errors']==0,'Exact source/schema/native run differs')
    require(m['samples'] in [3,1000] and m['seed_start']==440001+1000*m['block_index'] and m['equipment_level'] in [0,5] and m['weapon_level']==m['equipment_level'] and m['cutoff_seconds']==600 and m['strategy']=='basic' and not m['candidate_activation'],'Frozen inputs differ')
    require(len(m['deck'])==len(set(m['deck']))==20 and m['card_level']==0 and m['single_item_quality_change'] and m['outcome_effects_descriptive_only'],'Declared budget/interpretation differs')
    prefix={'Mage':'MAG','Priest':'PRI','Guardian':'GUA'}[m['hero']];require(m['deck']==list(COMMON)+[f'{prefix}-{i:02}' for i in range(1,7)],'Frozen legal source deck differs')
    before,after=m['equipment'];require(len(before)==len(after)==5 and len({i['Slot'] for i in before})==5 and all(a['Quality']=='Purple' and b['Quality']==('Orange' if i==0 else 'Purple') and {k:v for k,v in a.items() if k!='Quality'}=={k:v for k,v in b.items() if k!='Quality'} for i,(a,b) in enumerate(zip(before,after))),'Legal one-quality equipment pair differs')
    raw_resistance=[]
    for index,items in enumerate(m['equipment']):
        require(all(i['Level']==m['equipment_level'] and i['Element']==ELEMENTS[m['element']] and i['EffectAffix']=='Bulwark' and i['SecondaryTrait']=='DrawInterval' and i['UniqueAffix'] is None for i in items),'Frozen equipment fields differ')
        resistance=sum(m['quality_data'][i['Quality']]['Resistance']+i['Level']*m['quality_data'][i['Quality']]['ResistancePerLevel'] for i in items);raw_resistance.append(resistance)
        draw=sum(m['quality_data'][i['Quality']]['DrawInterval']+i['Level']*m['quality_data'][i['Quality']]['DrawIntervalPerLevel'] for i in items)
        require(near(resistance,m['raw_resistance'][index]) and near(draw,m['profiles'][index]['DrawIntervalModifier']),'Original legal equipment contributions differ')
    encounters={};outcomes=Counter();counts=Counter();ledger=defaultdict(Counter);witnesses={}
    def encounter(r):
        key=(r['Seed'],r['Profile']);require(key not in encounters and r['Error'] is None and r['Outcome'] in ['Victory','Death','Censored'],'Encounter identity/outcome differs');encounters[key]=r;outcomes[r['Outcome']]+=1
        require(r['Hero']==m['hero'] and r['Group']==m['group'] and r['WeaponLevel']==m['weapon_level'],'Encounter stratum differs')
    rows=stream(directory/'encounters.jsonl.gz',s,encounter);expected={(seed,arm) for seed in range(m['seed_start'],m['seed_start']+m['samples']) for arm in ARMS};require(encounters.keys()==expected and rows==s['rows']==m['samples']*2,'Paired seed coverage differs')
    for seed in range(m['seed_start'],m['seed_start']+m['samples']):
        a,b=[encounters[(seed,arm)] for arm in ARMS];require((a['OpeningEnemyHp'],a['OpeningEnemyShield'],a['EnemyNonHpInputSha256'])==(b['OpeningEnemyHp'],b['OpeningEnemyShield'],b['EnemyNonHpInputSha256']),'Paired enemy inputs differ')
    def event(r):
        key=(r['Seed'],r['Profile']);require(key in encounters and r['Hero']==m['hero'] and r['Group']==m['group'] and r['SeedBlock']==m['block_index'],'Event stratum/parent differs');arm=r['Profile']+'/';events=ledger[key];event_contract(r);witnesses.setdefault(r['kind'],r)
        require(0<=r['at']<=600,'Event outside observation interval');require(r['equipment']==m['profiles'][ARMS.index(r['Profile'])],'Original equipment profile differs')
        require(r['before']['MaximumHp']==r['after']['MaximumHp']=={'Mage':70,'Priest':80,'Guardian':100}[m['hero']],'Frozen base HP differs')
        if r['kind']=='cast':
            require(r['action']==events['casts'] and r['weapon_level']==m['weapon_level'],'Original cast sequence differs');events['casts']+=1;events['RequestedShield']+=r['requested'];events['EffectiveShield']+=r['effective'];events['ShieldOverflow']+=r['overflow'];counts[arm+'all_casts']+=1;counts[arm+('T03_positive_shield' if r['card_shield']>0 else 'T03_no_shield')]+=1
            if r['card_shield']>0 and r['before']['Shield']==r['before']['MaximumHp']//2:counts[arm+'T03_full_shield']+=1
            if r['overflow']>0:counts[arm+'T03_overflow']+=1
        else:
            require(r['element']==m['element'] and near(r['raw_resistance'],raw_resistance[ARMS.index(r['Profile'])]) and near(r['raw_marginal'],raw_resistance[1]-raw_resistance[0]) and near(r['effective_marginal'],min(.6,raw_resistance[1])-min(.6,raw_resistance[0])),'Original legal resistance marginal differs')
            require(r['step']==events['ticks'],'Original tick sequence differs');events['ticks']+=1;counts[arm+'all_ticks']+=1;counts[arm+('T01_capped_ticks' if r['raw_resistance']>=.6 else 'T01_below_cap_ticks')]+=1
            if clamp(4*(1+r['equipment']['DrawIntervalModifier']),1.8,6)==1.8:counts[arm+'T02_equipment_floor_ticks']+=1
            if r['before']['SpeedTicks']>0:counts[arm+'T02_card_speed_ticks']+=1
            if r['before']['ConversionTicks']>0:counts[arm+'T02_PVE_conversion_ticks']+=1
            if any(0<r['before'][k]<=TICKS//10 for k in ['SpeedTicks','ConversionTicks']):counts[arm+'T02_expiry_ticks']+=1
    total=0
    for part in s['event_parts']:
        p=(directory/part['path']).resolve();require(p.is_relative_to(directory.resolve()),'Part path escaped');n=stream(p,part,event);require(n==part['events'],'Part count differs');total+=n
    require(sum(v['casts'] for v in ledger.values())==s['actual_casts'] and sum(v['ticks'] for v in ledger.values())==s['actual_ticks'] and total==s['actual_casts']+s['actual_ticks'] and dict(counts)==s['case_denominators'],'Complete denominator differs')
    for key,row in encounters.items():
        require(ledger[key]['casts']==row['Actions'] and near(ledger[key]['ticks']/10,row['ObservedSeconds']),'Original encounter/event count differs')
        for field in ['RequestedShield','EffectiveShield','ShieldOverflow']:require(ledger[key][field]==row[field],'Original shield ledger differs')
    rejected=[]
    if controls:
        require(set(witnesses)=={'cast','tick'},'Actual cast and tick needed for controls')
        changes={'wrong-resistance-cap':('tick',lambda r:r.update(effective_resistance=r['effective_resistance']+.1)),'wrong-conversion-stage':('tick',lambda r:r['before'].update(Interval=r['before']['Interval']+1)),'wrong-shield-overflow':('cast',lambda r:r.update(overflow=r['overflow']+1)),'candidate-policy-enabled':('cast',lambda r:r['before'].update(ShieldPolicy='FractionalRemainder'))}
        for name,(kind,change) in changes.items():
            r=copy.deepcopy(witnesses[kind]);change(r)
            try:event_contract(r)
            except ValueError:rejected.append({'name':name,'rejected':True})
            else:raise ValueError('Corrupt cap event accepted: '+name)
    metadata_controls=collection_negative_controls(m,s,source,raw_unit_limit,business_source,collector_revision,instrumentation_source,mixed_input_manifest) if controls else []
    return {'ok':True,'source_sha':source,**collection,'encounters':rows,'pairs':rows//2,'actual_casts':s['actual_casts'],'actual_ticks':s['actual_ticks'],'outcomes':dict(outcomes),'case_denominators':dict(counts),'negative_controls':rejected,'collector_negative_controls':metadata_controls,'full_unit':m['samples']==1000,'whole_experiment_complete':False,'required_cases_accepted':False,'main_acceptance_granted':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True);p.add_argument('--controls',action='store_true');p.add_argument('--business-source-sha');p.add_argument('--instrumentation-source-sha');p.add_argument('--mixed-input-manifest-sha256');p.add_argument('--collector-revision');p.add_argument('--cap-raw-unit-limit-bytes',type=int);a=p.parse_args();require(not Path(a.output).exists(),'New validation result required');r=validate(a.input,a.source_sha,a.controls,a.cap_raw_unit_limit_bytes,a.business_source_sha,a.collector_revision,a.instrumentation_source_sha,a.mixed_input_manifest_sha256);Path(a.output).write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
