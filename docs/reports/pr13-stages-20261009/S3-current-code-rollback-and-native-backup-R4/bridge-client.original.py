#!/usr/bin/env python3
import json,socket,struct,sys
from pathlib import Path
def recv(s,n):
 out=bytearray()
 while len(out)<n:
  b=s.recv(n-len(out));assert b;out.extend(b)
 return bytes(out)
args=sys.argv[1:];input_bytes=sys.stdin.buffer.read(64*1024**2+1) if '-i' in args else b'';assert len(input_bytes)<=64*1024**2;header=json.dumps({'args':args,'stdin_bytes':len(input_bytes)}).encode();s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(35);s.connect('/bridge/owned-postgres.sock');s.sendall(struct.pack('!I',len(header))+header+input_bytes);n=struct.unpack('!I',recv(s,4))[0];assert n<4096;r=json.loads(recv(s,n));assert r['stdout_bytes']<=64*1024**2 and r['stderr_bytes']<=128*1024;sys.stdout.buffer.write(recv(s,r['stdout_bytes']));sys.stderr.buffer.write(recv(s,r['stderr_bytes']));s.close();raise SystemExit(r['exit_code'])
