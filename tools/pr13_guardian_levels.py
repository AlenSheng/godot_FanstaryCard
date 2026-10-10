"""Review each frozen Guardian weapon level without pooling away regressions."""
import argparse
import json
from pathlib import Path
import subprocess
import re
import sys

from pr13_candidate_review import paired_clusters
from pr13_simulation_report import ROOT, load_run, frozen_signature, sha
from pr13_raw_storage import raw_input


def write(path, value):
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matrix',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--evidence-root',type=Path,default=ROOT)
    p.add_argument('--analysis-source-sha',help='Verified Git implementation SHA for an immutable cloud source snapshot')
    args=p.parse_args();matrix=args.matrix.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    prereg=json.loads((matrix/'preregistration.json').read_text(encoding='utf8'))
    execution=json.loads((matrix/'execution.json').read_text(encoding='utf8'))
    if len(execution)!=18 or any(row['state']!='Completed' or row['exit_code']!=0 for row in execution):raise ValueError('All preregistered native level/seed jobs must complete')
    if sum(row['elapsed_seconds'] for row in execution)>prereg['max_matrix_seconds']:raise ValueError('Native matrix exceeded original budget')
    levels=[];parents=[];total=0;signatures={}
    for level in range(6):
        baseline={};candidate={}
        for seed_start in prereg['independent_seed_blocks']:
            directory=matrix/str(level)/str(seed_start)
            manifest,summary,rows=load_run(directory);signature=frozen_signature(manifest)
            if manifest['WeaponLevel']!=level or manifest['SourceSha']!=prereg['source_sha'] or manifest['SeedStart']!=seed_start:raise ValueError('Native frozen source/level/block differs')
            if manifest['DomainAssemblySha256']!=prereg['runtime_hashes']['FantasyCard.Domain.dll'] or manifest['SimulatorAssemblySha256']!=prereg['runtime_hashes']['FantasyCard.Numerics.dll']:raise ValueError('Native assembly differs from preregistration')
            if summary['ErrorCount']!=0:raise ValueError('Native errors retained, cannot report Passed')
            if level in signatures and signatures[level]!=signature:raise ValueError('Mixed source within a level')
            signatures[level]=signature;total+=len(rows)
            raw,compressed,raw_bytes=raw_input(directory,summary)
            parents.append(dict(path=directory.relative_to(args.evidence_root.resolve()).as_posix(),raw_bytes=raw_bytes,raw_sha256=summary['RawSha256'],raw_storage=summary.get('RawStorage'),manifest_sha256=sha(directory/'manifest.json'),summary_sha256=sha(directory/'summary.json')))
            for row in rows:
                key=(row['Deck'],row['Group'],row['Strategy'])
                target=baseline if row['Profile']=='Baseline' else candidate
                target.setdefault(key,[]).append(row)
        strata=[]
        for key,a in sorted(baseline.items()):
            b=candidate[key]
            intervals={}
            for metric in ['EffectiveShield','ShieldOverflow','Victory']:
                value=lambda row: int(row['Outcome']=='Victory') if metric=='Victory' else row[metric]
                intervals[metric]=paired_clusters([dict(seed=r['Seed'],battle='encounter',value=value(r)) for r in a],[dict(seed=r['Seed'],battle='encounter',value=value(r)) for r in b])
            strata.append(dict(deck=key[0],group=key[1],strategy=key[2],n=len(a),paired_intervals=intervals,baseline_outcomes={o:sum(r['Outcome']==o for r in a) for o in ['Victory','Death','Censored','Error']},candidate_outcomes={o:sum(r['Outcome']==o for r in b) for o in ['Victory','Death','Censored','Error']}))
        levels.append(dict(weapon_level=level,strata=strata,comparison_scope='Each stratum separately; descriptive paired seed bootstrap95, no family corrected recommendation',observed_regression=any(s['paired_intervals']['EffectiveShield']['mean_delta']<0 or s['paired_intervals']['Victory']['mean_delta']<0 for s in strata)))
    weakened={row['weapon_level']:row['observed_regression'] for row in levels}
    # Exercise the production reporter's mixed-level rejection, with real raw
    # parents. Exit 0 would turn an invalid aggregate into a misleading result.
    invalid=out/'mixed-level-negative'
    command=[sys.executable,str(ROOT/'tools/pr13_simulation_report.py'),'--inputs',str(matrix/'0'/'100001'),str(matrix/'1'/'100001'),'--output',str(invalid)]
    r=subprocess.run(command,capture_output=True,text=True,encoding='utf8',timeout=30)
    rejected=r.returncode!=0 and 'Mixed frozen inputs' in r.stderr
    analysis_sha=args.analysis_source_sha or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}',analysis_sha):raise ValueError('Exact verified analysis source SHA required')
    report=dict(source_sha=prereg['source_sha'],analysis_source_sha=analysis_sha,plan_sha256=sha(ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json'),source=dict(scope=prereg['scope'],native_preregistration_sha256=sha(matrix/'preregistration.json'),execution_sha256=sha(matrix/'execution.json'),analysis_sha256=sha(Path(__file__))),executed=3,passed=3 if weakened[2] and weakened[4] and not weakened[1] and rejected else 0,total_encounter_rows=total,levels=levels,parents=parents,mixed_level_aggregation_rejected=rejected,production_activation=False,human_acceptance=False,candidate_recommendation='Blocked: +2/+4 effective shield and survival regressions require explicit review; legal route/PVP/prepared Boss and other mandatory layers incomplete',accepted=False)
    write(out/'report.json',report)
    contracts={c['id']:c for pkg in json.loads((ROOT/'docs/plans/PR13_ACCEPTANCE_DETAILS_20260930.json').read_text(encoding='utf8'))['packages'] for t in pkg['subtasks'] for c in t['test_cases']}
    cases=[]
    for cid,ok,actual in [('PR13-B07.2-T01',weakened[2] and weakened[4],dict(affected_levels=[2,4],explicit_regressions=weakened,intervals='report.json levels[].strata[].paired_intervals')),
                          ('PR13-B07.2-T02',not weakened[1] and weakened[2] and weakened[4],dict(level1_does_not_mask_levels2_and4=True,independent_level_results=True)),
                          ('PR13-B07.2-T03',rejected,dict(actual_mixed_level_report_exit=r.returncode,actual_rejection='Mixed frozen inputs',level_count=6))]:
        cases.append(dict(case_id=cid,executed=True,status='Passed' if ok else 'Failed',setup=contracts[cid]['setup_and_injection'],expected=contracts[cid]['expected'],profiles_executed=['OFFLINE','EXPERIMENT'],actual=actual,scope='Real authoritative isolated encounter matrix, 3x1000 paired seeds per stratum per level; renderer, legal full route, PVP, prepared Boss and human layers separate'))
    (out/'cases.jsonl').write_bytes(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in cases).encode())
    write(out/'commands.json',dict(mixed_level_negative=command,exit_code=r.returncode,original_native_jobs=18,original_native_elapsed_seconds=sum(j['elapsed_seconds'] for j in execution)))
    print(json.dumps(dict(cases=len(cases),passed=sum(c['status']=='Passed' for c in cases),rows=total,regressions=weakened,mixed_levels_rejected=rejected)))
    return 0 if all(c['status']=='Passed' for c in cases) else 1


if __name__=='__main__':raise SystemExit(main())
