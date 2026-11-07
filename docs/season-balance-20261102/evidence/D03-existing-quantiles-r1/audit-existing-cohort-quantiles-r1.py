from pathlib import Path
import collections, hashlib, json, math, shutil, zipfile

b=Path(__file__).parent;repo=Path.cwd();out=b/'d03-existing-quantiles-r1';assert not out.exists();out.mkdir();(out/'banks').mkdir()
sha=lambda raw:hashlib.sha256(raw).hexdigest();checkpoint=json.loads((b/'current-journey-client-continuation-20261105.json').read_bytes())
budget_path=repo/'docs/season-balance-20261102/D03-BUDGET.json';budget_before=sha(budget_path.read_bytes());budget=json.loads(budget_path.read_bytes());assert budget['used']==budget['maximum']==308 and budget['remaining']==0
bank_source=repo/'server/tests/FantasyCard.Server.Tests/Config/SeasonCohortBank.cs';source=bank_source.read_text('utf-8')
assert 'Assert.Equal(GoldEarned,Gold)' in source and 'FragmentsEarned-FragmentsSpent' in source
raw_rows=[];identities=[]
for record in checkpoint['D03_latest_banks']:
    p=Path(record['source']);raw=p.read_bytes();assert sha(raw)==record['sha256'];d=json.loads(raw)
    target=out/'banks'/(d['Id']+'.original.json');target.write_bytes(raw)
    sets=[{x['Item']['ItemId'] for x in d[key]} for key in ['Items','Overflow','Recycled']]+[set(d['LostIds'])]
    assert all(not sets[i]&sets[j] for i in range(4) for j in range(i+1,4))
    assert set.union(*sets)==set(d['SeenIds'])
    assert d['Gold']==d['GoldEarned'] and d['Fragments']==d['FragmentsEarned']-d['FragmentsSpent']
    assert all(d[key]>=0 for key in ['Gold','Fragments','Blueprints','OrangeBlueprints']) and d['CombatSeconds']>0
    row={key:d[key] for key in ['Id','Hero','Cohort','Attempts','Deaths','GoldEarned','FragmentsEarned','FragmentsSpent','Fragments','Blueprints','OrangeBlueprints','BlueprintsSpent','OrangeBlueprintsSpent','CombatSeconds','FirstQualityAttempt','FirstReadyAttempt','FirstTargetAttempt','OriginSha256']}
    row.update(source=str(p),source_sha256=record['sha256'],gross_gold_not_operating_net=d['GoldEarned'],physical_IDs=len(d['SeenIds']),active_bodies=len(sets[0])+len(sets[1]),recycled_bodies=len(sets[2]),lost_bodies=len(sets[3]))
    raw_rows.append(row);identities.append(dict(id=d['Id'],seen=len(d['SeenIds']),active=len(sets[0])+len(sets[1]),recycled=len(sets[2]),lost=len(sets[3]),disjoint_and_complete=True))

def quantile(values,p):
    values=sorted(values);index=(len(values)-1)*p;lower=math.floor(index);upper=math.ceil(index)
    return values[lower]+(values[upper]-values[lower])*(index-lower)

groups=[]
for cohort in ['novice','returning','skilled']:
    rows=[r for r in raw_rows if r['Cohort']==cohort];assert len(rows)==3
    milestones={}
    for field in ['FirstQualityAttempt','FirstReadyAttempt','FirstTargetAttempt']:
        observations=[dict(hero=r['Hero'],observed_attempt=r[field],followed_through_attempt=r['Attempts'],right_censored=r[field] is None) for r in rows]
        complete=all(r[field] is not None for r in rows)
        milestones[field]=dict(observations=observations,observed_events=sum(r[field] is not None for r in rows),tracks=3,
            P50=quantile([r[field] for r in rows],.5) if complete else None,
            P90=quantile([r[field] for r in rows],.9) if complete else None,
            method='Empirical type7 across all3 named tracks only when all events observed; otherwise no complete-case percentile or censoring-independence assumption')
    groups.append(dict(cohort=cohort,tracks=3,historical_attempts=sum(r['Attempts'] for r in rows),deaths=sum(r['Deaths'] for r in rows),milestones=milestones))
zip_path=repo/'docs/season-balance-20261102/source/Season_Balance_Package.zip'
with zipfile.ZipFile(zip_path) as archive:
    name='analysis/independent_economy_results.json';raw=archive.read(name);model=json.loads(raw);(out/'original-conditional-economy.json').write_bytes(raw)
    model_origin=dict(zip_sha256=sha(zip_path.read_bytes()),member=name,member_sha256=sha(raw),scope=model['scope'])
expected_fragments=next(r['fragmentsPerSuccessfulR1'] for r in model['sourceFragComparisons'] if r['difficulty']=='D2')
assert expected_fragments==40
rebuild=model['learnedRecipeRebuild'];assert rebuild['fragmentRebuildCost']==66
rate=.7;net=rate*expected_fragments-(1-rate)*66;break_even=66/(expected_fragments+66)
assert math.isclose(net,rebuild['fragmentNetPerAttempt70pct'],abs_tol=1e-9) and math.isclose(break_even,rebuild['fragmentBreakEven'],abs_tol=1e-12)
conditional=dict(original_model=model_origin,R1_success_fragments=40,learned_template_rebuild_fragments=66,assumed_extraction_rate=rate,
    fragment_expected_net_per_attempt=net,fragment_break_even_extraction_rate=break_even,
    original_model_body_mark_break_even=rebuild['bodyMarkBreakEven'],original_model_net_marks_at70pct=rebuild['netMarksAfterReplacement70pct'],
    assumptions=['All5 target templates already learned','Original model R1 rewards and equipment choices','No claim that simulated or real extraction rates equal70percent','Target kit must be legal for difficulty; original D0/D1 target-kit stress ratios are not usable farming paths'],
    limitation='Conditional arithmetic, not new combat, current-version steady-state proof or evidence that novice target-kit farming is profitable')
result=dict(scope='Read-only existing nine-bank audit; no new cases or acceptance relaxation',bank_source_sha256=sha(bank_source.read_bytes()),
    definitions=dict(FirstQualityAttempt='D2-selected5slots, every quality rank>=Purple, exactly1Orange; not first green/blue piece',
        FirstReadyAttempt='Quality-set condition plus allselected levels>=3 and at least1 positive effect category; not exact target build',
        FirstTargetAttempt='Inventory holds every exact Water3/Fire2,2Piercing/3Vitality target slot with level>=3; not proof all5were worn in a route'),
    historical_bank_versions_mixed=True,cohort_groups=groups,banks=raw_rows,physical_id_conservation=identities,total_physical_IDs=sum(r['seen'] for r in identities),
    gold_scope='Bank asserts Gold==GoldEarned and contains no gold-spending balance. Treat as gross carried gold; real account operating costs require the separate F01 transaction evidence.',
    fragments_scope='Net of bank recorded enhancement/reforge spending, not a universal operating-cost model',conditional_model=conditional,
    limitations=['Only3 named tracks per cohort, one perclass; not population P90 confidence','Censored values remain unknown, not0 or successful','Do not backdate late lobby intervention milestones','Positive ending inventory and wallets are finite-history evidence, not infinite-horizon stationarity'],
    new_gameplay_starts=0,PG_started=False,cloud_changed=False,D03_used=308,D03_max=308,D03_accepted=False,whole_progress='33/35')
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
assert sha(budget_path.read_bytes())==budget_before
assert all(sha(Path(r['source']).read_bytes())==r['source_sha256'] for r in raw_rows)
(out/'integrity.original.json').write_text(json.dumps(dict(budget_before_sha256=budget_before,budget_after_sha256=sha(budget_path.read_bytes()),all9_original_banks_unchanged=True,all_physical_IDs_disjoint_and_accounted=True),indent=2)+'\n')
print(json.dumps(dict(groups=[dict(cohort=g['cohort'],quality_P50=g['milestones']['FirstQualityAttempt']['P50'],quality_P90=g['milestones']['FirstQualityAttempt']['P90'],ready_P50=g['milestones']['FirstReadyAttempt']['P50'],ready_P90=g['milestones']['FirstReadyAttempt']['P90']) for g in groups],physical_IDs=result['total_physical_IDs'],new_gameplay_starts=0,D03_accepted=False)))
