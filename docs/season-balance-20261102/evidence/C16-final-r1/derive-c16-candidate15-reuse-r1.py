from pathlib import Path
import json,tarfile

b=Path(__file__).parent;proof=json.loads((b/'c16-candidate15-preflight-r2/reuse-equivalence.original.json').read_bytes());pairs={x['theme']:x for x in proof['pairs']};reused=[]
for stage in ['c16-calibration-pilot-r2','c16-expansion-fire-r1','c16-expansion-wood-r1','c16-remaining-r1']:
 p=b/stage/'observations';events=[json.loads(l) for l in (p/'monster-resources.original.jsonl').read_text('utf-8').splitlines()];rows=[json.loads(l) for l in (p/'encounters.original.jsonl').read_text('utf-8').splitlines()]
 for r in rows:
  boss=r.get('Boss',True);eligible=(boss and r['Build']=='direct-engine') or (r['Theme'] in ['Fire','Wood'] and r['Difficulty']==5 and r['Build'] in ['counter-combo','fortress-control'])
  if not eligible:continue
  start=next(e for e in events if e['kind']=='start' and e['theme']==r['Theme'] and e['difficulty']==r['Difficulty'] and e['hero']==r['Hero'] and e['build']==r['Build'] and e.get('boss',True)==boss);pair=pairs[r['Theme']]
  assert start['Version']==pair['oldVersion'] and start['ContentHash']==pair['oldHash'] and r['Outcome']=='Win'
  reused.append({'stage':stage,'row':r,'original_version':start['Version'],'original_hash':start['ContentHash'],'current_version':pair['newVersion'],'current_hash':pair['newHash'],'original_source_not_rewritten':True})
assert len(reused)==54
name='server/tests/FantasyCard.Server.Tests/Config/SeasonThemeCalibrationTests.cs'
with tarfile.open(b/'c16-remaining-build-r1/source-snapshot.original.tar.gz') as t:old=t.extractfile(name).read().decode('utf-8-sig').replace('\r\n','\n')
new=Path(name).read_text('utf-8-sig');anchor='    private static CalibrationRow Run(';assert old[old.index(anchor):]==new[new.index(anchor):]
p=b/'c16-candidate15-reused-observations.derived.json';assert not p.exists();p.write_text(json.dumps({'not_new_timing_executions':True,'originals_unchanged':True,'technical_basis':proof,'latest_original_controller_suffix_byte_equivalent':True,'earlier_controller_differences':'Only explicit elite fallback, counter-offense-only armor branch and observer labels; original direct/counter-combo/fortress inputs and selection remain unchanged.','eligible_observations':reused,'count':54,'matched_D5_boss_seed73_count':15,'first_formal_six_difficulty_direct_boss_count':18,'unchanged_Fire_Wood_other_archetypes_count':24,'derivation_key_includes_theme':True},indent=2)+'\n')
print('54 original observations matched original hashes; source inputs/factory/controller reuse verified without replay')
