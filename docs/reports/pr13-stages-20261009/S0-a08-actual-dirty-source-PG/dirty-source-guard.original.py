import hashlib
import json
import os
import subprocess
from pathlib import Path
import gameplay_load_validation

C = Path('/control')
plan = json.loads((C/'plan.original.json').read_bytes())
os.environ.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory',
                  GIT_CONFIG_VALUE_0='/work', GIT_OPTIONAL_LOCKS='0')
path = plan['source_override_path']
paths = (path, 'server/config/generated/fantasycard.config.bytes')
clean = json.loads((C/'clean-source-provenance.original.json').read_bytes())
dirty = gameplay_load_validation.provenance(Path('/work'), paths)
status = subprocess.check_output(['git', '-C', '/work', 'status', '--porcelain', '--untracked-files=no']).decode().splitlines()
assert status == [' M '+path]
assert clean['git_dirty'] is False and dirty['git_dirty'] is True
assert dirty['git_commit'] == clean['git_commit'] != plan['source_base_sha']
assert clean['sha256'][path] == plan['original_test_source_sha256']
assert dirty['sha256'][path] == plan['modified_test_source_sha256']
assert dirty['sha256'][paths[1]] == clean['sha256'][paths[1]] == plan['published_config_bytes_sha256']
data = subprocess.check_output(['git', '-C', '/work', 'show', 'HEAD:'+path])
addition = (C/'addition.original.cs').read_bytes()
index = data.rfind(b'}')
assert (Path('/work')/path).read_bytes() == data[:index]+addition+data[index:]
print(json.dumps({'ok': True, 'clean': clean, 'dirty': dirty, 'actual_dirty_porcelain': status,
    'source_base_release_sha': plan['source_base_sha'],
    'source_snapshot_scope': '328 exact current release files in an isolated owned Git repository',
    'owned_snapshot_commit_is_release_commit': False,
    'compiled_dirty_source_matches_frozen_insertion': True,
    'tool_source_sha256': hashlib.sha256((C/'gameplay_load_validation.py').read_bytes()).hexdigest()}))
