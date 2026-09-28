"""Package tracked code/config inputs only for this private repository's diagnostics.
No deployment settings, environment files, databases, binaries, media or fonts.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[2]
out = Path(sys.argv[1]).resolve()
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
skip = {'bin', 'obj', 'artifacts', '.artifacts', '.godot', '.git', '.dotnet', '.packages', 'node_modules', 'local-backups', 'deploy', 'protection'}
extensions = {'.cs', '.csproj', '.props', '.targets', '.slnx', '.proto', '.gd', '.tscn', '.tres', '.md', '.py', '.ps1'}
exact = {'server/global.json', 'config/FantasyCard_Config.xlsx', 'config/card_descriptions.json', 'client/project.godot'}
manifest = {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip(), 'files': {}}
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in tracked:
        path = Path(name)
        if not name or set(path.parts) & skip:
            continue
        source = root / path
        if source.is_symlink() or not source.is_file():
            continue
        selected = name in exact or path.suffix in extensions or (path.suffix == '.bytes' and 'config' in path.parts and 'generated' in path.parts) or (name.startswith('client/') and 'localization' in name.lower() and path.suffix in {'.csv', '.json'})
        if not selected or source.stat().st_size > 5000000:
            continue
        data = source.read_bytes()
        archive.writestr(name, data)
        manifest['files'][name] = hashlib.sha256(data).hexdigest()
    archive.writestr('source-manifest.json', json.dumps(manifest, indent=2))
print(f'Packaged {len(manifest["files"])} tracked source/config inputs to {out.name}')
