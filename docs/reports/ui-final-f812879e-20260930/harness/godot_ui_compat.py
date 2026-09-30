#!/usr/bin/env python3
"""Add the reviewed Palette's transitive art imports to disposable PR13 fixtures.

No logic/theme substitution. Original runners and production files stay intact.
The real Godot executable owns all parsing, networking and rendering.
"""
import hashlib,json,os,sys
from pathlib import Path
import shutil
args=sys.argv[1:]
config=json.loads(Path(__file__).with_suffix('.config.json').read_text())
repo=Path(os.environ.get('RELICBOUND_UI_COMPAT_REPO',config['repo'])).resolve()
evidence=Path(os.environ.get('RELICBOUND_UI_COMPAT_EVIDENCE',config['evidence'])).resolve()
real=os.environ.get('RELICBOUND_REAL_GODOT_EXECUTABLE',config['real_godot'])
if '--path' in args:
 project=Path(args[args.index('--path')+1]).resolve()
 if project.is_relative_to(evidence) and (project/'ui/palette.gd').is_file():
  # Original isolated runners remove art.gd or omit it from their copy list.
  # Keep the complete original script, manifest and its eager texture imports.
  files=['ui/art.gd','assets/imported/manifest.json',
         'assets/generated/ui/safe_slot_frame_locked.png',
         'assets/generated/ui/safe_slot_frame_locked.png.import',
         'assets/generated/ui/signature_weapon_frames.png',
         'assets/generated/ui/signature_weapon_frames.png.import']
  copied=[]
  for relative in files:
   source=repo/'client'/relative;target=project/relative
   expected=hashlib.sha256(source.read_bytes()).hexdigest()
   if target.exists():
    assert hashlib.sha256(target.read_bytes()).hexdigest()==expected,relative
   else:
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    copied.append({'path':relative,'source_sha256':expected,'copied_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'bytes':target.stat().st_size})
  if copied:
   with (evidence/'compat-dependencies.jsonl').open('a') as log:
    log.write(json.dumps({'fixture':str(project.relative_to(evidence)),'added_verbatim_dependencies':copied,'original_logic_unmodified':True})+'\n')
os.execv(real,[real,*args])
