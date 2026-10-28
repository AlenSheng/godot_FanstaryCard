"""Full original bytes/CRC/Git/native JSON identity only; no local numerical replay."""
import gzip,hashlib,json,subprocess
from pathlib import Path
B=Path(__file__).parent;R=B.parents[1];S=R/'docs/reports/pr13-stages-20261009/S5-b07-current-full36000-table';G=Path('G:/PR13Evidence/B07-current-table-sequences-r1-20261013');OUT=B/'B07-preview-authority-full36000-G-audit-r1';assert not OUT.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
receipt=json.loads((S/'complete-original-G-receipt.json').read_bytes());manifest_path=G/'complete-original-manifest.json';manifest=json.loads(manifest_path.read_bytes());assert receipt['ok'] and receipt['native_ok'] and sha(manifest_path)==receipt['manifest_sha256'];backup=B/'B07-current-table-sequences-r1-20261013-complete-G';archive=backup/'complete-originals.private.tar.gz';assert archive.stat().st_size==receipt['archive_bytes'] and sha(archive)==receipt['archive_sha256']
with gzip.open(archive,'rb') as f:
 while f.read(1024**2):pass
shared={r['path']:r for r in json.loads((backup/'shared-original-G-references.json').read_bytes())};checked=[]
for row in manifest['files']:
 p=Path(shared[row['path']]['shared_G_reference']) if row['path'] in shared else G/row['path'];assert p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];checked.append(row['path'])
assert len(checked)==142 and len(shared)==2
references=json.loads((S/'shared-current-source-and-runtime-G-proof.json').read_bytes());assert references['ok'] and len(references['references'])==474;head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip();sources=0;runtime=0
for row in references['references']:
 p=Path(row['shared_G_reference']);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 if row['path'].startswith('current-frozen-source/'):
  rel=row['path'][len('current-frozen-source/'):];data=subprocess.check_output(['git','show',head+':'+rel],cwd=R);assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'];sources+=1
 else:runtime+=1
assert sources==328 and runtime==146
meta=json.loads((G/'metadata/inputs.original.json').read_bytes());native=json.loads((G/'metadata/result.original.json').read_bytes());report=json.loads((S/'report.original.json').read_bytes());oldproof=json.loads((S/'independent-terminal-source-validation.original.json').read_bytes());assert native['ok'] and native['exit_code']==0 and not native['oom_killed'] and native['owned_container_removed'] and native['source_runtime_and_fixture_unchanged'] and oldproof['ok'] and oldproof['original_full_native_rows']==36000 and oldproof['original_nine_boundary_observations_per_row'];assert report['ok'] and report['native_sequence_rows']==36000 and report['original_nine_sequence_boundaries_validated_per_row'] and report['required_seed_blocks']==3 and len(report['levels'])==6 and all(x['paired_seeds']==3000 and x['all_native_trace_states_independently_checked'] for x in report['levels'])
collector=(S/'Program.original.cs').read_bytes();assert b'Require(Hash(first! with { RoomRevision = actual.RoomRevision }) == Hash(actual)' in collector and b'Require(Hash(room.Capture()) == before' in collector and b'PreviewAndReject(trace);' in collector
raw=[r for r in manifest['files'] if r['path'].endswith('/Program.cs')];assert len(raw)==1 and raw[0]['sha256']==hashlib.sha256(collector).hexdigest()
v={'ok':True,'native_clean':True,'owned_container_removed':True,'source_inputs_match_git':True,'implementation_source_sha':head,'original_native_execution_source_sha':meta['implementation_source_sha'],'all_original_G_members_rehashed':142,'shared_current_source_members_rehashed_and_Git_verified':328,'shared_current_runtime_members_rehashed':146,'original_full_archive_SHA_CRC_reverified':True,'full_original_native_sequence_rows':36000,'full_original_paired_seeds_each_of_six_levels':3000,'original_independent_blocks':3,'original_preview_no_state_mutation_and_exact_successful_PlayCards_resolution_assertions_preserved':True,'actual_normalized_revision_only_preview_comparison':True,'original_independent_full_state_and_golden_resolution_validation_preserved':True,'exact_current_collector_bytes_and_runtime_identity':True,'mapping':'PR13-B07.3-T01 preview/commit boundary present in every complete original row also proves PR13-B07.4-T02 EXPERIMENT preview numeric authority parity only','scope':'Actual injected Room.PreviewCards/PlayCards with explicit prototype boundary hands; full all-six-level original budget, no natural-cycle/strength/LIVE or unexecuted client display claim','no_native_reexecution_or_new_samples':True,'MAIN_accepted':False};OUT.mkdir();(OUT/'independent-G-audit.original.json').write_bytes((json.dumps(v,indent=2)+'\n').encode());print(json.dumps({'ok':True,'full_original_rows':36000,'G_members':142,'current_source_members':328,'current_runtime_members':146,'mapped_case':'PR13-B07.4-T02 EXPERIMENT'}))
