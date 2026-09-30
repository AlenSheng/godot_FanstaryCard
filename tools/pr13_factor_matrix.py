"""Preregister and run isolated O6 single-factor experiments on frozen assemblies."""
import argparse
from collections import Counter,defaultdict
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

try:
    from .pr13_simulation_report import candidate_profile,load_run
except ImportError:  # Direct script invocation.
    from pr13_simulation_report import candidate_profile,load_run

ROOT=Path(__file__).resolve().parents[1]
FACTORS=('outer-o6-hp095','outer-o6-hp090','outer-o6-windup025','outer-o6-windup050')


def validate_controls(output, results):
    errors=[];total=controls=windups=0;states=Counter(r['state'] for r in results)
    try:
        registered=json.loads((output/'preregistration.json').read_text(encoding='utf8'))
    except (OSError,ValueError):
        return dict(total=0,errors=[dict(kind='missing_preregistration')],passed=False,
                    execution_states=dict(states),main_sample_floor_met=False,acceptance_eligible=False,
                    candidate_activation=False)
    identity=lambda job:(job['factor'],job['seed_start'],str(Path(job['output']).resolve()))
    try:
        samples=registered['samples_per_stratum_per_run']
        if type(samples) is not int or samples<3 or registered['independent_runs_per_factor']!=3:
            raise ValueError('Invalid declared sample or independent run budget')
        declared=Counter((job['factor'],job['seed_start']) for job in registered['jobs'])
        required=Counter((factor,start) for factor in FACTORS for start in (0,samples,samples*2))
        if declared!=required:raise ValueError('Preregistered jobs must cover every factor and all three seed blocks exactly once')
        expected=Counter(identity(job) for job in registered['jobs']);actual=Counter(identity(job) for job in results)
    except (KeyError,TypeError,ValueError) as error:
        return dict(total=0,errors=[dict(kind='invalid_preregistration',reason=str(error))],passed=False,
                    execution_states=dict(states),main_sample_floor_met=False,acceptance_eligible=False,
                    candidate_activation=False)
    blocks=defaultdict(list);config_hash=None
    for execution in results:
        if execution['state']!='Completed':
            errors.append(dict(kind='incomplete_job',output=execution['output'],state=execution['state'],reason=execution.get('reason')))
    if not expected or expected!=actual or any(count!=1 for count in actual.values()):
        errors.append(dict(kind='job_matrix_mismatch',expected_jobs=sum(expected.values()),actual_jobs=len(results)))
    for execution in results:
        if execution['state']!='Completed':continue
        directory=Path(execution['output']);factor=execution['factor']
        try:
            manifest,summary,rows=load_run(directory)
            if (factor not in FACTORS or manifest['Candidate']!=factor or
                    manifest['SeedStart']!=execution['seed_start'] or
                    manifest['SamplesPerStratum']!=registered['samples_per_stratum_per_run'] or
                    manifest['SourceSha']!=registered['source_sha'] or
                    manifest['DomainAssemblySha256']!=registered['assembly_hashes']['FantasyCard.Domain.dll'] or
                    manifest['SimulatorAssemblySha256']!=registered['assembly_hashes']['FantasyCard.Numerics.dll'] or
                    manifest.get('SingleFactorOnly') is not True or manifest.get('CandidateWhitelist')!=['O6'] or
                    set(manifest['Groups'])!={'O1','O6','E1','BOSS'} or
                    set(manifest['Strategies'])!={'baseline_all_hand','basic','build'} or
                    {deck['Hero'] for deck in manifest['Decks']}!={'Mage','Priest','Guardian'}):
                raise ValueError('Factor or frozen runtime contract differs from preregistration')
            # A factor label may differ, but all jobs must use the same actual config and observation policy.
            signature={k:manifest.get(k) for k in ('SourceConfigSha256','ConfigVersion','CutoffSeconds',
                       'ActionIntervalSeconds','StrategyPolicy','ProductionDefaults','WeaponLevel','Decks')}
            if config_hash is not None and config_hash!=signature:raise ValueError('Mixed frozen config or observation policy')
            config_hash=signature
        except (OSError,ValueError,KeyError,TypeError) as error:
            errors.append(dict(kind='invalid_run_contract',output=str(directory),reason=str(error)));continue
        blocks[factor].append((manifest['SeedStart'],manifest['SamplesPerStratum']))
        pairs={};total+=len(rows)
        for row in rows:
            key=tuple(row[k] for k in ('Seed','Hero','WeaponLevel','Deck','Group','Strategy'))
            pairs.setdefault(key,[]).append(row)
            if row['Outcome']=='Error':errors.append(dict(kind='encounter_error',key=key,output=str(directory)))
            if row['Group']=='O6' and row['Profile']!='Baseline' and 'windup' in factor:
                windups+=1;extra=250 if '025' in factor else 500
                indexes=row.get('FirstWindupIntentIndexes');extensions=row.get('FirstWindupExtensions')
                if (row.get('FirstWindupExtraMilliseconds')!=extra or type(extensions) is not int or extensions<1 or
                        not isinstance(indexes,list) or len(indexes)!=extensions or
                        any(type(i) is not int or i!=0 for i in indexes)):
                    errors.append(dict(kind='first_intent_not_extended',key=key,output=str(directory)))
            elif (row.get('FirstWindupExtraMilliseconds')!=0 or row.get('FirstWindupExtensions')!=0 or
                  row.get('FirstWindupIntentIndexes')!=[]):
                errors.append(dict(kind='unexpected_windup_change',key=key,output=str(directory)))
        for key,pair in pairs.items():
            expected_profiles={'Baseline',candidate_profile(factor,key[1],key[4])}
            if len(pair)!=2 or {row['Profile'] for row in pair}!=expected_profiles:
                errors.append(dict(kind='unpaired_seed',key=key));continue
            if key[4]=='O6':continue
            controls+=1;a,b=pair
            if {k:v for k,v in a.items() if k!='Profile'}!={k:v for k,v in b.items() if k!='Profile'}:
                errors.append(dict(kind='unaffected_control_changed',key=key,output=str(directory)))
    floor=set(blocks)==set(FACTORS)
    for factor in FACTORS:
        intervals=sorted(blocks[factor])
        if len(intervals)!=3 or any(n<1000 for start,n in intervals):floor=False
        if any(left[0]+left[1]>right[0] for left,right in zip(intervals,intervals[1:])):
            errors.append(dict(kind='overlapping_seed_blocks',factor=factor));floor=False
    return dict(total=total,unaffected_paired_controls_checked=controls,first_intent_extensions_checked=windups,
                validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                raw_contract_sha256=hashlib.sha256((Path(__file__).parent/'pr13_simulation_report.py').read_bytes()).hexdigest(),
                errors=errors,passed=not errors,execution_states=dict(states),main_sample_floor_met=floor,
                sample_budget_status='BudgetMet' if floor else 'Inconclusive',
                acceptance_eligible=False,candidate_recommendation='NotEvaluated',
                limitations=['Controls and sample budgets do not establish candidate benefit, precision, economic or human experience acceptance.'],
                candidate_activation=False)


def write(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2),encoding='utf8');temporary.replace(path)


def run_job(job,stop):
    record=dict(job);target=Path(job['output'])
    if stop.exists():
        record.update(state='NotExecuted',reason='operator_stop_before_launch',started_at=None,finished_at=time.time())
        write(target/'execution.json',record);return record
    record.update(state='Running',started_at=time.time())
    write(target/'execution.json',record)
    with (target/'execution.log').open('w',encoding='utf8') as log:
        try:
            child=subprocess.Popen(job['command'],stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError as error:
            record.update(state='Failed',reason='launch_failed',error=str(error),exit_code=None,finished_at=time.time())
            write(target/'execution.json',record);return record
        record['pid']=child.pid;write(target/'execution.json',record);deadline=time.monotonic()+2400
        try:
            while child.poll() is None and time.monotonic()<deadline and not stop.exists():time.sleep(.5)
            if child.poll() is None:
                cancelled=stop.exists()
                record.update(state='Cancelled' if cancelled else 'TimedOut',
                              reason='operator_stop_during_run' if cancelled else 'job_deadline_exceeded')
                child.kill()
            child.wait(timeout=10)
            record.update(exit_code=child.returncode,finished_at=time.time())
            if record['state']=='Running':record['state']='Completed' if child.returncode==0 else 'Failed'
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=10)
            write(target/'execution.json',record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=1000)
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    if args.samples<3 or not 1<=args.workers<=3:parser.error('At least3 samples; 1-3 bounded local workers')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    runtime=output/'runtime';runtime.mkdir()
    binary=ROOT/'server/tools/FantasyCard.Numerics/bin/Release/net10.0'
    files=('FantasyCard.Numerics.dll','FantasyCard.Numerics.deps.json','FantasyCard.Numerics.runtimeconfig.json','FantasyCard.Domain.dll')
    for name in files:shutil.copyfile(binary/name,runtime/name)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    jobs=[]
    for factor in FACTORS:
        for seed in (0,args.samples,args.samples*2):
            directory=output/factor/str(seed);directory.mkdir(parents=True)
            jobs.append(dict(factor=factor,seed_start=seed,output=str(directory),
                command=['dotnet',str(runtime/'FantasyCard.Numerics.dll'),'--combat-experience','--candidate',factor,
                    '--samples',str(args.samples),'--seed-start',str(seed),'--source-sha',head,'--output',str(directory)],state='Queued'))
    manifest=dict(schema_version=1,registered_at=time.time(),source_sha=head,source_file_sha256=hashlib.sha256((ROOT/'server/tools/FantasyCard.Numerics/CombatExperience.cs').read_bytes()).hexdigest(),
        source_git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        assembly_hashes={name:hashlib.sha256((runtime/name).read_bytes()).hexdigest() for name in files},
        samples_per_stratum_per_run=args.samples,independent_runs_per_factor=3,max_workers=args.workers,
        source_config='Same embedded actual config in each frozen Domain assembly; global config mutation is checked by simulator',
        scopes='O6 whitelist only; separate HP95/90 and first-windup250/500ms; O1/E1/BOSS paired unchanged controls',
        candidate_activation=False,main_sample_floor_met=args.samples>=1000,jobs=jobs)
    write(output/'preregistration.json',manifest)
    stop=output/'STOP'
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results=list(pool.map(lambda job:run_job(job,stop),jobs))
    controls=validate_controls(output,results)
    write(output/'controls-report.json',controls)
    write(output/'results.json',dict(jobs=results,candidate_activation=False,all_completed=all(r['state']=='Completed' for r in results)))
    print(json.dumps(dict(completed=sum(r['state']=='Completed' for r in results),total=len(results))))
    return 0 if all(r['state']=='Completed' for r in results) and controls['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
