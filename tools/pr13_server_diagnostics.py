"""Read actual owned native server windows; unavailable values never become zero."""
import json
import math
from pathlib import Path
import time


def finite(value): return type(value) in (int, float) and math.isfinite(value)


def current_window(path, pid, *, now_ms=None, maximum_age_ms=5000):
    result = dict(actor_wait=None, server_humans_in_room=None, server_rss_bytes=None, server_cpu_percent=None,
                  server_metrics_available=False)
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2); size = stream.tell(); stream.seek(max(0, size - 1024 * 1024))
            lines = stream.read().splitlines()
        # A concurrent last write may be incomplete; the prior complete row is
        # usable only if it has the same process identity and is still fresh.
        row = None
        for line in reversed(lines[-3:]):
            try: row = json.loads(line); break
            except (ValueError, UnicodeError): continue
        if not row or row.get('pid') != pid or not row.get('server_assembly_sha256') or not row.get('process_started_at'):
            raise ValueError('process_identity_absent_or_mismatched')
        age = (time.time() * 1000 if now_ms is None else now_ms) - row['observed_at_unix_ms']
        if not finite(age) or not 0 <= age <= maximum_age_ms: raise ValueError('native_snapshot_stale_or_future')
        if row.get('dropped_observations') != 0: raise ValueError('bounded_native_observations_dropped')
        rss, cpu = row.get('rss_bytes'), row.get('server_cpu_percent')
        if not finite(rss) or rss <= 0 or not finite(cpu) or cpu < 0: raise ValueError('native_process_resources_invalid')
        durations = row.get('durations', {}).get('fantasycard.room_actor.command.wait', {})
        wait = durations.get('p95_ms')
        if not finite(wait) or wait < 0 or durations.get('count', 0) < 1: wait = None
        humans = row.get('counters', {}).get('fantasycard.rooms.humans.active')
        if type(humans) is not int or humans < 0: humans = None
        result.update(actor_wait=wait, server_humans_in_room=humans, server_rss_bytes=rss, server_cpu_percent=cpu,
                      server_metrics_available=True, native_server_pid=pid, native_server_sequence=row['sequence'],
                      native_server_assembly_sha256=row['server_assembly_sha256'],
                      native_window_seconds=row['window_seconds'],
                      actor_wait_missing_reason=row.get('actor_wait_missing_reason') if wait is None else None,
                      managed_heap_bytes=row.get('managed_heap_bytes'), managed_allocated_bytes_total=row.get('managed_allocated_bytes_total'),
                      gc_collections=row.get('gc_collections'))
    except (OSError, ValueError, KeyError, TypeError) as error:
        result['server_metrics_missing_reason'] = str(error) if isinstance(error, ValueError) else type(error).__name__
    return result


def resource_trend(rows):
    if not 3 <= len(rows) <= 4096: raise ValueError('At least three bounded native windows required')
    identities = {(r['pid'], r['process_started_at'], r['server_assembly_sha256']) for r in rows}
    if len(identities) != 1: raise ValueError('Process restart or assembly changes cannot be pooled into one RSS slope')
    times = [r['elapsed_seconds'] for r in rows]; rss = [r['rss_bytes'] for r in rows]
    allocations = [r['managed_allocated_bytes_total'] for r in rows]
    if (not all(finite(v) and v >= 0 for v in times + rss + allocations) or
            any(b <= a for a, b in zip(times, times[1:])) or any(b < a for a, b in zip(allocations, allocations[1:]))):
        raise ValueError('Finite increasing monotonic times and cumulative allocations required')
    mean_x = sum(times) / len(times); mean_y = sum(rss) / len(rss)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(times, rss)) / sum((x - mean_x) ** 2 for x in times)
    return dict(native_windows=len(rows), elapsed_seconds=times[-1] - times[0], rss_slope_bytes_per_second=slope,
                rss_first_bytes=rss[0], rss_last_bytes=rss[-1], rss_peak_bytes=max(rss),
                managed_allocated_bytes_delta=allocations[-1] - allocations[0],
                managed_heap_first_bytes=rows[0]['managed_heap_bytes'], managed_heap_last_bytes=rows[-1]['managed_heap_bytes'],
                gc_first=rows[0]['gc_collections'], gc_last=rows[-1]['gc_collections'],
                leak_proven=False, capacity_acceptance=False,
                interpretation='Observed RSS trend and independent native allocation/GC evidence; a slope alone does not prove a leak')
