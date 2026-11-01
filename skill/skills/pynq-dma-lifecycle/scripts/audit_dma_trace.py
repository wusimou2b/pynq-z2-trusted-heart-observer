"""Audit declared fixed-length AXI simple-DMA events, never operate hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def integer(value, *, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError('expected ' + ('positive' if positive else 'nonnegative') + ' integer')
    return value


def strict_object(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise ValueError('duplicate JSON key: ' + k)
        value[k] = v
    return value


def load(path):
    if Path(path).stat().st_size > 16 * 1024**2:
        raise ValueError('trace exceeds 16 MiB limit')
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=strict_object,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def audit(trace):
    report = {'schema': 'pynq-dma-audit-v1', 'hardware_accessed': False,
              'hardware_cleanup_verified': False, 'errors': [], 'faults': [],
              'diagnostics': [], 'events_checked': 0,
              'scope': 'declared trace consistency only; fixed-length axi-dma-simple adapter'}
    buffers, channels, transfers, exited = {}, {}, {}, set()
    try:
        if not isinstance(trace, dict) or trace.get('schema') != 'pynq-dma-trace-v1':
            raise ValueError('unsupported trace schema')
        if set(trace) - {'schema', 'run_id', 'buffers', 'channels', 'events'}:
            raise ValueError('unknown top-level trace fields')
        run = trace['run_id']
        if not isinstance(run, str) or not run:
            raise ValueError('nonempty run_id required')
        for b in trace['buffers']:
            if set(b) != {'id', 'owner', 'nbytes', 'device_address', 'coherent', 'itemsize'}:
                raise ValueError('invalid buffer fields')
            if not isinstance(b['id'], str) or not b['id'] or b['id'] in buffers or not isinstance(b['owner'], str) or not b['owner']:
                raise ValueError('invalid/duplicate buffer identity')
            integer(b['nbytes'], positive=True); integer(b['device_address']); integer(b['itemsize'], positive=True)
            if type(b['coherent']) is not bool or b['nbytes'] % b['itemsize']:
                raise ValueError('coherence must be explicit; whole elements required')
            buffers[b['id']] = dict(b, freed=False, dirty=False, stale=False, initialized=False, borrowers=set(), views=set())
        # Aliases must be represented by views, not a second overlapping allocation.
        ordered = sorted(buffers.values(), key=lambda b: b['device_address'])
        for a, b in zip(ordered, ordered[1:]):
            if a['device_address'] + a['nbytes'] > b['device_address']:
                raise ValueError('overlapping physical allocations; represent aliases as views')
        for c in trace['channels']:
            fields = {'id', 'owner', 'kind', 'direction', 'data_width_bytes', 'address_bits', 'max_transfer_bytes', 'dre'}
            if set(c) != fields:
                raise ValueError('invalid channel fields')
            if not isinstance(c['id'], str) or not c['id'] or c['id'] in channels or not isinstance(c['owner'], str) or not c['owner']:
                raise ValueError('invalid/duplicate channel identity')
            if c['kind'] != 'axi-dma-simple':
                raise ValueError('unsupported channel kind: use a reviewed SG/VDMA/cyclic adapter, not simple-mode rules')
            if c['direction'] not in ('send', 'receive') or type(c['dre']) is not bool:
                raise ValueError('invalid direction/DRE declaration')
            width = integer(c['data_width_bytes'], positive=True)
            if width & (width - 1):
                raise ValueError('data width must be a power of two bytes')
            if not 1 <= integer(c['address_bits'], positive=True) <= 64:
                raise ValueError('unsupported address width')
            integer(c['max_transfer_bytes'], positive=True)
            channels[c['id']] = dict(c, active=None, halted=False)
        if not buffers or not channels:
            raise ValueError('nonempty buffers/channels required')
        events = trace['events']
        if not isinstance(events, list) or not events or len(events) > 100000:
            raise ValueError('events must contain 1..100000 records')
        last_seq, last_ns = -1, -1
        used_views = set()
        used_transfers = set()

        def active_on(buffer_id):
            return any(c['active'] and transfers[c['active']]['buffer'] == buffer_id for c in channels.values())

        def buffer_for(e):
            b = buffers[e['buffer']]
            if b['freed']:
                raise ValueError('buffer already freed')
            if e['actor'] != b['owner'] and e['actor'] not in b['borrowers']:
                raise ValueError('actor has no buffer ownership/borrow grant')
            return b

        def channel_for(e):
            c = channels[e['channel']]
            if e['actor'] != c['owner']:
                raise ValueError('channel operation by non-owner')
            return c

        def idle(b):
            if active_on(b['id']):
                raise ValueError('buffer still in use by DMA')

        event_fields = {
            'cpu_write': {'buffer'}, 'cpu_read': {'buffer'},
            'sync_to_device': {'buffer', 'via'}, 'sync_from_device': {'buffer', 'via'},
            'borrow': {'buffer', 'borrower'}, 'return': {'buffer'},
            'view_open': {'buffer', 'view'}, 'view_close': {'buffer', 'view'},
            'transfer': {'buffer', 'channel', 'transfer', 'offset', 'nbytes'},
            'complete': {'channel', 'transfer', 'actual_bytes'},
            'stop_request': {'channel'},
            'halted': {'channel', 'driver_verified', 'active_access_ended'},
            'wait_timeout': {'channel'}, 'channel_error': {'channel', 'message'},
            'free': {'buffer'}, 'process_exit': set(),
        }
        for index, e in enumerate(events):
            try:
                kind = e['event']
                if kind not in event_fields or set(e) != {'seq', 'ns', 'run_id', 'actor', 'event'} | event_fields[kind]:
                    raise ValueError('unknown event or fields')
                seq, ns = integer(e['seq']), integer(e['ns'])
                if seq != last_seq + 1 or ns < last_ns:
                    raise ValueError('missing/reordered event or regressing monotonic timestamp')
                if e['run_id'] != run or not isinstance(e['actor'], str) or not e['actor'] or e['actor'] in exited:
                    raise ValueError('run/actor mismatch or actor already exited')
                last_seq, last_ns = seq, ns
                if kind in ('cpu_write', 'cpu_read', 'sync_to_device', 'sync_from_device'):
                    b = buffer_for(e); idle(b)
                    if kind.startswith('sync_') and e['via'] not in ('driver', 'explicit'):
                        raise ValueError('sync via must identify driver or explicit synchronization')
                    if kind == 'cpu_write':
                        b.update(dirty=not b['coherent'], stale=False, initialized=True)
                    elif kind == 'cpu_read':
                        if b['stale'] or not b['initialized']:
                            raise ValueError('CPU read before valid completed/synchronized data')
                    elif kind == 'sync_to_device':
                        b['dirty'] = False
                    else:
                        if b['dirty']:
                            raise ValueError('invalidate would discard unsynchronized CPU writes')
                        b['stale'] = False
                elif kind == 'borrow':
                    b = buffer_for(e)
                    who = e['borrower']
                    if e['actor'] != b['owner'] or not isinstance(who, str) or not who or who == b['owner'] or who in b['borrowers'] or who in exited:
                        raise ValueError('invalid borrow grant')
                    b['borrowers'].add(who)
                elif kind == 'return':
                    b = buffer_for(e); idle(b)
                    if e['actor'] not in b['borrowers'] or any(actor == e['actor'] for _, actor in b['views']):
                        raise ValueError('borrower absent or still has views')
                    b['borrowers'].remove(e['actor'])
                elif kind == 'view_open':
                    b = buffer_for(e); view = e['view']
                    if not isinstance(view, str) or not view or view in used_views:
                        raise ValueError('invalid/reused view identity')
                    used_views.add(view); b['views'].add((view, e['actor']))
                elif kind == 'view_close':
                    b = buffer_for(e)
                    b['views'].remove((e['view'], e['actor']))
                elif kind == 'transfer':
                    b, c = buffer_for(e), channel_for(e)
                    tid = e['transfer']; offset = integer(e['offset']); n = integer(e['nbytes'], positive=True)
                    if not isinstance(tid, str) or not tid or tid in used_transfers:
                        raise ValueError('invalid/reused transfer identity')
                    if c['active'] or c['halted'] or active_on(b['id']):
                        raise ValueError('busy/stopped channel or buffer already in DMA use')
                    address = b['device_address'] + offset
                    if offset + n > b['nbytes'] or n > c['max_transfer_bytes'] or address + n > 2**c['address_bits']:
                        raise ValueError('transfer exceeds buffer/channel/address limit')
                    if offset % b['itemsize'] or n % b['itemsize']:
                        raise ValueError('transfer splits declared element size')
                    if not c['dre'] and address % c['data_width_bytes']:
                        raise ValueError('unaligned address without DRE')
                    # V1 treats each CPU read/write as a full buffer operation.
                    if offset != 0 or n != b['nbytes']:
                        raise ValueError('partial buffers need range-aware adapter; v1 requires whole-buffer transfers')
                    if b['dirty'] or (c['direction'] == 'send' and (not b['initialized'] or b['stale'])):
                        raise ValueError('device input is uninitialized/stale or CPU writes not synchronized')
                    used_transfers.add(tid)
                    transfers[tid] = {'buffer': b['id'], 'nbytes': n, 'channel': c['id'], 'completed': False}
                    c['active'] = tid
                    if c['direction'] == 'receive':
                        b.update(initialized=False, stale=not b['coherent'])
                elif kind == 'complete':
                    c = channel_for(e); tid = e['transfer']
                    if not c['active'] or c['active'] != tid:
                        raise ValueError('completion identity differs from active transfer')
                    t = transfers[tid]
                    if integer(e['actual_bytes']) != t['nbytes']:
                        raise ValueError('short/oversize completion under fixed-length contract')
                    t['completed'] = True; c['active'] = None
                    if c['direction'] == 'receive':
                        buffers[t['buffer']]['initialized'] = True
                elif kind == 'stop_request':
                    channel_for(e)  # Request alone does not clear an active transfer.
                elif kind == 'halted':
                    c = channel_for(e)
                    if e['driver_verified'] is not True or e['active_access_ended'] is not True:
                        raise ValueError('missing driver-specific end-of-access evidence')
                    if c['active']:
                        t = transfers[c['active']]
                        t['cancelled'] = True
                        if c['direction'] == 'receive':
                            buffers[t['buffer']]['initialized'] = False
                        c['active'] = None
                    c['halted'] = True
                elif kind in ('wait_timeout', 'channel_error'):
                    c = channel_for(e)
                    report['faults'].append({'event_index': index, 'channel': c['id'], 'type': kind,
                                             'message': e.get('message')})
                    if kind == 'wait_timeout':
                        report['diagnostics'].append('Timeout does not prove TLAST missing: inspect length, stream backpressure, TLAST, clocks/reset and driver status; do not free active buffers.')
                elif kind == 'free':
                    b = buffer_for(e); idle(b)
                    if e['actor'] != b['owner'] or b['borrowers'] or b['views']:
                        raise ValueError('free by non-owner or live borrowers/views')
                    b['freed'] = True
                elif kind == 'process_exit':
                    who = e['actor']
                    if any(not b['freed'] and (b['owner'] == who or who in b['borrowers']) for b in buffers.values()) or any(c['owner'] == who and c['active'] for c in channels.values()):
                        raise ValueError('process exit is not proof of DMA/buffer cleanup')
                    exited.add(who)
                report['events_checked'] += 1
            except (ValueError, TypeError, KeyError) as exc:
                report['errors'].append({'event_index': index, 'message': type(exc).__name__ + ': ' + str(exc)})
                # A malformed/incomplete trace cannot safely reconstruct later state.
                break
    except (ValueError, TypeError, KeyError) as exc:
        report['errors'].append({'event_index': None, 'message': type(exc).__name__ + ': ' + str(exc)})
    report['unreleased_buffers'] = [k for k, b in buffers.items() if not b['freed']]
    report['outstanding_transfers'] = [c['active'] for c in channels.values() if c['active']]
    report['trace_consistent'] = not report['errors']
    report['declared_resources_released'] = bool(buffers) and not report['errors'] and not report['unreleased_buffers'] and not report['outstanding_transfers']
    report['status'] = 'consistent_closed' if report['declared_resources_released'] and not report['faults'] else 'needs_attention'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', required=True)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    if Path(a.output).exists() or Path(a.output).resolve() == Path(a.trace).resolve():
        p.error('output exists or aliases input')
    try:
        trace = load(a.trace)
        result = audit(trace)
        result['input_sha256'] = hashlib.sha256(Path(a.trace).read_bytes()).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        result = {'status': 'invalid_input', 'errors': [str(exc)], 'hardware_accessed': False, 'hardware_cleanup_verified': False}
    with Path(a.output).open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({'status': result['status'], 'hardware_accessed': False}))
    return 0 if result['status'] == 'consistent_closed' else 2


if __name__ == '__main__':
    sys.exit(main())
