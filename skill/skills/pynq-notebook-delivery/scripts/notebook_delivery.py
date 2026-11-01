"""Seal/verify a declared notebook bundle; optionally spawn a trusted pure preflight.

No PYNQ dependency. The import guard is a mistake detector, not a security sandbox.
"""
import argparse
import functools
import hashlib
import importlib
import importlib.abc
import importlib.util
import inspect
import json
import math
import multiprocessing
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
import uuid

SCHEMA = 'pynq-notebook-delivery-v1'
SPEC = 'pynq-notebook-spec-v1'
NOTEBOOK = 'notebook-source-v1'
BLOCKED = {'pynq', 'cv2', 'serial', 'smbus', 'smbus2', 'usb', 'periphery'}
EXECUTABLE = {'.py', '.pyc', '.pyo', '.so', '.pyd', '.dll', '.ipynb', '.bit', '.hwh'}


def object_pairs(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate JSON key: ' + k)
        result[k] = v
    return result


def load(path):
    if Path(path).stat().st_size > 16 * 1024**2:
        raise ValueError('JSON input exceeds 16 MiB')
    def finite_float(token):
        value = float(token)
        if not math.isfinite(value): raise ValueError('nonfinite JSON number')
        return value
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=object_pairs, parse_float=finite_float,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf8')


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024**2), b''):
            h.update(b)
    return h.hexdigest()


def member(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('member must be a local canonical POSIX path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or rel.as_posix() != name or name == '.':
        raise ValueError('noncanonical/escaping member path')
    path = Path(root)
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink member or parent')
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('resolved member escapes package')
    return path


def source_text(source):
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(x, str) for x in source):
        return ''.join(source)
    raise ValueError('Notebook source must be a string or string list')


def notebook_identity(path):
    n = load(path)
    if not isinstance(n, dict) or n.get('nbformat') != 4 or type(n.get('nbformat_minor')) is not int or n['nbformat_minor'] < 0:
        raise ValueError('Notebook v4 with explicit minor version required')
    meta = n['metadata']; kernel = meta['kernelspec']; language = meta['language_info']
    for value in (kernel['name'], kernel['language'], language['name']):
        if not isinstance(value, str) or not value:
            raise ValueError('explicit kernel/language identity required')
    if not isinstance(n['cells'], list):
        raise ValueError('Notebook cells must be a list')
    cells = []
    for cell in n['cells']:
        if cell['cell_type'] not in ('code', 'markdown', 'raw'):
            raise ValueError('unknown cell type')
        tags = cell.get('metadata', {}).get('tags', [])
        attachments = cell.get('attachments', {})
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags) or not isinstance(attachments, dict):
            raise ValueError('invalid tags or attachments')
        cells.append({'cell_type': cell['cell_type'], 'source': source_text(cell['source']),
                      'tags': tags, 'attachments': attachments})
    identity = {'policy': NOTEBOOK, 'nbformat': 4, 'nbformat_minor': n['nbformat_minor'],
                'kernel_name': kernel['name'], 'kernel_language': kernel['language'],
                'language_name': language['name'], 'cells': cells}
    return hashlib.sha256(canonical(identity)).hexdigest()


def digest(path, kind):
    if kind == 'bytes': return sha_file(path)
    if kind == NOTEBOOK: return notebook_identity(path)
    raise ValueError('unknown member identity policy')


def validate_layout(root, doc, manifest_name):
    member(root, manifest_name)
    files, runtime, entry = doc['files'], doc['runtime_dirs'], doc['entry']
    if not isinstance(files, dict) or not files or not isinstance(runtime, list):
        raise ValueError('nonempty files map and runtime_dirs list required')
    for name in runtime:
        runtime_path = member(root, name)
        if runtime_path.exists() and not runtime_path.is_dir():
            raise ValueError('runtime directory name refers to a regular file')
        if len(PurePosixPath(name).parts) != 1 or '.' in name or name.startswith('_'):
            raise ValueError('runtime directories must be top-level plain data names')
    if len(set(runtime)) != len(runtime): raise ValueError('duplicate runtime directory')
    for name in files:
        member(root, name)
        if name == manifest_name or PurePosixPath(name).parts[0] in runtime:
            raise ValueError('source member overlaps manifest/runtime directory')
    if not isinstance(entry, dict) or set(entry) != {'module', 'callable', 'kwargs'}:
        raise ValueError('entry requires module, callable, kwargs')
    if any(not isinstance(entry[k], str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', entry[k]) for k in ('module', 'callable')):
        raise ValueError('entry must name a top-level Python module and callable')
    if not isinstance(entry['kwargs'], dict): raise ValueError('kwargs must be an object')
    if entry['module'] + '.py' not in files: raise ValueError('entry module missing from manifest')
    actual = set()
    for path in Path(root).rglob('*'):
        name = path.relative_to(root).as_posix()
        member(root, name)
        if not path.is_file(): continue
        if name == manifest_name: continue
        if PurePosixPath(name).parts[0] in runtime:
            if path.suffix.lower() in EXECUTABLE:
                raise ValueError('executable artifact in data-only runtime directory: ' + name)
            continue
        actual.add(name)
    if actual != set(files):
        raise ValueError('undeclared/missing files: ' + str(sorted(actual ^ set(files))))


def package_root(root):
    p = Path(root)
    if p.is_symlink() or not p.is_dir(): raise ValueError('root must be an existing nonsymlink directory')
    return p.resolve()


def seal(root, spec_name, manifest_name):
    root = package_root(root)
    dest = member(root, manifest_name)
    if dest.exists(): raise FileExistsError('manifest already exists')
    spec = load(member(root, spec_name))
    if not isinstance(spec, dict) or set(spec) != {'schema', 'files', 'entry', 'runtime_dirs'} or spec['schema'] != SPEC:
        raise ValueError('unsupported delivery specification')
    if spec['files'].get(spec_name) != 'bytes': raise ValueError('spec must itself be a byte-pinned member')
    validate_layout(root, spec, manifest_name)
    doc = dict(spec, schema=SCHEMA, files={name: {'kind': kind, 'sha256': digest(member(root, name), kind)} for name, kind in spec['files'].items()})
    validate_manifest(doc)
    with dest.open('x', encoding='utf8') as f: json.dump(doc, f, ensure_ascii=False, indent=2, allow_nan=False)
    return {'manifest_sha256': sha_file(dest), 'members': len(doc['files']), 'hardware_accessed': False,
            'scope': 'identity creation, not trusted provenance or execution validation'}


def validate_manifest(doc):
    if not isinstance(doc, dict) or set(doc) != {'schema', 'files', 'entry', 'runtime_dirs'} or doc['schema'] != SCHEMA:
        raise ValueError('unsupported delivery manifest')
    for name, row in doc['files'].items():
        if not isinstance(row, dict) or set(row) != {'kind', 'sha256'} or row['kind'] not in ('bytes', NOTEBOOK):
            raise ValueError('invalid member identity fields')
        if not isinstance(row['sha256'], str) or re.fullmatch('[0-9a-f]{64}', row['sha256']) is None:
            raise ValueError('expected lowercase SHA256')
        if name.endswith('.py') and row['kind'] != 'bytes': raise ValueError('Python source must use byte identity')


def verify(root, manifest_name, expected_sha256=None):
    root = package_root(root)
    path = member(root, manifest_name)
    actual_sha = sha_file(path)
    if expected_sha256 is not None and actual_sha != expected_sha256:
        raise ValueError('manifest SHA256 differs')
    doc = load(path); validate_manifest(doc); validate_layout(root, doc, manifest_name)
    for name, row in doc['files'].items():
        if digest(member(root, name), row['kind']) != row['sha256']:
            raise ValueError('member identity differs: ' + name)
    return doc, {'manifest_sha256': actual_sha, 'members': len(doc['files']), 'integrity_verified': True,
                 'manifest_pin_matched': expected_sha256 is not None, 'provenance_verified': False,
                 'hardware_accessed': False, 'scope': 'declared source identity; no payload imported'}


class NoHardwareImports(importlib.abc.MetaPathFinder):
    def __init__(self): self.attempts = []
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in BLOCKED:
            self.attempts.append(fullname)
            raise ImportError('hardware-facing import blocked in pure preflight: ' + fullname)
        return None


def verified_worker(connection, *, root, manifest_name, expected_sha256, run_id):
    """Top-level pickleable target; bound keyword arguments use functools.partial."""
    sys.dont_write_bytecode = True
    phase = 'identity'; guard = NoHardwareImports(); started = time.perf_counter_ns()
    stages = []; result = {'run_id': run_id, 'ok': False, 'tool_hardware_operations': False,
                           'payload_hardware_access': 'not_independently_verified'}
    try:
        doc, check = verify(root, manifest_name, expected_sha256)
        stages.append({'phase': 'identity', 'elapsed_ns': time.perf_counter_ns()-started})
        present = sorted(name for name in sys.modules if name.split('.')[0] in BLOCKED)
        if present: raise RuntimeError('unexpected hardware modules present before payload: ' + str(present))
        result['hardware_modules_before_payload'] = present
        phase = 'import'; sys.meta_path.insert(0, guard)
        root = str(Path(root).resolve()); sys.path.insert(0, root)
        entry = doc['entry']
        local_names = {PurePosixPath(name).parts[0].removesuffix('.py') for name in doc['files'] if name.endswith('.py')}
        collisions = sorted(local_names & sys.modules.keys())
        if collisions: raise ValueError('declared local modules collide with bootstrap modules: ' + str(collisions))
        os.chdir(root)
        mod = importlib.import_module(entry['module'])
        if Path(mod.__file__).resolve() != Path(root)/(entry['module']+'.py'):
            raise ValueError('entry loaded outside package')
        if getattr(mod, 'PURE_PREFLIGHT', None) is not True:
            raise ValueError('entry must declare PURE_PREFLIGHT = True; caller must review this claim')
        stages.append({'phase': phase, 'elapsed_ns': time.perf_counter_ns()-started})
        phase = 'bind'; function = getattr(mod, entry['callable'])
        inspect.signature(function).bind(**entry['kwargs'])
        stages.append({'phase': phase, 'elapsed_ns': time.perf_counter_ns()-started})
        phase = 'call'; returned = function(**entry['kwargs'])
        canonical(returned)
        if len(canonical(returned)) > 32768: raise ValueError('preflight result exceeds 32 KiB')
        if guard.attempts: raise RuntimeError('hardware import was attempted, even if payload caught the error')
        stages.append({'phase': phase, 'elapsed_ns': time.perf_counter_ns()-started})
        phase = 'reverify'; verify(root, manifest_name, expected_sha256)
        result.update(ok=True, result=returned, integrity_verified_in_child=True)
    except BaseException as exc:
        result['error'] = {'phase': phase, 'type': type(exc).__name__, 'message': str(exc)[:2000]}
    finally:
        result['blocked_imports'] = guard.attempts[:32]; result['stages'] = stages
        try: connection.send_bytes(canonical(result))
        finally: connection.close()


def spawn_preflight(root, manifest_name, expected_sha256, timeout_seconds=10):
    if not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError('timeout must be finite and positive')
    _, checked = verify(root, manifest_name, expected_sha256)
    run_id = uuid.uuid4().hex
    ctx = multiprocessing.get_context('spawn'); recv, send = ctx.Pipe(duplex=False)
    worker = functools.partial(verified_worker, root=str(Path(root).resolve()), manifest_name=manifest_name,
                               expected_sha256=checked['manifest_sha256'], run_id=run_id)
    process = ctx.Process(target=worker, args=(send,))
    report = {'run_id': run_id, 'identity': checked, 'child': None, 'error': None,
              'forced_termination': False, 'natural_exit': False, 'tool_hardware_operations': False,
              'payload_hardware_access': 'not_independently_verified', 'scope': 'trusted pure preflight only, not a hardware runner'}
    try:
        process.start(); report['pid'] = process.pid; send.close()
        deadline = time.monotonic()+timeout_seconds
        if recv.poll(max(0, deadline-time.monotonic())):
            try:
                child = json.loads(recv.recv_bytes(65536))
                if child['run_id'] != run_id: raise ValueError('child response run_id differs')
                report['child'] = child
            except (EOFError, OSError, ValueError, KeyError) as exc:
                report['error'] = {'phase': 'receipt', 'type': type(exc).__name__, 'message': str(exc)}
        else:
            report['error'] = {'phase': 'wait', 'type': 'TimeoutError', 'message': 'pure preflight exceeded own deadline'}
        process.join(max(0, deadline-time.monotonic()))
    except BaseException as exc:
        report['error'] = {'phase': 'parent', 'type': type(exc).__name__, 'message': str(exc)[:2000]}
    finally:
        send.close(); recv.close()
        # This is only our explicitly executed pure-software child, never a board owner.
        if process.pid is not None and process.is_alive():
            if report['error'] is None:
                report['error'] = {'phase': 'exit', 'type': 'TimeoutError', 'message': 'child replied but did not exit within the preflight deadline'}
            report['forced_termination'] = True; process.terminate(); process.join(2)
            if process.is_alive(): process.kill(); process.join(2)
        report['exitcode'] = process.exitcode
        report['natural_exit'] = process.pid is not None and process.exitcode == 0 and not report['forced_termination']
        report['process_closed'] = not process.is_alive()
        if report['process_closed']: process.close()
    report['passed'] = bool(not report['error'] and report['child'] and report['child']['ok'] and report['natural_exit'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('seal', 'verify', 'spawn'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', default='delivery-manifest.json')
    parser.add_argument('--spec', default='delivery-spec.json')
    parser.add_argument('--expected-manifest-sha256')
    parser.add_argument('--execute-trusted-pure-preflight', action='store_true')
    parser.add_argument('--timeout-seconds', type=float, default=10)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve(); root = Path(args.root).resolve()
    if output.exists() or output.is_relative_to(root): parser.error('use a new report outside source bundle')
    try:
        if args.mode == 'seal':
            report = seal(root, args.spec, args.manifest); report['passed'] = True
        elif args.mode == 'verify':
            _, report = verify(root, args.manifest, args.expected_manifest_sha256); report['passed'] = True
        else:
            if not args.execute_trusted_pure_preflight or args.expected_manifest_sha256 is None:
                raise ValueError('spawn needs reviewed pure code, explicit execution flag and expected manifest SHA256')
            report = spawn_preflight(root, args.manifest, args.expected_manifest_sha256, args.timeout_seconds)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        report = {'passed': False, 'error': {'type': type(exc).__name__, 'message': str(exc)}, 'tool_hardware_operations': False}
    with output.open('x', encoding='utf8') as f: json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'passed': report['passed'], 'mode': args.mode}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    multiprocessing.freeze_support()
    raise SystemExit(main())
