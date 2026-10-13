"""Publish complete frozen B04 conditions; local byte/identity checks only.

This observes the existing native driver. It never starts native encounters,
changes the frozen plan, calculates experiment statistics, or accepts profiles.
"""
import gzip
import hashlib
import json
import msvcrt
import subprocess
import sys
import time
from pathlib import Path

from current_PR13_stage_publication_helpers import B, R, commit_stage, git

G = Path('G:/PR13Evidence/B04-single-factor-full-r1')
OUT = B / 'B04-complete-condition-release-followthrough-r1'
POINTER = R / 'docs/plans/PR13_CURRENT_ACCEPTANCE_POINTER_20261009.json'
PLAN_SHA = 'd978c08db8759c79cd8a1630e7dbdf25eccbdaf3b92551266143c8047d05ab4f'
STRATEGIES = ['baseline_all_hand', 'basic', 'build']


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    require(not path.exists(), 'Preserve original observation: ' + str(path))
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def event(phase, **detail):
    print(json.dumps({'at': time.time(), 'phase': phase, **detail}), flush=True)


def run(script, folder):
    require(not folder.exists(), 'Preserve existing script attempt: ' + str(folder))
    folder.mkdir()
    write(folder / 'intent.original.json', {'script': script.name, 'script_sha256': sha(script), 'at': time.time()})
    with (folder / 'stdout.original.log').open('wb') as stdout, (folder / 'stderr.original.log').open('wb') as stderr:
        result = subprocess.run([sys.executable, str(script)], cwd=R, stdout=stdout, stderr=stderr)
    write(folder / 'terminal.original.json', {'exit_code': result.returncode, 'at': time.time()})
    require(result.returncode == 0, 'Script failed; preserve and inspect exact attempt: ' + str(folder))


def verify_condition(plan, number):
    specs = plan['units'][number * 150:(number + 1) * 150]
    require(len(specs) == 150, 'Complete original condition required')
    hero, group, block = (specs[0][k] for k in ['hero', 'group', 'block'])
    require(all((s['hero'], s['group'], s['block'], s['samples'], s['encounters']) ==
                (hero, group, block, 20, 40) for s in specs), 'Original condition identity differs')
    require([s['offset'] for s in specs] == list(range(0, 1000, 20)) * 3 and
            [s['strategy'] for s in specs] == [v for name in STRATEGIES for v in [name] * 50],
            'All three original strategies and full 1000-seed blocks required')
    for s in specs:
        require((G / 'units' / s['unit'] / 'cloud-cleanup.original.json').is_file(), 'Condition not G-closed')
    old = git('rev-parse', 'HEAD').decode().strip()
    require(git('rev-parse', 'origin/release').decode().strip() == old and not git('status', '--porcelain').strip(),
            'Release synchronization and clean working tree required')
    require(not git('diff', '--name-only', plan['source_sha'], old, '--', 'server', 'protocol').strip(),
            'Executed product source differs from current release')
    rows = []
    members = original_bytes = 0
    for s in specs:
        root = G / 'units' / s['unit']
        manifest_path = root / 'complete-original-manifest.json'
        manifest = read(manifest_path)
        receipt = read(root / 'local-G-receipt.original.json')
        clean = read(root / 'cloud-cleanup.original.json')
        require(manifest['ok'] and manifest['unit'] == s['unit'] and manifest['encounters'] == 40 and
                receipt['ok'] and receipt['all_members_SHA_verified'] and receipt['gzip_CRC_verified'] and
                not receipt['native_reexecuted_by_backup'] and clean['ok'] and clean['originals_G_complete'] and
                sha(manifest_path) == receipt['manifest_sha256'] == clean['manifest_sha256'],
                'Original complete custody differs')
        for f in manifest['files']:
            path = root / f['path']
            require(path.stat().st_size == f['bytes'] and sha(path) == f['sha256'], 'Original member bytes differ')
            members += 1
            original_bytes += f['bytes']
        archive = G / 'archives' / (s['unit'] + '.original.tar.gz')
        require(archive.stat().st_size == receipt['archive_bytes'] and sha(archive) == receipt['archive_sha256'],
                'Original archive bytes differ')
        with gzip.open(archive, 'rb') as stream:
            while stream.read(1024 ** 2):
                pass
        native = read(root / 'metadata/result.original.json')
        validation = read(root / 'outputs/native/independent-part-validation.original.json')
        meta = read(root / 'outputs/native/manifest.original.json')
        require(native['ok'] and native['exit_code'] == 0 and not native['oom_killed'] and
                native['owned_container_removed'] and native['runtime_and_controller_unchanged'] and native['spec'] == s,
                'Actual native part did not pass')
        require(validation['ok'] and validation['samples'] == 20 and validation['encounters'] == 40 and
                validation['seed_start'] == 450001 + block * 1000 + s['offset'] and validation['block'] == block and
                validation['hero'] == hero and validation['group'] == group and validation['strategy'] == s['strategy'] and
                validation['source_sha'] == plan['source_sha'], 'Actual native validation identity differs')
        require(validation['actual_twenty_original_instances_and_legal_additions_verified'] and
                validation['fixed_default_policies_off'] and validation['complete_gzip_SHA_and_CRC_verified'] and
                meta['baseline_budget'] == meta['candidate_budget'] and
                meta['embedded_resource_bytes_sha256'] == validation['embedded_resource_bytes_sha256'],
                'Original inputs or native validation differ')
        rows.append({'unit': s['unit'], 'spec': s, 'original_G_archive_sha256': receipt['archive_sha256'],
                     'original_delivery_manifest_sha256': receipt['manifest_sha256'],
                     'actual_native_result_sha256': sha(root / 'metadata/result.original.json'),
                     'independent_original_validation_sha256': sha(root / 'outputs/native/independent-part-validation.original.json'),
                     'actual_native_result': native, 'actual_independent_cloud_validation': validation,
                     'complete_original_G_receipt': receipt, 'exact_cloud_cleanup': clean})
    return old, {'ok': True, 'implementation_source_sha': plan['source_sha'], 'current_documentation_release_sha': old,
                 'original_complete_blocks': {'hero': hero, 'group': group, 'strategies': STRATEGIES, 'block': block,
                                              'actual_logical_blocks': 3, 'actual_physical_parts': 150,
                                              'actual_paired_seed_count_per_strategy': 1000, 'actual_both_arm_encounters': 6000},
                 'original_plan_sha256': sha(G / 'common-frozen-inputs/plan.original.json'),
                 'all150_original_archives_SHA_CRC_rechecked': True, 'all_original_member_count_rehashed': members,
                 'all_original_member_bytes_rehashed': original_bytes, 'full_required_physical_parts': 5400,
                 'full_required_encounters': 216000, 'full_required_independent_blocks': 3,
                 'local_operations': 'byte SHA CRC Git and immutable JSON identities only; native rules and statistics run on Tencent',
                 'full_statistics_not_executed': True, 'formal_profile_acceptance': False, 'MAIN_accepted': False, 'units': rows}


def publish_generic(plan, number):
    old, proof = verify_condition(plan, number)
    identity = proof['original_complete_blocks']
    hero, group, block = (identity[k] for k in ['hero', 'group', 'block'])
    label = f'B04_{hero}_{group}_B{block}_three_strategies_S4'
    stage = R / f'docs/reports/pr13-stages-20261009/S4-b04-{hero}-{group}-B{block}-three-original-strategies'
    require(not stage.exists(), 'Existing stage requires exact outcome inspection')
    stage.mkdir()
    write(stage / 'all150-independent-G-byte-check.original.json', proof)
    (stage / 'G-byte-verifier.executed.original.py').write_bytes(Path(__file__).read_bytes())
    summary = {k: v for k, v in proof.items() if k != 'units'}
    summary.update(stage=label, full_scope_acceptance=False, canonical_profiles_closed=0,
                   remaining_logical_original_blocks=108 - (number + 1) * 3,
                   independent_seed_block_count_for_this_condition=1)
    write(stage / 'summary.json', summary)
    (stage / 'README.md').write_bytes((f'# PR13 B04 {hero} {group} B{block} 三种策略完整原件\n\n'
        f'{hero}／{group}／B{block} 的 baseline_all_hand、basic、build 按原冻结计划完成。'
        '每策略 1,000 配对种子、50 个物理批次、2,000 场两臂战斗，合计 150 批、6,000 场。'
        '三策略共用同一个种子块，不能计为三个独立种子块。\n\n'
        '逐批云端实际出牌、默认 20 实例、合法击杀新增、等待原因、资源守恒与原输入身份验证通过。'
        '本地只复核全部原件 SHA、归档 SHA／gzip CRC 和原验证 JSON；没有本地数值实验。'
        '成功批次在完整 G 归档后精确回收云端输出，失败原件和共享运行时保留。\n\n'
        f'当前完整原条件至少 {(number + 1) * 3}／108 个逻辑块；原总配额仍为 5,400 批、216,000 场。'
        '此阶段不计算局部强度统计、不关闭规范 EXPERIMENT／RENDER 或 MAIN。'
        '即使原件配额完成，也须完成全量云端统计和用例审查后再决定验收。\n').encode())
    pointer = read(POINTER)
    pointer['latest_development'].update(
        B04_latest_complete_condition_stage=(stage / 'summary.json').relative_to(R).as_posix(),
        B04_original_complete_logical_blocks_at_least=(number + 1) * 3,
        B04_full_original_G_verified_encounters_at_least=(number + 1) * 6000,
        B04_latest_complete_condition_G_recheck=True)
    POINTER.write_bytes((json.dumps(pointer, ensure_ascii=False, indent=2) + '\n').encode())
    publication = commit_stage(stage, POINTER,
        f'docs(pr13): verify complete {hero} {group} B{block} original B04 condition', old, label)
    run(B / publication['publication_script'], OUT / f'condition-{number:02d}-publication')
    write(OUT / f'condition-{number:02d}-published.original.json', publication)
    event('CompleteConditionPublishedAndCloudSynchronized', condition=number, **publication)


def main():
    require(not OUT.exists(), 'Do not restart an immutable watcher attempt')
    OUT.mkdir()
    with (G / 'condition-stage-publication-ownership.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        plan_path = G / 'common-frozen-inputs/plan.original.json'
        plan = read(plan_path)
        require(len(plan['units']) == 5400 and plan['expected_encounters'] == 216000 and
                plan['required_paired_seeds_per_stratum'] == 3000 and plan['required_independent_blocks'] == 3 and
                plan['worker_count'] == 1 and plan['controller_sha256'] == PLAN_SHA,
                'Frozen original full plan differs')
        frozen_sha = sha(plan_path)
        write(OUT / 'started.original.json', {'pid': __import__('os').getpid(), 'at': time.time(),
              'original_plan_sha256': frozen_sha, 'script_sha256': sha(Path(__file__)),
              'first_condition_index': 2, 'last_condition_index': 35, 'native_encounters_started': 0,
              'formal_profiles_accepted': False, 'source_study_unchanged': True})
        for number in range(2, 36):
            specs = plan['units'][number * 150:(number + 1) * 150]
            previous = None
            while True:
                require(sha(plan_path) == frozen_sha, 'Original frozen plan changed')
                require(not (B / 'B04-full-r1-resumed-G-driver-r1/resume-failure.original.json').exists(),
                        'Existing native/G driver failed; preserve its original handle')
                closed = sum((G / 'units' / s['unit'] / 'cloud-cleanup.original.json').is_file() for s in specs)
                if closed != previous:
                    event('WaitingForExactCompleteCondition', condition=number, G_closed_parts=closed, required=150)
                    previous = closed
                if closed == 150:
                    break
                log = B / 'B04-full-r1-resumed-driver-r1.stdout.original.log'
                require(log.is_file() and time.time() - log.stat().st_mtime < 3600,
                        'Native/G driver activity unavailable; inspect original handle before continuing')
                time.sleep(30)
            # A stage may be published only after all preceding original parts
            # have actual G closure receipts, not by extrapolating the current group.
            require(all((G / 'units' / s['unit'] / 'cloud-cleanup.original.json').is_file()
                        for s in plan['units'][:(number + 1) * 150]), 'Earlier original condition is incomplete')
            if number == 2:
                run(B / 'verify_B04_Mage_E1_three_strategies_full150_G_once.py', OUT / 'condition-02-verification')
                run(B / 'prepare_commit_B04_Mage_E1_three_strategies_S4_once.py', OUT / 'condition-02-commit')
                run(B / 'publish_B04_Mage_E1_three_strategies_S4_stage_low_memory_HTTPS_once.py', OUT / 'condition-02-publication')
                write(OUT / 'condition-02-published.original.json',
                      {'ok': True, 'commit': git('rev-parse', 'HEAD').decode().strip(), 'cloud_sync_script_exit_code': 0})
                event('CompleteConditionPublishedAndCloudSynchronized', condition=2)
            else:
                publish_generic(plan, number)
        write(OUT / 'all36-original-condition-stages-published.original.json',
              {'ok': True, 'original_conditions': 36, 'physical_parts': 5400, 'encounters': 216000,
               'full_statistics_executed': False, 'formal_profiles_accepted': False, 'MAIN_accepted': False})
        event('OriginalConditionsPublishedFullStatisticsStillRequired')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if OUT.exists() and not (OUT / 'failure.original.json').exists():
            write(OUT / 'failure.original.json', {'at': time.time(), 'error': type(exc).__name__, 'message': str(exc),
                  'native_driver_not_restarted': True, 'unknown_mutations_not_retried': True})
        raise
