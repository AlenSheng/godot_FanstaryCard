import hashlib,runpy,subprocess
R='/opt/fantasycard-github';S='docs/reports/pr13-stages-20261009/S0-a07-stale-original-PG-suite-source-gate/controller.original.py';HEAD='c983c3174f39e56e7418411b553390f442985eb8'
assert subprocess.check_output(['git','-c','safe.directory='+R,'-C',R,'rev-parse','HEAD']).decode().strip()==HEAD
runpy.run_path(R+'/'+S,run_name='__main__')
