"""Read-only PL occupancy snapshot. Never signal, close or reset other tasks."""
from pathlib import Path
import os
import platform
import time


def inspect_pl_occupancy(proc='/proc',*,own_pids=None):
    proc=Path(proc);own_pids=set(own_pids or {os.getpid()});occupied=[];unknown=[];examined=0
    for path in sorted(proc.iterdir()):
        if not path.name.isdecimal() or int(path.name) in own_pids:continue
        pid=int(path.name)
        try:
            content=(path/'maps').read_text('ascii');examined+=1
            hit=False
            for line in content.splitlines():
                fields=line.split(None,5)
                if len(fields)<6 or fields[5].strip()!='/dev/mem':continue
                extent,offset=fields[0],int(fields[2],16)
                lo,hi=(int(v,16) for v in extent.split('-'))
                if offset<0x80000000 and offset+hi-lo>0x40000000:hit=True
            fds=path/'fd'
            if fds.exists():
                for fd in fds.iterdir():
                    try:
                        name=os.readlink(fd)
                        if name in ('/dev/xdevcfg','/dev/fpga0'):hit=True
                    except FileNotFoundError:pass
            if hit:occupied.append(pid)
        except FileNotFoundError:pass # The vanished process cannot own a mapping.
        except (PermissionError,OSError,ValueError):unknown.append(pid)
    return dict(pl_free_confirmed=not occupied and not unknown,occupied_pids=occupied,
        unknown_pids=unknown,processes_examined=examined,tasks_stopped=0,
        inspected_monotonic_ns=time.monotonic_ns(),scope='Current PL/devcfg mappings; original advisory lease still required')


def require_pl_free():
    if platform.system()!='Linux' or platform.machine()!='armv7l':raise RuntimeError('PL preflight only on original ARM board')
    result=inspect_pl_occupancy()
    if not result['pl_free_confirmed']:
        raise RuntimeError('PL occupied or cannot confirm free; do not stop other tasks: '+str(result))
    return result
