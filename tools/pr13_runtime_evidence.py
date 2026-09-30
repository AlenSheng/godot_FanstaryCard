"""Pure acceptance accounting. Input evidence stays immutable; no server access."""
from __future__ import annotations

from collections import Counter
import math


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def sampling_integrity(samples, started_monotonic_ms, stop_monotonic_ms, maximum_gap_seconds=20):
    """Check real sampler observations, including the unobserved stop tail."""
    errors=[]
    if (not isinstance(samples,list) or any(not isinstance(s,dict) for s in samples) or
            not all(finite(v) for v in (started_monotonic_ms,stop_monotonic_ms,maximum_gap_seconds))):
        return dict(passed=False,reasons=['invalid_sampling_schema'],tail_gap_seconds=None)
    points=[s.get('sample_monotonic_ms') for s in samples if isinstance(s,dict)]
    if not points or any(not finite(v) for v in points):
        return dict(passed=False,reasons=['monotonic_observation_missing'],tail_gap_seconds=None)
    gaps=[(b-a)/1000 for a,b in zip([started_monotonic_ms]+points,points+[stop_monotonic_ms])]
    if any(g<0 or g>maximum_gap_seconds for g in gaps):errors.append('sampling_gap_over_contract')
    origin=samples[0]
    if any(not finite(s.get('at')) or abs((s['at']-origin['at'])-(s['sample_monotonic_ms']-origin['sample_monotonic_ms'])/1000)>2 for s in samples):
        errors.append('wall_clock_discontinuity')
    return dict(passed=not errors,reasons=errors,tail_gap_seconds=gaps[-1],maximum_observed_gap_seconds=max(gaps))


def coverage(samples, *, start, end, target_online, target_active,
             minimum_command_rate=1.0, maximum_gap=20.0, minimum_window=600.0,
             minimum_continuous=120.0, minimum_coverage=.95):
    """Count only intervals bounded by TWO valid observations. Never bridge gaps."""
    parameters = (start, end, target_online, target_active, minimum_command_rate,
                  maximum_gap, minimum_window, minimum_continuous, minimum_coverage)
    if (not all(finite(v) for v in parameters) or end <= start or maximum_gap <= 0 or
            min(target_online, target_active, minimum_command_rate, minimum_window,
                minimum_continuous) < 0 or not 0 <= minimum_coverage <= 1):
        raise ValueError("Invalid preregistered coverage contract")
    ordered = sorted((s for s in samples if isinstance(s, dict) and finite(s.get("at"))),
                     key=lambda s: s["at"])
    compliant_seconds = observed_seconds = longest = streak = 0.0
    intervals = []
    def compliant(s):
        return (finite(s.get("online")) and s["online"] >= target_online and
                finite(s.get("active_in_room")) and s["active_in_room"] >= target_active and
                finite(s.get("command_rate")) and s["command_rate"] >= minimum_command_rate and
                not s.get("workload_failure", False))
    for a, b in zip(ordered, ordered[1:]):
        left, right = max(start, a["at"]), min(end, b["at"])
        if right <= left:
            continue
        gap = b["at"] - a["at"]
        valid = 0 < gap <= maximum_gap
        passed = valid and compliant(a) and compliant(b)
        duration = right - left
        observed_seconds += duration if valid else 0
        compliant_seconds += duration if passed else 0
        streak = streak + duration if passed else 0.0
        longest = max(longest, streak)
        intervals.append({"start": left, "end": right, "observed": valid, "compliant": passed})
    duration = end - start
    ratio = compliant_seconds / duration
    return {"passed": duration >= minimum_window and ratio >= minimum_coverage and longest >= minimum_continuous,
            "window_seconds": duration, "observed_seconds": observed_seconds,
            "compliant_seconds": compliant_seconds, "coverage": ratio,
            "longest_continuous_seconds": longest, "intervals": intervals,
            "target_online": target_online, "target_active": target_active,
            "minimum_command_rate": minimum_command_rate,
            "maximum_gap": maximum_gap, "minimum_window": minimum_window,
            "minimum_continuous": minimum_continuous, "minimum_coverage": minimum_coverage}


def reconcile_cycles(events, stop_ms, final_ms):
    """One derivation for total/table/cutoffs; never infer cycles from process exit."""
    unique = {}
    errors = []
    for e in events:
        if not isinstance(e, dict):
            errors.append("invalid_event"); continue
        identity = tuple(e.get(k) for k in ("run_id", "client_id", "process_epoch", "event_seq"))
        if (any(not isinstance(v,str) or not v for v in identity[:3]) or
                not isinstance(identity[3],int) or isinstance(identity[3],bool) or identity[3]<1 or
                not finite(e.get("at_unix_ms")) or e["at_unix_ms"]<0 or
                not isinstance(e.get("cycle_id"), str) or not e["cycle_id"]):
            errors.append("missing_context"); continue
        if e.get('event_type') in ('settlement.acknowledged','cycle.completed') and (
                not isinstance(e.get('match_id'),str) or not e['match_id']):
            errors.append('missing_business_context');continue
        if identity in unique and unique[identity] != e:
            errors.append("conflicting_duplicate")
        unique.setdefault(identity, e)
    buckets = {"running": [], "drain": [], "final": []}
    for e in unique.values():
        if e["at_unix_ms"] > final_ms: continue
        buckets["final"].append(e)
        buckets["running" if e["at_unix_ms"] <= stop_ms else "drain"].append(e)
    def derive(rows):
        ack = Counter()
        complete = Counter()
        fallback = set()
        seen = set()
        for e in rows:
            kind = e.get("event_type")
            business_key = tuple(e.get(k) for k in ("run_id", "client_id", "process_epoch", "cycle_id", "match_id", "event_type"))
            if kind in ("settlement.acknowledged", "cycle.completed") and business_key in seen:
                errors.append("duplicate_business_completion"); continue
            seen.add(business_key)
            if kind == "settlement.acknowledged": ack[e["client_id"]] += 1
            if kind == "cycle.completed": complete[e["client_id"]] += 1
            if kind == "battle.abandon.fallback": fallback.add((e["client_id"], e["cycle_id"]))
        return {"acknowledgements": sum(ack.values()), "completed_cycles": sum(complete.values()),
                "cycles_by_client": dict(sorted(complete.items())),
                "acknowledgements_by_client": dict(sorted(ack.items())),
                "distribution": dict(sorted(Counter(complete.values()).items())),
                "fallback_cycles": len(fallback)}
    result = {name: derive(rows) for name, rows in buckets.items()}
    for key in ("acknowledgements", "completed_cycles"):
        if result["running"][key] + result["drain"][key] != result["final"][key]:
            errors.append("cutoff_conservation")
    # Zero-cycle clients must be taken from a launch manifest, never guessed here.
    result["zero_cycle_clients"] = None
    result["zero_cycle_reason"] = "requires_launch_manifest"
    result["evidence_errors"] = sorted(set(errors))
    result["stop_ms"] = stop_ms
    result["final_ms"] = final_ms
    return result


def result_dimensions(*, execution, evidence, load, gameplay, performance, cleanup, applicable=None):
    """None is Unknown, never a successful zero. Applicable dimensions all pass."""
    values = dict(execution=execution, evidence=evidence, load=load,
                  gameplay=gameplay, performance=performance, cleanup=cleanup)
    selected = set(values) if applicable is None else set(applicable)
    if not selected or selected - set(values): raise ValueError("Invalid preregistered acceptance scope")
    return {"dimensions": {k: "NotApplicable" if k not in selected else "Passed" if v is True else "Failed" if v is False else "Unknown"
                           for k, v in values.items()},
            "applicable": sorted(selected),
            "all_applicable_passed": all(values[k] is True for k in selected),
            "full_acceptance_passed": all(v is True for v in values.values())}
