"""Preregister and run isolated O6 single-factor experiments on frozen assemblies."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
FACTORS=('outer-o6-hp095','outer-o6-hp090','outer-o6-windup025','outer-o6-windup050')


def validate_controls(output, results):
    errors=[];total=controls=windups=0
    for execution in results:
        if execution['state']!='Completed':errors.append(dict(kind='incomplete_job',output=execution['output']));continue
        directory=Path(execution['output']);summary=json.loads((directory/'summary.json').read_text())
        raw=directory/'encounters.jsonl'
        if hashlib.sha256(raw.read_bytes()).hexdigest()!=summary['RawSha256']:
            errors.append(dict(kind='raw_hash_mismatch',output=str(directory)));continue
        pairs={};count=0
        with raw.open(encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line);total+=1;count+=1
                key=tuple(row[k] for k in ('Seed','Hero','WeaponLevel','Deck','Group','Strategy'))
                pairs.setdefault(key,[]).append(row)
                if row['Outcome']=='Error':errors.append(dict(kind='encounter_error',key=key,output=str(directory)))
                if row['Group']=='O6' and row['Profile'].startswith('TargetedO6Windup'):
                    windups+=1;expected=250 if '025' in execution['factor'] else 500
                    if (row.get('FirstWindupExtraMilliseconds')!=expected or row.get('FirstWindupExtensions',0)<1 or
                            any(i!=0 for i in row.get('FirstWindupIntentIndexes',[]))):
                        errors.append(dict(kind='first_intent_not_extended',key=key,output=str(directory)))
        if count!=summary['Total']:errors.append(dict(kind='raw_count_mismatch',output=str(directory)))
        for key,pair in pairs.items():
            if len(pair)!=2:errors.append(dict(kind='unpaired_seed',key=key));continue
            if key[4]=='O6':continue
            controls+=1;a,b=pair
            if {k:v for k,v in a.items() if k!='Profile'}!={k:v for k,v in b.items() if k!='Profile'}:
                errors.append(dict(kind='unaffected_control_changed',key=key,output=str(directory)))
    return dict(total=total,unaffected_paired_controls_checked=controls,first_intent_extensions_checked=windups,
                errors=errors,passed=not errors,candidate_activation=False)


def write(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2),encoding='utf8');temporary.replace(path)


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
        assembly_hashes={name:hashlib.sha256((runtime/name).read_bytes()).hexdigest() for name in files},
        samples_per_stratum_per_run=args.samples,independent_runs_per_factor=3,max_workers=args.workers,
        source_config='Same embedded actual config in each frozen Domain assembly; global config mutation is checked by simulator',
        scopes='O6 whitelist only; separate HP95/90 and first-windup250/500ms; O1/E1/BOSS paired unchanged controls',
        candidate_activation=False,main_sample_floor_met=args.samples>=1000,jobs=jobs)
    write(output/'preregistration.json',manifest)
    stop=output/'STOP'
    def run(job):
        record=dict(job,state='Running',started_at=time.time());target=Path(job['output'])
        if stop.exists():
            record.update(state='NotExecuted',reason='operator_stop_before_launch',finished_at=time.time())
            write(target/'execution.json',record);return record
        write(target/'execution.json',record)
        with (target/'execution.log').open('w',encoding='utf8') as log:
            child=subprocess.Popen(job['command'],stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            record['pid']=child.pid;write(target/'execution.json',record);deadline=time.monotonic()+2400
            try:
                while child.poll() is None and time.monotonic()<deadline and not stop.exists():time.sleep(.5)
                if child.poll() is None:
                    record['state']='Cancelled' if stop.exists() else 'TimedOut';child.kill()
                child.wait(timeout=10)
                record.update(exit_code=child.returncode,finished_at=time.time())
                if record['state']=='Running':record['state']='Completed' if child.returncode==0 else 'Failed'
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                write(target/'execution.json',record)
        return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results=list(pool.map(run,jobs))
    controls=validate_controls(output,results)
    write(output/'controls-report.json',controls)
    write(output/'results.json',dict(jobs=results,candidate_activation=False,all_completed=all(r['state']=='Completed' for r in results)))
    print(json.dumps(dict(completed=sum(r['state']=='Completed' for r in results),total=len(results))))
    return 0 if all(r['state']=='Completed' for r in results) and controls['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
