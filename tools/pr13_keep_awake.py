"""Temporary owned Windows execution request during bounded load validation."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=7200)
    args=parser.parse_args()
    if os.name!='nt' or not 1<=args.seconds<=14400:parser.error('Windows and a 1-14400 second lifetime required')
    args.directory.mkdir(parents=True,exist_ok=True)
    call=ctypes.windll.kernel32.SetThreadExecutionState
    call.argtypes=[ctypes.c_uint32];call.restype=ctypes.c_uint32
    if not call(0x80000001):raise OSError('Windows execution request failed')
    start=time.monotonic();record=dict(pid=os.getpid(),started_at=time.time(),maximum_seconds=args.seconds,
        scope='System execution request while this process is alive; display remains managed by Windows',finished=False)
    owner=args.directory/'owner.json';owner.write_text(json.dumps(record,indent=2),encoding='utf8');print(json.dumps(record),flush=True)
    try:
        while time.monotonic()-start<args.seconds and not (args.directory/'STOP').exists():time.sleep(1)
    finally:
        call(0x80000000);record.update(finished=True,ended_at=time.time())
        owner.write_text(json.dumps(record,indent=2),encoding='utf8')
    return 0


if __name__=='__main__':raise SystemExit(main())
