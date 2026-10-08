"""Pool actual encounter rows by stratum; preserve censored/dead/error outcomes."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import subprocess

ROOT=Path(__file__).resolve().parents[1]
if __package__:
    from .pr13_candidate_review import paired_clusters
    from .pr13_experience_metrics import recovery_totals
else:
    from pr13_candidate_review import paired_clusters
    from pr13_experience_metrics import recovery_totals
STRATUM_FIELDS=('Hero','WeaponLevel','Deck','Group','Strategy','Profile')
OUTCOMES={'Victory','Death','Censored','Error'}
TARGET_PROFILES={
    'outer-o6-hp085':'TargetedO6Hp085','outer-o6-hp095':'TargetedO6Hp095',
    'outer-o6-hp090':'TargetedO6Hp090','outer-o6-interval110':'TargetedO6Interval110',
    'outer-o6-windup025':'TargetedO6Windup025','outer-o6-windup050':'TargetedO6Windup050'}


def candidate_profile(candidate,hero,group):
    if candidate=='class-passives':
        return {'Mage':'CoreCardsSpent','Guardian':'FractionalRemainder','Priest':'BaselinePairedControl'}[hero]
    if candidate not in TARGET_PROFILES:raise ValueError('Unknown candidate: '+str(candidate))
    return TARGET_PROFILES[candidate] if group=='O6' else 'BaselinePairedControl'


def frozen_signature(manifest):
    fields=('Kind','SourceSha','DomainAssemblySha256','SimulatorAssemblySha256','SourceConfigSha256',
            'ConfigVersion','Candidate','CutoffSeconds','ActionIntervalSeconds','WeaponLevel')
    return {**{k:manifest[k] for k in fields},
            **{k:manifest.get(k) for k in ('StrategyPolicy','ProductionDefaults','PreviewAudit',
                                          'Decks','Groups','Strategies','CandidateWhitelist','SingleFactorOnly',
                                          'SourceGitDirty')}}


def load_run(directory):
    """Check the declared matrix against raw rows, including whole missing pairs."""
    raw=directory/'encounters.jsonl'
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
    summary=json.loads((directory/'summary.json').read_text(encoding='utf8'))
    try:
        frozen_signature(manifest)
        start=manifest['SeedStart'];samples=manifest['SamplesPerStratum'];level=manifest['WeaponLevel']
        if type(start) is not int or start<0 or type(samples) is not int or samples<1:
            raise ValueError('Invalid declared seed block')
        if type(level) is not int or not 0<=level<=5:raise ValueError('Invalid weapon level')
        for field in ('CutoffSeconds','ActionIntervalSeconds'):
            value=manifest[field]
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Invalid observation policy: '+field)
        if manifest.get('CandidateActivation') is not False:raise ValueError('Candidate activation is not isolated')
        if summary['SourceSha']!=manifest['SourceSha']:raise ValueError('Summary source differs')
        for field in ('Groups','Strategies'):
            declared=manifest[field]
            if not isinstance(declared,list) or not declared or any(type(v) is not str or not v for v in declared) or len(set(declared))!=len(declared):
                raise ValueError('Invalid or duplicate declared matrix dimension: '+field)
        decks=manifest['Decks']
        if not isinstance(decks,list) or not decks:raise ValueError('Empty declared decks')
        deck_keys=[(deck['Hero'],deck['Key']) for deck in decks]
        if any(type(value) is not str or not value for key in deck_keys for value in key) or len(set(deck_keys))!=len(deck_keys):
            raise ValueError('Invalid or duplicate declared deck')
        expected=set()
        for deck in decks:
            for group in manifest['Groups']:
                for strategy in manifest['Strategies']:
                    for profile in ('Baseline',candidate_profile(manifest['Candidate'],deck['Hero'],group)):
                        expected.add((deck['Hero'],level,deck['Key'],group,strategy,profile))
        if not expected:raise ValueError('Empty declared matrix')
        if sha(raw)!=summary['RawSha256']:raise ValueError('Raw digest differs')
        values=[];seeds=defaultdict(set)
        with raw.open(encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line);key=tuple(row[k] for k in STRATUM_FIELDS);seed=row['Seed']
                if key not in expected:raise ValueError('Undeclared stratum: '+str(key))
                if type(seed) is not int or not start<=seed<start+samples:raise ValueError('Seed outside declared block')
                if type(row['SeedBlock']) is not int or row['SeedBlock']!=(seed-start)%3:
                    raise ValueError('SeedBlock differs from declared run')
                if seed in seeds[key]:raise ValueError('Duplicate seed in stratum: '+str((key,seed)))
                if row['Outcome'] not in OUTCOMES:raise ValueError('Unknown encounter outcome')
                for field in ('ObservedSeconds','LongestEffectiveGapSeconds','Damage60','EffectiveShield',
                              'HealOverflow','ShieldOverflow','PreviewParityChecks'):
                    value=row[field]
                    if type(value) not in (int,float) or not math.isfinite(value) or value<0:
                        raise ValueError('Invalid numeric encounter field: '+field)
                if row['ObservedSeconds']>manifest['CutoffSeconds']:raise ValueError('Observation exceeds cutoff')
                seeds[key].add(seed);values.append(row)
        if type(summary['Total']) is not int or len(values)!=summary['Total']:raise ValueError('Raw count differs')
        if set(seeds)!=expected or any(len(block)!=samples for block in seeds.values()):
            raise ValueError('Missing declared stratum or seed pair')
        if 'ErrorCount' in summary and summary['ErrorCount']!=sum(r['Outcome']=='Error' for r in values):
            raise ValueError('Raw error count differs')
    except (KeyError,TypeError) as error:
        raise ValueError('Missing or invalid run contract: '+str(directory)) from error
    return manifest,summary,values


def sample_budget(blocks):
    sizes=[dict(seed_start=start,n=n) for start,n in sorted(blocks.items())]
    met=len(sizes)>=3 and all(block['n']>=1000 for block in sizes)
    return dict(seed_blocks=sizes,required_independent_blocks=3,required_paired_seeds_per_block=1000,
                main_sample_floor_met=met,status='BudgetMet' if met else 'Inconclusive',
                precision_guaranteed=False)


def victory_ttk_p95(values):
    """Identify a finite empirical all-started tail only from observed outcome bounds."""
    outcomes=Counter(row['Outcome'] for row in values);reasons=[];rank=math.ceil(.95*len(values))
    victories=sorted(row['ObservedSeconds'] for row in values if row['Outcome']=='Victory')
    upper=victories[rank-1] if len(victories)>=rank else None
    # Death has no future victory; censoring only gives a lower bound. The rank
    # is identified when every compatible completion has the same finite value,
    # including ties where early censoring cannot move the 95% order statistic.
    lower=sorted(row['ObservedSeconds'] if row['Outcome'] in ('Victory','Censored')
                 else math.inf for row in values)[rank-1]
    if upper is None:reasons.append('insufficient_observed_victories_for_p95')
    if outcomes['Censored'] and (upper is None or lower!=upper):
        reasons.append('right_censored_outcomes')
    if outcomes['Death'] and upper is None:reasons.append('competing_death_outcomes')
    if outcomes['Error']:reasons.append('error_outcomes')
    return dict(endpoint='time_to_victory_among_all_started_encounters',population_n=len(values),
                identified=not reasons,value=None if reasons else upper,missing_reasons=reasons,
                method='nearest-rank among all starts; death never becomes victory; censored outcomes must not alter the rank; no independent-censoring assumption')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    ordered=sorted(values)
    return {'n':len(ordered),'mean':statistics.fmean(ordered),
            **{name:ordered[max(0,math.ceil(len(ordered)*q)-1)] for name,q in [('p10',.1),('p50',.5),('p90',.9),('p95',.95),('p99',.99)]}} if ordered else {'n':0}


def wilson(wins,n):
    z=1.959963984540054;p=wins/n;den=1+z*z/n
    center=(p+z*z/(2*n))/den;spread=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,center-spread),min(1,center+spread)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rows=defaultdict(list);sources=[];seen=set();runs=defaultdict(Counter);signature=None
    for directory in args.inputs:
        raw=directory/'encounters.jsonl';manifest,summary,values=load_run(directory);digest=summary['RawSha256']
        current=frozen_signature(manifest)
        if signature is not None and signature!=current:raise ValueError('Mixed frozen inputs; report cohorts separately')
        signature=current
        for row in values:
            key='/'.join(str(row[k]) for k in STRATUM_FIELDS);identity=(key,row['Seed'])
            if identity in seen:raise ValueError('Duplicate seed in stratum: '+str(identity))
            seen.add(identity);rows[key].append(row);runs[key][manifest['SeedStart']]+=1
        count=len(values)
        sources.append(dict(path=str(directory),raw_sha256=digest,raw_bytes=raw.stat().st_size,count=count,
            manifest_sha256=sha(directory/'manifest.json'),summary_sha256=sha(directory/'summary.json'),
            source_sha=manifest['SourceSha'],domain_sha256=manifest['DomainAssemblySha256'],
            simulator_sha256=manifest['SimulatorAssemblySha256'],config_sha256=manifest['SourceConfigSha256'],
            source_git_dirty=manifest.get('SourceGitDirty','Unknown'),
            kind=manifest['Kind'],seed_start=manifest['SeedStart'],samples_per_stratum=manifest['SamplesPerStratum']))
    strata=[];comparisons=[]
    for key,values in sorted(rows.items()):
        outcomes=Counter(row['Outcome'] for row in values);victories=[r for r in values if r['Outcome']=='Victory']
        strata.append(dict(stratum=key,n=len(values),independent_seed_runs=sorted(runs[key]),outcomes=dict(outcomes),
            recovery_accounting=recovery_totals(values),
            sample_budget=sample_budget(runs[key]),censored_rate=outcomes['Censored']/len(values),
            victory_ttk_p95_all_started=victory_ttk_p95(values),
            victory_rate=outcomes['Victory']/len(values),victory_rate_wilson95=wilson(outcomes['Victory'],len(values)),
            all_outcome_observed_seconds=distribution([r['ObservedSeconds'] for r in values]),
            victory_seconds=distribution([r['ObservedSeconds'] for r in victories]),
            longest_effective_gap_seconds=distribution([r['LongestEffectiveGapSeconds'] for r in values]),
            damage60=distribution([r['Damage60'] for r in values]),
            effective_shield=distribution([r['EffectiveShield'] for r in values]),
            heal_overflow=sum(r['HealOverflow'] for r in values),shield_overflow=sum(r['ShieldOverflow'] for r in values),
            preview_parity_checks=sum(r['PreviewParityChecks'] for r in values)))
        if not key.endswith('/Baseline'):continue
        alternatives=[k for k in rows if k.startswith(key[:-len('Baseline')]) and k!=key]
        if len(alternatives)!=1:raise ValueError('Ambiguous paired profile: '+key)
        other=alternatives[0];baseline={r['Seed']:r for r in values};candidate={r['Seed']:r for r in rows[other]}
        if baseline.keys()!=candidate.keys():raise ValueError('Unpaired seeds: '+key)
        if runs[key]!=runs[other]:raise ValueError('Unpaired seed blocks: '+key)
        pairs=[(baseline[s],candidate[s]) for s in sorted(baseline)]
        deltas={field:[b[field]-a[field] for a,b in pairs] for field in ('Damage60','EffectiveShield','ObservedSeconds')}
        cluster_summary=paired_clusters(
            [dict(seed=s,battle='encounter',value=baseline[s]['Damage60']) for s in sorted(baseline)],
            [dict(seed=s,battle='encounter',value=candidate[s]['Damage60']) for s in sorted(candidate)])
        damage=deltas['Damage60']
        comparisons.append(dict(baseline=key,candidate=other,n=len(pairs),
            sample_budget=sample_budget(runs[key]),
            mean_damage60_delta=statistics.fmean(damage),paired_seed_bootstrap_damage60_95=cluster_summary['paired_seed_cluster_bootstrap95'],
            paired_seed_cluster_summary=cluster_summary,
            mean_effective_shield_delta=statistics.fmean(deltas['EffectiveShield']),
            observed_seconds_delta_all_outcomes=distribution(deltas['ObservedSeconds']),
            baseline_wins=sum(a['Outcome']=='Victory' for a,b in pairs),candidate_wins=sum(b['Outcome']=='Victory' for a,b in pairs),
            baseline_deaths=sum(a['Outcome']=='Death' for a,b in pairs),candidate_deaths=sum(b['Outcome']=='Death' for a,b in pairs),
            baseline_censored=sum(a['Outcome']=='Censored' for a,b in pairs),candidate_censored=sum(b['Outcome']=='Censored' for a,b in pairs),
            retain_production_defaults=True))
    report=dict(schema_version=2,report_source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        report_git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        report_algorithm_sha256=sha(Path(__file__)),algorithm_version='raw-nearest-rank-paired-seed-bootstrap-v2',
        sources=sources,total=sum(len(v) for v in rows.values()),errors=sum(r['Outcome']=='Error' for v in rows.values() for r in v),
        scope='Raw encounter statistics; input kind and frozen provenance recorded per source. No network, legal route, prepared Boss or human UX claim.',
        frozen_inputs=signature,candidate_recommendation='NotEvaluated',multiple_comparison_plan=None,
        limitations=['Sample budget is not a precision guarantee.',
                     'Intervals are descriptive per stratum; no preregistered primary endpoint or multiple-comparison plan was supplied.',
                     'Victory-only quantiles do not establish an all-started TTK tail with censoring or competing outcomes.'],
        candidate_activation=False,human_experience_verified=False,strata=strata,paired_comparisons=comparisons)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# PR13 遭遇原样本分层汇总','','来自输入逐战样本；超时、死亡和错误均保留。候选未启用。',
           '',f"共 {report['total']:,} 条，运行错误 {report['errors']} 条。各层实际种子块及样本预算见 JSON；分位数从原始样本重算。",'',
           '少于三个互不重叠种子块或任一块少于1000配对seed时，样本预算为 Inconclusive。预算满足不保证精度；未提供预登记主要终点及多重比较方案，候选推荐为 NotEvaluated。',
           '全结果观测时长保留截止/死亡；胜局时长只描述胜局。胜局数不足全体开战样本的95%秩、删失仍可能改变该秩或存在错误时，全体击杀时间 P95 记为不可识别；不能由胜局 P95 推断。','',
           '默认裸装、直接进入指定遭遇的离线模拟；不代表合法完整探索、联网容量或真人体验。Boss 层也不代表完成装备准备后的难度。','',
           '| 职业/武器/场景/策略/规则 | N | 胜/死/超时 | 全结果观测秒 P50/P95 | 最长无有效动作秒 P95 |',
           '| --- | ---: | --- | --- | ---: |']
    for s in strata:
        o=s['outcomes'];d=s['all_outcome_observed_seconds'];g=s['longest_effective_gap_seconds']
        lines.append(f"| {s['stratum']} | {s['n']} | {o.get('Victory',0)}/{o.get('Death',0)}/{o.get('Censored',0)} | {d['p50']:.1f}/{d['p95']:.1f} | {g['p95']:.1f} |")
    lines+=['','## 候选差异','','+2/+4 护盾候选的收益必须分别评估；下表直接展示有效护盾变化，不能描述为全等级加强。胜局时长与全结果观测时长已分列于 JSON。','',
            '| 分层 | 胜数变化 | 有效护盾均值变化 | 60秒伤害均值变化与95%区间 |','| --- | ---: | ---: | --- |']
    for c in comparisons:
        lines.append(f"| {c['baseline']} → {c['candidate'].rsplit('/',1)[-1]} | {c['candidate_wins']-c['baseline_wins']} | {c['mean_effective_shield_delta']:.2f} | {c['mean_damage60_delta']:.2f} [{c['paired_seed_bootstrap_damage60_95'][0]:.2f}, {c['paired_seed_bootstrap_damage60_95'][1]:.2f}] |")
    (args.output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(dict(total=report['total'],errors=report['errors'],strata=len(strata),paired=len(comparisons))))
    return 0 if not report['errors'] else 1


if __name__=='__main__':raise SystemExit(main())
