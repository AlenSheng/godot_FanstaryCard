"""Build the closed Guardian8 report from already verified G originals only.

This reads archives, JSON, PNG CRC/deflate and typed protocol metadata. It
does not run a game, simulator, cloud command or native business validator.
The 54 original pictures were individually inspected through view_image.
After staging, the publisher must compare manifest hashes with committed Git
blob bytes; a working-tree hash alone is not a publication verification.
"""
import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

PUBLIC = Path(__file__).resolve().parent
REPO = PUBLIC.parents[3]
sys.path.insert(0, str(REPO))
from tools.pr13_pool_render_evidence import read_json, require, sha, verify_archive, verify_segment


SOURCE = 'bded54cf8f4b64e41807b1a871a9fd836c53186f'
NATIVE = '1341e160afc67ba826d4b37250c9ec58f8c99462'
G = REPO / 'outputs/pr13-tencent-20261009/pool-render-segment-r3-raw'
SEGMENTS = tuple(f'Guardian-8-{case}-{locale}'
                 for case in ('T02', 'T01', 'T03') for locale in ('zh-CN', 'en'))


def save(name, value):
    path = PUBLIC / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    if path.exists():
        require(path.read_bytes() == content, 'Existing public report differs; preserve it: ' + name)
    else:
        path.write_bytes(content)


def copy_original(source, name):
    target = PUBLIC / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        require(sha(target) == sha(source), 'Existing original public copy differs')
    else:
        shutil.copyfile(source, target)
    require(target.stat().st_size == source.stat().st_size and sha(target) == sha(source),
            'Original public member copy differs')
    return {'path': name, 'bytes': target.stat().st_size, 'sha256': sha(target)}


def main():
    require(G.is_dir(), 'Original local G evidence root missing')
    segments = []
    pictures = []
    rows_total = wire_total = reclaimed = 0
    for segment in SEGMENTS:
        local = G / segment
        extraction = local / 'verified'
        transfer = read_json(local / 'transport-receipt.json')
        receipt = read_json(extraction / 'local-backup-receipt.json')
        cleanup = read_json(local / 'cloud-cleanup-receipt.json')
        archive = local / 'delivery.private.tar.gz'
        require(transfer['ok'] is True and receipt['ok'] is True and cleanup['ok'] is True,
                'Closed segment is missing a successful delivery/G/cleanup proof')
        require(Path(receipt['local_archive']).resolve() == archive.resolve()
                and Path(receipt['local_directory']).resolve() == extraction.resolve(),
                'Original G archive/extraction anchors differ')
        manifest = verify_archive(archive, transfer, extraction)
        verified = verify_segment(extraction, manifest)
        require(verified['segment']['id'] == segment and verified['render_source_sha'] == SOURCE
                and verified['native_source_sha'] == NATIVE, 'Execution segment/source differs')
        require(receipt['segment'] == verified['segment']
                and receipt['matrix_rows_verified'] == verified['matrix_rows_verified']
                and receipt['independent_wire_command_rows_verified'] == verified['independent_wire_command_rows_verified']
                and receipt['PNG_CRC_deflate_verified'] == verified['PNG_CRC_deflate_verified'] == 9
                and receipt['members_verified'] == len(manifest['files'])
                and receipt['archive_gzip_CRC_verified'] is True,
                'Saved G verification receipt differs from independent reinspection')
        require(cleanup['segment'] == segment and cleanup['render_source_sha'] == SOURCE
                and cleanup['native_source_sha'] == NATIVE
                and cleanup['local_G_archive_sha256'] == receipt['sha256'] == transfer['sha256']
                and cleanup['local_G_archive_bytes'] == receipt['bytes'] == transfer['bytes']
                and cleanup['manifest_sha256'] == receipt['manifest_sha256'] == transfer['manifest_sha256']
                and cleanup['members_verified'] == len(manifest['files'])
                and cleanup['source_and_metadata_retained'] is True
                and cleanup['failed_originals_retained'] is True
                and cleanup['production_unchanged'] is True
                and cleanup['whole_task_accepted'] is False, 'Cloud cleanup lacks exact original G anchors')
        result = read_json(extraction / 'metadata/result.json')
        prereg = read_json(extraction / 'metadata/preregistration.json')
        case = verified['segment']['case']
        native = read_json(extraction / 'outputs' / case / 'native-result.json')
        inputs = read_json(extraction / 'metadata/inputs.json')
        for name in ('client/data/catalog.json', 'client/data/card_names.json'):
            original_blob = subprocess.check_output(['git', 'show', SOURCE + ':' + name], cwd=REPO)
            require(inputs[name] == hashlib.sha256(original_blob).hexdigest()
                    and json.loads(original_blob) == read_json(REPO / name),
                    'Catalog differs from exact execution Git bytes or current semantic contents')
        observations = native['observations']
        languages = {row.get('actual_language') for row in observations}
        requested = verified['segment']['language']
        require(languages == {requested}, 'Actual UI locale differs or is missing')
        count = 162 if case.endswith('T03') else 81
        require(len(observations) == verified['matrix_rows_verified'] == count,
                'Closed Guardian8 segment row count differs')
        require(result['source_sha'] == prereg['render_source_sha'] == SOURCE
                and result['shutdown_resources_clean'] is True
                and verified['normal_shutdown_clean'] is True,
                'Source or normal shutdown proof differs')
        prefix = 'segments/' + segment + '/'
        for original, name in (
            (extraction / 'metadata/result.json', 'result.json'),
            (extraction / 'metadata/preregistration.json', 'preregistration.json'),
            (extraction / 'local-backup-receipt.json', 'local-backup-receipt.json'),
            (local / 'cloud-cleanup-receipt.json', 'cloud-cleanup-receipt.json'),
            (extraction / 'outputs' / case / 'result.json', 'runtime-result.json'),
            (extraction / 'outputs' / case / 'engine.log', 'engine.log'),
        ):
            copy_original(original, prefix + name)
        representative = f'{case}_{requested}_960_30_8.png'
        copy_original(extraction / 'outputs' / case / representative, prefix + 'representative-960-30.png')
        for picture in verified['images']:
            picture_path = picture['path']
            require(picture_path.endswith('.png') and picture['sha256'] == sha(extraction / picture_path),
                    'Original inspected PNG hash differs')
            entry = {'segment': segment, 'original_G_relative_path': segment + '/verified/' + picture_path,
                     **picture, 'inspection': 'Direct view_image of this original; no montage or editing',
                     'actual_locale': requested, 'visually_observed_candidate_name': '火蝠' if requested == 'zh-CN' else 'Fire Bat',
                     'dialog_text_and_buttons_inside_image': True,
                     'hint_and_candidate_name_readable': True,
                     'clipping_or_overlap_observed': False,
                     'absorb_visually_disabled_as_expected': case.endswith('T02'),
                     'pool_occupancy_visible_in_picture': 8 if case.endswith('T02') else 7 if case.endswith('T01') else 0,
                     'visual_issues': [],
                     'notes': ['Static capture before the action; enabled/disabled state is interpreted at that boundary.',
                               'The default OK button is visible in both locales.']}
            if requested == 'en' and not case.endswith('T03'):
                entry['notes'].append('The repeated Fire Bat list wraps across two visible lines without clipping.')
            if case.endswith('T03'):
                entry['notes'].append('PNG captures the empty pool; the full-pool skip boundary is covered by native observations, not these pictures.')
            pictures.append(entry)
        rows_total += count
        wire_total += verified['independent_wire_command_rows_verified']
        reclaimed += cleanup['root_disk_bytes_reclaimed']
        segments.append({'id': segment, 'case': case, 'hero': 'Guardian', 'capacity': 8,
            'requested_language': requested, 'actual_languages': sorted(languages),
            'rows_verified': count, 'PNG_originals_verified_and_directly_viewed': 9,
            'independent_typed_wire_rows_verified': verified['independent_wire_command_rows_verified'],
            'production_catalog_name_verified_rows': count, 'normal_shutdown_clean': True,
            'archive_bytes': receipt['bytes'], 'archive_sha256': receipt['sha256'],
            'manifest_sha256': receipt['manifest_sha256'], 'members_verified': len(manifest['files']),
            'original_G_relative_directory': segment, 'cloud_cleanup_verified': True,
            'root_disk_bytes_reclaimed': cleanup['root_disk_bytes_reclaimed'],
            'representative_original_PNG': prefix + 'representative-960-30.png',
            'metadata_directory': prefix, 'whole_task_accepted': False})
        print(json.dumps({'segment': segment, 'rows': count, 'PNG': 9,
                          'archive_original_members': len(manifest['files']), 'cleanup_verified': True}), flush=True)
    require(rows_total == wire_total == 648 and len(pictures) == 54 and len(segments) == 6,
            'Closed Guardian8 total differs')
    save('images.json', {'render_source_sha': SOURCE, 'native_source_sha': NATIVE,
                        'original_PNGs_individually_viewed': 54, 'images': pictures,
                        'no_image_editing_or_compositing': True, 'whole_task_accepted': False})
    save('summary.json', {'ok': True, 'stage': 'S3_RENDER_Guardian8_closed_fixture_subset',
        'task_id': 'PR13-B09.2', 'render_execution_source_sha': SOURCE, 'native_source_sha': NATIVE,
        'closed_segments': segments, 'segment_count': 6, 'matrix_rows_verified': rows_total,
        'PNG_originals_verified_and_individually_viewed': 54, 'independent_typed_wire_rows_verified': wire_total,
        'actual_locale_and_production_catalog_name_verified_rows': rows_total,
        'normal_shutdown_clean_segments': 6, 'cloud_cleanup_verified_segments': 6,
        'cloud_root_disk_bytes_reclaimed_sum': reclaimed,
        'local_archive_CRC_all_member_SHA_reverified_segments': 6,
        'current_product_locale_matrix': {'segments_required': 54, 'rows_required': 5832, 'PNG_required': 486,
                                          'closed_subset_segments': 6, 'closed_subset_rows': 648, 'closed_subset_PNG': 54,
                                          'remaining_outside_this_report_segments': 48,
                                          'remaining_outside_this_report_rows': 5184,
                                          'remaining_outside_this_report_PNG': 432},
        'visual_issues_observed': [], 'visual_review_scope': 'These 54 static original dialog captures only',
        'three_frame_caps_are_configurations_not_measured_hardware_FPS': True,
        'controlled_response_delays_are_fixture_projections_not_WAN_measurements': True,
        'T03_full_pool_skip_has_native_rows_but_no_full_pool_static_capture': True,
        'capacity_3_5_and_other_heroes_accepted': False, 'full_fixture_matrix_accepted': False,
        'canonical_RENDER_pending': True, 'formal_EXPERIMENT_pending': True,
        'MAIN_accepted': False, 'LIVE_accepted': False, 'hardware_FPS_accepted': False,
        'human_experience_accepted': False, 'human_experience_in_current_scope': False,
        'authenticated_same_account_multigame_accepted': False,
        'whole_task_accepted': False, 'current_register_states_unchanged': True,
        'complete_raw_archives_retained_on_G_not_copied_to_Git': True,
        'publication_manifest_committed_Git_bytes_verification_required': True})
    files = []
    for path in sorted(PUBLIC.rglob('*')):
        if path.is_file() and path.name != 'manifest.json' and '__pycache__' not in path.parts:
            files.append({'path': path.relative_to(PUBLIC).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)})
    save('manifest.json', {'files': files})
    print(json.dumps({'ok': True, 'rows': 648, 'original_PNGs_viewed': 54,
                      'public_manifest_members': len(files), 'full_scope_still_pending': True}), flush=True)


if __name__ == '__main__':
    main()
