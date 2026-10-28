import json
import os
import runpy
import sys
import traceback
from pathlib import Path

B=Path(__file__).resolve().parent
script,stdout_path,stderr_path=map(Path,sys.argv[1:])
assert all(p.resolve().is_relative_to(B) for p in [script,stdout_path,stderr_path])
with stdout_path.open('x',encoding='utf-8') as stdout,stderr_path.open('x',encoding='utf-8') as stderr:
    sys.stdout=stdout;sys.stderr=stderr
    try:
        assert Path.home().resolve()==Path('C:/Users/SHENGJIAHAO').resolve(), 'Expected same user profile for pinned SSH and Git credentials'
        print(json.dumps({'phase':'ActualHiddenProcessStarted','PID':os.getpid(),'parent_PID':os.getppid(),
            'script':script.name,'cwd':str(Path.cwd()),'user_profile_verified':True}),flush=True)
        sys.path.insert(0,str(B));sys.argv=[str(script)]
        runpy.run_path(str(script),run_name='__main__')
    except BaseException:
        traceback.print_exc();raise
    finally:
        stdout.flush();stderr.flush()
