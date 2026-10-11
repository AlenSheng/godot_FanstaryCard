"""Inspect original GUI result and PNG metadata; no Godot execution."""
from collections import Counter
import hashlib
import json
import itertools
from pathlib import Path

from tools.pr13_pool_render_evidence import POOL_HINTS, png_validate


def verify_authority(row):
    expected = {
        'foreign': {'negative_original_transport_request_exact', 'negative_transport_request_correlated',
                    'no_player_mutation_during_controlled_delay', 'rejection_preserved_full_player'},
        'choice-replay': {'pending_registered', 'no_player_mutation_during_controlled_delay',
                          'first_original_player_applied', 'first_original_revision_exact',
                          'pending_cleared', 'replay_kept_full_state', 'replay_original_player_applied'},
        'pvp-state': {'return_original_player_applied', 'return_original_revision_exact'},
    }
    checks = row['authority_checks']
    assert set(checks) == expected[row['operation']] and all(x is True for x in checks.values())


def verify_layout(row):
    checks = row['combat_layout_checks']
    expected = {'waiting_and_opponent_controls_present', 'waiting_does_not_intersect_opponent_stats',
                'monster_name_count_matches_original_hand', 'all_monster_name_glyphs_fit'}
    if row['operation'] == 'pvp-state':
        assert set(checks) == expected and all(x is True for x in checks.values())
        labels = row['combat_layout_observation']['visible_label_paths']
        waiting = [x['text'] for x in labels if x['name'] == 'DuelWaitLabel']
        assert waiting == [{'en': 'Waiting for Action', 'zh-CN': '等待行动'}[row['locale']]]
    else:
        assert checks == {}


def verify_smoke(directory, authority_checks_required=False, layout_checks_required=False):
    root = Path(directory)
    result = json.loads((root / 'native-result.json').read_bytes())
    assert result['ok'] and result['display_driver'] == 'X11'
    assert 'llvmpipe' in result['adapter'] and result['development_smoke']
    assert not result['full_matrix_claimed'] and not result['human_experience_claimed']
    rows = result['observations']
    assert len(rows) == 9 and {(int(x['capacity']), x['operation']) for x in rows} == {
        (c, op) for c in (3, 5, 8) for op in ('foreign', 'choice-replay', 'pvp-state')}
    pixels = []
    for row in rows:
        if authority_checks_required:
            verify_authority(row)
        if layout_checks_required:
            verify_layout(row)
        assert row['passed'] and row['original_before_snapshot_applied']
        assert row['hero'] == 'Mage' and row['locale'] == 'en' and row['resolution'] == [960, 540]
        assert row['seed'] == 484001
        assert row['native_source_sha'] == '2a1d7e649f61aa1dc04bf50899f7cc32bb553d26'
        assert not row['PVP_leave_button_clicked'] and not row['foreign_candidate_UI_click_claimed']
        if row['operation'] == 'pvp-state':
            assert row['checkpoint_reader_reset_explicit'] and len(row['screenshots']) == 2
        else:
            assert row['dialog_opened'] and row['original_command_exact']
            assert row['labels'] and all(x['inside'] and x['all_lines_visible'] for x in row['labels'])
            assert POOL_HINTS['en'] in {x['text'] for x in row['labels']}
            assert row['choice_input_submitted'] == (row['operation'] == 'choice-replay')
            assert len(row['screenshots']) == 1
        for name in row['screenshots']:
            assert Path(name).name == name
            p = root / name
            info = png_validate(p)
            pixels.append({'path': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'PNG_validation': info})
    assert len(pixels) == len({x['path'] for x in pixels}) == 12
    assert set(x['path'] for x in pixels) == {p.name for p in root.glob('*.png')}
    return {'ok': True, 'render_observations_verified': 9, 'original_PNG_CRC_and_deflate_verified': 12,
            'software_rendering_only': True, 'foreign_click_and_PVP_leave_input_not_claimed': True,
            'full_matrix_claimed': False, 'explicit_authority_checks_verified': authority_checks_required,
            'combat_layout_checks_verified': layout_checks_required, 'pixels': pixels}


def verify_full_segment(directory, hero, locale, authority_checks_required=True, layout_checks_required=True):
    root = Path(directory)
    result = json.loads((root / 'native-result.json').read_bytes())
    assert result['ok'] and result['display_driver'] == 'X11'
    assert 'llvmpipe' in result['adapter'] and not result['development_smoke']
    assert result['declared_full_segment_executed'] and not result['full_matrix_claimed']
    assert not result['human_experience_claimed'] and result['language'] == locale
    assert hero in ('Mage', 'Priest', 'Guardian') and locale in ('zh-CN', 'en')
    rows = result['observations']
    expected = set(itertools.product((3, 5, 8), ('foreign', 'choice-replay', 'pvp-state'),
                   ((1920, 1080), (1280, 720), (960, 540)), (30, 60, 144), (0, 250, 1000)))
    actual = [(int(x['capacity']), x['operation'], tuple(x['resolution']),
               int(x['frame_cap']), int(x['controlled_response_delay_ms'])) for x in rows]
    assert len(rows) == len(set(actual)) == 243 and set(actual) == expected
    pixels = []
    for row in rows:
        if authority_checks_required:
            verify_authority(row)
        if layout_checks_required:
            verify_layout(row)
        assert row['passed'] and row['original_before_snapshot_applied']
        assert row['hero'] == hero and row['locale'] == locale and row['seed'] == 484001
        assert row['actual_window_size'] == row['resolution'] and row['frame_cap'] == row['requested_frame_cap']
        assert row['native_source_sha'] == '2a1d7e649f61aa1dc04bf50899f7cc32bb553d26'
        assert not row['PVP_leave_button_clicked'] and not row['foreign_candidate_UI_click_claimed']
        capture = row['frame_cap'] == 30 and row['controlled_response_delay_ms'] == 0
        if row['operation'] == 'pvp-state':
            assert row['checkpoint_reader_reset_explicit']
            count = 2
        else:
            assert row['dialog_opened'] and row['original_command_exact']
            assert row['labels'] and all(x['inside'] and x['all_lines_visible'] for x in row['labels'])
            assert POOL_HINTS[locale] in {x['text'] for x in row['labels']}
            assert row['choice_input_submitted'] == (row['operation'] == 'choice-replay')
            count = 1
        assert len(row['screenshots']) == (count if capture else 0)
        for name in row['screenshots']:
            assert Path(name).name == name
            p = root / name
            info = png_validate(p)
            pixels.append({'path': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'PNG_validation': info})
    assert len(pixels) == len({x['path'] for x in pixels}) == 36
    assert set(x['path'] for x in pixels) == {p.name for p in root.glob('*.png')}
    return {'ok': True, 'hero': hero, 'locale': locale, 'render_observations_verified': 243,
            'original_PNG_CRC_and_deflate_verified': 36, 'software_rendering_only': True,
            'frame_caps_are_not_hardware_FPS_measurements': True,
            'delays_are_controlled_fixture_delays_not_WAN_latency_measurements': True,
            'foreign_click_and_PVP_leave_input_not_claimed': True,
            'explicit_authority_checks_verified': authority_checks_required,
            'combat_layout_checks_verified': layout_checks_required, 'pixels': pixels}
