from pathlib import Path
import ast,json,hashlib
base=Path(__file__).parent;repo=Path.cwd()
tree=ast.parse((base/'package-config17-r1.py').read_text(encoding='utf-8'))
statement=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='old_ui' for t in n.targets))
scope={'repo':repo};exec(compile(ast.fix_missing_locations(ast.Module(body=[statement],type_ignores=[])),'<reuse-comparison-only>','exec'),scope)
print(ascii([l for l in scope['old_ui'].splitlines() if 'current credit and5percent' in l]))
print(ascii([l for l in (repo/'client/tests/ui_visual_review.gd').read_text(encoding='utf-8').splitlines() if 'current credit and5percent' in l]))
pin={k.replace('\\','/'):v for k,v in json.loads((base/'config17-ui-final-r1-en/source-pin.original.json').read_bytes()).items()}
variants={name:hashlib.sha256(text.encode()).hexdigest() for name,text in [('lf',scope['old_ui']),('crlf',scope['old_ui'].replace('\n','\r\n'))]}
print(variants)
digest=next((h for h in variants.values() if h==pin['client/tests/ui_visual_review.gd']),None)
assert digest==pin['client/tests/ui_visual_review.gd'],(digest,pin['client/tests/ui_visual_review.gd'])
print('Original rendered test hash reproduced by reverting exactly one comparison expression; product source bytes separately checked during packaging.')
