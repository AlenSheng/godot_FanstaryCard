from pathlib import Path
import json,hashlib
home=Path('/home/ubuntu');root=home/'season-balance-20261102-a03-storage-r57'
proof=json.loads((root/'ended-expanded-inputs-v1.json').read_text())
assert proof['expanded_copies_retired']
assert hashlib.sha256((root/'ended-expanded-inputs-v1.tar.gz').read_bytes()).hexdigest()==proof['archive_sha256']
for stage in proof['stages']:
 p=home/stage['root'];assert p.parent==home and not (p/'input').exists()
 assert hashlib.sha256((p/'source.tar.gz').read_bytes()).hexdigest()==stage['source_archive_sha256']
 assert hashlib.sha256((p/'public-evidence.tar.gz').read_bytes()).hexdigest()==stage['public_archive_sha256']
 target=p/'expanded-input-location.json';assert not target.exists()
 target.write_text(json.dumps({'complete_snapshot':str(root/'ended-expanded-inputs-v1.tar.gz'),'snapshot_sha256':proof['archive_sha256'],
  'snapshot_member_prefix':p.name+'/input/','retained_local_snapshot':proof['retained_local_snapshot'],
  'original_source_archive_and_public_results_retained_in_this_directory':True,
  'expanded_copy_retired_only_after_full_byte_verification':True},indent=2)+'\n')
print(json.dumps({'stage_pointers_written':len(proof['stages']),'snapshot_and_original_archives_unchanged':True}))

