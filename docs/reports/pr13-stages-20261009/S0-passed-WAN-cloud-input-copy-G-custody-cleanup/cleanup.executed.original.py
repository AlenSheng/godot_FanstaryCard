G_RECEIPT={'ok': True, 'original_G_root': 'G:\\PR13Evidence\\WAN-Mage-natural3-r3', 'local_archive': 'G:\\PR13Evidence\\WAN-Mage-natural3-r3-complete-original-G-backup\\complete-originals.private.tar.gz', 'archive_bytes': 72473210, 'archive_sha256': 'fdd64c3d1926bcf9e4df0dcf1953f537fdab04ce76c6c10ba50878c59cf0a9df', 'manifest_sha256': '71ce11610a3a3be3189922e218c73d0a0bf0fc6168c2227691f12a8aea3ab2b0', 'original_members': 138, 'all_original_members_SHA_verified': True, 'archive_gzip_CRC_verified': True, 'original_client_sources_fonts_project_imports_full_JSONL_monitor_and_private_player_SQL_preserved': True, 'no_local_numerical_or_statistical_execution': True, 'native_gameplay_not_reexecuted_by_backup': True, 'private_account_and_raw_originals_not_published_to_Git': True}
INPUT_MANIFEST={'source': 'OriginalGBytesOnly', 'files': [{'path': 'player.original.json', 'bytes': 454191, 'sha256': '65e67f27fdac5135b24d52410dc220c453d688cbf8660d6d9bc7934ad31be29e'}, {'path': 'driver-result.original.json', 'bytes': 423, 'sha256': '484f11843befb0784353a6b40107d7e21c8aa189854f99fa8fbe6d4eb1f0593c'}, {'path': 'player.original.json.telemetry.jsonl', 'bytes': 1991530, 'sha256': '9245c0a7499571f155418e84ae367885f8b7fa7e7744384cc72c9594308dcd12'}, {'path': 'cloud-monitor.original.jsonl', 'bytes': 14643687, 'sha256': 'b6f2ffac0c1491cfbd532b08f912e1c911bf157bea7d5273345093a05f313e55'}, {'path': 'before-cloud.original.json', 'bytes': 1188, 'sha256': '6a294542806f9b452206927c8c685ea6c501742a07b1425cb62be43a842e66fd'}, {'path': 'after-cloud.original.json', 'bytes': 1187, 'sha256': 'a4b7aec04f9178b5851722fbc3dcafdcc606042f00f92fe5d04c0e215f16239f'}, {'path': 'started.original.json', 'bytes': 985, 'sha256': '472df028f1725ed8eaa5ea4477974278d4e4443391f054b896b3fcca849a1fcb'}], 'local_numerical_analysis': False}

import fcntl,hashlib,json,os,shutil,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');E=B/'evidence/WAN-Mage-natural3-r3-original-review';root=E/'originals';assert root.resolve(strict=True)==root and root.parent==E and not root.is_symlink();marker=E/'passed-original-input-copy-cleanup.original.json';assert not marker.exists()
with (B/'evidence/shared-resource-coordination.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);review=json.loads((E/'natural-baseline-review-result-semantics-r2.original.json').read_bytes());assert review['ok'] and review['natural_single_Mage_baseline_verified'] and review['SQL_all_three_ACK_and_no_pending_holds_active_members_or_tickets'];assert set(p.name for p in root.iterdir())=={r['path'] for r in INPUT_MANIFEST['files']}
 for row in INPUT_MANIFEST['files']:
  p=root/row['path'];assert p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
 for p in Path('/proc').iterdir():
  if not p.name.isdecimal() or int(p.name)==os.getpid():continue
  try:cmd=(p/'cmdline').read_bytes().decode(errors='replace').replace('\0',' ')
  except OSError:continue
  assert str(E) not in cmd,'Live prior review still refers to originals'
 ids=subprocess.check_output(['docker','ps','-aq'],text=True).split();cs=json.loads(subprocess.check_output(['docker','inspect',*ids])) if ids else []
 for c in cs:
  for bind in c.get('Mounts',[]):
   if bind.get('Type')!='bind':continue
   p=Path(bind['Source']).resolve()
   if c['Id']=='2734235cbfa1f9d8f1352cd9a925251f6356021d86ede341f80c6196e799149a' and p==Path('/') and bind.get('RW') is False:continue
   assert not (p==root or p.is_relative_to(root) or root.is_relative_to(p)),'Retained container refers to audit input copies'
 result_hashes={name:hashlib.sha256((E/name).read_bytes()).hexdigest() for name in ['review.original.json','natural-baseline-review.original.json','natural-baseline-review-result-semantics-r2.original.json','player-readonly-SQL.original.json']};intent=E/'passed-original-input-copy-cleanup-intent.original.json';assert not intent.exists();intent.write_text(json.dumps({'G_receipt':G_RECEIPT,'input_manifest':INPUT_MANIFEST,'target':str(root)},indent=2)+'\n');before=os.statvfs('/');shutil.rmtree(root);after=os.statvfs('/')
 for name,digest in result_hashes.items():assert hashlib.sha256((E/name).read_bytes()).hexdigest()==digest
 v={'ok':True,'exact_passed_cloud_original_input_copy_root_removed':str(root),'original_input_members':len(INPUT_MANIFEST['files']),'G_archive_SHA_CRC_and_all_selected_inputs_reverified':True,'all_original_cloud_reviews_and_SQL_summaries_retained':True,'failed_R1_R2_and_Priest_inputs_preserved':True,'active_Guardian_and_B04_inputs_preserved':True,'actual_root_bytes_reclaimed':(after.f_bavail-before.f_bavail)*after.f_frsize,'root_15pct_headroom_bytes_after':(after.f_bavail-.15*after.f_blocks)*after.f_frsize,'MAIN_accepted':False};marker.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
