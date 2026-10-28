"""Actual aggregate/coordinator request contracts for LOAD-03 and LOAD-06."""
import math
import unittest

from tools.gameplay_load_validation import aggregate_window, request_cutoffs


def event(sequence, at, duration, **changes):
    row = dict(type="http", event_type="http", run_id="run", client_id="client", process_epoch="epoch",
               event_seq=sequence, at_unix_ms=at, cycle_id="client:1", match_id="match-1", phase="playing",
               path="/api/v1/bootstrap", duration_ms=duration, status=200, ok=True, result="success")
    row.update(changes)
    return row


class RequestCutoffTests(unittest.TestCase):
    def test_running_drain_and_final_use_one_full_sample_population(self):
        rows = [event(i + 1, 100 + i, 10) for i in range(99)] + [event(100, 1100, 2000)]
        report = request_cutoffs(rows, 1000, 2000, started_ms=0)
        self.assertEqual(report["running"]["http"]["p95_ms"], 10)
        self.assertEqual(report["drain"]["http"]["p95_ms"], 2000)
        self.assertEqual(report["final"]["http"]["p95_ms"], 10)
        self.assertEqual(report["final"]["http"]["max_ms"], 2000)
        self.assertEqual(report["final"]["logical_requests_per_second"], 50)

    def test_route_and_origin_phase_are_retained_for_late_completion(self):
        row = event(1, 1100, 100, phase="settlement", path="/api/v1/matches/current?cursor=private")
        report = request_cutoffs([row], 1000, 2000, started_ms=0)
        route = report["drain"]["route_http"]["/api/v1/matches/current"]
        self.assertEqual(route["logical_request_count"], 1)
        self.assertEqual(report["drain"]["phase_http"]["settlement"]["count"], 1)
        self.assertNotIn("cursor=private", report["drain"]["route_http"])

    def test_bad_duration_keeps_failed_request_denominator(self):
        row = event(1, 100, float("nan"), ok=False, status=500, result="decode_error")
        report = request_cutoffs([row], 1000, 2000, started_ms=0)["running"]
        self.assertEqual(report["error_count"], 1)
        self.assertEqual(report["sample_count"], 1)
        self.assertEqual(report["valid_latency_count"], 0)
        self.assertEqual(report["logical_result_counts"]["decode_error"], 1)

    def test_protocol_template_pools_different_ticket_ids_and_keeps_errors(self):
        route = "/api/v1/matches/tickets/{ticketId:guid}"
        rows = [event(1, 100, 10, path="/api/v1/matches/tickets/first?cursor=private", route=route),
                event(2, 110, 100, path="/api/v1/matches/tickets/second", route=route,
                      status=503, ok=False, result="http_error")]
        result = request_cutoffs(rows, 1000, 2000)["running"]["route_http"]
        self.assertEqual(set(result), {route})
        self.assertEqual(result[route]["logical_request_count"], 2)
        self.assertEqual(result[route]["error_count"], 1)
        self.assertEqual(result[route]["p95_ms"], 100)

    def test_malformed_route_uses_legacy_path_without_query_values(self):
        rows = [event(1, 100, 10, route=[], path="/api/v1/bootstrap?token=private")]
        result = request_cutoffs(rows, 1000, 2000)["running"]["route_http"]
        self.assertEqual(set(result), {"/api/v1/bootstrap"})

    def test_cancelled_attempt_is_not_service_error_or_second_logical_request(self):
        rows = [event(1, 100, 10, type="http_attempt", result="transport_error", status=0, ok=False),
                event(2, 200, 10, type="http_attempt"),
                event(3, 210, 20), event(4, 220, 20, result="cancelled", status=0, ok=False)]
        report = request_cutoffs(rows, 1000, 2000, started_ms=0)["running"]
        self.assertEqual(report["logical_request_count"], 2)
        self.assertEqual(report["all_attempt_count"], 2)
        self.assertEqual(report["cancelled_count"], 1)
        self.assertEqual(report["error_count"], 0)

    def test_empty_or_short_window_stays_unavailable_or_insufficient(self):
        empty = request_cutoffs([], 1000, 2000)["running"]
        self.assertIsNone(empty["logical_requests_per_second"])
        self.assertEqual(empty["latency_sample_quality"]["http"], "unavailable")
        short = request_cutoffs([event(i + 1, i + 100, 1) for i in range(19)], 1000, 2000)["running"]
        self.assertEqual(short["latency_sample_quality"]["http"], "insufficient")

    def test_bad_context_duplicate_and_outside_cutoff_invalidate_evidence(self):
        good = event(1, 100, 10)
        result = request_cutoffs([good, good, event(True, 200, 10), event(3, 3000, 10)], 1000, 2000)
        self.assertEqual(result["final"]["logical_request_count"], 1)
        self.assertEqual(set(result["evidence_errors"]), {"duplicate_request_event", "missing_request_context", "request_outside_run_cutoffs"})

    def test_invalid_observation_interval_never_creates_fake_throughput(self):
        for value in (0, -1, False, math.nan, math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                aggregate_window([], observed_seconds=value)


if __name__ == "__main__":
    unittest.main()
