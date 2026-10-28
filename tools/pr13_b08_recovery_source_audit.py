"""Metadata-only B08.3 evidence and exact Git/source audit; never run combat.

Completed original execution evidence is separate from current-source reuse.
Changed source files remain unproven even when a static call-path review is
available. This tool never changes the acceptance register or signs MAIN.
"""
import argparse
from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import threading

EXPERIMENT_SOURCE = '3a984bc64f5346b7f1d134926deec54be928a060'
VECTOR_SOURCE = '014a601c9a72a8bd2aec357e56a349914f6613f4'
RENDER_SOURCE = '671299f3c118a195c47cc7ce07d4d68dc84b75f0'
ANALYSIS_SOURCE = '49ba3183c247282083f558fd3c3f528d2d476fb3'
CASES = tuple('PR13-B08.3-T0' + str(n) for n in (1, 2, 3))
REGISTER = 'docs/reports/pr13-stages-20261009/S6-after-b08-control-render/register.json'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    require(path.is_file() and not path.is_symlink(), 'Missing/linked metadata: ' + str(path))
    return json.loads(path.read_bytes())


def git(repo, *args):
    result = subprocess.run(['git', *args], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    require(result.returncode == 0, 'Read-only Git object command failed')
    return result.stdout


def tree(repo, revision):
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'An exact Git commit SHA is required')
    require(git(repo, 'cat-file', '-t', revision).strip() == b'commit', 'Source is not a Git commit')
    rows = {}
    for line in git(repo, 'ls-tree', '-rz', '--full-tree', revision).split(b'\0'):
        if not line:
            continue
        attributes, name = line.split(b'\t', 1)
        mode, kind, oid = attributes.decode('ascii').split()
        rows[name.decode('utf-8')] = {'mode': mode, 'kind': kind, 'git_blob_sha1': oid}
    return rows


def blob_hashes(repo, object_ids):
    """Stream actual Git blob bytes with bounded memory; no checkout or execution."""
    objects = sorted(set(object_ids))
    if not objects:
        return {}
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=repo,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def send():
        try:
            for oid in objects:
                process.stdin.write((oid + '\n').encode('ascii'))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    writer = threading.Thread(target=send, daemon=True)
    writer.start()
    result = {}
    try:
        for oid in objects:
            header = process.stdout.readline().decode('ascii').strip().split()
            require(len(header) == 3 and header[0] == oid and header[1] == 'blob', 'Missing/non-blob Git input')
            size = int(header[2]); remaining = size; digest = hashlib.sha256()
            while remaining:
                data = process.stdout.read(min(65536, remaining))
                require(bool(data), 'Truncated Git blob')
                digest.update(data); remaining -= len(data)
            require(process.stdout.read(1) == b'\n', 'Invalid Git batch separator')
            result[oid] = {'bytes': size, 'sha256': digest.hexdigest()}
        require(process.wait() == 0, 'Git blob stream failed')
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        writer.join(timeout=5)
    return result


def source_scope(name, path):
    # Git may contain historical build artifacts. Being tracked does not make
    # obj/bin/packages an authored or default-compiled input source file.
    if any(part in {'obj','bin','.artifacts','.packages','.dotnet','.godot'} for part in PurePosixPath(path).parts):
        return False
    build = {'server/global.json', 'server/Directory.Build.props', 'server/Directory.Packages.props', 'server/NuGet.Config'}
    if name == 'analysis':
        return path in {'tools/' + x for x in ('pr13_tuning_recovery_statistics_input.py', 'pr13_tuning_recovery_report.py', 'pr13_tuning_recovery_experiment.py', 'pr13_candidate_review.py', 'pr13_element_marginal_report.py', 'pr13_element_marginals.py')}
    if name == 'render':
        return path.startswith('client/') or path == 'tools/cloud/pr13/render_runtime.py'
    return (path.startswith(('server/src/', 'server/config/generated/', 'server/tools/FantasyCard.Numerics/'))
            and (path.endswith(('.cs', '.csproj', '.bytes', '.sha256', '.txt')))
            or path in build or path == 'tools/pr13_tuning_recovery_experiment.py'
            or name == 'native_vectors' and path.startswith('protocol/'))


def original_manifest_member(root, relative):
    manifest = load(root / 'manifest.json')
    row = next((r for r in manifest['files'] if r['path'] == relative), None)
    require(row is not None, 'Original input map not anchored in G delivery manifest')
    data = (root / relative).read_bytes()
    require(row['bytes'] == len(data) and row['sha256'] == sha(data), 'G metadata member differs')
    return {'path': str(root / relative), 'bytes': len(data), 'sha256': sha(data), 'original_delivery_manifest_sha256': sha((root / 'manifest.json').read_bytes())}


def audit_sources(repo, evidence, current):
    roots = {
        'experiment': evidence / 'tuning-pilot-local-verified/pr13-tuning-pilot-delivery-20261010',
        'native_vectors': evidence / 'tuning-recovery-local-verified/pr13-tuning-recovery-delivery-20261010',
        'render': evidence / 'tuning-render-local-verified/pr13-tuning-render-delivery-20261010',
        'analysis': repo / 'docs/reports/pr13-stages-20261009/S5-b08-tuning-recovery-full',
    }
    relatives = {'experiment': 'inputs.json', 'native_vectors': 'tuning-recovery-native-r5/inputs.json', 'render': 'attempt-7/inputs.json', 'analysis': 'statistics-controls.json'}
    revisions = {'experiment': EXPERIMENT_SOURCE, 'native_vectors': VECTOR_SOURCE, 'render': RENDER_SOURCE, 'analysis': ANALYSIS_SOURCE}
    current_tree = tree(repo, current); maps = {}; trees = {}; members = {}; object_ids = []
    for name, root in roots.items():
        members[name] = original_manifest_member(root, relatives[name])
        raw = load(root / relatives[name])
        if name not in ('render','analysis'):
            require(raw['source_sha'] == revisions[name], 'Original actual source label differs')
        if name == 'analysis':
            require(raw['analysis_source_sha'] == ANALYSIS_SOURCE, 'Original analysis source differs')
            maps[name] = {'tools/'+p:h for p,h in raw['source_hashes'].items()}
        else:
            maps[name] = raw.get('source_hashes', raw)
        require(all(isinstance(p, str) and re.fullmatch('[0-9a-f]{64}', h) for p, h in maps[name].items()), 'Invalid actual source hash map')
        trees[name] = tree(repo, revisions[name])
        for path in set(maps[name]) | set(current_tree):
            if not source_scope(name, path):
                continue
            for t in [trees[name], current_tree]:
                if path in t and t[path]['kind'] == 'blob':
                    object_ids.append(t[path]['git_blob_sha1'])
    hashes = blob_hashes(repo, object_ids); results = {}
    for name, mapping in maps.items():
        old_tree = trees[name]; rows = []; nongit = []; selected_not_git = []
        for path, actual in sorted(mapping.items()):
            if path not in old_tree:
                nongit.append({'path': path, 'actual_sha256': actual, 'classification': 'Historical non-Git artifact or generated input; never called tracked source'})
                if source_scope(name, path):
                    selected_not_git.append(path)
        for path in sorted({p for p in mapping if source_scope(name, p) and p in old_tree}
                           | {p for p in current_tree if source_scope(name, p)}):
            old = old_tree.get(path); new = current_tree.get(path); actual = mapping.get(path)
            old_hash = hashes.get(old['git_blob_sha1']) if old and old['kind'] == 'blob' else None
            new_hash = hashes.get(new['git_blob_sha1']) if new and new['kind'] == 'blob' else None
            rows.append({'path': path, 'actual_execution_sha256': actual,
                         'original_git_blob_sha1': old['git_blob_sha1'] if old else None,
                         'original_git_sha256': old_hash['sha256'] if old_hash else None,
                         'current_git_blob_sha1': new['git_blob_sha1'] if new else None,
                         'current_git_sha256': new_hash['sha256'] if new_hash else None,
                         'actual_matches_original_git_bytes': bool(actual and old_hash and actual == old_hash['sha256']),
                         'actual_matches_current_git_bytes': bool(actual and new_hash and actual == new_hash['sha256']),
                         'original_equals_current_git_bytes': bool(old_hash and new_hash and old_hash == new_hash),
                         'mode_unchanged': bool(old and new and old['mode'] == new['mode'])})
        # Generated fixtures must have a separate G member proof, not a fictitious Git blob.
        fixture = None
        if name == 'render':
            fixture_path = 'client/tests/data/tuning_recovery_native.json'
            require(fixture_path in selected_not_git, 'Frozen generated render fixture was not separately classified')
            native_root = roots['native_vectors']
            native_relative = 'pr13-tuning-recovery-client-r1-20261010/validated/render-vectors.json'
            fixture = original_manifest_member(native_root, native_relative)
            require(fixture['sha256'] == mapping[fixture_path], 'Frozen renderer fixture differs from actual native G vectors')
            fixture['not_tracked_source'] = True
        changed = [r for r in rows if not r['actual_matches_current_git_bytes'] or not r['mode_unchanged']]
        domain = [r for r in rows if r['path'].startswith('server/src/FantasyCard.Domain/')]
        config = [r for r in rows if '/config/generated/' in r['path'] or '/data/generated/' in r['path']]
        results[name] = {'execution_source_sha': revisions[name], 'current_source_sha': current,
                         'actual_input_manifest': members[name], 'actual_input_entries': len(mapping),
                         'tracked_selected_source_rows': rows, 'changed_or_new_selected_paths': [r['path'] for r in changed],
                         'actual_original_selected_bytes_match': all(r['actual_matches_original_git_bytes'] for r in rows if r['actual_execution_sha256'] is not None),
                         'current_selected_byte_equivalence_verified': not changed,
                         'Domain_file_count': len(domain), 'Domain_exact_bytes_match': bool(domain) and all(r['actual_matches_current_git_bytes'] for r in domain),
                         'selected_config_file_count': len(config), 'selected_config_exact_bytes_match': bool(config) and all(r['actual_matches_current_git_bytes'] for r in config),
                         'historical_nonGit_entries': nongit, 'selected_nonGit_paths': selected_not_git,
                         'historical_generated_or_dependency_artifact_count': sum(any(part in {'obj','bin','.artifacts','.packages','.dotnet','.godot'} for part in PurePosixPath(p).parts) for p in mapping),
                         'artifact_exclusion_rule': 'obj/bin/.artifacts/.packages/.dotnet/.godot are generated or dependency artifacts even if historically tracked; original map preserved and never relabelled source',
                         'generated_render_fixture_proof': fixture,
                         'no_runtime_DLL_equivalence_inference': True}
    return results


def audit_evidence(repo, evidence):
    reports = repo / 'docs/reports/pr13-stages-20261009'
    full = reports / 'S5-b08-tuning-recovery-full'; render = reports / 'S3-b08-tuning-recovery-render'
    result = load(full / 'result.json'); summary = load(full / 'summary.json'); index = load(full / 'unit-evidence-index.json')['units']
    cases = load(full / 'cases.json')['cases']; controls = load(full / 'statistics-controls.json')
    require(result['ok'] and result['exit_code'] == 0 and not result['oom_killed'] and result['owned_container_removed'] and result['analysis_inputs_unchanged'], 'Statistics execution proof not clean')
    require(result['native_source_sha'] == EXPERIMENT_SOURCE and result['analysis_source_sha'] == ANALYSIS_SOURCE, 'Experiment/analysis source differs')
    require(result['rows'] == 216000 and result['pairs'] == 108000 and result['families'] == 36 and result['case_coverage_gaps'] == [], 'Incomplete full experiment')
    require(result['report_sha256'] == sha((full / 'full-statistics.json').read_bytes()), 'Final statistics bytes differ')
    expected = {f'{h}-{g}-{a}-B{b}' for h,g,a,b in product(('Mage','Priest','Guardian'),('O1','O6','E1','BOSS'),('ET-WOOD-G','ET-EARTH-G','ET-METAL-G'),range(3))}
    require(len(index) == 108 and {x['unit'] for x in index} == expected, 'Original 108-unit matrix differs')
    archive_bytes = members = events = reclaimed = 0; outcomes = Counter(); unit_proofs = []
    for row in index:
        name = row['unit']; directory = evidence / 'tuning-experiment-full-raw' / name
        backup_path = directory / 'local-backup-receipt.json'; cleanup_path = directory / 'cloud-cleanup-receipt.json'
        backup, cleanup = load(backup_path), load(cleanup_path)
        require(sha(backup_path.read_bytes()) == row['backup_receipt_sha256'] and sha(cleanup_path.read_bytes()) == row['cleanup_receipt_sha256'], 'Actual G receipt raw SHA differs: '+name)
        execution = load(directory / name / 'result.json'); native = load(directory / name / 'native/manifest.json')
        require(execution == row['execution'], 'Native G result differs from published index: '+name)
        require(execution['ok'] and execution['exit_code'] == 0 and not execution['oom_killed'] and execution['owned_container_removed'] and execution['compiled_runtime_unchanged'] and execution['source_inputs_unchanged'], 'Native unit not clean: '+name)
        require(execution['source_sha'] == native['source_sha'] == backup['source_sha'] == EXPERIMENT_SOURCE, 'Original source mismatch: '+name)
        require(backup['ok'] and backup['gzip_CRC_SHA_counts_verified'] and backup['members_verified'] == backup['members'], 'G byte/CRC proof incomplete: '+name)
        require(backup['raw_encounters_verified'] == 2000 and native['samples'] == 1000, 'Native pair/sample matrix changed: '+name)
        require(cleanup['ok'] and cleanup['local_G_verified'] and cleanup['cloud_raw_removed'] and cleanup['runtime_source_and_summaries_retained'], 'G cleanup closure missing: '+name)
        require(backup['sha256'] == cleanup['sha256'] and backup['bytes'] == cleanup['bytes'], 'Cleanup wrong G archive: '+name)
        require((directory / 'raw.private.tar.gz').stat().st_size == backup['bytes'], 'Actual G archive missing/truncated: '+name)
        validation = execution['validation']
        require(validation['ok'] and validation['full_unit'] and validation['encounters'] == 2000 and validation['pairs'] == 1000, 'Native validation incomplete: '+name)
        require(len(validation['negative_controls']) == 4 and all(c['rejected'] for c in validation['negative_controls']), 'Original oracle control missing: '+name)
        for case in ('T01','T02','T03'):
            require(all(validation['applicable_cases'][case].get(arm,0) > 0 for arm in ('BaselineGreenWater','SingleGreenReplacement')), 'Applicable case denominator absent: '+name)
        archive_bytes += backup['bytes']; members += backup['members']; events += backup['raw_events_verified']; reclaimed += cleanup['RAM_bytes_reclaimed']; outcomes.update(validation['outcomes'])
        unit_proofs.append({'unit': name, 'backup_receipt_sha256': row['backup_receipt_sha256'], 'cleanup_receipt_sha256': row['cleanup_receipt_sha256'], 'archive_sha256': backup['sha256'], 'archive_bytes': backup['bytes'], 'members': backup['members'], 'original_source_sha': EXPERIMENT_SOURCE})
    require(archive_bytes == summary['local_G_archive_bytes'] and members == summary['local_G_archive_members'] and events == summary['actual_casts'], 'Full G totals differ')
    require(dict(outcomes) == {k:v for k,v in summary['outcomes'].items() if v}, 'All outcomes accounting differs')
    require(set(c['case_id'] for c in cases) == set(CASES) and all(c['profile'] == 'EXPERIMENT' and c['execution_state'] == 'Passed' for c in cases), 'Canonical experiment case evidence incomplete')
    require(controls['ok'] and len(controls['actual_cloud_controls']['negative_controls']) == 4 and all(c['rejected'] for c in controls['actual_cloud_controls']['negative_controls']), 'Statistics provenance controls missing')
    render_summary = load(render / 'summary.json'); visual = load(render / 'visual-inspection.json'); render_receipt = load(render / 'local-backup-receipt.json')
    require(render_summary['render_source_sha'] == RENDER_SOURCE and render_summary['native_source_sha'] == VECTOR_SOURCE, 'Render source differs')
    require(render_receipt['ok'] and render_receipt['members_verified'] == 106 and render_receipt['bytes'] == 13510241, 'G render receipt incomplete')
    archive = evidence / 'tuning-render-delivery.private.tar.gz'
    require(archive.stat().st_size == render_receipt['bytes'], 'G render archive missing/truncated')
    matrix = []; witnesses = 0
    expected_render = {(language,width,height,fps) for language,(width,height),fps in product(('zh-CN','en'),((1920,1080),(1280,720),(960,540)),(30,60,144))}
    for cid in CASES:
        path = render / 'attempt-7/outputs' / cid
        wrapper = load(path / 'result.json'); native = load(path / 'native-result.json')
        require(wrapper['ok'] and wrapper['exit_code'] == 0 and not wrapper['oom_killed'] and wrapper['native_clean'] and wrapper['owned_container_removed'] and wrapper['source_inputs_unchanged'], 'Actual renderer not clean: '+cid)
        require(native['ok'] and not native['diagnostic_only'] and len(native['observations']) == 18 and all(x['passed'] for x in native['observations']), 'Renderer matrix not actually passed: '+cid)
        rows = {(x['language'], *x['resolution'], x['fps_cap']) for x in native['observations']}
        require(rows == expected_render, 'Language/size/FPS matrix differs: '+cid)
        witnesses += native['native_witness_renders']; matrix.extend({'case_id':cid, 'language':x['language'], 'resolution':x['resolution'], 'fps_cap':x['fps_cap'], 'passed':True} for x in native['observations'])
    require(len(matrix) == 54 and witnesses == 432 and visual['ok'] and visual['image_count'] == 9 and len(visual['images']) == 9, 'Render/visual original totals differ')
    for row in visual['images']:
        require(row['reviewed'] and row['readable'] and not row['layout_overlap_observed'], 'Actual visual review not passed')
        parts = PurePosixPath(row['path']).parts
        require(parts[0] == 'tuning-render-local-verified' and '..' not in parts, 'Unexpected visual evidence path')
        original = evidence.joinpath(*parts)
        require(original.stat().st_size == row['bytes'] and sha(original.read_bytes()) == row['sha256'], 'Actual reviewed G PNG differs')
    return {'original_experiment_profile_passed':True, 'original_render_profile_passed':True,
            'experiment_units':108, 'encounters':216000, 'pairs':108000, 'actual_casts':events,
            'comparison_families':36, 'outcomes':summary['outcomes'], 'archive_bytes':archive_bytes,
            'G_members_verified':members, 'actual_G_receipt_raw_hashes_matched':108,
            'original_oracle_controls_rejected':432, 'statistics_controls_rejected':4,
            'cloud_RAM_reclaimed_cumulative_bytes':reclaimed, 'render_matrix_rows':matrix,
            'native_witness_renders':432, 'actual_visual_PNGs_reviewed_and_hash_joined':9,
            'visual_covers_all_language_size_FPS_rows':False, 'hardware_FPS_claimed':False,
            'unit_receipt_anchors':unit_proofs, 'raw_gzip_not_revalidated_again':True,
            'no_native_business_or_statistical_oracle_executed_locally':True}


def audit(repo, evidence, current):
    sources = audit_sources(repo, evidence, current); execution = audit_evidence(repo, evidence)
    register = load(repo / REGISTER); task = next(t for t in register['tasks'] if t['task_id']=='PR13-B08.3')
    require(task['dependencies'] == ['PR13-B08.2'] and task['state'] == 'Partial', 'Unexpected canonical task state; inspect before supplement')
    shutdown = load(repo / 'docs/reports/pr13-stages-20261009/S4-b08-element-render-shutdown/lifetime-checkpoint/summary.json')
    require(shutdown['long_normal_shutdown_clean'] is False and shutdown['full_fix_verified'] is False, 'Preserve actual B08.2 unfinished shutdown')
    equivalent = all(row['current_selected_byte_equivalence_verified']
                     and row['actual_original_selected_bytes_match']
                     and set(row['selected_nonGit_paths']) <= ({'client/tests/data/tuning_recovery_native.json'} if name == 'render' else set())
                     for name,row in sources.items())
    proof = {'native_clean':True, 'owned_container_removed':True, 'source_inputs_match_git':equivalent,
             'implementation_source_sha':current, 'original_execution_source_shas':{'EXPERIMENT':EXPERIMENT_SOURCE,'RENDER':RENDER_SOURCE,'native_vectors':VECTOR_SOURCE},
             'equivalence_scope':'Exact selected tracked source and configuration bytes against actual original G input maps; changed files have no semantic waiver',
             'register_supplement_authorized':equivalent, 'S4_current_source_review_complete':equivalent,
             'acceptance_granted':False, 'MAIN_accepted':False}
    records = [{'case_id':cid,'executed':True,'status':'Passed','profiles_executed':['EXPERIMENT','RENDER'],
                'actual':{'original_EXPERIMENT_passed':True,'original_RENDER_passed':True,'full_experiment_encounters':216000,'render_rows_per_case':18,'visual_PNGs_per_case':3,'current_source_reuse_verified':equivalent},
                'evidence':['docs/reports/pr13-stages-20261009/S5-b08-tuning-recovery-full/cases.json','docs/reports/pr13-stages-20261009/S3-b08-tuning-recovery-render/attempt-7/outputs/'+cid+'/result.json','docs/reports/pr13-stages-20261009/S4-b08-tuning-recovery-current-source/audit.json']} for cid in CASES]
    return {'ok':True,'kind':'PR13-B08.3-metadata-source-gate-audit','current_source_sha':current,
            'source_audits':sources,'original_execution_evidence':execution,
            'current_source_equivalence_verified':equivalent,'S4_current_source_review_complete':equivalent,
            'register_supplement_authorized':equivalent,'supplement_proof':proof,
            'proposed_original_profile_records':records, 'records_must_not_be_applied_unless_source_gate_true':True,
            'MASTER_register_mutated':False,'canonical_missing_profiles_preserved':task['missing_case_profiles'],
            'B08_2_long_normal_shutdown_clean':False,'B08_2_dependency_accepted':False,
            'remaining_focus':'Review current Program/CombatExperience observer integration and changed shared UI, then bounded current-source cloud replay; no repeat of complete 216000 experiment',
            'whole_task_accepted':False,'MAIN_accepted':False,'local_native_business_execution':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--evidence-root',type=Path)
    parser.add_argument('--current-source-sha',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--require-current-equivalence',action='store_true')
    args = parser.parse_args(); repo = args.repo.resolve()
    evidence = args.evidence_root or repo / 'outputs/pr13-tencent-20261009'
    result = audit(repo,evidence,args.current_source_sha)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'ok':result['ok'],'current_source_sha':result['current_source_sha'],'current_source_equivalence_verified':result['current_source_equivalence_verified'],'register_supplement_authorized':result['register_supplement_authorized'],'output_sha256':sha(args.output.read_bytes()),'no_native_business_executed_locally':True}))
    return 2 if args.require_current_equivalence and not result['current_source_equivalence_verified'] else 0


if __name__=='__main__':
    raise SystemExit(main())
