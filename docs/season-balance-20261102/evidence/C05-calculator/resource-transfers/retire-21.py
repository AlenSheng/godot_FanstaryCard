import hashlib,json,subprocess
from pathlib import Path

items=json.loads(Path('/home/ubuntu/season-balance-20261102-a03-storage-r49/consumed-transfer-origins.json').read_text())
allowed={f'storage-r{n}' for n in range(21,29)}
proof=[]
for item in items:
    stage=item['stage'];assert stage in allowed
    root=Path('/home/ubuntu/season-balance-20261102-a03-'+stage).resolve();assert root.parent==Path('/home/ubuntu')
    assert not subprocess.check_output(['docker','ps','-q','--filter','label=com.fantasycard.task=season-balance-20261102-a03-'+stage],text=True).strip()
    archive=(root/'transfer.tar.gz').resolve();assert archive.parent==root and not archive.is_symlink()
    if not archive.exists():continue
    assert (root/'public-evidence.tar.gz').is_file()
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==item['sha256']
    assert json.loads((root/'input-manifest.json').read_text())['archive_sha256']==item['source_sha256']
    assert hashlib.sha256((root/'source.tar.gz').read_bytes()).hexdigest()==item['source_sha256']
    location={'stage':stage,'sha256':item['sha256'],'retained_local_path':item['local_path'],
              'cloud_source_archive_manifest_scripts_and_original_results_retained':True,'retired_transport_bytes':archive.stat().st_size}
    (root/'transport-archive-location.json').write_text(json.dumps(location,indent=2)+'\n')
    archive.unlink();proof.append(location)
print(json.dumps({'retired_consumed_transport_envelopes':proof,'freed_bytes':sum(p['retired_transport_bytes']for p in proof)}))
