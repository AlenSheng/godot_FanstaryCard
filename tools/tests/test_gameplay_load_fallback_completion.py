"""A completed ACK workflow cannot turn a recorded abandon into a normal game."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from tools.pr13_runtime_evidence import reconcile_cycles
from tools.tests import test_gameplay_load_finalization as fixtures


def event(sequence, kind, *, at=None, match='m', cycle='c:1', **extra):
    return dict(run_id='r', client_id='c', process_epoch='e', event_seq=sequence,
                at_unix_ms=sequence if at is None else at, cycle_id=cycle,
                match_id=match, event_type=kind, **extra)


def add_origin(entry, _child, origin):
    report = entry['report']
    original = json.loads(report.read_text(encoding='utf8'))
    rows = copy.deepcopy(original['telemetry'])
    first = dict(rows[0], event_type=origin)
    rows.insert(0, first)
    for sequence, row in enumerate(rows, 1):
        row.update(event_seq=sequence, at_unix_ms=100000000 + sequence)
    for target in [report, Path(str(report) + '.status.json')]:
        content = json.loads(target.read_text(encoding='utf8'))
        content.update(telemetry=rows, event_seq_max=len(rows))
        target.write_text(json.dumps(content), encoding='utf8')
    Path(str(report) + '.telemetry.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf8')


class FallbackCompletionTests(unittest.TestCase):
    def test_acknowledged_fallback_is_not_a_normal_completed_cycle(self):
        rows = [event(1, 'battle.abandon.fallback'),
                event(2, 'settlement.acknowledged'), event(3, 'cycle.completed')]
        final = reconcile_cycles(rows, 10, 20)['final']
        self.assertEqual(final['completed_cycles'], 1)
        self.assertEqual(final['fallback_completed_cycles'], 1)
        self.assertEqual(final['normal_completed_cycles'], 0)

    def test_origin_before_stop_classifies_completion_after_stop(self):
        rows = [event(1, 'battle.abandon.fallback', at=99),
                event(2, 'settlement.acknowledged', at=101),
                event(3, 'cycle.completed', at=102)]
        result = reconcile_cycles(rows, 100, 120)
        self.assertEqual(result['drain']['fallback_completed_cycles'], 1)
        self.assertEqual(result['drain']['normal_completed_cycles'], 0)
        self.assertEqual(result['final']['completed_cycles'], 1)

    def test_same_client_cycle_in_another_match_does_not_poison_normal_completion(self):
        rows = [event(1, 'battle.abandon.fallback', match='old'),
                event(2, 'settlement.acknowledged', match='new'),
                event(3, 'cycle.completed', match='new')]
        final = reconcile_cycles(rows, 10, 20)['final']
        self.assertEqual(final['normal_completed_cycles'], 1)
        self.assertEqual(final['fallback_completed_cycles'], 0)

    def test_owned_stream_keeps_scenario_abandon_classification(self):
        class Owned(list):
            _owned_audit_stream_version = 1
        rows = Owned([event(1, 'battle.abandon.scenario'),
                      event(2, 'settlement.acknowledged'), event(3, 'cycle.completed')])
        final = reconcile_cycles(rows, 10, 20)['final']
        self.assertEqual(final['scenario_completed_cycles'], 1)
        self.assertEqual(final['normal_completed_cycles'], 0)

    def test_drain_ack_cannot_be_reported_as_normal_if_a_completion_is_present(self):
        rows = [event(1, 'settlement.acknowledged', completion_stage='drain_ack_only'),
                event(2, 'cycle.completed')]
        final = reconcile_cycles(rows, 10, 20)['final']
        self.assertEqual(final['drain_only_completed_cycles'], 1)
        self.assertEqual(final['normal_completed_cycles'], 0)

    def test_actual_coordinator_does_not_pass_natural_smoke_after_fallback_ack(self):
        fixture = fixtures.FinalizationTests()
        code, report = fixture.run_fixture(before_stop=lambda e, p: add_origin(e, p, 'battle.abandon.fallback'))
        self.assertEqual(code, 1)
        self.assertFalse(report['acceptance_passed'])
        self.assertEqual(report['cycle_cutoffs']['final']['completed_cycles'], 3)
        self.assertEqual(report['cycle_cutoffs']['final']['normal_completed_cycles'], 2)
        self.assertFalse(report['normal_cycle_requirement']['passed'])
        self.assertIn('normal_cycle_requirement_not_met', report['final_triggers'])

    def test_declared_functional_workflow_still_passes_without_natural_claim(self):
        fixture = fixtures.FinalizationTests()
        original = fixtures.coordinator.main
        def functional():
            with patch.object(sys, 'argv', sys.argv + ['--load-profile', 'functional-cycles']):
                return original()
        with patch.object(fixtures.coordinator, 'main', functional):
            code, report = fixture.run_fixture(before_stop=lambda e, p: add_origin(e, p, 'battle.abandon.scenario'))
        self.assertEqual(code, 0)
        self.assertTrue(report['acceptance_passed'])
        self.assertFalse(report['normal_cycle_requirement']['required'])
        self.assertEqual(report['cycle_cutoffs']['final']['scenario_completed_cycles'], 1)
        self.assertEqual(report['cycle_cutoffs']['final']['normal_completed_cycles'], 2)


    def test_sent_abandon_without_origin_is_unclassified_in_both_stream_paths(self):
        class Owned(list):
            _owned_audit_stream_version = 1
        rows = [event(1, 'command.sent', action='battle.abandon'),
                event(2, 'settlement.acknowledged'), event(3, 'cycle.completed')]
        for stream in [rows, Owned(rows)]:
            with self.subTest(owned=hasattr(stream, '_owned_audit_stream_version')):
                final = reconcile_cycles(stream, 10, 20)['final']
                self.assertEqual(final['normal_completed_cycles'], 0)
                self.assertEqual(final['unclassified_completed_cycles'], 1)

    def test_explicit_fallback_origin_resolves_an_abandon_send_trace(self):
        class Owned(list):
            _owned_audit_stream_version = 1
        rows = Owned([event(1, 'command.sent', action='battle.abandon'),
                      event(2, 'battle.abandon.fallback'),
                      event(3, 'settlement.acknowledged'), event(4, 'cycle.completed')])
        result = reconcile_cycles(rows, 10, 20)
        self.assertEqual(result['final']['fallback_completed_cycles'], 1)
        self.assertEqual(result['final']['unclassified_completed_cycles'], 0)
        self.assertEqual(result['evidence_errors'], [])


if __name__ == '__main__':
    unittest.main()
