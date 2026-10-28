"""Continue original complete-condition publication after terminal R1 watcher."""
import hashlib
import importlib.util
import json
import msvcrt
import os
import time
from pathlib import Path

B = Path(__file__).parent
G = Path('G:/PR13Evidence/B04-single-factor-full-r1')
OUT = B / 'B04-complete-condition-release-followthrough-r2'
assert not OUT.exists()
OUT.mkdir()
spec = importlib.util.spec_from_file_location('original_condition_publisher',
    B / 'B04_complete_condition_G_release_followthrough_R1.original.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.OUT = OUT


def main():
    with (G / 'condition-stage-publication-ownership.lock').open('a+b') as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        plan_path = G / 'common-frozen-inputs/plan.original.json'
        frozen_sha = m.sha(plan_path)
        assert frozen_sha == '6de1f123007ab9bd7018a1b3d6e6e1bdaa5eb1687ac0efa00890acef86c387fe'
        plan = m.read(plan_path)
        assert len(plan['units']) == 5400 and plan['expected_encounters'] == 216000
        for number in [2, 3]:
            p = B / f'B04-complete-condition-release-followthrough-r1/condition-{number:02d}-published.original.json'
            assert p.is_file()
        m.write(OUT / 'started.original.json', {'pid': os.getpid(), 'at': time.time(),
            'original_plan_sha256': frozen_sha, 'original_publication_functions_sha256':
            m.sha(B / 'B04_complete_condition_G_release_followthrough_R1.original.py'),
            'first_remaining_condition': 4, 'last_condition': 35, 'native_jobs_started': 0,
            'previous_successful_condition_stages_not_republished': [2, 3], 'MAIN_accepted': False})
        for number in range(4, 36):
            specs = plan['units'][number * 150:(number + 1) * 150]
            previous = None
            while True:
                assert m.sha(plan_path) == frozen_sha
                assert not (B / 'B04-full-r1-resumed-G-driver-r2/resume-failure.original.json').exists()
                closed = sum((G / 'units' / item['unit'] / 'cloud-cleanup.original.json').is_file() for item in specs)
                if closed != previous:
                    m.event('WaitingForExactCompleteCondition', condition=number, G_closed_parts=closed, required=150)
                    previous = closed
                if closed == 150:
                    break
                log = B / 'B04-full-r1-resumed-driver-r2.stdout.original.log'
                assert log.is_file() and time.time() - log.stat().st_mtime < 3600, 'Inspect original active G driver handle'
                time.sleep(30)
            assert all((G / 'units' / item['unit'] / 'cloud-cleanup.original.json').is_file()
                       for item in plan['units'][:(number + 1) * 150])
            m.publish_generic(plan, number)
        m.write(OUT / 'all36-original-condition-stages-published.original.json',
            {'ok': True, 'original_conditions': 36, 'physical_parts': 5400, 'encounters': 216000,
             'full_statistics_executed': False, 'formal_profiles_accepted': False, 'MAIN_accepted': False})


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        if not (OUT / 'failure.original.json').exists():
            m.write(OUT / 'failure.original.json', {'at': time.time(), 'error': type(error).__name__,
                'message': str(error), 'native_driver_not_restarted': True, 'unknown_mutations_not_retried': True})
        raise
