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
    rows=defaultdict(list);sources=[];seen=set();runs=defaultdict(set)
    for directory in args.inputs:
        raw=directory/'encounters.jsonl';manifest=json.loads((directory/'manifest.json').read_text())
        summary=json.loads((directory/'summary.json').read_text());digest=sha(raw)
        if digest!=summary['RawSha256']:raise ValueError('Raw digest differs: '+str(raw))
        count=0
        with raw.open(encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line);key='/'.join(str(row[k]) for k in ('Hero','WeaponLevel','Deck','Group','Strategy','Profile'))
                identity=(key,row['Seed'])
                if identity in seen:raise ValueError('Duplicate seed in stratum: '+str(identity))
                seen.add(identity);rows[key].append(row);runs[key].add(manifest['SeedStart']);count+=1
        if count!=summary['Total']:raise ValueError('Raw count differs: '+str(raw))
        sources.append(dict(path=str(directory),raw_sha256=digest,raw_bytes=raw.stat().st_size,count=count,
            manifest_sha256=sha(directory/'manifest.json'),summary_sha256=sha(directory/'summary.json'),
            source_sha=manifest['SourceSha'],domain_sha256=manifest['DomainAssemblySha256'],
            simulator_sha256=manifest['SimulatorAssemblySha256'],seed_start=manifest['SeedStart']))
    strata=[];comparisons=[]
    for key,values in sorted(rows.items()):
        outcomes=Counter(row['Outcome'] for row in values);victories=[r for r in values if r['Outcome']=='Victory']
        strata.append(dict(stratum=key,n=len(values),independent_seed_runs=sorted(runs[key]),outcomes=dict(outcomes),
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
        pairs=[(baseline[s],candidate[s]) for s in sorted(baseline)]
        deltas={field:[b[field]-a[field] for a,b in pairs] for field in ('Damage60','EffectiveShield','ObservedSeconds')}
        rng=random.Random(20260930)
        # A paired seed bootstrap, separately per stratum; no per-run P95 averaging.
        damage=deltas['Damage60'];bootstrap=sorted(statistics.fmean(rng.choices(damage,k=len(damage))) for _ in range(1000))
        comparisons.append(dict(baseline=key,candidate=other,n=len(pairs),
            mean_damage60_delta=statistics.fmean(damage),paired_seed_bootstrap_damage60_95=[bootstrap[24],bootstrap[974]],
            mean_effective_shield_delta=statistics.fmean(deltas['EffectiveShield']),
            observed_seconds_delta_all_outcomes=distribution(deltas['ObservedSeconds']),
            baseline_wins=sum(a['Outcome']=='Victory' for a,b in pairs),candidate_wins=sum(b['Outcome']=='Victory' for a,b in pairs),
            baseline_deaths=sum(a['Outcome']=='Death' for a,b in pairs),candidate_deaths=sum(b['Outcome']=='Death' for a,b in pairs),
            baseline_censored=sum(a['Outcome']=='Censored' for a,b in pairs),candidate_censored=sum(b['Outcome']=='Censored' for a,b in pairs),
            retain_production_defaults=True))
    report=dict(schema_version=1,report_source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        sources=sources,total=sum(len(v) for v in rows.values()),errors=sum(r['Outcome']=='Error' for v in rows.values() for r in v),
        scope='Actual Domain encounters; default 20-card decks. Synthetic entry; no network, legal route, prepared Boss or human UX claim.',
        candidate_activation=False,human_experience_verified=False,strata=strata,paired_comparisons=comparisons)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# PR13 战斗机器人分层汇总','','来自原始逐战样本；超时、死亡和错误均保留。候选未启用。',
           '',f"共 {report['total']:,} 条，运行错误 {report['errors']} 条。每个主要层合并三段互不重叠的种子，分位数从原始样本重算。",'',
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
