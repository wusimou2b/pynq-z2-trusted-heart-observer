"""Manual project-private build. Existing compiler only; absolutely no hardware."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
if __package__:
    from .joint_owner import require_board
    from .joint_iic_native import NativeLibrary,ABI
    from .joint_iic_guard import sha,write_new
else:
    from joint_owner import require_board
    from joint_iic_native import NativeLibrary,ABI
    from joint_iic_guard import sha,write_new

SOURCES=('joint_iic_native.c','joint_iic_native_selftest.c')


def _check_elf(path):
    with Path(path).open('rb') as stream:header=stream.read(20)
    if len(header)!=20 or header[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(header[18:20],'little')!=40:
        raise ValueError('native library must be little-endian ELF32 ARM')


def verify_build(root):
    if __package__:
        from .joint_iic_native_guard import verify_native,MANIFEST
    else:
        from joint_iic_native_guard import verify_native,MANIFEST
    root=Path(root);verify_native(root)
    record=root/'native-build.json';library=root/'native_build/libjoint_iic_native.so'
    if record.is_symlink() or (root/'native_build').is_symlink() or library.is_symlink():
        raise ValueError('native build symlink forbidden')
    doc=json.loads(record.read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_native_iic_build_v1' or doc.get('build_complete') is not True or
        doc.get('abi')!=ABI or doc.get('package_manifest_sha256')!=sha(root/MANIFEST) or
        doc.get('source_hashes')!={name:sha(root/name) for name in SOURCES} or
        doc.get('library_sha256')!=sha(library) or doc.get('hardware_accessed') is not False or
        doc.get('selftest',{}).get('passed')!=10 or doc.get('selftest',{}).get('total')!=10):
        raise ValueError('native build identity/selftest mismatch')
    _check_elf(library)
    return doc


def load_verified(root):
    root=Path(root);doc=verify_build(root)
    lib=ctypes.CDLL(str((root/'native_build/libjoint_iic_native.so').resolve()))
    if hasattr(lib,'ji_test_init'):raise ValueError('callback-enabled test library forbidden in production')
    return NativeLibrary(lib,identity=dict(build_record_sha256=sha(root/'native-build.json'),
        library_sha256=doc['library_sha256'],source_hashes=doc['source_hashes'],abi=ABI,
        memory_selftest=doc['selftest']))


def build_native(root,*,confirmation=None):
    if confirmation!='BUILD-IIC-NATIVE':raise ValueError('explicit BUILD-IIC-NATIVE confirmation required')
    require_board()
    if ctypes.sizeof(ctypes.c_void_p)!=4 or sys.byteorder!='little':raise RuntimeError('requires little-endian ARM32 Python')
    if __package__:
        from .joint_iic_native_guard import verify_native,MANIFEST
    else:
        from joint_iic_native_guard import verify_native,MANIFEST
    root=Path(root).resolve();verify_native(root)
    if any((root/name).exists() for name in ('native-build-attempt.json','native-build.json','native_build')):
        raise FileExistsError('native build already attempted; preserve files, no retry/overwrite')
    write_new(root/'native-build-attempt.json',dict(schema='native_iic_build_attempt_v1',hardware_accessed=False))
    output=root/'native_build';output.mkdir()
    result=dict(schema='v3b25_native_iic_build_v1',build_complete=False,hardware_accessed=False,
        package_manifest_sha256=sha(root/MANIFEST),source_hashes={name:sha(root/name) for name in SOURCES},
        compiler=None,commands=[],fault=None)
    try:
        compiler=shutil.which('cc') or shutil.which('gcc')
        if not compiler:raise RuntimeError('existing C compiler missing; not installing anything')
        compiler=str(Path(compiler).resolve(strict=True));result['compiler']=compiler
        version=subprocess.run([compiler,'--version'],capture_output=True,text=True,timeout=10,check=True)
        result['compiler_version']=version.stdout[:8192];result['compiler_sha256']=sha(compiler)
        common=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror']
        commands=[common+['-fPIC','-shared',str(root/SOURCES[0]),'-o',str(output/'libjoint_iic_native.so')],
                  common+[str(root/SOURCES[1]),'-o',str(output/'memory_selftest')]]
        for index,command in enumerate(commands):
            result['commands'].append(command)
            run=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=60)
            with (output/f'compile-{index}.txt').open('x',encoding='utf-8') as stream:
                stream.write(run.stdout+run.stderr)
            if run.returncode:raise RuntimeError(f'compiler failed ({run.returncode}); preserve compile-{index}.txt')
        _check_elf(output/'libjoint_iic_native.so')
        check=subprocess.run([str(output/'memory_selftest')],capture_output=True,text=True,timeout=10)
        with (output/'memory-selftest.txt').open('x',encoding='utf-8') as stream:stream.write(check.stdout+check.stderr)
        data=json.loads(check.stdout)
        if check.returncode or data!=dict(schema='native_iic_memory_selftest_v1',passed=10,total=10,hardware_accessed=False):
            raise RuntimeError('memory-only C selftest failed')
        lib=ctypes.CDLL(str(output/'libjoint_iic_native.so'))
        if hasattr(lib,'ji_test_init'):raise ValueError('test hooks present in production shared library')
        library=NativeLibrary(lib,identity={})
        result.update(abi=lib.ji_abi(),context_bytes=lib.ji_size(),selftest=data,
                      library_sha256=sha(output/'libjoint_iic_native.so'),build_complete=True)
        del library
    except BaseException as exc:
        result['fault']=dict(type=type(exc).__name__,message=str(exc))
    write_new(root/'native-build.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--confirm',required=True)
    args=parser.parse_args(argv);result=build_native(Path(__file__).resolve().parent,confirmation=args.confirm)
    return 0 if result['build_complete'] else 1


if __name__=='__main__':sys.exit(main())
