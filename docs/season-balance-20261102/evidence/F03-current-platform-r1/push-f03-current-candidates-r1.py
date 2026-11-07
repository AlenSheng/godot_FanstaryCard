from pathlib import Path
import importlib.util,json,os,subprocess,datetime

b=Path(__file__).parent;repo=Path.cwd();refs={
    'refs/heads/codex/season-balance-google-candidate-20261107':'406fb2eb93b3f02f93853663c38a6a59fee1c721',
    'refs/heads/codex/season-balance-steam-candidate-20261107':'018cd7ab51f94897e275d0baca041bdbc7cc49a5'}
for head in refs.values():subprocess.run(['git','cat-file','-e',head+'^{commit}'],check=True)
before=subprocess.check_output(['git','ls-remote','--heads','origin',*refs],timeout=45).decode();assert not before
out=b/'f03-current-candidate-push-r1';assert not out.exists();out.mkdir()
(out/'plan.original.json').write_text(json.dumps(dict(refs=refs,force=False,atomic=True,formal_release_refs_updated=False),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('guard',repo/'client/tests/fixture_runtime.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
command=['git','push','--atomic','origin',*[head+':'+ref for ref,head in refs.items()]]
r=guard.guarded_run(command,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),timeout=120,wait_seconds=30)
(out/'push.original.log').write_text(r.stdout+r.stderr,encoding='utf-8')
after=subprocess.check_output(['git','ls-remote','--heads','origin',*refs],timeout=45).decode()
(out/'remote-refs.original.txt').write_text(after)
observed={line.split()[1]:line.split()[0] for line in after.splitlines()};assert r.returncode==0 and observed==refs
proof=dict(exit=r.returncode,refs_verified=observed,formal_release_refs_updated=False,production_changed=False,new_gameplay_cases=0,at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
