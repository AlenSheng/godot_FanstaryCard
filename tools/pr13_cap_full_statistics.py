#!/usr/bin/env python3
"""Full B08.4 descriptive statistics. Computation is cloud-only; gates are portable.

The projection contains original encounter gzip bytes and original cloud/G proofs.
Event JSONL stays on G: the independent native event oracle has already checked it.
This tool does not promote MAIN or reinterpret a missing case as a passing case.
"""
from __future__ import annotations

import argparse
import collections
import copy
import gzip
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import sys

BUSINESS = 'b0423bfe6fedc3f034ba12c8400df5ebb8713f32'
MIXED = '581cd9f74962dd61424e77c529b1259afbb39fe7'
INSTRUMENTATION = '66c7420532536431b906d1fdb1e68d6d3448e6b9'
INPUTS_SHA = 'ab06c98792af1b3766dac9cde3668924529f07ee23a9eb10646e1b4367ca4716'
ADOPTION_SHA = '198578607d8eb89f4961374caf1f02d4b3ec18ebccdd382c0e6a5b4efb10e12a'
RECOVERY_RESULT_SHA = '427d0b675953aecad1308e6029c49f888ad3a8116779523934e209c1462735cc'
MISSING_ORIGINAL_RESULT_SHA = '38ed8979d4bc0119c654e2487e72705a74eb14a1d522e3c9bc999611b0af7695'
COLLECTOR = 'cap-effective-raw-budget-v2'
GIB = 1024 ** 3
ARMS = ('BaselinePurple', 'SingleOrangeHead')
OUTCOMES = ('Victory', 'Death', 'Censored', 'Error')
ORIGINAL_CONTROLS = {'wrong-resistance-cap', 'wrong-conversion-stage',
                     'wrong-shield-overflow', 'candidate-policy-enabled'}
COLLECTOR_CONTROLS = {'collector-declared-budget-tampered', 'collector-event-part-missing',
                      'collector-cumulative-budget-exceeded'}
OVERRIDES = {'server/tools/FantasyCard.Numerics/CapEffectiveExperiment.cs',
             'tools/pr13_cap_effective_experiment.py'}
V2_FIELDS = {'business_source_sha', 'instrumentation_source_sha', 'mixed_input_manifest_sha256',
             'collector_revision', 'raw_unit_limit_bytes', 'raw_unit_limit_explicit',
             'event_raw_bytes', 'collection_complete'}
COUNTERS = ('all_casts', 'all_ticks', 'T01_capped_ticks', 'T01_below_cap_ticks',
            'T02_equipment_floor_ticks', 'T02_card_speed_ticks', 'T02_PVE_conversion_ticks',
            'T02_expiry_ticks', 'T03_positive_shield', 'T03_no_shield',
            'T03_full_shield', 'T03_overflow')
INTEGER_METRICS = (
    'WeaponLevel OpeningEnemyHp OpeningEnemyShield Actions EffectiveActions ZeroEffectiveActions '
    'CardsSpent ImmediateCardsDrawn RequestedImmediateCards RequestedHeal RequestedShield '
    'RequestedControlTicks ConvertedControlTicks AdmittedControlTicks AddedAliveControlUnionTicks '
    'ObservedAliveControlUnionTicks NaturalCardsDrawn EffectiveHeal EffectiveShield HealOverflow '
    'ShieldOverflow Damage10 Damage30 Damage60 TotalEffectiveDamage RemainingMonsterHp '
    'RemainingPlayerHp FinalPoolSize PreviewParityChecks FirstWindupExtensions').split()
FLOAT_METRICS = (
    'ObservedSeconds FirstEffectiveSeconds LongestEffectiveGapSeconds NoCardsSeconds '
    'PlayerStunSeconds DrawBlockedSeconds FullHandSeconds TargetControlSeconds '
    'LegalOpportunitySeconds StrategyHoldSeconds MonsterHpProgressRatio '
    'FirstWindupExtraMilliseconds').split()
METRICS = tuple(INTEGER_METRICS + FLOAT_METRICS)
ROW_FIELDS = set(METRICS) | {'Seed', 'SeedBlock', 'Hero', 'Deck', 'Group', 'Strategy',
                           'Profile', 'EnemyNonHpInputSha256', 'Outcome', 'Error',
                           'ControlUnionTicksByTarget', 'FirstWindupIntentIndexes'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, value):
    path = Path(path)
    require(not path.exists(), 'Refuse to overwrite an existing result: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write((json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8'))


def safe(root, relative):
    require(isinstance(relative, str) and '\\' not in relative, 'POSIX relative projection path required')
    p = PurePosixPath(relative)
    require(not p.is_absolute() and relative and all(x not in ('..', '.') for x in p.parts), 'Unsafe projection path')
    value = (Path(root) / relative).resolve()
    require(value.is_relative_to(Path(root).resolve()) and value.is_file(), 'Projection member missing or escaped: ' + relative)
    require(not (Path(root) / relative).is_symlink(), 'Projection symlinks are forbidden')
    return value


def record(root, reference):
    require(isinstance(reference, dict) and set(reference) == {'path', 'bytes', 'sha256'}, 'Exact file reference required')
    p = safe(root, reference['path'])
    require(type(reference['bytes']) is int and p.stat().st_size == reference['bytes']
            and digest(p) == reference['sha256'], 'Projection original-byte SHA/size differs: ' + reference['path'])
    return p


def matrix():
    rows = []
    for hero in ('Mage', 'Priest', 'Guardian'):
        for group in ('O1', 'O6', 'E1', 'BOSS'):
            for element in ('Fire', 'Wood', 'Earth', 'Metal', 'Water'):
                for level in (0, 5):
                    for block, seed in enumerate((440001, 441001, 442001)):
                        rows.append({'index': len(rows), 'unit': f'{hero}-{group}-{element}-L{level}-B{block}',
                                     'hero': hero, 'group': group, 'element': element, 'level': level,
                                     'block': block, 'seed_start': seed, 'seed_end': seed + 999})
    return rows


def provenance(index):
    return ({'source_sha': BUSINESS} if index < 90 else
            {'source_sha': MIXED, 'business_source_sha': BUSINESS,
             'instrumentation_source_sha': INSTRUMENTATION,
             'mixed_input_manifest_sha256': INPUTS_SHA, 'collector_revision': COLLECTOR})


def kind(index):
    return 'original' if index < 87 else 'named-recovery' if index == 87 else 'r2' if index < 90 else 'r3'


def exact_provenance(obj, expected):
    require(all(obj.get(k) == v for k, v in expected.items()), 'Frozen source/collector provenance differs')


def controls(value, expected):
    require(isinstance(value, list) and len(value) == len(expected)
            and {x.get('name') for x in value} == expected
            and all(x.get('rejected') is True for x in value), 'Independent negative controls incomplete')


def collection_metadata(index, manifest, summary, frozen_budget=None):
    parts = summary.get('event_parts', [])
    require(parts and len({x['path'] for x in parts}) == len(parts)
            and all(re.fullmatch(r'cap-events-\d{3}\.jsonl\.gz', x['path'])
                    and type(x['events']) is int and x['events'] > 0
                    and type(x['raw_bytes']) is int and 0 < x['raw_bytes'] <= 128 * 1024 ** 2
                    and type(x['stored_bytes']) is int and x['stored_bytes'] > 0
                    and all(re.fullmatch('[0-9a-f]{64}', x.get(k, '')) for k in ('raw_sha256', 'stored_sha256'))
                    for x in parts)
            and sum(x['events'] for x in parts) == summary['actual_casts'] + summary['actual_ticks'],
            'Complete original event-part counts/byte/hash metadata required')
    total = sum(x['raw_bytes'] for x in parts)
    if index < 90:
        require(not (V2_FIELDS & set(manifest)) and not (V2_FIELDS & set(summary)) and total <= 2 * GIB,
                'Frozen v1 retains original 2 GiB budget and original metadata')
    else:
        require(type(frozen_budget) is int and 16 * GIB <= frozen_budget <= 32 * GIB,
                'Frozen explicit v2 budget must be 16..32 GiB')
        for obj in (manifest, summary):
            exact_provenance(obj, provenance(index))
            require(obj.get('raw_unit_limit_bytes') == frozen_budget
                    and obj.get('raw_unit_limit_explicit') is True and obj.get('collection_complete') is True
                    and obj.get('event_raw_bytes') == total <= frozen_budget,
                    'v2 frozen budget/complete original cumulative raw bytes differ')
    return total


def outcomes_metadata(outcomes):
    require(isinstance(outcomes, dict) and set(outcomes) <= set(OUTCOMES)
            and all(type(n) is int and n >= 0 for n in outcomes.values())
            and sum(outcomes.values()) == 2000 and outcomes.get('Error', 0) == 0,
            'All original outcomes required; hidden Error or changed count rejected')


def retained_proof_metadata(proof, unit, objects, raw_hashes):
    require(proof.get('kind') == 'cap-effective-r3-retained-collector-proof' and proof.get('unit') == unit,
            'Wrong retained collector proof')
    for name in ('native_manifest', 'native_summary', 'validation'):
        require(proof.get(name) == objects[name] and proof.get(name + '_sha256') == raw_hashes[name],
                'Retained collector parsed object/original bytes differ: ' + name)


def validate_index(dataset):
    require(dataset.get('schema_version') == 1 and dataset.get('kind') == 'pr13-cap-full-statistics-projection', 'Wrong projection schema')
    require(dataset.get('logical_units') == 360 and dataset.get('encounters') == 720000
            and dataset.get('pairs') == 360000 and dataset.get('successful_native_executions') == 361,
            'Full 360/720000/360000/361 scope required')
    units = dataset.get('units', [])
    require(len(units) == 360, 'Incomplete dataset: all 360 units are required before statistics')
    require([x.get('identity') for x in units] == matrix(), 'Unique canonical 360 unit indices/order required')
    require([x.get('kind') for x in units] == [kind(i) for i in range(360)], 'Original/recovery/r2/r3 adoption allocation differs')
    require(dataset.get('original_success_without_raw_count') == 1
            and dataset.get('original_success_without_raw_result_sha256') == MISSING_ORIGINAL_RESULT_SHA,
            'Named missing-raw recovery must have one logical row and two successful attempt anchors')


def validate_adoption(root, reference):
    path = record(root, reference)
    require(digest(path) == ADOPTION_SHA, 'Original revision-2/r3 adoption bytes changed')
    adoption = read(path)
    require(adoption.get('business_source_sha') == BUSINESS
            and adoption.get('logical_verified_units') == 90
            and adoption.get('successful_native_executions') == 91
            and adoption.get('original_G_verified_units') == 87
            and adoption.get('named_raw_recovery_units') == 1
            and adoption.get('r2_G_verified_units') == 2, 'Adoption reconciliation differs')
    entries = adoption['base88_adoption']['entries'] + adoption['r2_entries']
    require([x['unit'] for x in entries] == [x['unit'] for x in matrix()[:90]], 'Adoption canonical order differs')
    return entries


def manifest_member(manifest, basename, expected_path=None):
    files = manifest.get('files')
    require(isinstance(files, list) and len({x['path'] for x in files}) == len(files), 'Duplicate original delivery member')
    for f in files:
        p = PurePosixPath(f['path'])
        require(not p.is_absolute() and '..' not in p.parts and '\\' not in f['path'], 'Unsafe original delivery member')
    found = [f for f in files if f['path'] == expected_path] if expected_path else [f for f in files if PurePosixPath(f['path']).name == basename]
    require(len(found) == 1, 'Exactly one original delivery member required: ' + basename)
    return found[0]


def member_matches(manifest, path, basename, expected_path=None):
    m = manifest_member(manifest, basename, expected_path)
    require(m['bytes'] == Path(path).stat().st_size and m['sha256'] == digest(path), 'Original archive member anchor differs: ' + basename)


def validate_source_gate(root, refs):
    names = ('inputs', 'original_inputs', 'original_pilot_inputs', 'source_freeze', 'build', 'pilot', 'equivalence', 'runtime_G_receipt', 'runtime_manifest')
    require(set(refs) == set(names), 'Complete source/runtime/equivalence gate references required')
    paths = {k: record(root, refs[k]) for k in names}
    objs = {k: read(p) for k, p in paths.items()}
    inp, baseline, build, pilot, equiv = [objs[k] for k in ('inputs', 'original_inputs', 'build', 'pilot', 'equivalence')]
    require(digest(paths['inputs']) == INPUTS_SHA, 'Original frozen mixed-input manifest bytes differ')
    # inputs.json is the original byte anchor itself; it has no self-hash field.
    exact_provenance(inp, {k: v for k, v in provenance(90).items() if k != 'mixed_input_manifest_sha256'})
    exact_provenance(equiv, provenance(90))
    source_fields = {k: v for k, v in provenance(90).items() if k != 'collector_revision'}
    exact_provenance(build, source_fields); exact_provenance(pilot, source_fields)
    # original_input_manifest_sha256 anchors the pre-recovery pilot-r4 2068-file
    # original, while original_inputs is the later frozen 372-file recovery proof.
    require(digest(paths['original_pilot_inputs']) == inp['original_input_manifest_sha256'], 'Original pilot-r4 input byte anchor differs')
    original_pilot = objs['original_pilot_inputs']
    require(original_pilot.get('source_sha') == BUSINESS and len(original_pilot.get('source_hashes', {})) == 2068,
            'Original 2068-file pilot input source manifest required')
    actual, original = inp['source_hashes'], inp['original_source_hashes']
    require(len(actual) == len(original) == 372 and actual.keys() == original.keys()
            and {k for k in actual if actual[k] != original[k]} == OVERRIDES
            and set(inp['override_paths']) == OVERRIDES
            and inp.get('original370_inputs_unchanged') is True
            and inp.get('Domain_business_sources_unchanged') is True
            and inp.get('exact_two_overrides_match_instrumentation_Git_bytes') is True
            and baseline.get('source_sha') == BUSINESS and baseline.get('source_hashes') == original,
            'All 372 original source records and exactly two instrumentation overrides required')
    require(all(original_pilot['source_hashes'].get(path) == value for path, value in original.items()),
            'Recovered 372 original sources must match the frozen pilot input manifest')
    freeze = objs['source_freeze']
    require(freeze.get('ok') is True and freeze.get('mixed_source_sha') == MIXED
            and freeze.get('business_source_sha') == BUSINESS and freeze.get('instrumentation_source_sha') == INSTRUMENTATION
            and freeze.get('mixed_parent_is_original_B042') is True
            and {x['path']: x['sha256'] for x in freeze['exact_override_files']} == {x: actual[x] for x in OVERRIDES},
            'Mixed Git/source freeze differs')
    domain = inp['required_Domain_hashes']
    require(len(domain) == 3 and build.get('domain_original_hashes') == domain
            and all(build['runtime_hashes'].get(k) == v == inp['original_runtime_hashes'].get(k) for k, v in domain.items())
            and len(build['runtime_hashes']) == 8 and build.get('domain_hashes_identical_to_original') is True
            and build.get('runtime_identical_to_original') is False
            and build.get('domain_regression_exact_56_passed') is True
            and build.get('source_inputs_unchanged') is True
            and build.get('ok') is True and build.get('exit_code') == 0 and build.get('oom_killed') is False,
            'Actual original Domain/runtime56 gate failed')
    c = build['domain_regression_counters']
    require(c.get('total') == c.get('executed') == c.get('passed') == 56
            and all(v == 0 for k, v in c.items() if k not in ('total', 'executed', 'passed')),
            'All original 56 regressions must pass without hidden counters')
    require(pilot.get('ok') is True and pilot.get('exit_code') == 0 and pilot.get('oom_killed') is False
            and pilot.get('equivalence_ok') is True and pilot.get('same_three_seed_paired_pilots') is True
            and pilot.get('source_and_runtime_inputs_unchanged') is True
            and pilot.get('equivalence_json_sha256') == digest(paths['equivalence']), 'Original three-pilot gate differs')
    require(equiv.get('ok') is True and equiv.get('three_complete_original_pilot_sets_retained') is True
            and equiv.get('same_business_values_equipment_state_outcomes_and_order') is True
            and len(equiv.get('comparisons', [])) == 2
            and all(x.get('ok') is True and x.get('encounters_exactly_joined') == 6
                    and x.get('paired_seeds_exactly_joined') == 3 and x.get('numeric_tolerance_used') is False
                    for x in equiv['comparisons']), 'Pilot equality proof incomplete')
    backup, manifest = objs['runtime_G_receipt'], objs['runtime_manifest']
    require(backup.get('ok') is True and backup.get('source_files_verified') == 372
            and backup.get('original_business_source_files_unchanged_verified') == 370
            and backup.get('runtime_files_verified') == 8 and backup.get('domain_regressions_verified') == 56
            and backup.get('pilot_sets_verified') == 3 and backup.get('pilot_equivalence_verified') is True
            and backup.get('domain_hashes_identical_to_original') is True
            and backup.get('runtime_identical_to_original') is False
            and backup.get('members_verified') == backup.get('members') == len(manifest['files'])
            and backup.get('manifest_sha256') == digest(paths['runtime_manifest'])
            and all(backup.get(k) is True for k in ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
                                                 'inner_gzip_CRC_raw_SHA_counts_verified')),
            'Complete runtime G original proof required')
    for key, name in [('inputs', 'inputs.json'), ('build', 'build-result.json'), ('pilot', 'pilot-result.json'), ('equivalence', 'equivalence.json')]:
        member_matches(manifest, paths[key], name, 'metadata/' + name)
    return {'inputs': inp, 'build': build, 'paths': paths}


def validate_unit(root, entry, adopted, source_gate):
    identity, i, k = entry['identity'], entry['identity']['index'], entry['kind']
    expected = provenance(i)
    names = {'native_manifest', 'native_summary', 'validation', 'result', 'delivery_manifest', 'G_receipt', 'cloud_cleanup', 'encounters'}
    if i >= 90: names |= {'preregistration', 'collector_proof'}
    require(set(entry['files']) == names, 'Exact original per-unit projection files required')
    paths = {name: record(root, ref) for name, ref in entry['files'].items()}
    values = {name: read(p) for name, p in paths.items() if name != 'encounters'}
    m, s, v, result, delivery, backup, cleanup = [values[x] for x in
        ('native_manifest', 'native_summary', 'validation', 'result', 'delivery_manifest', 'G_receipt', 'cloud_cleanup')]
    exact_provenance(m, expected); exact_provenance(s, expected); exact_provenance(v, expected)
    require(m.get('schema') == 'actual_cap_effective_experiment_v' + ('1' if i < 90 else '2'), 'Original native schema differs')
    require((m.get('hero'), m.get('group'), m.get('element'), m.get('equipment_level'), m.get('weapon_level'),
             m.get('block_index'), m.get('samples'), m.get('seed_start')) ==
            (identity['hero'], identity['group'], identity['element'], identity['level'], identity['level'],
             identity['block'], 1000, identity['seed_start']), 'Original manifest stratum/seed/sample count differs')
    require(m.get('strategy') == 'basic' and m.get('cutoff_seconds') == 600
            and m.get('candidate_activation') is False and m.get('shield_policy') == 'CurrentSteps'
            and m.get('fenxian_policy') == 'CurrentRhythm' and m.get('single_item_quality_change') is True
            and m.get('outcome_effects_descriptive_only') is True, 'Frozen native policy differs')
    require(s.get('passed') is True and s.get('errors') == 0 and s.get('rows') == 2000 and s.get('full_unit') is True
            and v.get('ok') is True and v.get('encounters') == 2000 and v.get('pairs') == 1000
            and v.get('full_unit') is True, 'Native result or independent validation incomplete')
    require(result.get('ok') is True and result.get('exit_code') == 0 and result.get('oom_killed') is False
            and result.get('owned_container_removed') is True and result.get('validation') == v,
            'Original cloud native result/validator linkage differs')
    exact_provenance(result, expected)
    for flag in ('main_acceptance_granted', 'required_cases_accepted'):
        require(s.get(flag) is False and v.get(flag) is False, 'Per-unit result cannot grant formal/MAIN acceptance')
    controls(v.get('negative_controls'), ORIGINAL_CONTROLS)
    require(type(s.get('actual_casts')) is int and type(s.get('actual_ticks')) is int
            and s['actual_casts'] > 0 and s['actual_ticks'] > 0
            and v.get('actual_casts') == s['actual_casts'] and v.get('actual_ticks') == s['actual_ticks']
            and v.get('case_denominators') == s.get('case_denominators'), 'Actual original cast/tick/case denominators differ')
    counters = s['case_denominators']
    require(set(counters) <= {a + '/' + c for a in ARMS for c in COUNTERS}
            and all(type(x) is int and x >= 0 for x in counters.values()), 'Unknown/invalid actual case denominator')
    require(sum(counters.get(a + '/all_casts', 0) for a in ARMS) == s['actual_casts']
            and sum(counters.get(a + '/all_ticks', 0) for a in ARMS) == s['actual_ticks'], 'Arm/event denominator reconciliation differs')
    for arm in ARMS:
        get = lambda name: counters.get(arm + '/' + name, 0)
        require(get('T01_capped_ticks') + get('T01_below_cap_ticks') == get('all_ticks')
                and get('T03_positive_shield') + get('T03_no_shield') == get('all_casts')
                and all(get(name) <= get('all_ticks') for name in COUNTERS if name.startswith('T02_'))
                and get('T03_full_shield') <= get('T03_positive_shield')
                and get('T03_overflow') <= get('all_casts'), 'Case denominators exceed actual original events')
    outcomes = v.get('outcomes', {})
    outcomes_metadata(outcomes)
    parts = s.get('event_parts', [])
    raw_total = collection_metadata(i, m, s, values['preregistration'].get('raw_unit_limit_bytes') if i >= 90 else None)
    require(backup.get('ok') is True and backup.get('source_sha') == expected['source_sha']
            and backup.get('raw_encounters_verified') == 2000
            and backup.get('raw_events_verified') == s['actual_casts'] + s['actual_ticks']
            and backup.get('members') == backup.get('members_verified') == len(delivery['files'])
            and type(backup.get('members')) is int and backup['members'] > 0
            and re.fullmatch('[0-9a-f]{64}', backup.get('sha256', ''))
            and type(backup.get('bytes')) is int and backup['bytes'] > 0
            and str(backup.get('local_archive', '')).replace('\\', '/').lower().startswith('g:/'),
            'Original complete G archive/inner raw counts proof required')
    require(cleanup.get('ok') is True and cleanup.get('unit') == identity['unit']
            and cleanup.get('source_sha') == expected['source_sha'], 'Original cloud cleanup receipt missing')
    archive_sha = cleanup.get('local_G_archive_sha256', cleanup.get('sha256'))
    archive_bytes = cleanup.get('local_G_archive_bytes', cleanup.get('bytes'))
    require(archive_sha == backup['sha256'] and archive_bytes == backup['bytes'], 'Cloud cleanup/G original archive linkage differs')
    require(entry.get('local_original_archive_rehashed') == {'sha256': backup['sha256'], 'bytes': backup['bytes']},
            'Projection must anchor the rehashed original G archive')
    require(s['stored_sha256'] == digest(paths['encounters']) and s['stored_bytes'] == paths['encounters'].stat().st_size,
            'Original encounter gzip bytes differ')
    for name, basename in [('native_manifest', 'manifest.json'), ('native_summary', 'summary.json'),
                            ('validation', 'validation.json'), ('encounters', 'encounters.jsonl.gz')]:
        member_matches(delivery, paths[name], basename)
    result_member = manifest_member(delivery, 'result.json', 'result.json' if k == 'original' else 'metadata/result.json')
    require(result_member['sha256'] == digest(paths['result']) and result_member['bytes'] == paths['result'].stat().st_size,
            'Original result archive member differs')
    for part in parts:
        f = manifest_member(delivery, part['path'])
        require(f['sha256'] == part['stored_sha256'] and f['bytes'] == part['stored_bytes'], 'Retained event-part archive member anchor differs')
    if i < 90:
        require(not (V2_FIELDS & set(m)) and not (V2_FIELDS & set(s)) and raw_total <= 2 * GIB,
                'Frozen v1 must retain the original 2 GiB budget and original metadata')
        a = adopted[i]
        require(a['backup_receipt'] == backup, 'Original adopted G receipt object differs')
        backup_anchor = a.get('backup_receipt_raw_sha256', a.get('backup_receipt_sha256'))
        require(backup_anchor == digest(paths['G_receipt']), 'Original adopted G receipt byte anchor differs')
        require(a['cloud_cleanup'] == cleanup, 'Original adopted cleanup semantic object differs')
        cleanup_anchor = a.get('cloud_cleanup_raw_sha256', a.get('cloud_cleanup_local_receipt_raw_sha256', a.get('cloud_cleanup_sha256')))
        require(cleanup_anchor == digest(paths['cloud_cleanup']), 'Original adopted local cleanup byte anchor differs')
        if i == 87:
            require(digest(paths['result']) == a.get('recovery_result_sha256') == RECOVERY_RESULT_SHA
                    and a.get('original_result_sha256') == MISSING_ORIGINAL_RESULT_SHA
                    and a.get('original_raw_still_missing') is True and a.get('original_cleanup_not_fabricated') is True
                    and backup.get('runtime_identical_to_original') is True
                    and backup.get('original_result_preserved') is True and backup.get('replacement_evidence_only') is True
                    and cleanup.get('original_result_preserved') is True, 'Named recovery cannot fabricate the missing original raw/cleanup')
        else:
            require(digest(paths['result']) == a['original_result_sha256'], 'Original successful native result anchor differs')
        if k == 'original':
            require(backup.get('gzip_CRC_SHA_counts_verified') is True
                    and cleanup.get('cloud_raw_removed') is True and cleanup.get('local_G_verified') is True
                    and result.get('compiled_runtime_unchanged') is True and result.get('source_inputs_unchanged') is True,
                    'Legacy original G/native/cleanup gates incomplete')
        else:
            require(all(backup.get(x) is True for x in ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
                                                       'inner_gzip_CRC_raw_SHA_counts_verified'))
                    and backup.get('manifest_sha256') == digest(paths['delivery_manifest'])
                    and backup.get('actual_casts_verified') == s['actual_casts']
                    and backup.get('actual_ticks_verified') == s['actual_ticks'], 'Recovery/r2 G full raw verification incomplete')
            require(result.get('compiled_runtime_unchanged_and_identical_to_original') is True
                    and result.get('source_subset_inputs_unchanged') is True, 'Actual original recovery/r2 business/runtime inputs changed')
    else:
        prereg, proof = values['preregistration'], values['collector_proof']
        budget = prereg.get('raw_unit_limit_bytes')
        require(type(budget) is int and 16 * GIB <= budget <= 32 * GIB, 'Frozen explicit v2 unit budget must be 16..32 GiB')
        for obj in (m, s, v, result, prereg, delivery, backup):
            exact_provenance(obj, expected)
            require(obj.get('raw_unit_limit_bytes') == budget, 'Frozen unit budget differs across original evidence')
        require(all(obj.get('raw_unit_limit_explicit') is True for obj in (m, s, result, prereg))
                and m.get('collection_complete') is True and s.get('collection_complete') is True
                and m.get('event_raw_bytes') == s.get('event_raw_bytes') == raw_total <= budget
                and v.get('event_raw_bytes') == raw_total
                and backup.get('event_raw_bytes_verified') == raw_total
                and backup.get('collector_metadata_complete') is True, 'v2 collection/raw cumulative budget incomplete')
        controls(v.get('collector_negative_controls'), COLLECTOR_CONTROLS)
        retained_proof_metadata(proof, identity['unit'], values,
                                {name: digest(paths[name]) for name in ('native_manifest', 'native_summary', 'validation')})
        require(backup.get('manifest_sha256') == digest(paths['delivery_manifest'])
                and all(backup.get(x) is True for x in ('archive_gzip_CRC_verified', 'all_original_members_sha256_verified',
                                                      'inner_gzip_CRC_raw_SHA_counts_verified', 'domain_hashes_identical_to_original'))
                and backup.get('actual_casts_verified') == s['actual_casts'] and backup.get('actual_ticks_verified') == s['actual_ticks']
                and backup.get('original_outcomes_verified') == outcomes
                and backup.get('source_subset_files_verified_by_cloud') == 372
                and backup.get('runtime_identical_to_original') is False
                and result.get('compiled_mixed_runtime_unchanged') is True
                and result.get('source_subset_inputs_unchanged') is True
                and result.get('domain_hashes_identical_to_original') is True
                and cleanup.get('cloud_raw_removed') is True
                and cleanup.get('source_runtime_and_metadata_retained') is True
                and cleanup.get('backup_receipt_sha256') == digest(paths['G_receipt'])
                and cleanup.get('manifest_sha256') == digest(paths['delivery_manifest']), 'r3 immutable G/source/cleanup linkage incomplete')
        contracts = [obj.get('runtime_contract') for obj in (prereg, result, backup)]
        require(contracts[0] == contracts[1] == contracts[2], 'Per-unit original runtime contract differs')
        contract = contracts[0]; exact_provenance(contract, expected)
        require(contract.get('source_subset_files') == 372 and contract.get('original_business_files') == 370
                and set(contract.get('override_paths', [])) == OVERRIDES
                and contract.get('runtime_hashes') == source_gate['build']['runtime_hashes']
                and contract.get('domain_original_hashes') == source_gate['build']['domain_original_hashes']
                and contract.get('domain_hashes_identical_to_original') is True
                and contract.get('runtime_identical_to_original') is False, 'All 372 original sources and actual compiled runtime contract required')
        for field, name in [('build_result_sha256', 'build'), ('pilot_result_sha256', 'pilot'),
                            ('equivalence_json_sha256', 'equivalence'), ('G_backup_receipt_sha256', 'runtime_G_receipt'),
                            ('G_manifest_sha256', 'runtime_manifest')]:
            require(contract.get(field) == digest(source_gate['paths'][name]), 'Runtime original proof byte pointer differs: ' + field)
    return {'identity': identity, 'paths': paths, 'manifest': m, 'summary': s, 'validation': v}


def validate_projection(directory, expected_prereg_sha, expected_formal_sha):
    root = Path(directory).resolve(); dataset = read(root / 'dataset.json')
    validate_index(dataset)
    prereg_path = record(root, dataset['analysis_preregistration'])
    formal_path = record(root, dataset['formal_plan'])
    require(digest(prereg_path) == expected_prereg_sha and digest(formal_path) == expected_formal_sha,
            'Caller must anchor committed analysis preregistration and original formal plan bytes')
    prereg = read(prereg_path)
    require(prereg.get('schema_version') == 1 and prereg.get('kind') == 'PR13-B08.4-full-descriptive-statistics'
            and prereg.get('formal_plan_sha256') == expected_formal_sha
            and prereg.get('logical_units') == 360 and prereg.get('statistical_inference') is False
            and prereg.get('candidate_changes') is False and prereg.get('MAIN_accepted') is False,
            'Full descriptive preregistration required; no unregistered inference or candidate change')
    adoption = validate_adoption(root, dataset['adoption'])
    source = validate_source_gate(root, dataset['source_gate'])
    units = [validate_unit(root, e, adoption, source) for e in dataset['units']]
    return dataset, units, source


def cloud_guard(directory):
    require(platform.system() == 'Linux' and os.environ.get('PR13_CAP_STATISTICS_CLOUD') == 'tencent-readonly-v1',
            'Business/statistical computation is authorized only inside the Tencent cloud container')
    require(Path(directory).resolve() == Path('/inputs') and Path('/work').is_dir()
            and os.statvfs('/inputs').f_flag & os.ST_RDONLY
            and os.statvfs('/work').f_flag & os.ST_RDONLY,
            'Cloud projection and tool source must be readonly mounted inputs')
    # Host runner admits no network and anchors the exact image/tool/projection first.
    require(os.getuid() == 1000 and Path('/.dockerenv').exists(), 'Owned isolated cloud container/user required')


def distribution(values, total):
    present = sorted(x for x in values if x is not None)
    n = len(present)
    result = {'count': n, 'null_count': total - n}
    if not n:
        return {**result, 'min': None, 'max': None, 'sum': None, 'mean': None, 'quantiles': None}
    def quantile(p):
        pos = (n - 1) * p; lo = math.floor(pos); hi = math.ceil(pos)
        return present[lo] + (present[hi] - present[lo]) * (pos - lo)
    return {**result, 'min': present[0], 'max': present[-1], 'sum': math.fsum(present),
            'mean': math.fsum(present) / n,
            'quantiles': {str(p): quantile(p) for p in (.1, .25, .5, .75, .9)}}


def case_coverage(level, denominators):
    required = (['T01_capped_ticks'] if level == 5 else ['T01_below_cap_ticks']) + [
        'T02_equipment_floor_ticks', 'T02_card_speed_ticks', 'T02_PVE_conversion_ticks',
        'T02_expiry_ticks', 'T03_positive_shield', 'T03_full_shield', 'T03_overflow']
    return {case: {'actual_validated_events': denominators.get(case, 0),
                   'status': 'Observed' if denominators.get(case, 0) > 0 else 'Gap'} for case in required}


def stream_rows(unit):
    summary = unit['summary']; h = hashlib.sha256(); raw = 0; rows = {}
    with gzip.open(unit['paths']['encounters'], 'rb') as f:
        for line in f:
            require(len(line) <= 1024 * 1024, 'Encounter line exceeds frozen projection bound')
            h.update(line); raw += len(line); row = json.loads(line)
            require(set(row) == ROW_FIELDS, 'Original EncounterSample field set changed; never silently drop a field')
            require(row['Hero'] == unit['identity']['hero'] and row['Group'] == unit['identity']['group']
                    and row['SeedBlock'] == unit['identity']['block'] and row['WeaponLevel'] == unit['identity']['level']
                    and row['Profile'] in ARMS and row['Strategy'] == 'basic' and row['Deck'] == 'CapLegalTwenty'
                    and type(row['Seed']) is int and unit['identity']['seed_start'] <= row['Seed'] <= unit['identity']['seed_end'],
                    'Original encounter identity differs')
            key = row['Seed'], row['Profile']; require(key not in rows, 'Duplicate original paired encounter')
            require(row['Outcome'] in OUTCOMES and row['Outcome'] != 'Error' and row['Error'] is None,
                    'Unexpected Error retained and rejected rather than filtered')
            require(re.fullmatch('[0-9a-f]{64}', row['EnemyNonHpInputSha256'] or ''), 'Original paired enemy identity missing')
            for metric in METRICS:
                value = row[metric]
                require(value is None and metric == 'FirstEffectiveSeconds' or
                        type(value) in (int, float) and math.isfinite(value)
                        and (metric not in INTEGER_METRICS or type(value) is int), 'Original numerical field invalid: ' + metric)
            require(isinstance(row['ControlUnionTicksByTarget'], dict)
                    and all(isinstance(k, str) and type(v) is int and v >= 0 for k, v in row['ControlUnionTicksByTarget'].items())
                    and isinstance(row['FirstWindupIntentIndexes'], list)
                    and all(type(v) is int for v in row['FirstWindupIntentIndexes']), 'Original target/intent fields invalid')
            rows[key] = row
    require(raw == summary['raw_bytes'] and h.hexdigest() == summary['raw_sha256'] and len(rows) == 2000,
            'Original encounter gzip CRC/raw SHA/byte/count differs')
    expected = {(seed, arm) for seed in range(unit['identity']['seed_start'], unit['identity']['seed_end'] + 1) for arm in ARMS}
    require(set(rows) == expected, 'All 1000 original seed pairs required')
    require(collections.Counter(r['Outcome'] for r in rows.values()) == unit['validation']['outcomes'], 'Original outcomes/validator reconciliation differs')
    require(sum(r['Actions'] for r in rows.values()) == summary['actual_casts']
            and abs(math.fsum(r['ObservedSeconds'] * 10 for r in rows.values()) - summary['actual_ticks']) <= 1e-6,
            'Original per-encounter cast/tick totals differ (aggregate floating representation only)')
    for seed in range(unit['identity']['seed_start'], unit['identity']['seed_end'] + 1):
        a, b = [rows[seed, arm] for arm in ARMS]
        require(all(a[f] == b[f] for f in ('OpeningEnemyHp', 'OpeningEnemyShield', 'EnemyNonHpInputSha256')),
                'Original paired enemy input changed')
    return rows


def compute(directory, output, prereg_sha, formal_sha):
    cloud_guard(directory)
    dataset, units, _ = validate_projection(directory, prereg_sha, formal_sha)
    report = {'schema_version': 1, 'kind': 'PR13-B08.4-full-descriptive-statistics',
              'full_data_complete': True, 'logical_units': 360, 'strata': 120, 'blocks_per_stratum': 3,
              'encounters': 720000, 'paired_encounters': 360000, 'successful_native_executions': 361,
              'source_allocation': {'original_B042_units': 90, 'mixed_collector_units': 270,
                                    'missing_original_raw_replaced_once': True},
              'dataset_sha256': digest(Path(directory) / 'dataset.json'),
              'analysis_preregistration_sha256': prereg_sha, 'formal_plan_sha256': formal_sha,
              'descriptive_only': True, 'statistical_inference': False, 'candidate_changes': False,
              'event_oracle': 'Original independent cloud validation and G full raw CRC/SHA proof, not recomputed from projection',
              'quantiles': 'Linear interpolation at (n-1)*p; p=0.1,0.25,0.5,0.75,0.9',
              'stratum_reports': [], 'gaps': [], 'outcomes': {x: 0 for x in OUTCOMES},
              'actual_casts': 0, 'actual_ticks': 0,
              'required_cases_accepted': False, 'formal_EXPERIMENT_accepted': False, 'MAIN_accepted': False}
    for start in range(0, 360, 3):
        selected = units[start:start + 3]; first = selected[0]['identity']
        rows = {}; denominators = collections.Counter()
        for unit in selected:
            current = stream_rows(unit)
            for (seed, arm), row in current.items():
                key = unit['identity']['block'], seed, arm
                require(key not in rows, 'Duplicate complete block pair'); rows[key] = row
            denominators.update(unit['validation']['case_denominators'])
            report['actual_casts'] += unit['summary']['actual_casts']; report['actual_ticks'] += unit['summary']['actual_ticks']
        require(len(rows) == 6000, 'All three blocks/6000 encounters required per stratum')
        stratum = {x: first[x] for x in ('hero', 'group', 'element', 'level')}
        stratum.update({'encounters': 6000, 'pairs': 3000, 'blocks': [0, 1, 2], 'arms': {},
                        'paired_outcome_transitions': {}, 'paired_numeric_deltas_orange_minus_purple': {}})
        for arm in ARMS:
            armrows = [row for (_, _, profile), row in rows.items() if profile == arm]
            outcomes = collections.Counter(r['Outcome'] for r in armrows)
            report['outcomes'].update({x: report['outcomes'][x] + outcomes.get(x, 0) for x in OUTCOMES})
            actual = {x: denominators.get(arm + '/' + x, 0) for x in COUNTERS}
            coverage = case_coverage(first['level'], actual)
            for case, value in coverage.items():
                if value['status'] == 'Gap':
                    report['gaps'].append({**{x: first[x] for x in ('hero', 'group', 'element', 'level')},
                                           'arm': arm, 'case': case, 'actual_validated_events': 0})
            target = collections.defaultdict(list); intent = collections.Counter(); sequences = collections.Counter()
            for r in armrows:
                for name, count in r['ControlUnionTicksByTarget'].items(): target[name].append(count)
                intent.update(r['FirstWindupIntentIndexes']); sequences[json.dumps(r['FirstWindupIntentIndexes'], separators=(',', ':'))] += 1
            stratum['arms'][arm] = {'encounters': 3000, 'outcomes': {x: outcomes.get(x, 0) for x in OUTCOMES},
                'numerical_metrics': {m: distribution([r[m] for r in armrows], 3000) for m in METRICS},
                'ControlUnionTicksByTarget': {k: {'present_encounters': len(v), 'distribution_when_present': distribution(v, len(v))}
                                            for k, v in sorted(target.items())},
                'FirstWindupIntentIndexes': {'individual_index_frequencies': {str(k): v for k, v in sorted(intent.items())},
                                            'ordered_sequence_frequencies': dict(sorted(sequences.items()))},
                'actual_cloud_validated_case_denominators': actual, 'case_coverage': coverage}
        transitions = collections.Counter(); deltas = {m: [] for m in METRICS}
        for block in range(3):
            for seed in range(440001 + block * 1000, 441001 + block * 1000):
                a, b = [rows[block, seed, arm] for arm in ARMS]
                transitions[a['Outcome'] + '->' + b['Outcome']] += 1
                for m in METRICS: deltas[m].append(None if a[m] is None or b[m] is None else b[m] - a[m])
        stratum['paired_outcome_transitions'] = {a + '->' + b: transitions.get(a + '->' + b, 0) for a in OUTCOMES for b in OUTCOMES}
        stratum['paired_numeric_deltas_orange_minus_purple'] = {m: distribution(v, 3000) for m, v in deltas.items()}
        report['stratum_reports'].append(stratum)
    require(sum(report['outcomes'].values()) == 720000 and report['outcomes']['Error'] == 0
            and len(report['stratum_reports']) == 120, 'Full final count reconciliation differs')
    report['all_registered_case_predicates_observed'] = not report['gaps']
    report['statistical_computation_complete'] = True
    report['ok'] = True  # Computation success is distinct from formal case acceptance.
    write_new(output, report)
    return {k: report[k] for k in ('ok', 'full_data_complete', 'logical_units', 'encounters', 'paired_encounters',
                                    'actual_casts', 'actual_ticks', 'all_registered_case_predicates_observed',
                                    'required_cases_accepted', 'MAIN_accepted')} | {'gap_count': len(report['gaps']), 'report_sha256': digest(output)}


def metadata_controls():
    """Synthetic metadata only. Never calls stream_rows/distribution/compute."""
    good = {'schema_version': 1, 'kind': 'pr13-cap-full-statistics-projection', 'logical_units': 360,
            'encounters': 720000, 'pairs': 360000, 'successful_native_executions': 361,
            'original_success_without_raw_count': 1, 'original_success_without_raw_result_sha256': MISSING_ORIGINAL_RESULT_SHA,
            'units': [{'identity': x, 'kind': kind(x['index'])} for x in matrix()]}
    validate_index(good); rejected = []
    mutations = {'missing_unit': lambda x: x['units'].pop(),
                 'duplicate_unit_index': lambda x: x['units'].__setitem__(91, copy.deepcopy(x['units'][90])),
                 'adoption_recovery_double_counted': lambda x: x.update(original_success_without_raw_count=0),
                 'incomplete_pairs': lambda x: x.update(pairs=359999),
                 'old_unit_relabelled_v2': lambda x: x['units'][87].update(kind='r3')}
    for name, mutation in mutations.items():
        bad = copy.deepcopy(good); mutation(bad)
        try: validate_index(bad)
        except ValueError: rejected.append({'name': name, 'rejected': True})
        else: raise ValueError('Synthetic invalid metadata accepted: ' + name)
    for name, obj, expected in [('wrong_mixed_source', {'source_sha': BUSINESS}, provenance(90)),
                                 ('wrong_old_source', {'source_sha': MIXED}, provenance(0))]:
        try: exact_provenance(obj, expected)
        except ValueError: rejected.append({'name': name, 'rejected': True})
        else: raise ValueError('Synthetic invalid provenance accepted')
    part = {'path': 'cap-events-000.jsonl.gz', 'events': 2, 'raw_bytes': 100,
            'stored_bytes': 80, 'raw_sha256': '0'*64, 'stored_sha256': '1'*64}
    old_m = {'source_sha': BUSINESS}; old_s = {'actual_casts': 1, 'actual_ticks': 1, 'event_parts': [part]}
    new_m = {**provenance(90), 'raw_unit_limit_bytes': 16*GIB, 'raw_unit_limit_explicit': True,
             'event_raw_bytes': 100, 'collection_complete': True}
    new_s = {**new_m, **old_s}
    collection_metadata(0, old_m, old_s); collection_metadata(90, new_m, new_s, 16*GIB)
    mutations = {
        'old_v1_larger_raw_budget': (0, old_m, old_s, None, lambda x,y: y.update(
            actual_ticks=33, event_parts=[{**part, 'path': f'cap-events-{i:03}.jsonl.gz', 'raw_bytes':128*1024**2} for i in range(17)])),
        'old_v1_relabelled_new_fields': (0, old_m, old_s, None, lambda x,y: x.update(raw_unit_limit_bytes=16*GIB)),
        'new_declared_budget_changed': (90, new_m, new_s, 16*GIB, lambda x,y: x.update(raw_unit_limit_bytes=32*GIB)),
        'new_cumulative_raw_changed': (90, new_m, new_s, 16*GIB, lambda x,y: y.update(event_raw_bytes=99)),
        'new_collection_incomplete': (90, new_m, new_s, 16*GIB, lambda x,y: y.update(collection_complete=False)),
        'original_event_part_missing': (90, new_m, new_s, 16*GIB, lambda x,y: y.update(event_parts=[])),
        'original_event_part_duplicate': (90, new_m, new_s, 16*GIB, lambda x,y: y.update(event_parts=[part,part]))}
    for name, (i, mm, ss, budget, mutation) in mutations.items():
        mm, ss = copy.deepcopy(mm), copy.deepcopy(ss); mutation(mm, ss)
        try: collection_metadata(i, mm, ss, budget)
        except ValueError: rejected.append({'name': name, 'rejected': True})
        else: raise ValueError('Synthetic invalid collection metadata accepted: ' + name)
    for name, outcomes in [('hidden_Error', {'Victory': 1999, 'Error': 1}),
                           ('outcome_denominator_changed', {'Victory': 1999}),
                           ('unknown_outcome', {'Passed': 2000})]:
        try: outcomes_metadata(outcomes)
        except ValueError: rejected.append({'name': name, 'rejected': True})
        else: raise ValueError('Synthetic invalid outcome metadata accepted')
    objects = {name: {'synthetic_only': True} for name in ('native_manifest', 'native_summary', 'validation')}
    hashes = {name: 'a'*64 for name in objects}
    proof = {'kind': 'cap-effective-r3-retained-collector-proof', 'unit': 'synthetic', **objects,
             **{name+'_sha256': value for name,value in hashes.items()}}
    retained_proof_metadata(proof, 'synthetic', objects, hashes)
    for name, mutation in [('retained_parsed_object_changed', lambda x: x.update(native_summary={})),
                           ('retained_original_byte_SHA_changed', lambda x: x.update(validation_sha256='b'*64))]:
        bad=copy.deepcopy(proof);mutation(bad)
        try: retained_proof_metadata(bad, 'synthetic', objects, hashes)
        except ValueError: rejected.append({'name': name, 'rejected': True})
        else: raise ValueError('Synthetic invalid retained proof accepted')
    require(all(v['status'] == 'Gap' for v in case_coverage(5, {}).values()), 'Zero case denominator cannot pass')
    rejected.append({'name': 'zero_actual_case_is_Gap', 'rejected': True})
    require('T01_below_cap_ticks' in case_coverage(0, {}) and 'T01_capped_ticks' not in case_coverage(0, {}), 'L0 below-cap scope must remain separate')
    return {'ok': True, 'scope': 'synthetic metadata gates only', 'controls': rejected,
            'business_or_statistical_computation_executed': False, 'MAIN_accepted': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata-controls', action='store_true')
    p.add_argument('--validate-projection', action='store_true', help='Hash/metadata gates only; no statistics')
    p.add_argument('--input'); p.add_argument('--output'); p.add_argument('--prereg-sha256'); p.add_argument('--formal-plan-sha256')
    a = p.parse_args()
    if a.metadata_controls:
        require(not any((a.input, a.output, a.validate_projection)), 'Metadata controls cannot use real encounter input')
        result = metadata_controls()
    else:
        require(all((a.input, a.prereg_sha256, a.formal_plan_sha256)), 'Input and two frozen plan SHA256 anchors required')
        if a.validate_projection:
            dataset, units, _ = validate_projection(a.input, a.prereg_sha256, a.formal_plan_sha256)
            result = {'ok': True, 'metadata_only': True, 'logical_units': len(units), 'dataset_sha256': digest(Path(a.input) / 'dataset.json'), 'MAIN_accepted': False}
        else:
            require(a.output, 'Fresh output required')
            result = compute(a.input, a.output, a.prereg_sha256, a.formal_plan_sha256)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
