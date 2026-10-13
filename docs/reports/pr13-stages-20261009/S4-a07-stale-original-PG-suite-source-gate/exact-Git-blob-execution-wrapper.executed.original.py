import hashlib,json,subprocess
R='/opt/fantasycard-github';S='docs/reports/pr13-stages-20261009/S0-a07-stale-original-PG-suite-source-gate';HEAD='c983c3174f39e56e7418411b553390f442985eb8'
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,*args])
assert git('rev-parse','HEAD').decode().strip()==HEAD
raw=git('show',HEAD+':'+S+'/controller.original.py');plan=json.loads(git('show',HEAD+':'+S+'/plan.original.json'));assert hashlib.sha256(raw).hexdigest()==plan['controller_sha256']
exec(compile(raw,HEAD+':'+S+'/controller.original.py','exec'),{'__name__':'__main__'})
