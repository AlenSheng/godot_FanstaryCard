"""Conservative shared-window guard for distributed native load evidence.

This checks overlap only. It never awards capacity acceptance: each original
cohort's execution, provenance, latency, sampling and cleanup gates still apply.
Clock probes and the evaluation window must be captured by the study controller;
an evaluator must not choose a better window after observing the results.
"""
from __future__ import annotations

try:
    from .pr13_runtime_evidence import coverage, finite
except ImportError:
    from pr13_runtime_evidence import coverage, finite

GLOBAL50_SURPLUS_PROFILE = 'full-native60-global50-win35-cloud25'
GLOBAL50_SURPLUS_PARTITIONS = {'windows': (35, 25), 'cloud': (25, 15)}


def _union(intervals):
    """Union already-certified intervals without bridging a real gap."""
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return merged


def _certified_active_runs(samples, count, active, envelope, start, end, maximum_gap):
    measured = coverage(samples, start=samples[0]['at'], end=samples[-1]['at'],
                        target_online=count, target_active=active, maximum_gap=maximum_gap)
    if measured['evidence_errors']:
        raise ValueError('invalid_original_observation_timeline')
    result = []
    for left, right in _runs(measured['intervals']):
        lo = max(start / 1000, left + envelope['upper_ms'] / 1000)
        hi = min(end / 1000, right + envelope['lower_ms'] / 1000)
        if hi > lo:
            result.append([lo, hi])
    return result


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def _stable_clock(points, maximum_drift_ms):
    if not points or any(not finite(x) or not finite(y) or min(x, y) < 0 for x, y in points):
        raise ValueError('invalid_clock_capture')
    offsets = [wall - mono for wall, mono in points]
    # The range bounds any two captures, including captures on opposite
    # sides of the first observation's offset.
    drift = max(offsets) - min(offsets)
    if drift > maximum_drift_ms:
        raise ValueError('clock_discontinuity')
    return drift


def clock_envelope(probes, samples, *, host_id, window_start_ms, window_end_ms,
                   maximum_round_trip_ms=1500, maximum_drift_ms=250,
                   maximum_uncertainty_ms=3000):
    """Bound reference-minus-host UTC; never subtract RTT/2 as an exact offset.

    Use the union of before/after bounds, expanded by the declared clock drift.
    Taking their intersection could conceal actual drift during the experiment.
    """
    if not isinstance(probes, list) or len(probes) < 2 or not samples:
        raise ValueError('missing_bracketing_clock_probes')
    remote_points = [(s['at'] * 1000, s['sample_monotonic_ms']) for s in samples]
    reference_points, before, after, bounds, rtts = [], [], [], [], []
    previous_sent = None
    fields = ('reference_sent_unix_ms', 'reference_received_unix_ms',
              'reference_sent_monotonic_ms', 'reference_received_monotonic_ms',
              'remote_unix_ms', 'remote_monotonic_ms')
    for p in probes:
        if (not isinstance(p, dict) or p.get('host_id') != host_id or
                p.get('phase') not in ('before', 'after') or
                any(not finite(p.get(k)) or p[k] < 0 for k in fields)):
            raise ValueError('invalid_clock_probe')
        sent, received, mono_sent, mono_received, remote, remote_mono = (p[k] for k in fields)
        rtt = mono_received - mono_sent
        if (received < sent or not 0 <= rtt <= maximum_round_trip_ms or
                abs(received - sent - rtt) > maximum_drift_ms or
                (previous_sent is not None and mono_sent <= previous_sent)):
            raise ValueError('invalid_clock_round_trip')
        previous_sent = mono_sent
        reference_points.extend(((sent, mono_sent), (received, mono_received)))
        remote_points.append((remote, remote_mono))
        bounds.append((sent - remote, received - remote))
        rtts.append(rtt)
        (before if p['phase'] == 'before' else after).append(p)
    if (not before or not after or
            any(p['remote_unix_ms'] > samples[0]['at'] * 1000 or
                p['reference_received_unix_ms'] > window_start_ms for p in before) or
            any(p['remote_unix_ms'] < samples[-1]['at'] * 1000 or
                p['reference_sent_unix_ms'] < window_end_ms for p in after) or
            max(p['reference_received_monotonic_ms'] for p in before) >=
            min(p['reference_sent_monotonic_ms'] for p in after)):
        raise ValueError('clock_probes_do_not_bracket_observations')
    remote_drift = _stable_clock(remote_points, maximum_drift_ms)
    reference_drift = _stable_clock(reference_points, maximum_drift_ms)
    # Reference and remote clocks can drift in opposite directions. Both
    # declared bounds are needed; one clock's bound would understate skew.
    relative_drift_ms = 2 * maximum_drift_ms
    lower = min(x[0] for x in bounds) - relative_drift_ms
    upper = max(x[1] for x in bounds) + relative_drift_ms
    if upper - lower > maximum_uncertainty_ms:
        raise ValueError('clock_uncertainty_too_large')
    return dict(lower_ms=lower, upper_ms=upper, maximum_round_trip_ms=max(rtts),
                measured_remote_drift_ms=remote_drift,
                measured_reference_drift_ms=reference_drift,
                before_probes=len(before), after_probes=len(after),
                reference_points=reference_points)


def _runs(intervals):
    """Merge touching compliant observations, preserving every failed gap."""
    result = []
    for row in intervals:
        if not row['compliant']:
            continue
        left, right = row['start'], row['end']
        if result and result[-1][1] == left:
            result[-1][1] = right
        else:
            result.append([left, right])
    return result


def _intersect(left, right):
    result = []
    a = b = 0
    while a < len(left) and b < len(right):
        start, end = max(left[a][0], right[b][0]), min(left[a][1], right[b][1])
        if end > start:
            result.append([start, end])
        if left[a][1] < right[b][1]:
            a += 1
        else:
            b += 1
    return result


def joint_overlap(cohorts, contract):
    """Recompute overlap from raw observations, not scalar passed/count fields.

    Each cohort supplies host_id, clients, raw samples and bracketing probes.
    Server human counts are global values from the shared isolated backend:
    every compliant observation must see the full joint target, not just its
    own generator's partition. Original reports and identities are separate
    mandatory inputs to the eventual capacity adjudicator.
    """
    output = dict(joint_overlap_passed=False, capacity_acceptance=False,
                  scope='Clock-bounded shared-window overlap only', evidence_errors=[],
                  remaining_required_checks=['Original cohort evidence and latency gates',
                      'Actual official full native executable and identical game inputs',
                      'Distinct process-client-user identities on both hosts',
                      'One unchanged isolated backend and real global human gauge',
                      'Original process and business cleanup for every participant'])
    try:
        start, end = contract['window_start_ms'], contract['window_end_ms']
        target = contract['target_clients']
        population = contract.get('target_online_clients', target)
        reference_host = contract['reference_host_id']
        duration = (end - start) / 1000
        maximum_gap = contract.get('maximum_gap_seconds', 20)
        minimum_window = contract.get('minimum_window_seconds', 600)
        minimum_continuous = contract.get('minimum_continuous_seconds', 120)
        minimum_coverage = contract.get('minimum_coverage', .95)
        if (not finite(start) or not finite(end) or start < 0 or end <= start or
                not _integer(target, 1) or not _integer(population, target) or population > 300 or not isinstance(reference_host, str) or not reference_host or
                not all(finite(x) for x in (maximum_gap, minimum_window, minimum_continuous, minimum_coverage)) or
                not 0 < maximum_gap <= 20 or minimum_window < 600 or
                minimum_continuous < 120 or not .95 <= minimum_coverage <= 1):
            raise ValueError('invalid_or_relaxed_joint_contract')
        if not isinstance(cohorts, list) or len(cohorts) < 2:
            raise ValueError('missing_distinct_generator_cohorts')
        global_surplus = contract.get('workload_profile') == GLOBAL50_SURPLUS_PROFILE
        if global_surplus and (target != 50 or population != 60 or len(cohorts) != 2):
            raise ValueError('invalid_global50_surplus_population')
        hosts, total, total_active, shared = set(), 0, 0, None
        levels = {}
        host_results, reference_points = [], []
        for cohort in cohorts:
            host = cohort['host_id']
            count = cohort['clients']
            active = cohort.get('target_active', count)
            if (not isinstance(host, str) or not host or host in hosts or not _integer(count, 1) or
                    not _integer(active, 1) or active > count):
                raise ValueError('invalid_or_duplicate_host_identity')
            if global_surplus and GLOBAL50_SURPLUS_PARTITIONS.get(host) != (count, active):
                raise ValueError('wrong_global50_surplus_partitions')
            hosts.add(host)
            total += count
            total_active += active
            samples = cohort['samples']
            if not isinstance(samples, list) or len(samples) < 2:
                raise ValueError('missing_raw_samples')
            normalized = []
            for row in samples:
                if (not isinstance(row, dict) or
                        any(not finite(row.get(k)) or row[k] < 0 for k in ('at', 'sample_monotonic_ms')) or
                        any(not _integer(row.get(k)) for k in ('online', 'active_in_room', 'alive_processes', 'fresh_status_clients')) or
                        type(row.get('workload_failure')) is not bool or
                        any(not isinstance(row.get(k), list) for k in ('reasons', 'failed_processes', 'stale_clients', 'stalled_clients', 'missing_clients', 'invalid_clients'))):
                    raise ValueError('invalid_raw_sample')
                confirmed = row.get('server_confirmed_in_room')
                certified = (finite(confirmed) and confirmed == int(confirmed) and target <= confirmed <= population and
                             row['online'] == count and active <= row['active_in_room'] <= count and
                             row['alive_processes'] == count and row['fresh_status_clients'] == count and
                             not any(row[k] for k in ('reasons', 'failed_processes', 'stale_clients', 'stalled_clients', 'missing_clients', 'invalid_clients')))
                normalized.append(dict(row, workload_failure=row['workload_failure'] or not certified))
            if any(b['sample_monotonic_ms'] <= a['sample_monotonic_ms'] for a, b in zip(samples, samples[1:])):
                raise ValueError('nonincreasing_monotonic_samples')
            envelope = clock_envelope(cohort['clock_probes'], samples, host_id=host,
                                      window_start_ms=start, window_end_ms=end)
            reference_points.extend(envelope.pop('reference_points'))
            if host == reference_host:
                reference_points.extend((s['at'] * 1000, s['sample_monotonic_ms']) for s in samples)
                for p in cohort['clock_probes']:
                    if not p['reference_sent_monotonic_ms'] <= p['remote_monotonic_ms'] <= p['reference_received_monotonic_ms']:
                        raise ValueError('reference_host_monotonic_basis_mismatch')
                    reference_points.append((p['remote_unix_ms'], p['remote_monotonic_ms']))
            measured = coverage(normalized, start=samples[0]['at'], end=samples[-1]['at'],
                                target_online=count, target_active=active, maximum_gap=maximum_gap)
            if measured['evidence_errors']:
                raise ValueError('invalid_original_observation_timeline')
            # Erode whole continuous runs once. Eroding every sample interval
            # would invent uncertainty gaps at otherwise shared observations.
            certified_runs = []
            for left, right in _runs(measured['intervals']):
                lo = max(start / 1000, left + envelope['upper_ms'] / 1000)
                hi = min(end / 1000, right + envelope['lower_ms'] / 1000)
                if hi > lo:
                    certified_runs.append([lo, hi])
            shared = certified_runs if shared is None else _intersect(shared, certified_runs)
            if global_surplus:
                levels[host] = {k: _certified_active_runs(normalized, count, k, envelope, start, end, maximum_gap)
                                for k in range(active, count + 1)}
            host_results.append(dict(host_id=host, clients=count, target_active=active, clock=envelope,
                                     certified_runs_reference_seconds=certified_runs))
        if reference_host not in hosts:
            raise ValueError('missing_reference_host_cohort')
        expected_active_sum = 40 if global_surplus else target
        if total != population or total_active != expected_active_sum:
            raise ValueError('partition_does_not_equal_joint_target')
        if global_surplus:
            # The25/15 local floors alone prove only40. Require an actual
            # clock-certified sum of at least50 native active clients by
            # intersecting every possible50-summing pair of count level sets.
            shared = _union([interval for windows in range(25, 36)
                             for interval in _intersect(levels['windows'][windows], levels['cloud'][50-windows])])
        _stable_clock(reference_points, 250)
        seconds = sum(b - a for a, b in shared)
        longest = max((b - a for a, b in shared), default=0)
        ratio = seconds / duration
        output.update(joint_overlap_passed=duration >= minimum_window and ratio >= minimum_coverage and longest >= minimum_continuous,
                      target_clients=target, target_online_clients=population, window_seconds=duration,
                      compliant_seconds=seconds, coverage=ratio,
                      longest_continuous_seconds=longest,
                      common_intervals_reference_seconds=shared, hosts=host_results)
        if global_surplus:
            output.update(native_active_aggregation='clock-eroded-count-level-set-union',
                          necessary_host_active_floor_sum=40, actual_native_active_required=50)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        output['evidence_errors'].append(str(error) if isinstance(error, ValueError) else 'malformed_joint_input')
    return output
