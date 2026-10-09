"""Pure Python statistical fixtures; no Domain, network, or historic acceptance claims."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

from tools import pr13_factor_matrix as factors
from tools import pr13_simulation_report as reports

PROFILES = dict(zip(factors.FACTORS, ('TargetedO6Hp095', 'TargetedO6Hp090',
                                     'TargetedO6Windup025', 'TargetedO6Windup050')))


def row(seed, profile='Baseline', group='O6', hero='Mage', strategy='basic'):
    windup = 250 if profile == 'TargetedO6Windup025' else 500 if profile == 'TargetedO6Windup050' else 0
    return dict(Seed=seed, SeedBlock=seed % 3, Hero=hero, WeaponLevel=0, Deck='default',
                Group=group, Strategy=strategy, Profile=profile, Outcome='Victory',
                ObservedSeconds=10, LongestEffectiveGapSeconds=1, Damage60=10,
                EffectiveShield=0, HealOverflow=0, ShieldOverflow=0, PreviewParityChecks=1,
                FirstWindupExtraMilliseconds=windup, FirstWindupExtensions=1 if windup else 0,
                FirstWindupIntentIndexes=[0] if windup else [])


def fixture(directory, rows, seed_start=0, samples=3, factor='outer-o6-hp095', **changes):
    directory.mkdir(parents=True, exist_ok=True)
    manifest = dict(Kind='statistical_fixture', SourceSha='fixture-source',
                    DomainAssemblySha256='fixture-domain', SimulatorAssemblySha256='fixture-simulator',
                    SourceConfigSha256='fixture-config', ConfigVersion='fixture-v1',
                    SeedStart=seed_start, SamplesPerStratum=samples, Candidate=factor,
                    CutoffSeconds=60, ActionIntervalSeconds=.4, Groups=['O6'], Strategies=['basic'],
                    Decks=[dict(Hero='Mage', Key='default')], WeaponLevel=0,
                    CandidateActivation=False, SingleFactorOnly=True, CandidateWhitelist=['O6'])
    manifest.update(changes)
    raw = directory / 'encounters.jsonl'
    raw.write_text(''.join(json.dumps(value) + '\n' for value in rows), encoding='utf8')
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    (directory / 'summary.json').write_text(json.dumps(dict(
        SourceSha=manifest['SourceSha'], RawSha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        Total=len(rows))), encoding='utf8')
    return directory


class SimulationReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def paired(self, start=0, samples=3):
        return [dict(row(seed, profile),SeedBlock=(seed-start)%3) for seed in range(start, start + samples)
                for profile in ('Baseline', 'TargetedO6Hp095')]

    def report(self, inputs):
        target = self.root / 'report'
        argv = ['report', '--inputs', *map(str, inputs), '--output', str(target)]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            exit_code = reports.main()
        return json.loads((target / 'report.json').read_text(encoding="utf-8")), (target / 'report.md').read_text(encoding="utf-8"), exit_code

    def test_small_single_run_has_no_three_block_claim(self):
        directory = fixture(self.root / 'input', self.paired())
        report, markdown, exit_code = self.report([directory])
        self.assertEqual(exit_code, 0)
        self.assertNotIn('每个主要层合并三段', markdown)
        budget = report['strata'][0]['sample_budget']
        self.assertFalse(budget['main_sample_floor_met'])
        self.assertEqual(budget['status'], 'Inconclusive')
        self.assertEqual(budget['seed_blocks'], [{'seed_start': 0, 'n': 3}])
        self.assertEqual(report['candidate_recommendation'], 'NotEvaluated')

    def test_elite_hp_candidates_keep_other_encounters_as_exact_paired_controls(self):
        for candidate,profile in [('elite-e4-hp095','TargetedE4Hp095'),('elite-e4-hp090','TargetedE4Hp090')]:
            with self.subTest(candidate=candidate):
                rows=[row(seed,profile=name,group=group) for seed in range(3)
                      for group in ('E4','O6') for name in ('Baseline',profile if group=='E4' else 'BaselinePairedControl')]
                directory=fixture(self.root/candidate,rows,factor=candidate,Groups=['E4','O6'],CandidateWhitelist=['E4'])
                _,_,loaded=reports.load_run(directory)
                self.assertEqual(12,len(loaded))
                self.assertEqual({'Baseline','BaselinePairedControl'},{value['Profile'] for value in loaded if value['Group']=='O6'})

    def test_elite_hp_candidate_applied_outside_whitelist_is_rejected(self):
        rows=[row(seed,profile=name,group='O6') for seed in range(3) for name in ('Baseline','TargetedE4Hp095')]
        directory=fixture(self.root/'wrong-group',rows,factor='elite-e4-hp095',CandidateWhitelist=['E4'])
        with self.assertRaisesRegex(ValueError,'Undeclared stratum'):
            reports.load_run(directory)

    def test_report_provenance_uses_checkout_when_called_outside_repo(self):
        directory=fixture(self.root/'input',self.paired())
        caller=Path.cwd()
        try:
            os.chdir(self.root)
            report,_,_=self.report([directory])
        finally:
            os.chdir(caller)
        self.assertRegex(report['report_source_sha'],r'^[0-9a-f]{40}$')
        self.assertEqual(report['report_algorithm_sha256'],hashlib.sha256(Path(reports.__file__).read_bytes()).hexdigest())

    def test_three_blocks_of_one_thousand_meet_budget_without_acceptance(self):
        inputs = [fixture(self.root / str(start), self.paired(start, 1000), seed_start=start, samples=1000)
                  for start in (0, 1000, 2000)]
        report, _, _ = self.report(inputs)
        self.assertTrue(report['paired_comparisons'][0]['sample_budget']['main_sample_floor_met'])
        self.assertFalse(report['paired_comparisons'][0]['sample_budget']['precision_guaranteed'])
        self.assertEqual(report['candidate_recommendation'], 'NotEvaluated')

    def test_observed_p95_and_completed_p95_cannot_claim_all_started_ttk(self):
        rows = self.paired(samples=20)
        for value in rows:
            if value['Seed'] >= 10:
                value.update(Outcome='Censored', ObservedSeconds=60)
        report, _, _ = self.report([fixture(self.root / 'input', rows, samples=20)])
        for stratum in report['strata']:
            self.assertEqual(stratum['all_outcome_observed_seconds']['p95'], 60)
            self.assertEqual(stratum['victory_seconds']['p95'], 10)
            self.assertEqual(stratum['censored_rate'], .5)
            ttk = stratum['victory_ttk_p95_all_started']
            self.assertIsNone(ttk['value'])
            self.assertFalse(ttk['identified'])
            self.assertIn('right_censored_outcomes', ttk['missing_reasons'])

    def test_error_and_death_remain_in_denominator(self):
        rows = self.paired()
        for value in rows:
            if value['Seed'] == 1: value['Outcome'] = 'Death'
            if value['Seed'] == 2: value['Outcome'] = 'Error'
        report, _, exit_code = self.report([fixture(self.root / 'input', rows)])
        self.assertEqual(exit_code, 1)
        self.assertEqual(report['total'], 6)
        self.assertEqual(report['errors'], 2)
        self.assertEqual(report['strata'][0]['victory_rate'], 1 / 3)
        self.assertFalse(report['strata'][0]['victory_ttk_p95_all_started']['identified'])

    def test_p95_with_small_censoring_uses_all_started_rank_and_censor_bounds(self):
        for early_censor in (False, True):
            with self.subTest(early_censor=early_censor):
                rows = self.paired(samples=100)
                for value in rows:
                    value['ObservedSeconds'] = value['Seed'] + 1
                    if value['Seed'] >= 95:
                        value.update(Outcome='Censored', ObservedSeconds=1 if early_censor else 120)
                report, _, _ = self.report([fixture(self.root / 'input', rows, samples=100, CutoffSeconds=120)])
                for stratum in report['strata']:
                    ttk = stratum['victory_ttk_p95_all_started']
                    self.assertEqual(stratum['victory_seconds']['p95'], 91)
                    self.assertEqual(ttk['population_n'], 100)
                    self.assertEqual(ttk['identified'], not early_censor)
                    self.assertEqual(ttk['value'], None if early_censor else 95)

    def test_tied_victories_identify_p95_even_with_early_censoring(self):
        rows=self.paired(samples=100)
        for value in rows:
            if value['Seed']>=95:value.update(Outcome='Censored',ObservedSeconds=1)
        report,_,_=self.report([fixture(self.root/'input',rows,samples=100)])
        for stratum in report['strata']:
            self.assertTrue(stratum['victory_ttk_p95_all_started']['identified'])
            self.assertEqual(stratum['victory_ttk_p95_all_started']['value'],10)
        self.assertEqual(report['sources'][0]['source_git_dirty'],'Unknown')
        self.assertIsInstance(report['report_git_dirty'],bool)

    def test_competing_death_stays_in_all_started_rank(self):
        rows = self.paired(samples=100)
        for value in rows:
            value['ObservedSeconds'] = value['Seed'] + 1
            if value['Seed'] >= 96: value['Outcome'] = 'Death'
        report, _, _ = self.report([fixture(self.root / 'input', rows, samples=100, CutoffSeconds=120)])
        for stratum in report['strata']:
            self.assertEqual(stratum['victory_seconds']['p95'], 92)
            self.assertEqual(stratum['victory_ttk_p95_all_started']['value'], 95)
            self.assertEqual(stratum['victory_ttk_p95_all_started']['population_n'], 100)

    def test_mixed_frozen_inputs_are_rejected(self):
        for field in ('SourceSha', 'DomainAssemblySha256', 'SimulatorAssemblySha256',
                      'SourceConfigSha256', 'CutoffSeconds', 'Candidate', 'Decks'):
            with self.subTest(field=field):
                first = fixture(self.root / 'a', self.paired())
                changed = 120 if field == 'CutoffSeconds' else ([dict(Hero='Mage', Key='default', Sha256='different-deck')]
                           if field == 'Decks' else 'different-fixture-value')
                other = fixture(self.root / 'b', self.paired(3), seed_start=3, **{field: changed})
                with self.assertRaises(ValueError): self.report([first, other])

    def test_removed_or_out_of_block_samples_are_rejected(self):
        for rows in (self.paired()[:-2], self.paired(1)):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    self.report([fixture(self.root / 'input', rows)])

    def test_duplicate_seed_and_candidate_without_baseline_are_rejected(self):
        for rows in (self.paired() + [row(0)], [row(seed, 'TargetedO6Hp095') for seed in range(3)]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    self.report([fixture(self.root / 'input', rows)])

    def test_empty_unknown_and_nonfinite_samples_are_rejected(self):
        for changed in ([], [dict(row(0), Outcome='Unknown')], [dict(row(0), Damage60=float('nan'))]):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    self.report([fixture(self.root / 'input', changed)])

    def test_duplicate_matrix_dimensions_are_not_silent_deduplication(self):
        for changes in ({'Groups':['O6','O6']},{'Strategies':['basic','basic']},
                        {'Decks':[dict(Hero='Mage',Key='default')]*2}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.report([fixture(self.root/'input',self.paired(),**changes)])

    def test_same_seed_paired_damage_delta_and_raw_pooled_quantile(self):
        inputs = []
        for start in (0, 3, 6):
            rows = self.paired(start)
            for value in rows:
                value['ObservedSeconds'] = value['Seed'] + 1
                value['Damage60'] = value['Seed'] + (7 if value['Profile'] != 'Baseline' else 0)
            inputs.append(fixture(self.root / str(start), rows, seed_start=start))
        report, _, _ = self.report(inputs)
        comparison = report['paired_comparisons'][0]
        self.assertEqual(comparison['n'], 9)
        self.assertEqual(comparison['mean_damage60_delta'], 7)
        self.assertEqual(comparison['paired_seed_bootstrap_damage60_95'], [7, 7])
        self.assertEqual(report['strata'][0]['all_outcome_observed_seconds']['p95'], 9)
        self.assertFalse(comparison['sample_budget']['main_sample_floor_met'])


class FactorControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.samples = 3
        self.jobs = []
        for factor in factors.FACTORS:
            for start in (0, 3, 6):
                rows = [row(seed, profile, group, hero, strategy)
                        for seed in range(start, start + self.samples)
                        for hero in ('Mage', 'Priest', 'Guardian')
                        for strategy in ('baseline_all_hand', 'basic', 'build')
                        for group in ('O1', 'O6', 'E1', 'BOSS')
                        for profile in ('Baseline', PROFILES[factor] if group == 'O6' else 'BaselinePairedControl')]
                directory = fixture(self.root / factor / str(start), rows, seed_start=start, factor=factor,
                                    Groups=['O1', 'O6', 'E1', 'BOSS'],
                                    Strategies=['baseline_all_hand', 'basic', 'build'],
                                    Decks=[dict(Hero=hero, Key='default') for hero in ('Mage', 'Priest', 'Guardian')])
                self.jobs.append(dict(factor=factor, seed_start=start, output=str(directory), state='Completed'))
        (self.root / 'preregistration.json').write_text(json.dumps(dict(
            source_sha='fixture-source', samples_per_stratum_per_run=3, independent_runs_per_factor=3,
            assembly_hashes={'FantasyCard.Domain.dll': 'fixture-domain',
                             'FantasyCard.Numerics.dll': 'fixture-simulator'}, jobs=self.jobs)), encoding="utf-8")

    def change_rows(self, mutate, job_index=0):
        directory = Path(self.jobs[job_index]['output'])
        rows = [json.loads(line) for line in (directory / 'encounters.jsonl').read_text(encoding="utf-8").splitlines()]
        mutate(rows)
        manifest = json.loads((directory / 'manifest.json').read_text(encoding="utf-8"))
        fixture(directory, rows, **manifest)

    def validate(self, jobs=None):
        return factors.validate_controls(self.root, self.jobs if jobs is None else jobs)

    def test_valid_smoke_controls_do_not_meet_primary_floor(self):
        result = self.validate()
        self.assertTrue(result['passed'], result['errors'])
        self.assertFalse(result['main_sample_floor_met'])
        self.assertFalse(result['acceptance_eligible'])
        self.assertEqual(result['execution_states'], {'Completed': 12})

    def test_duplicate_baseline_or_wrong_candidate_is_not_a_pair(self):
        for replacement in ('Baseline', 'TargetedO6Hp090'):
            with self.subTest(replacement=replacement):
                self.change_rows(lambda rows: [value.update(Profile=replacement) for value in rows
                                              if value['Group'] == 'O6' and value['Profile'] != 'Baseline'])
                self.assertFalse(self.validate()['passed'])

    def test_non_o6_changed_and_hp_factor_windup_are_rejected(self):
        self.change_rows(lambda rows: next(value for value in rows if value['Profile'] == 'BaselinePairedControl').update(Damage60=999))
        self.assertIn('unaffected_control_changed', [e['kind'] for e in self.validate()['errors']])
        self.change_rows(lambda rows: next(value for value in rows if value['Profile'] == 'TargetedO6Hp095').update(FirstWindupExtraMilliseconds=250))
        self.assertIn('unexpected_windup_change', [e['kind'] for e in self.validate()['errors']])

    def test_first_windup_extension_needs_one_matching_index_per_extension(self):
        self.change_rows(lambda rows: next(value for value in rows if value['Profile'] == 'TargetedO6Windup025').update(FirstWindupIntentIndexes=[]), 6)
        self.assertIn('first_intent_not_extended', [e['kind'] for e in self.validate()['errors']])

    def test_missing_whole_seed_pair_and_wrong_seed_are_rejected(self):
        self.change_rows(lambda rows: rows.__setitem__(slice(None), [value for value in rows if value['Seed'] != 2]))
        self.assertFalse(self.validate()['passed'])
        self.change_rows(lambda rows: [value.update(Seed=999) for value in rows])
        self.assertFalse(self.validate()['passed'])

    def test_frozen_assembly_or_wrong_factor_manifest_is_rejected(self):
        directory = Path(self.jobs[0]['output'])
        manifest = json.loads((directory / 'manifest.json').read_text(encoding="utf-8"))
        manifest['DomainAssemblySha256'] = 'different-domain'
        manifest['Candidate'] = 'outer-o6-windup050'
        (directory / 'manifest.json').write_text(json.dumps(manifest), encoding="utf-8")
        self.assertFalse(self.validate()['passed'])

    def test_incomplete_preregistration_cannot_hide_unrun_factors_or_blocks(self):
        path=self.root/'preregistration.json'
        original=json.loads(path.read_text(encoding="utf-8"))
        for selected in (self.jobs[:3],self.jobs[:-1],self.jobs+[self.jobs[0]]):
            with self.subTest(jobs=len(selected)):
                path.write_text(json.dumps(dict(original,jobs=selected)), encoding="utf-8")
                result=self.validate(selected)
                self.assertFalse(result['passed'])
                self.assertEqual(result['errors'][0]['kind'],'invalid_preregistration')
                self.assertFalse(result['main_sample_floor_met'])
        path.write_text(json.dumps(dict(original,independent_runs_per_factor=2)), encoding="utf-8")
        self.assertFalse(self.validate()['passed'])

    def test_nonzero_preregistered_seed_blocks_are_supported_and_checked(self):
        path = self.root / 'preregistration.json'
        registered = json.loads(path.read_text(encoding='utf8'))
        for job in self.jobs:
            directory = Path(job['output'])
            manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf8'))
            rows = [json.loads(line) for line in (directory / 'encounters.jsonl').read_text(encoding='utf8').splitlines()]
            for record in rows:
                record['Seed'] += 100001
            job['seed_start'] += 100001
            manifest['SeedStart'] = job['seed_start']
            fixture(directory, rows, **manifest)
        registered['seed_start'] = 100001
        registered['jobs'] = self.jobs
        path.write_text(json.dumps(registered), encoding='utf8')
        self.assertTrue(self.validate()['passed'])
        registered['seed_start'] = 100002
        path.write_text(json.dumps(registered), encoding='utf8')
        result = self.validate()
        self.assertFalse(result['passed'])
        self.assertEqual(result['errors'][0]['kind'], 'invalid_preregistration')

    def test_matrix_deadline_before_launch_records_notexecuted(self):
        job = dict(self.jobs[0], matrix_deadline_monotonic=0)
        with patch.object(factors.subprocess, 'Popen') as launch:
            result = factors.run_job(job, self.root / 'STOP')
        launch.assert_not_called()
        self.assertEqual(result['state'], 'NotExecuted')
        self.assertEqual(result['reason'], 'matrix_deadline_before_launch')

    def test_cancelled_notexecuted_and_missing_jobs_stay_incomplete(self):
        for state in ('Cancelled', 'NotExecuted', 'TimedOut', 'Failed'):
            with self.subTest(state=state):
                jobs = [dict(job) for job in self.jobs]
                jobs[0].update(state=state, reason='fixture-stop')
                result = self.validate(jobs)
                self.assertFalse(result['passed'])
                self.assertEqual(result['execution_states'][state], 1)
                self.assertEqual(result['errors'][0]['state'], state)
        self.assertFalse(self.validate([])['passed'])
        self.assertFalse(self.validate(self.jobs[:-1])['passed'])
        self.assertFalse(self.validate(self.jobs + [self.jobs[0]])['passed'])

    def test_stop_before_launch_records_notexecuted_without_a_child(self):
        stop = self.root / 'STOP'
        stop.touch()
        job = dict(self.jobs[0], state='Queued', command=['must-not-launch'])
        with patch.object(factors.subprocess, 'Popen', side_effect=AssertionError('launched')):
            result = factors.run_job(job, stop)
        self.assertEqual(result['state'], 'NotExecuted')
        self.assertNotIn('pid', result)
        self.assertIsNone(result['started_at'])

    def test_launch_failure_is_recorded_without_an_invented_exit_code(self):
        job = dict(self.jobs[0], state='Queued', command=['fixture-command'])
        with patch.object(factors.subprocess, 'Popen', side_effect=OSError('fixture launch failure')):
            result = factors.run_job(job, self.root / 'STOP')
        self.assertEqual(result['state'], 'Failed')
        self.assertEqual(result['reason'], 'launch_failed')
        self.assertIsNone(result['exit_code'])
        self.assertEqual(json.loads((Path(job['output']) / 'execution.json').read_text(encoding="utf-8")), result)

    def test_running_stop_and_deadline_kill_owned_child_and_preserve_state(self):
        for cancelled in (True, False):
            with self.subTest(cancelled=cancelled):
                stop = self.root / 'STOP'
                stop.unlink(missing_ok=True)
                child = Mock(pid=42, returncode=None)
                def poll():
                    if cancelled and child.returncode is None: stop.touch()
                    return child.returncode
                def kill(): child.returncode = -9
                child.poll.side_effect = poll
                child.kill.side_effect = kill
                job = dict(self.jobs[0], state='Queued', command=['fixture-command'])
                with patch.object(factors.subprocess, 'Popen', return_value=child), \
                        patch.object(factors.time, 'monotonic', side_effect=[0, 2401]):
                    result = factors.run_job(job, stop)
                self.assertEqual(result['state'], 'Cancelled' if cancelled else 'TimedOut')
                child.kill.assert_called_once()
                child.wait.assert_called_once_with(timeout=10)


if __name__ == '__main__':
    unittest.main()
