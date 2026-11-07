from pathlib import Path
import datetime,gzip,hashlib,json,shutil,subprocess

b=Path(__file__).parent;repo=Path.cwd();common='75d7ef91a0e8846ade7f3dd1517a8c611b6bc4cd'
assert subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()==common
pending=subprocess.check_output(['git','status','--porcelain','-z']).decode().split('\0')
assert all(not row or row[3:] in ('.gitattributes','docs/season-balance-20261102/F03-CURRENT-PLATFORM-INTEGRATION.md') for row in pending)
destination=repo/'docs/season-balance-20261102/evidence/F03-current-platform-r1';assert not destination.exists();destination.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
platforms=[]
for platform in ('google','steam'):
    out=b/f'f03-{platform}-current-r1';work=b/f'work/f03-{platform}-integration-r1'
    info=json.loads((out/'source.original.json').read_bytes());build=json.loads((out/'build-result.json').read_bytes())
    assert build['exit']==0 and build['source_unchanged'] and '0 Warning(s)' in (out/'solution-build.original.log').read_text() and '0 Error(s)' in (out/'solution-build.original.log').read_text()
    assert subprocess.check_output(['git','-C',str(work),'rev-parse','HEAD']).decode().strip()==info['head']
    assert not subprocess.check_output(['git','-C',str(work),'status','--porcelain'])
    pin=json.loads((out/'source-pin.original.json').read_bytes());assert all(sha(work/n)==h for n,h in pin.items())
    cmd=['python',str(work/'tools/generate_network_protocol.py'),'--check'];r=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert r.returncode==0
    (out/'protocol-check.original.json').write_text(json.dumps(dict(command=cmd,exit=r.returncode,stdout=r.stdout,stderr=r.stderr),indent=2)+'\n')
    products=['server/src','protocol','client/ui','client/state','client/network','client/data','config']
    assert not subprocess.check_output(['git','-C',str(work),'diff','--name-only',info['prior'],info['head'],'--',*products])
    platforms.append(dict(platform=platform,head=info['head'],prior_validated_candidate=info['prior'],parents=info['parents'],source_entries=build['source_entries'],source_unchanged=True,
        full_solution_release_passed=True,warnings=0,errors=0,protocol_check=r.stdout.strip(),product_delta_from_validated_candidate=[],
        old_UI_and_platform_evidence_retained=True,new_UI_render_claim=False,worktree_clean=True))
remote=subprocess.check_output(['git','ls-remote','--heads','origin','release','release_google','release_steam','main'],timeout=45).decode()
(b/'f03-current-platform-target-refs.original.txt').write_text(remote)
proof=dict(scope='Current common source integrated and fully compiled in both existing isolated platform candidates',common=common,platforms=platforms,
    D03_used=299,D03_maximum=300,D03_accepted=False,F01_used=255,B05_used=330,whole_progress='33/35',F03_accepted=False,
    new_gameplay_cases=0,no_new_budgets_granted=True,remote_targets_updated=False,production_updated=False,
    memory_reserve_GiB=2,startup_GiB=1,one_heavy_process_at_a_time=True,
    old_metadata_archived_before_restoring_only_task_owned_imports=True,
    release_gate='D03 remains incomplete. No production promotion/restart before the outstanding acceptance gates are resolved.',
    at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(b/'f03-current-platform-audit-r1.derived.json').write_text(json.dumps(proof,indent=2)+'\n')
files=[]
for platform in ('google','steam'):files += [p for p in (b/f'f03-{platform}-current-r1').rglob('*') if p.is_file()]
files += [b/n for n in ['prepare-f03-current-platform-r1.py','build-f03-current-platform-r1.py','f03-current-platform-audit-r1.derived.json','f03-current-platform-target-refs.original.txt']]
manifest=[]
for p in sorted(files):
    assert p.suffix.lower() not in ('.dll','.exe','.pdb','.key')
    rel=p.relative_to(b).as_posix();compressed=p.stat().st_size>80000;q=destination/(rel+'.gz' if compressed else rel);q.parent.mkdir(parents=True,exist_ok=True)
    if compressed:q.write_bytes(gzip.compress(p.read_bytes(),mtime=0));assert gzip.decompress(q.read_bytes())==p.read_bytes()
    else:shutil.copyfile(p,q);assert sha(p)==sha(q)
    manifest.append(dict(path=q.relative_to(destination).as_posix(),source=str(p),source_sha256=sha(p),sha256=sha(q),source_bytes=p.stat().st_size,gzip=compressed))
(destination/'source-copy-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(destination/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
entries=[dict(path=p.relative_to(destination).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(destination.rglob('*')) if p.is_file()]
(destination/'manifest.json').write_text(json.dumps(entries,indent=2)+'\n')
print(json.dumps(dict(files=len(entries)+1,bytes=sum(p.stat().st_size for p in destination.rglob('*') if p.is_file()),platforms=platforms,new_gameplay_cases=0,F03_accepted=False)))
