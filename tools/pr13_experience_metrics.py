"""Finite recovery accounting and interval union in an explicit clock domain."""
import math


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def recovery(requested,applied):
    if not all(finite(v) and v>=0 for v in [requested,applied]) or applied>requested:raise ValueError('Recovery must be nonnegative and applied cannot exceed requested')
    return dict(requested=requested,effective=applied,overflow=requested-applied)


def elapsed(start,end):
    if not start.get('clock_origin') or start.get('clock_origin')!=end.get('clock_origin'):
        return dict(available=False,value_ms=None,reason='cross_clock_or_unknown_origin')
    a=start.get('monotonic_ms');b=end.get('monotonic_ms')
    if not finite(a) or not finite(b) or b<a:return dict(available=False,value_ms=None,reason='invalid_monotonic_bounds')
    return dict(available=True,value_ms=b-a,clock_origin=start['clock_origin'])


def control_union(intervals):
    if not intervals:return dict(available=True,union_ms=0,interval_count=0)
    origin=intervals[0].get('clock_origin')
    if not origin or any(i.get('clock_origin')!=origin for i in intervals):return dict(available=False,union_ms=None,reason='cross_clock_or_unknown_origin')
    bounds=[]
    for row in intervals:
        a=row.get('start_ms');b=row.get('end_ms')
        if not finite(a) or not finite(b) or b<a:raise ValueError('Invalid control interval')
        bounds.append((a,b))
    merged=[]
    for a,b in sorted(bounds):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return dict(available=True,union_ms=sum(b-a for a,b in merged),interval_count=len(intervals),merged_intervals=merged,clock_origin=origin)


def recovery_totals(rows):
    if any('EffectiveHeal' not in r or 'HealOverflow' not in r for r in rows):return dict(available=False,reason='parent_recovery_fields_missing',effective=None,overflow=None)
    values=[recovery(r['EffectiveHeal']+r['HealOverflow'],r['EffectiveHeal']) for r in rows]
    return dict(available=True,requested=sum(r['requested'] for r in values),effective=sum(r['effective'] for r in values),overflow=sum(r['overflow'] for r in values),scope='actual native authoritative draft and capped result fields')
