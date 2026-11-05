from pathlib import Path
import importlib.util,os,sys,json
repo=Path.cwd();b=Path(r'G:\PR13Evidence\season-balance-20261102-r1');mode=sys.argv[1];assert mode in ['before','edit']
log=b/'workbook/outputs/01a1737c-c1cf-7342-92cd-7cea01eded79/refresh-prices-r1'/('artifact-'+mode+'.original.log');assert not log.exists()
spec=importlib.util.spec_from_file_location('fixture_runtime',repo/'client/tests/fixture_runtime.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cmd=[r'C:\Users\SHENGJIAHAO\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe',str(b/'workbook/refresh-prices.mjs')]+(['--before'] if mode=='before' else [])
r=m.guarded_run(cmd,env=os.environ.copy(),timeout=180);log.parent.mkdir(parents=True,exist_ok=True);log.write_text(r.stdout+r.stderr,encoding='utf-8');print((r.stdout+r.stderr)[-4000:]);assert r.returncode==0
