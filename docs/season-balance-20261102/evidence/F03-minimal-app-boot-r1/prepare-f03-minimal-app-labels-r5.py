from pathlib import Path

b=Path(__file__).parent;source=(b/'f03-minimal-app-worker-r4.py').read_text('utf-8')
source=source.replace('season-balance-20261107-f03-minimal-app-r4','season-balance-20261107-f03-minimal-app-r5').replace('fc-f03-app4-','fc-f03-app5-').replace('app-candidate-r4','app-candidate-r5')
old="'--label','com.fantasycard.task='+label,"
new="'--label','com.fantasycard.task='+label,'--label','com.docker.compose.project='+label,'--label','com.docker.compose.service=owned-probe',"
assert source.count(old)==3;source=source.replace(old,new)
source=source.replace("assert len(archive.getmembers())==18","assert len(archive.getmembers())==len(manifest['transport_files'])")
source=source.replace("member.name in files and '/' not in member.name","member.name in manifest['transport_files'] and '/' not in member.name")
target=b/'f03-minimal-app-worker-r5.py';assert not target.exists();compile(source,str(target),'exec');target.write_text(source,encoding='utf-8')
prepare=(b/'prepare-f03-minimal-app-input-r4.py').read_text('utf-8').replace('f03-minimal-app-input-r4','f03-minimal-app-input-r5').replace('season-balance-20261107-f03-minimal-app-r4','season-balance-20261107-f03-minimal-app-r5')
old="tar.addfile(member,io.BytesIO(raw));files[name]=digest;total+=len(raw)"
new="files[name]=digest;total+=len(raw)\n        if name.startswith('FantasyCard.') or not name.endswith('.dll'):tar.addfile(member,io.BytesIO(raw))"
assert old in prepare;prepare=prepare.replace(old,new)
old="canonical_file_mode='0644',file_uid=1654,file_gid=1654"
new="transport_files={n:h for n,h in files.items() if n.startswith('FantasyCard.') or not n.endswith('.dll')},parent_reuse_verified_before_program_start=True,canonical_file_mode='0644',file_uid=1654,file_gid=1654"
assert old in prepare;prepare=prepare.replace(old,new)
(b/'prepare-f03-minimal-app-input-r5.py').write_text(prepare,encoding='utf-8')
runner=(b/'run-f03-minimal-app-cloud-r4.py').read_text('utf-8').replace('f03-minimal-app-cloud-r4','f03-minimal-app-cloud-r5').replace('f03-minimal-app-input-r4','f03-minimal-app-input-r5').replace('f03-minimal-app-worker-r4.py','f03-minimal-app-worker-r5.py').replace('season-balance-20261107-f03-minimal-app-r4','season-balance-20261107-f03-minimal-app-r5')
(b/'run-f03-minimal-app-cloud-r5.py').write_text(runner,encoding='utf-8');compile(runner,str(b/'run-f03-minimal-app-cloud-r5.py'),'exec');print(str(target))
