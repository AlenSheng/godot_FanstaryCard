"""Explicit per-run memory floors; legacy profiles retain their original guards."""
import math


DEFAULT_GENERATOR_FLOOR = 2 * 1024 ** 3


def memory_causes(resource, generator, generator_floor=DEFAULT_GENERATOR_FLOOR,
                  cloud_floor=None):
    causes = []
    key = 'memory_available' if cloud_floor is None else 'memory_available_bytes'
    value = resource.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        causes.append('monitoring_unavailable')
    elif value < (15 if cloud_floor is None else cloud_floor):
        causes.append(key + '_redline')
    if generator.get('available'):
        value = generator.get('host_memory_available_bytes')
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < generator_floor:
            causes.append('generator_memory_low')
    else:
        causes.append('generator_memory_monitoring_unavailable')
    return causes


def launch_memory_ready(available_bytes, floor, start_budget_mib):
    return available_bytes >= floor + start_budget_mib * 1024 ** 2
