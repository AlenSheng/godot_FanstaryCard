"""Temporary diagnostic packaging of public compiler/dependency files only.
Does not include user configuration, tokens, deployment data, source assets or fonts.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

sdk_root = Path(shutil.which('dotnet')).resolve().parent
version = subprocess.check_output(['dotnet', '--version'], cwd='server').decode().strip()
out = Path(sys.argv[1])
def clean(info):
    if Path(info.name).suffix.lower() in {'.ttf', '.otf', '.woff', '.woff2', '.pfx', '.pem', '.key'}:
        return None
    return info
with tarfile.open(out, 'w:gz', compresslevel=3) as archive:
    for relative in ['dotnet', 'host', f'sdk/{version}', 'shared/Microsoft.NETCore.App', 'shared/Microsoft.AspNetCore.App', 'packs']:
        source = sdk_root / relative
        if source.is_file():
            archive.add(source, f'dotnet/{relative}', filter=clean)
        elif source.is_dir():
            if relative in {'host', f'sdk/{version}'}:
                archive.add(source, f'dotnet/{relative}', filter=clean)
            elif relative == 'packs':
                for family in source.iterdir():
                    if family.is_dir():
                        candidates = sorted([p for p in family.iterdir() if p.is_dir() and p.name.startswith('10.')], key=lambda p: tuple(int(x) for x in p.name.split('.') if x.isdigit()))
                        if candidates: archive.add(candidates[-1], f'dotnet/{relative}/{family.name}/{candidates[-1].name}', filter=clean)
            else:
                candidates = sorted([p for p in source.iterdir() if p.is_dir() and p.name.startswith('10.')], key=lambda p: tuple(int(x) for x in p.name.split('.') if x.isdigit()))
                if candidates: archive.add(candidates[-1], f'dotnet/{relative}/{candidates[-1].name}', filter=clean)
    packages = Path(os.environ.get('NUGET_PACKAGES', str(Path.home() / '.nuget/packages')))
    if packages.is_dir(): archive.add(packages, 'nuget-packages', filter=clean)
print(f'Compiler {version}: {out.stat().st_size} bytes')
