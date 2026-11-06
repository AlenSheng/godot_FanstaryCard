from pathlib import Path
import gzip,hashlib,json,re,shutil,subprocess
import xml.etree.ElementTree as E
repo=Path.cwd();b=Path(__file__).parent;e=repo/'docs/season-balance-20261102/evidence/C15-journey/core'
assert e.exists() and not (e/'result.json').exists() and not (e/'manifest.json').exists()
raw=json.loads((e/'ui/raw-frame-manifest.json').read_text(encoding='utf-8'))
final=json.loads((e/'ui/final-frame-manifest.json').read_text(encoding='utf-8'));checks=final['checks'];assert len(final['frames'])==330
for stage in ['storage-r88','storage-r89']:
 audit=json.loads((e/stage/'public/audit.json').read_text(encoding='utf-8'))
 for n,h in audit['files'].items():assert hashlib.sha256((e/stage/'public'/n).read_bytes()).hexdigest()==h,n
def copy(relative,dest=None):
 src=b/relative;target=e/(dest or relative);assert src.is_file()
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert target.read_bytes()==src.read_bytes()
 else:shutil.copy2(src,target)
copy('record-journey-core-r1.py','collection/record-journey-core-r1.py')
copy('resume-journey-core-collection.py','collection/resume-journey-core-collection.py')
(e/'collection/failure-note.json').write_text(json.dumps({'failure':'collection verifier expected all journey_ keys to total29; the pre-existing journey_end made30','new_keys':29,'existing_key_excluded':'journey_end','product_or_test_assertions_relaxed':False,'original_copied_raw_evidence_unchanged':True},indent=2)+'\n',encoding='utf-8')
script=(b/'record-journey-core.py').read_text(encoding='utf-8');tail=script[script.index('packs={'):];exec(compile(tail,'record-journey-core-tail','exec'))
