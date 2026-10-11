"""Inspect original GUI result and PNG metadata; no Godot execution."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from tools.pr13_pool_render_evidence import png_validate


def verify_smoke(directory):
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
            'full_matrix_claimed': False, 'pixels': pixels}
