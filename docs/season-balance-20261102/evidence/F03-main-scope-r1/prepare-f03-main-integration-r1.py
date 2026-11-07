from pathlib import Path
import datetime,hashlib,importlib.util,json,os,subprocess

b=Path(__file__).parent;repo=Path.cwd();out=b/'f03-main-integration-r1';work=b/'work/f03-main-integration-r1'
common='838fa615700eefcd4f490afb08b16948db32d76a';target='5658c57a43e2de6309b1006c44d88d499165a9b1'
assert not out.exists() and not work.exists();assert not subprocess.check_output(['git','status','--porcelain']);out.mkdir()
def git(*args):return subprocess.check_output(['git',*args],stderr=subprocess.STDOUT)
assert git('rev-parse','HEAD').decode().strip()==common
r=subprocess.run(['git','merge-tree','--write-tree',common,target],capture_output=True,text=True,encoding='utf-8');(out/'merge-tree.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
tree=r.stdout.splitlines()[0];base=git('merge-base',common,target).decode().strip()
names=lambda *args:set(git('diff','--name-only',*args).decode().splitlines())
left=names(base,common);right=names(base,target);both=left&right
blob=lambda ref,name:git('rev-parse',ref+':'+name).decode().strip()
target_only=sorted(right-left);same=sorted(name for name in both if blob(common,name)==blob(target,name));auto=sorted(both-set(same))
assert all(blob(tree,name)==blob(target,name) for name in target_only)
delta=sorted(names(common,tree));audit=dict(base=base,common=common,target=target,tree=tree,target_only_files=target_only,overlap_same_final_blob=same,overlap_different_blobs_auto_merged=auto,actual_delta_from_common=delta,target_only_blobs_preserved=True)
(out/'three-way-source-audit.original.json').write_text(json.dumps(audit,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
r=guard.guarded_run(['git','worktree','add','--detach',str(work),target],env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),timeout=240,wait_seconds=30)
(out/'worktree-create.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
r=guard.guarded_run(['git','-C',str(work),'merge','--no-ff','--no-edit','-m','Merge current season into isolated main candidate',common],env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),timeout=120,wait_seconds=30)
(out/'merge.original.log').write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0
head=git('-C',str(work),'rev-parse','HEAD').decode().strip();assert git('-C',str(work),'rev-parse','HEAD^{tree}').decode().strip()==tree
assert not git('-C',str(work),'status','--porcelain')
proof=dict(worktree=str(work),common=common,target=target,head=head,tree=tree,parents=git('-C',str(work),'show','-s','--format=%P','HEAD').decode().strip().split(),target_only_preserved=True,source_audit=audit,
    formal_main_updated=False,production_changed=False,new_gameplay_cases=0,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'source.original.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(dict(head=head,common=common,target_only=len(target_only),same_overlap=len(same),auto_merged_different_blobs=auto,actual_delta_from_common=delta)))
