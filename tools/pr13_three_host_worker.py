"""Authenticated loopback-only control for one registered Windows native cohort.

Use a study-only SSH reverse forward. No arbitrary command, path or executable
is accepted from HTTP. The secret lives in a local config file, never argv/logs.
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import threading
import time


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args(argv)
    config=json.loads(args.config.read_text(encoding='utf-8'))
    assert os.name=='nt' and os.environ['COMPUTERNAME']==config['machine_name']=='SJH'
    if config.get('dependency_path'):sys.path.insert(0,config['dependency_path'])
    import psutil
    token=config['bearer_token'];assert isinstance(token,str) and len(token)>=48
    root=args.config.resolve(strict=True).parent
    source=Path(config['source_root']).resolve(strict=True)
    assert Path(__file__).resolve().is_relative_to(source/'tools')
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==config['source_head']
    capture=root/'capture';capture.mkdir(exist_ok=False)
    registered=root/'study-spec.original.json';job=None;lock=threading.Lock()
    stop=root/'STOP-STUDY';started=time.monotonic();last_activity=started
    node=capture/'producer';archive=root/'native-originals.tar.gz'
    def status():
        terminal=node/'terminal.original.json'
        return dict(machine_name='SJH',source_head=config['source_head'],registered=registered.exists(),
            memory_available_bytes=psutil.virtual_memory().available,
            logical_cpus=os.cpu_count(),cpu_percent=psutil.cpu_percent(interval=.1),
            evidence_disk_available_bytes=psutil.disk_usage(root.anchor).free,
            job_PID=job.pid if job is not None else None,job_exit=job.poll() if job is not None else None,
            terminal=json.loads(terminal.read_text(encoding='utf-8')) if terminal.exists() else None,
            stop_requested=stop.exists(),at_unix_ms=time.time_ns()/1e6,monotonic_ms=time.monotonic_ns()/1e6)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def response(self,code,value):
            raw=json.dumps(value,allow_nan=False).encode();self.send_response(code)
            self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        def authorized(self):
            nonlocal last_activity
            supplied=self.headers.get('Authorization','')
            if not hmac.compare_digest(supplied,'Bearer '+token): self.response(403,{'error':'unauthorized'});return False
            last_activity=time.monotonic();return True
        def do_GET(self):
            if not self.authorized():return
            if self.path=='/clock':
                self.response(200,dict(machine_name='SJH',unix_ms=time.time_ns()/1e6,monotonic_ms=time.monotonic_ns()/1e6));return
            if self.path=='/status':self.response(200,status());return
            if self.path!='/originals':self.response(404,{'error':'unknown_route'});return
            with lock:
                if job is None or job.poll() is None:self.response(409,{'error':'cohort_not_terminal'});return
                if not archive.exists():
                    with tarfile.open(archive,'x:gz') as out:
                        out.add(capture,arcname='capture')
                        for name in ('supervisor.stdout.original.log','supervisor.stderr.original.log',
                                     'worker-started.original.json','study-spec.original.json'):
                            item=root/name
                            if item.exists():out.add(item,arcname='control/'+name)
            self.send_response(200);self.send_header('Content-Type','application/gzip')
            self.send_header('Content-Length',str(archive.stat().st_size));self.end_headers()
            with archive.open('rb') as stream:
                while data:=stream.read(1024*1024):self.wfile.write(data)
        def do_POST(self):
            nonlocal job
            if not self.authorized():return
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:self.response(400,{'error':'invalid_body_size'});return
            if not 0<length<=1048576:self.response(400,{'error':'invalid_body_size'});return
            try:payload=json.loads(self.rfile.read(length))
            except (ValueError,UnicodeError):self.response(400,{'error':'invalid_json'});return
            with lock:
                if self.path=='/register':
                    spec=payload.get('spec');part=next((p for p in spec.get('partitions',[]) if p.get('host_id')=='sjh'),{}) if isinstance(spec,dict) else {}
                    if (registered.exists() or job is not None or not isinstance(spec,dict) or
                        spec.get('source_head')!=config['source_head'] or spec.get('target_clients')!=100 or
                        spec.get('workload_profile')!='full-native100-sjh50-windows30-cloud20-v1' or
                        part.get('machine_name')!='SJH' or part.get('clients')!=50 or
                        Path(part.get('project_path','')).resolve()!=source/'client' or
                        part.get('engine_path')!=config['engine_path'] or
                        part.get('server_url')!='http://127.0.0.1:18691' or
                        part.get('prometheus_url')!='http://127.0.0.1:18696'):
                        self.response(409,{'error':'foreign_duplicate_or_changed_spec'});return
                    with registered.open('x',encoding='utf-8') as out:json.dump(spec,out,indent=2,allow_nan=False)
                    self.response(200,{'registered':True});return
                if self.path=='/start':
                    if not registered.exists() or job is not None or stop.exists():self.response(409,{'error':'not_registered_or_already_started'});return
                    command=[sys.executable,'-B',str(source/'tools/pr13_three_host_windows.py'),'--spec',str(registered),
                        '--host-id','sjh','--output',str(node)]
                    if config.get('dependency_path'):command+=['--dependency-path',config['dependency_path']]
                    stdout=(root/'supervisor.stdout.original.log').open('xb');stderr=(root/'supervisor.stderr.original.log').open('xb')
                    try:job=subprocess.Popen(command,cwd=source,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                        creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
                    finally:stdout.close();stderr.close()
                    self.response(200,status());return
                if self.path=='/stop':
                    if not stop.exists():stop.write_text('peer_or_parent_stop\n',encoding='utf-8')
                    if job is not None and job.poll() is None:
                        peer=node.parent/'STOP-STUDY'
                        if not peer.exists():peer.write_text('peer_or_parent_stop\n',encoding='utf-8')
                    self.response(200,status());return
                self.response(404,{'error':'unknown_route'})
    server=ThreadingHTTPServer(('127.0.0.1',int(config['listen_port'])),Handler)
    server.timeout=.5
    with (root/'worker-started.original.json').open('x',encoding='utf-8') as out:
        json.dump({'PID':os.getpid(),'machine_name':'SJH','source_head':config['source_head'],
            'worker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'at_ns':time.time_ns()},out)
    while time.monotonic()-started<7200:
        server.handle_request()
        if job is None and time.monotonic()-last_activity>1800:break
        if job is not None and job.poll() is not None and time.monotonic()-last_activity>180:break
    server.server_close()


if __name__=='__main__': main()
