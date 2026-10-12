"""Metadata-only preparation; original native vectors remain byte attributable."""
import ast,gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];D=B/'cap-RENDER-r7-development';assert not D.exists();D.mkdir()
source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert source=='6f3d61568f204f6b32b5a0574c8829d83f879b50'
original=(R/'client/tests/pr13_cap_effective_render.gd').read_text(encoding='utf-8')
replacement=original
def change(old,new,count=1):
 global replacement
 assert replacement.count(old)==count,(old,replacement.count(old));replacement=replacement.replace(old,new)
change('final_witness and P.language()=="en" and get_window().size.x==960 and Engine.max_fps==60','final_witness and Engine.max_fps==60',2)
change('var languages: Array = ["en"] if cap_diagnostic_one_row else ["zh-CN","en"]\n\tvar sizes: Array = [Vector2i(960,540)] if cap_diagnostic_one_row else [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]\n\tvar caps: Array = [60] if cap_diagnostic_one_row else [30,60,144]',
 '''var segment_language: String = OS.get_environment("PR13_CAP_SEGMENT_LANGUAGE")
\tvar segment_width: int = int(OS.get_environment("PR13_CAP_SEGMENT_WIDTH"))
\tassert(segment_language in ["zh-CN", "en"] and segment_width in [1920, 1280, 960] and not cap_diagnostic_one_row)
\tvar segment_height: int = 1080 if segment_width == 1920 else 720 if segment_width == 1280 else 540
\tvar languages: Array = [segment_language]
\tvar sizes: Array = [Vector2i(segment_width, segment_height)]
\tvar caps: Array = [30,60,144]''')
change('observations.size()==(1 if cap_diagnostic_one_row else 18)','observations.size()==3')
change('"diagnostic_only":cap_diagnostic_one_row,"whole_task_accepted":false','"diagnostic_only":false,"segment_language":segment_language,"segment_resolution":[segment_width,segment_height],"all_original_native_vectors_for_case_retained":true,"whole_task_accepted":false')
(D/'pr13_cap_effective_render.gd').write_text(replacement,encoding='utf-8',newline='\n')
root=B/'cap-offline-local-verified/pr13-cap-offline-delivery-20261011/cap-effective-offline-r2/raw/native'
manifest=json.loads((root.parents[2]/'manifest.json').read_bytes()) if (root.parents[2]/'manifest.json').exists() else json.loads((B/'cap-offline-local-verified/pr13-cap-offline-delivery-20261011/manifest.json').read_bytes())
rows=[];identities=[]
for p in sorted(root.glob('*.jsonl.gz')):
 raw_file=p.read_bytes();name=p.relative_to(B/'cap-offline-local-verified/pr13-cap-offline-delivery-20261011').as_posix()
 member=next(x for x in manifest['files'] if x['path']==name)
 assert member['bytes']==len(raw_file) and member['sha256']==hashlib.sha256(raw_file).hexdigest()
 with gzip.open(p,'rb') as f:
  for raw in f:
   row=json.loads(raw);a=row['actual'];cid=row['case_id']
   include=a['seed']==430001 and (a['level']==5 if cid.endswith('T01') else a['level'] in [0,5] if cid.endswith('T02') else a['weapon']==5 and a['position']=='full' and a['card_shield']==100)
   if include:rows.append({**row,'original_line_sha256':hashlib.sha256(raw).hexdigest()})
 identities.append({'path':name,'bytes':len(raw_file),'sha256':hashlib.sha256(raw_file).hexdigest()})
counts={cid:sum(x['case_id']==cid for x in rows) for cid in ['PR13-B08.4-T01','PR13-B08.4-T02','PR13-B08.4-T03']}
assert counts=={'PR13-B08.4-T01':15,'PR13-B08.4-T02':12,'PR13-B08.4-T03':3}
native={'source_sha':'8ff06ef8fff0ed592fae52facca680ddf9a5b8a7','kind':'actual_cap_contract_native_subset','rows':rows,'case_counts':counts,'original_offline_rows':864,'render_executed':False}
raw=(json.dumps(native,indent=2)+'\n').encode();assert hashlib.sha256(raw).hexdigest()=='dfdf390177a6a786dce13951b31e5d3067c1b808db86466f68180de4de375597'
(D/'cap_effective_native.json').write_bytes(raw)
segments=[{'slug':f'cap-RENDER-r7-t{c}-{lang.lower()}-{w}','case_id':f'PR13-B08.4-T0{c}','case_number':c,'language':lang,'resolution':[w,h],'expected_rows':3,'expected_witnesses':counts[f'PR13-B08.4-T0{c}']*3,'expected_inactive':9 if c==3 else 0,'expected_shield':9 if c==3 else 0,'expected_pngs':2 if c==3 else 1} for c in (1,2,3) for lang in ('zh-CN','en') for w,h in ((1920,1080),(1280,720),(960,540))]
plan={'kind':'complete_original_cap_RENDER_matrix_split_into_18_bounded_units','source_sha':source,'native_source_sha':native['source_sha'],'native_vectors_sha256':hashlib.sha256(raw).hexdigest(),'test_fixture_original_sha256':hashlib.sha256(original.encode()).hexdigest(),'candidate_fixture_sha256':hashlib.sha256(replacement.encode()).hexdigest(),'original_vector_files':identities,'segments':segments,'full_matrix_rows':54,'original_native_witnesses':540,'additional_inactive_contexts':54,'additional_shield_displays':54,'screenshots':24,'deadline_per_segment_seconds':900,'all_original_assertions_retained':True,'production_changed':False,'failed_R6_preserved':True,'MAIN_accepted':False}
assert len(segments)==18 and sum(s['expected_rows'] for s in segments)==54 and sum(s['expected_witnesses'] for s in segments)==540 and sum(s['expected_pngs'] for s in segments)==24
(D/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');print(json.dumps({k:v for k,v in plan.items() if k not in ('segments','original_vector_files')}))
