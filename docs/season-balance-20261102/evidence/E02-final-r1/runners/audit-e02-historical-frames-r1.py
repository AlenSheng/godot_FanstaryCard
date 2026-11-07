from pathlib import Path
import json,hashlib,datetime
repo=Path.cwd();base=Path(__file__).parent;root=repo/'docs/season-balance-20261102/evidence'
sources={
 'C05':'C05-integration/final-frame-manifest.json',
 'C06':'C06-enhancement/final-frame-manifest.json',
 'C07-C08':'C07-C08-ui/final-frame-manifest.json',
 'C09':'C09-loot-preference/final-frame-manifest.json',
 'C11':'C11-red/final-frame-manifest.json',
 'C12':'C12-market/final-frame-manifest.json',
 'C13':'C13-shop/backend/ui/final-frame-manifest.json',
 'C14':'C14-activities/ui/final-frame-manifest.json',
 'C15-experience':'C15-journey/core/ui/final-frame-manifest.json',
 'C15-rewards':'C15-final-r1/UI-final-frame-manifest.json',
 'C16-theme-UI':'C16-themes/core/ui/final-frame-manifest.json',
 'original-refresh':'C01-refresh-price-ui/final-frame-manifest.json',
 'original-preparation':'A04-client-preparation-config-r1/final-frame-manifest.json'}
reports={};total=0;bytes_read=0
for name,path in sources.items():
 manifest=root/path;data=json.loads(manifest.read_bytes());rows=data['frames'] if 'frames' in data and isinstance(data['frames'],list) else [dict(file=k if k.endswith('.png') else k+'.png',**v) for k,v in data.items()]
 used=[]
 for row in rows:
  run=row.get('run',row.get('stage'));f=base/run/row['file'];assert f.is_file(),str(f)
  raw=f.read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256'],str(f);bytes_read+=len(raw)
  used.append({'file':row['file'],'run':run,'sha256':row['sha256']})
 total+=len(rows);reports[name]={'manifest':str(manifest.relative_to(repo)),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'verified_original_final_frame_entries':len(rows),'frames':used}
 print(name,len(rows),flush=True)
for name in ['E01-inventory-management-ui-r1','E01-season-archive-r1','E01-final-r1']:
 manifest=root/name/'source-byte-manifest.json';data=json.loads(manifest.read_bytes());used=[]
 for key,row in data.items():
  if not key.endswith('.png') or 'ui-' not in key.split('/')[0]:continue
  f=Path(row['source']);assert f.is_file(),str(f);raw=f.read_bytes();expected=row['original_sha256'];assert hashlib.sha256(raw).hexdigest()==expected,str(f);bytes_read+=len(raw);used.append({'file':key,'source':str(f),'sha256':expected})
 reports[name]={'manifest':str(manifest.relative_to(repo)),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'verified_pinned_UI_PNGs_including_prior_failed_or_partial':len(used),'original_acceptance_result':str((root/name/'result.json').relative_to(repo)),'original_acceptance_result_sha256':hashlib.sha256((root/name/'result.json').read_bytes()).hexdigest(),'frames':used};total+=len(used)
 print(name,len(used),'pinned includes failed/partial; do not count as passes',flush=True)
manifest=root/'C01-config17-r1/ui/frame-manifest.derived.json';used=[]
for row in json.loads(manifest.read_bytes()):
 f=Path(row['path']);assert f.is_file();raw=f.read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256'];bytes_read+=len(raw);used.append({'source':str(f),'sha256':row['sha256']})
reports['config17']={'manifest':str(manifest.relative_to(repo)),'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'verified_candidate_PNGs':len(used),'accepted_subset_basis':'Original result uses147 unchanged accepted frames plus84 targeted frames;273 candidate PNGs are not273 passing final frames.','frames':used};total+=len(used)
proof={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'groups':reports,'verified_PNG_entries':total,'bytes_read':bytes_read,'new_rendered_frames':0,'historical_verdicts_unchanged':True,'integrity_not_additional_passing_test_count':True,'E02_complete':False}
out=base/'e02-historical-frames-r1.derived.json';assert not out.exists();out.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'groups':len(reports),'PNG_entries':total,'bytes_read':bytes_read,'integrity_only':True}))
