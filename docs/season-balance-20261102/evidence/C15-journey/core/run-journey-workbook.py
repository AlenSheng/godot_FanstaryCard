from pathlib import Path
import importlib.util,os,sys,json
repo=Path.cwd();base=Path(r'G:\PR13Evidence\season-balance-20261102-r1');mode=sys.argv[1];assert mode in ['before','edit'];log=base/'workbook'/('journey-'+mode+'.original.log');assert not log.exists()
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');rt=importlib.util.module_from_spec(spec);spec.loader.exec_module(rt)
cmd=[r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe',str(base/'workbook/season-journey.mjs')]+(['--before'] if mode=='before' else [])
r=rt.guarded_run(cmd,env=dict(os.environ),timeout=180);text=r.stdout+r.stderr;log.write_text(text,encoding='utf-8');print(text[-4000:]);assert r.returncode==0
