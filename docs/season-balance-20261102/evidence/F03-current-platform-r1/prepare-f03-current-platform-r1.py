from pathlib import Path
import datetime,hashlib,json,os,subprocess,sys,tarfile

b=Path(__file__).parent;repo=Path.cwd();platform=sys.argv[1];assert platform in ('google','steam')
common='75d7ef91a0e8846ade7f3dd1517a8c611b6bc4cd'
prior={'google':'bc24f56e02fc2870a7e543a3d8f0d6e10f2f85f1','steam':'14b3a1729d55e59aea1aa3d24a47ac002ebf1a91'}[platform]
work=(b/f'work/f03-{platform}-integration-r1').resolve();assert work.is_relative_to((b/'work').resolve())
out=b/f'f03-{platform}-current-r1';assert not out.exists();out.mkdir()
def git(*args):return subprocess.check_output(['git','-C',str(work),*args],stderr=subprocess.STDOUT)
assert git('rev-parse','HEAD').decode().strip()==prior
assert not subprocess.check_output(['git','status','--porcelain'])
status=git('status','--porcelain','-z');(out/'before-status.original.bin').write_bytes(status)
entries=[s for s in status.decode().split('\0') if s];assert len(entries)==840
names=[]
for row in entries:
    assert row[:3]==' M ' and row[3:].startswith('client/assets/') and row.endswith('.import'),row
    path=work/row[3:];assert path.resolve().is_relative_to(work);names.append(row[3:])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
raw={n:sha(work/n) for n in names};(out/'importer-metadata-before.original.json').write_text(json.dumps(raw,indent=2)+'\n')
archive=out/'importer-metadata-before.original.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for name in names:tar.add(work/name,arcname=name,recursive=False)
with tarfile.open(archive,'r:gz') as tar:
    members=tar.getmembers();assert len(members)==840
    for entry in members:assert hashlib.sha256(tar.extractfile(entry).read()).hexdigest()==raw[entry.name]
spec=out/'importer-metadata-pathspec.original.nul';spec.write_bytes(b'\0'.join(n.encode() for n in names)+b'\0')
# Only task-generated metadata in this task's isolated checkout, with verified original-byte backup.
git('restore','--worktree','--pathspec-from-file='+str(spec),'--pathspec-file-nul')
assert not git('status','--porcelain')
command=['git','-C',str(work),'merge','--no-ff','--no-edit','-m',f'Merge current season verification into isolated {platform} candidate',common]
r=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW,timeout=60)
(out/'merge.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
assert r.returncode==0,(r.stdout+r.stderr)[-1500:]
head=git('rev-parse','HEAD').decode().strip();parents=git('show','-s','--format=%P','HEAD').decode().strip().split();assert parents==[prior,common]
assert not git('status','--porcelain')
products=['server/src','protocol','client/ui','client/state','client/network','client/data','config']
delta=git('diff','--name-only',prior,head,'--',*products).decode().splitlines();assert delta==[],delta
proof=dict(platform=platform,prior=prior,common=common,head=head,parents=parents,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    archived_task_importer_metadata_files=840,archive_sha256=sha(archive),exact_product_delta_from_prior_validated_candidate=delta,
    worktree_clean=True,actual_remote_target_updated=False,production_updated=False,new_gameplay_cases=0)
(out/'source.original.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
