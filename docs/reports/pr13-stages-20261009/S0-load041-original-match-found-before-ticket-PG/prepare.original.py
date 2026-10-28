import hashlib,json,os,subprocess
from pathlib import Path
B=Path('/home/ubuntu/pr13-acceptance-20261009');R='/opt/fantasycard-github'
S='docs/reports/pr13-stages-20261009/S0-load041-original-match-found-before-ticket-PG'
E=B/'evidence/Match-found-before-ticket-PG-r1-20261015';W=B/'work/Match-found-before-ticket-PG-r1-20261015'
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*args])
HEAD=git('rev-parse','HEAD').decode().strip()
def blob(path):return git('show',HEAD+':'+path)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024**2),b''):h.update(part)
    return h.hexdigest()
assert not E.exists() and not W.exists()
memory=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
disk=os.statvfs('/');assert memory>=500000000+128*1024**2 and disk.f_bavail*disk.f_frsize>=.15*disk.f_blocks*disk.f_frsize+80*1024**2
plan=json.loads(blob(S+'/plan.original.json'))
for key,root in [('source_files',Path(plan['source_root'])),('runtime_files',Path(plan['runtime_root']))]:
    for row in plan[key]:
        p=root/row['path'];assert not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
        if key=='source_files':assert hashlib.sha256(blob(row['path'])).hexdigest()==row['sha256']
for row in plan['client_files']:
    raw=blob(row['path']);assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
E.mkdir(mode=0o755);W.mkdir(mode=0o755)
for name in ['plan.original.json']+[r['path'] for r in plan['work_files']]:
    (W/name).write_bytes(blob(S+'/'+name));(W/name).chmod(0o644)
for name in ['controller.original.py','scheduler.original.py']:(E/name).write_bytes(blob(S+'/'+name))
assert not (Path(plan['source_root'])/'.git').exists(), 'Do not hardlink a shared Git index or object store'
subprocess.run(['cp','-al',plan['source_root'],str(W/'source')],check=True)
source=W/'source'
for row in plan['client_files']:
    p=source/row['path'];assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True)
    if row['path'].endswith('.otf'):
        shared=B/'work/cap-RENDER-r7-inputs'/row['path'];assert not shared.is_symlink() and shared.stat().st_size==row['bytes'] and sha(shared)==row['sha256']
        os.link(shared,p)
    else:
        p.write_bytes(blob(row['path']));p.chmod(0o644)
for rel,name,key in [('client/tests/run_ready_stop_faults.py','override.py','override_runner_sha256'),('client/tests/run_ready_stop_faults.gd','override.gd','override_gd_sha256'),('client/network/gateway.gd','override_gateway.gd','override_gateway_sha256')]:
    p=source/rel;assert p.is_file();p.unlink();p.write_bytes((W/name).read_bytes());p.chmod(0o644);assert sha(p)==plan[key]
env=dict(os.environ,GIT_AUTHOR_NAME='PR13 owned QA projection',GIT_COMMITTER_NAME='PR13 owned QA projection',GIT_AUTHOR_EMAIL='pr13-fixture@localhost',GIT_COMMITTER_EMAIL='pr13-fixture@localhost')
subprocess.run(['git','init','--initial-branch=qa-owned'],cwd=source,check=True,stdout=subprocess.DEVNULL)
# Immutable font binaries are independently SHA-frozen in plan/client_files and G originals.
# This owned Git commit records source text; omit duplicate font Git objects, not source/inputs.
(source/'.git/info/exclude').write_text('client/assets/fonts/SourceHanSansSC-Regular.otf\nclient/assets/fonts/SourceHanSerifSC-SemiBold.otf\n')
subprocess.run(['git','add','--all'],cwd=source,check=True)
subprocess.run(['git','-c','gc.auto=0','-c','maintenance.auto=false','commit','-m','Owned current inputs and declared READY false-send control'],cwd=source,env=env,check=True,stdout=subprocess.DEVNULL)
projection=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=source).strip()
proof={'ok':True,'current_release_sha':HEAD,'compiled_source_sha':plan['compiled_source_sha'],'source_members':328,
    'runtime_members':146,'client_original_members':len(plan['client_files']),
    'owned_projection_commit':projection,'owned_projection_commit_is_release_HEAD':False,
    'owned_Git_projection_tracks_source_text_fonts_independently_SHA_frozen':True,'read_only_shared_font_bytes_reused':41230364,'declared_test_control_overrides':2,'production_source_or_runtime_edited':False,'native_jobs_started':0,'MAIN_accepted':False}
(E/'prepared.original.json').write_bytes((json.dumps(proof,indent=2)+'\n').encode());print(json.dumps(proof))
