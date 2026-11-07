from pathlib import Path
import os,signal,time,subprocess,json,hashlib
u=Path('/home/ubuntu/season-balance-20261107-f03-fixed-app-r1-upload');assert u.resolve()==u and not u.is_symlink()
pid=3279849;p=Path('/proc')/str(pid);handle=os.pidfd_open(pid)
assert p.stat().st_uid==1000 and (p/'comm').read_text().strip()=='sftp-server' and (p/'stat').read_text().split()[21]=='91246202'
assert os.readlink(p/'fd/3')==str(u/'stream.bin')
assert (u/'stream.bin').stat().st_size==1719700 and hashlib.sha256((u/'stream.bin').read_bytes()).hexdigest()=='a5afdb4bf6fecf233d203046e1d5d3122644b0d1b47cf568863c726742e23b77'
assert json.loads((u/'ownership.original.json').read_text())['sha256']=='a5afdb4bf6fecf233d203046e1d5d3122644b0d1b47cf568863c726742e23b77'
signal.pidfd_send_signal(handle,signal.SIGTERM);os.close(handle)
for _ in range(40):
 if not p.exists() or (p/'stat').read_text().split()[2]=='Z':break
 time.sleep(.25)
else:raise RuntimeError('Follow the same verified upload holder; do not force other processes')
subprocess.run(['umount',str(u)],check=True,timeout=10)
r=subprocess.run(['findmnt','--mountpoint',str(u),'-n'],capture_output=True,text=True,timeout=10);assert r.returncode!=0 and not list(u.iterdir())
print(json.dumps(dict(verified_owned_sftp_pid=pid,start_ticks='91246202',exact_owned_stream_handle_verified=True,only_SIGTERM_to_verified_owned_holder=True,upload_tmpfs_unmounted=True,empty_mountpoint=True,no_other_process_changed=True)))
