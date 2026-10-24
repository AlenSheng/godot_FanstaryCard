"""Read actual native processes and software bytes without generating load.

Only the named launch-manifest PIDs and a small non-secret ownership environment
are observed. Capturing evidence does not adjudicate capacity.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

OWNERSHIP_ENV = (
    'FANTASYCARD_LOAD_CLIENT_ID', 'FANTASYCARD_LOAD_RUN_ID', 'FANTASYCARD_LOAD_PROCESS_EPOCH',
    'FANTASYCARD_LOAD_PROFILE', 'FANTASYCARD_LOAD_MAX_CYCLES', 'FANTASYCARD_LOAD_SEED',
    'FANTASYCARD_LOAD_HERO_CLASS', 'FANTASYCARD_LOAD_STRATEGY', 'FANTASYCARD_LOAD_HOLD_SECONDS',
    'FANTASYCARD_LOAD_RUN_SECONDS', 'FANTASYCARD_LOAD_CYCLE_LIMIT_SECONDS',
    'FANTASYCARD_LOAD_HTTP_TRANSPORT', 'FANTASYCARD_SERVER_URL', 'FANTASYCARD_LOAD_REPORT',
)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data := stream.read(1048576):
            h.update(data)
    return h.hexdigest()


def observe_processes(manifest, count, process_factory=None):
    if process_factory is None:
        import psutil
        process_factory = psutil.Process
    launches = manifest['launches']
    if len(launches) != count or len({r['pid'] for r in launches}) != count:
        raise ValueError('All distinct expected native PIDs must be launched before capture')
    rows = []
    for receipt in launches:
        pid = receipt['pid']
        if type(pid) is not int or pid < 1:
            raise ValueError('Invalid owned native PID')
        process = process_factory(pid)
        # Avoid observing or retaining unrelated secrets from the inherited env.
        environment = process.environ()
        selected = {key:environment.get(key) for key in OWNERSHIP_ENV}
        if any(selected[key] != receipt[field] for key, field in (
                ('FANTASYCARD_LOAD_CLIENT_ID', 'client_id'),
                ('FANTASYCARD_LOAD_RUN_ID', 'run_id'),
                ('FANTASYCARD_LOAD_PROCESS_EPOCH', 'process_epoch'))):
            raise ValueError('PID no longer belongs to its original launch')
        rows.append(dict(pid=pid, exe=process.exe(), command=process.cmdline(),
                         process_created_unix_ms=process.create_time()*1000,
                         load_environment=selected, priority_class=int(process.nice()),
                         cpu_affinity=process.cpu_affinity(), resident_bytes=process.memory_info().rss))
    return dict(observed_unix_ms=time.time_ns()/1000000,
                observed_monotonic_ms=time.monotonic_ns()/1000000,
                monotonic_implementation=time.get_clock_info('monotonic').implementation,
                logical_cpus=os.cpu_count(), processes=rows,
                scope='Actual OS native PIDs from this one owned manifest; not heartbeat-only claims')


def observe_software(source_root, engine, controls):
    root, requested = Path(source_root).resolve(), Path(engine).absolute()
    engine = requested.resolve()
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)
    commit = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,timeout=15,creationflags=flags)
    if commit.returncode:
        raise ValueError('Actual source Git worktree unavailable')
    version = subprocess.run([str(engine),'--headless','--audio-driver','Dummy','--version'],
                             capture_output=True,timeout=20,creationflags=flags,
                             env=dict(os.environ,GODOT_SILENCE_ROOT_WARNING='1'))
    if version.returncode:
        raise ValueError('Actual engine version probe failed')
    hashes = {}
    for name in controls:
        path = root/name
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError('Invalid physical control input')
        hashes[name] = sha256(path)
    inputs = {}
    for directory, children, files in os.walk(root/'client',followlinks=False):
        children[:] = [n for n in children if n not in ('.git','.godot')]
        if any(Path(directory,n).is_symlink() for n in children):
            raise ValueError('Symlinked client directory')
        for name in files:
            path = Path(directory,name)
            if path.is_symlink() or not path.is_file():
                raise ValueError('Nonregular physical client input')
            inputs[path.relative_to(root).as_posix()] = sha256(path)
    return dict(observed_unix_ms=time.time_ns()/1000000,
                source_head=commit.stdout.decode().strip(), source_controls=hashes,
                client_inputs=inputs, requested_engine=str(requested), real_engine=str(engine),
                engine_bytes=engine.stat().st_size, engine_sha256=sha256(engine),
                engine_version=version.stdout.decode().strip(),
                scope='Actual post/import or post/run filesystem bytes; import cache excluded')


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    native=sub.add_parser('processes');native.add_argument('--manifest',type=Path,required=True)
    native.add_argument('--count',type=int,required=True);native.add_argument('--output',type=Path,required=True)
    software=sub.add_parser('software');software.add_argument('--source-root',type=Path,required=True)
    software.add_argument('--engine',type=Path,required=True);software.add_argument('--controls-json',required=True)
    software.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.mode=='processes':
        result=observe_processes(json.loads(args.manifest.read_text(encoding='utf-8')),args.count)
    else:
        result=observe_software(args.source_root,args.engine,json.loads(args.controls_json))
    with args.output.open('xb') as out:out.write(json.dumps(result,indent=2).encode()+b'\n')
    print(json.dumps({'captured':True,'mode':args.mode,'capacity_accepted':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
