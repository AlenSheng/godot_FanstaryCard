from pathlib import Path
import hashlib,json,subprocess

b=Path(__file__).parent;out=b/'f03-main-integration-r1';work=b/'work/f03-main-integration-r1'
paths=['client/ui/i18n.gd','client/tests/branch_sync_compatibility.gd','client/tests/ui_branch_sync_preview.gd','client/tests/ui_branch_sync_preview.tscn','client/tests/ui_branch_sync_preview.gd.uid']
status=subprocess.check_output(['git','-C',str(work),'status','--porcelain','-z']).decode().split('\0')
assert all(not row or row[3:] in paths or row.startswith(' M client/assets/') and row.endswith('.import') for row in status)
assert not subprocess.check_output(['git','-C',str(work),'diff','--cached','--name-only'])
spec=out/'fixture-stage.original.nul';spec.write_bytes(b'\0'.join(n.encode() for n in paths)+b'\0')
subprocess.run(['git','-C',str(work),'add','--pathspec-from-file='+str(spec),'--pathspec-file-nul'],check=True)
staged=subprocess.check_output(['git','-C',str(work),'diff','--cached','--name-only','-z']).decode().strip('\0').split('\0');assert sorted(staged)==sorted(paths)
for p in paths:
    raw=(work/p).read_bytes();cached=subprocess.check_output(['git','-C',str(work),'show',':'+p]);assert raw.replace(b'\r\n',b'\n')==cached.replace(b'\r\n',b'\n')
subprocess.run(['git','-C',str(work),'diff','--cached','--check'],check=True)
subprocess.run(['git','-C',str(work),'commit','-m','fix(i18n): align retained main adapter and verify eleven-language settings'],check=True,stdout=subprocess.DEVNULL)
head=subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip()
assert subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD:client/ui/i18n.gd']).decode().strip()=='0c82e37036237a5bf148b564251b4801cdbe807e'
info=json.loads((out/'source.original.json').read_bytes());info.update(merge_head=info['head'],head=head,detached_validation_commit=head,working_importer_metadata_only=True,
    narrow_product_fix=['client/ui/i18n.gd'],fixture_changes=paths[1:],modified_source_sha256={p:hashlib.sha256((work/p).read_bytes()).hexdigest() for p in paths})
(out/'source.current.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(dict(head=head,product_fix_matches_validated_steam_blob=True,fixture_changes=4)))
