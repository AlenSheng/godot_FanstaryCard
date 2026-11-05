from pathlib import Path
import hashlib, json, subprocess, sys

sys.stdout.reconfigure(encoding='utf-8'); base=Path(__file__).parent; repo=Path.cwd(); old=base/'e01-inventory-ui-matrix-r1'
assert json.loads((old/'terminal.original.json').read_bytes())['stop_reason']=='OwnedRendererDeadline'
rows=[json.loads(line) for line in (old/'frames.original.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(rows)==70 and all(all(row['checks'].values()) for row in rows)
pin=json.loads((old/'source-pin.original.json').read_bytes()); assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
scenes=['e01_gear','e01_manage','e01_manage_bottom','e01_manage_selected','e01_manage_confirm','e01_manage_closed']
locales=list(json.loads((repo/'client/data/localization_registry.json').read_bytes())['languages'])
complete={row['name'] for row in rows}; groups=[]
for locale in locales:
    for width in [960,1280,1920]:
        missing=[s for s in scenes if f'{locale}_{width}_{s}' not in complete]
        if missing: groups.append(dict(locale=locale,width=width,scenes=missing,output=str(base/f'e01-inventory-ui-remainder-r1-{locale}-{width}')))
plan=base/'e01-inventory-ui-remainder-r1.plan.original.json'; assert not plan.exists(); plan.write_text(json.dumps(dict(original_complete=70,remaining=128,groups=groups),indent=2)+'\n')
engine=r'G:\Program Files\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64.exe'
for group in groups:
    command=[sys.executable,str(repo/'tools/validate_ui_hidden.py'),'--godot',engine,'--output',group['output'],'--screens',','.join('='+s for s in group['scenes']),'--locale',group['locale'],'--width',str(group['width']),'--wait-seconds','180']
    print('Starting remaining',group['locale'],group['width'],len(group['scenes']),flush=True)
    result=subprocess.run(command)
    terminal=json.loads((Path(group['output'])/'terminal.original.json').read_bytes())
    print(json.dumps(dict(locale=group['locale'],width=group['width'],exit=result.returncode,PNGs=terminal.get('PNGs'),stop_reason=terminal.get('stop_reason'))),flush=True)
    assert result.returncode==0 and terminal['native_exit']==0 and terminal['source_unchanged']
assert all(hashlib.sha256((repo/n).read_bytes()).hexdigest()==h for n,h in pin.items())
print('All128remaining frames finished, originals70 not replayed.',flush=True)
