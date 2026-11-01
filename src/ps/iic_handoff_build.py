"""Manual, private existing-compiler build; no MMIO, Overlay or installation."""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from .iic_handoff_guard import verify_package, MANIFEST, sha, write_new
    from .iic_handoff import HandoffLibrary, HANDOFF_ABI
    from .joint_iic_native import ABI
    from .joint_iic_native_build import _check_elf
    from .joint_owner import require_board
else:
    from iic_handoff_guard import verify_package, MANIFEST, sha, write_new
    from iic_handoff import HandoffLibrary, HANDOFF_ABI
    from joint_iic_native import ABI
    from joint_iic_native_build import _check_elf
    from joint_owner import require_board

SOURCES = ('joint_iic_native.c', 'joint_iic_native_selftest.c', 'iic_handoff.c',
           'iic_handoff_impl.h', 'iic_handoff_selftest.c')
SELFTEST = dict(schema='iic_handoff_memory_selftest_v1', passed=22, total=22, hardware_accessed=False)


def validate_selftest(output, returncode):
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    original = dict(schema='native_iic_memory_selftest_v1', passed=10, total=10, hardware_accessed=False)
    if returncode or rows != [original, SELFTEST]: raise ValueError('complete and original memory selftests failed')
    return rows[1]


def verify_build(root):
    root = Path(root); verify_package(root)
    record, directory = root / 'handoff-build.json', root / 'handoff_build'
    library = directory / 'libiic_handoff.so'
    if any(p.is_symlink() for p in (record, directory, library)): raise ValueError('handoff build symlink forbidden')
    doc = json.loads(record.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_iic_handoff_build_v1' or doc.get('build_complete') is not True
        or doc.get('abi') != ABI or doc.get('handoff_abi') != HANDOFF_ABI
        or doc.get('hardware_accessed') is not False or doc.get('selftest') != SELFTEST
        or doc.get('package_manifest_sha256') != sha(root / MANIFEST)
        or doc.get('source_hashes') != {n:sha(root / n) for n in SOURCES}
        or doc.get('library_sha256') != sha(library)):
        raise ValueError('handoff build identity/selftest mismatch')
    _check_elf(library)
    return doc


def load_verified(root):
    root = Path(root); doc = verify_build(root)
    lib = ctypes.CDLL(str((root / 'handoff_build/libiic_handoff.so').resolve()))
    if hasattr(lib, 'ji_test_init'): raise ValueError('callback-enabled library forbidden in production')
    return HandoffLibrary(lib, identity=dict(build_record_sha256=sha(root / 'handoff-build.json'),
        library_sha256=doc['library_sha256'], source_hashes=doc['source_hashes'], abi=ABI,
        handoff_abi=HANDOFF_ABI, memory_selftest=doc['selftest']))


def build_native(root, *, confirmation=None):
    if confirmation != 'BUILD-IIC-HANDOFF': raise ValueError('explicit BUILD-IIC-HANDOFF required')
    require_board()
    if ctypes.sizeof(ctypes.c_void_p) != 4 or sys.byteorder != 'little': raise RuntimeError('requires little-endian ARM32 Python')
    root = Path(root).resolve(); verify_package(root)
    if any((root / n).exists() for n in ('handoff-build-attempt.json', 'handoff-build.json', 'handoff_build')):
        raise FileExistsError('build already attempted; preserve, no retry/overwrite')
    write_new(root / 'handoff-build-attempt.json', dict(schema='iic_handoff_build_attempt_v1', hardware_accessed=False))
    output = root / 'handoff_build'; output.mkdir()
    result = dict(schema='v3b25_iic_handoff_build_v1', build_complete=False, hardware_accessed=False,
        package_manifest_sha256=sha(root / MANIFEST), source_hashes={n:sha(root / n) for n in SOURCES}, commands=[], fault=None)
    try:
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler: raise RuntimeError('existing C compiler missing; no installation')
        compiler = str(Path(compiler).resolve(strict=True)); result['compiler'] = compiler
        version = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=10, check=True)
        result.update(compiler_version=version.stdout[:8192], compiler_sha256=sha(compiler))
        common = [compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror']
        commands = [common + ['-fPIC', '-shared', str(root / 'iic_handoff.c'), '-o', str(output / 'libiic_handoff.so')],
                    common + [str(root / 'iic_handoff_selftest.c'), '-o', str(output / 'memory_selftest')]]
        for i, command in enumerate(commands):
            result['commands'].append(command)
            run = subprocess.run(command, cwd=output, capture_output=True, text=True, timeout=60)
            with (output / f'compile-{i}.txt').open('x', encoding='utf-8') as stream: stream.write(run.stdout + run.stderr)
            if run.returncode: raise RuntimeError('compiler failed; preserve compile log')
        _check_elf(output / 'libiic_handoff.so')
        run = subprocess.run([str(output / 'memory_selftest')], capture_output=True, text=True, timeout=10)
        with (output / 'memory-selftest.txt').open('x', encoding='utf-8') as stream: stream.write(run.stdout + run.stderr)
        checked = validate_selftest(run.stdout, run.returncode)
        lib = ctypes.CDLL(str(output / 'libiic_handoff.so'))
        if hasattr(lib, 'ji_test_init'): raise ValueError('test callbacks forbidden in production')
        HandoffLibrary(lib, identity={})
        result.update(abi=lib.ji_abi(), handoff_abi=lib.jih_abi(), context_bytes=lib.ji_size(), selftest=checked,
            library_sha256=sha(output / 'libiic_handoff.so'), build_complete=True)
    except BaseException as exc: result['fault'] = dict(type=type(exc).__name__, message=str(exc))
    write_new(root / 'handoff-build.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--confirm', required=True)
    args = parser.parse_args()
    sys.exit(0 if build_native(Path(__file__).resolve().parent, confirmation=args.confirm)['build_complete'] else 1)
