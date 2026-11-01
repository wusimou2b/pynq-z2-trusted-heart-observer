"""Private ARM compiler/RAM qualification. No MMIO mapping or hardware reads.

RAM timing is deliberately not accepted as physical communication evidence.
The exact resulting library/assembly/source identity accompanies the release.
"""
import ctypes as C
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

if __package__:
    from .main_heart_readback import SnapshotLibrary,ADDRESSES,DecodedResult
else:
    from main_heart_readback import SnapshotLibrary,ADDRESSES,DecodedResult

SOURCE='main_heart_readback.c'
OUTPUT='main_native_build'
BINARY='libmain_heart_readback.so'
ASSEMBLY='main_heart_readback.s'
REPORT='main-native-build.json'
PUBLIC_ORIGINAL_BUILDER_SHA256='95ec2b6498e1ea6308fd6da63e01d33c61d443ec1b23e057c2d29bf6185211e2'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def elf(path):
    with Path(path).open('rb') as stream:header=stream.read(20)
    if len(header)!=20 or header[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(header[18:20],'little')!=40:
        raise ValueError('main transport requires ARM32 little-endian ELF')


def check_assembly(text):
    if text.count('hm_read_snapshot:')!=1:raise ValueError('main snapshot assembly function missing')
    section=text.split('hm_read_snapshot:',1)[1].split('.size',1)[0]
    if (not all(x in section for x in ('dmb sy','dsb sy')) or not re.search(r'\bldr\b',section)
        or re.search(r'\b(memcpy|memmove|vld[1-4]|vst[1-4])\b',section)):
        raise ValueError('main scalar MMIO assembly/barrier gate failed')
    return dict(scalar_barriers_verified=True,vector_copy_used=False)


def ram_transaction_case():
    """Ordinary allocation, deliberately no device mapping or fake ACK."""
    memory=(C.c_uint32*16384)();identity=(C.c_uint32*22)();identity[10]=1;identity[11]=1
    packed=(C.c_uint32*174)();packed[:22]=identity[:];packed[32]=3
    for branch in range(4):
        p=54+30*branch;packed[p+10]=5;packed[p+24]=1;packed[p+23]=0x4052c000
        for j in range(5):packed[p+12+2*j]=0x9999999a;packed[p+13+2*j]=0x3fe99999
    for address,value in zip(ADDRESSES,packed):memory[address//4]=value
    memory[1]=0x20001;memory[3]=114;memory[6]=1;memory[7]=2
    return memory,identity,DecodedResult(),C.c_uint32()


def memory_test(library):
    library.check_clock()
    mapped=(C.c_uint32*16384)(*(i*73+9 for i in range(16384)));before=bytes(mapped)
    output=(C.c_uint32*174)();done=C.c_uint32()
    rc=library.lib.hm_read_snapshot(mapped,16384,output,174,time.monotonic()+1.,C.byref(done))
    if rc or done.value!=174 or list(output)!=[mapped[a//4] for a in ADDRESSES] or bytes(mapped)!=before:
        raise ValueError('main native RAM bit/extent/no-write check failed')
    output[:]=[0x87654321]*174
    rc=library.lib.hm_read_snapshot(mapped,16384,output,174,time.monotonic()-1.,C.byref(done))
    if rc!=1 or done.value or list(output)!=[0x87654321]*174:
        raise ValueError('main expired native copy not refused')
    # A nonphysical same-pointer overlap must be refused before any read.
    rc=library.lib.hm_read_snapshot(mapped,16384,mapped,174,time.monotonic()+1.,C.byref(done))
    if rc!=2 or bytes(mapped)!=before:raise ValueError('main aliased native copy not refused')
    packed=(C.c_uint32*174)();identity=(C.c_uint32*22)();decoded=DecodedResult();packed[32]=3
    for branch in range(4):
        p=54+30*branch;packed[p+10]=5;packed[p+24]=1;packed[p+23]=0x4052c000
        for j in range(5):packed[p+12+2*j]=0x9999999a;packed[p+13+2*j]=0x3fe99999
    rc=library.lib.hm_decode_snapshot(packed,174,identity,22,1,C.byref(decoded),480)
    if (rc or decoded.status!=3 or any(b.count!=5 or b.bpm!=75. or list(b.ibis)!=[.8]*5 for b in decoded.branches)):
        raise ValueError('ARM native format decoding differs')
    memory,identity,decoded,phase=ram_transaction_case()
    code=library.lib.hm_transact_sample(memory,16384,identity,22,1,C.byref(decoded),480,time.monotonic()+.020,C.byref(phase))
    # New production C must refuse the already-DONE static RAM before writes.
    # RAM cannot emulate hardware ACK. The earlier qualification expected an
    # unconsumed ACK; that path is now intentionally blocked by the idle guard.
    if code!=7 or phase.value!=0 or memory[2]!=0:
        raise ValueError('native stale-DONE RAM not refused before writes')
    memory[3]=64
    code=library.lib.hm_transact_sample(memory,16384,identity,22,1,C.byref(decoded),480,time.monotonic()+.020,C.byref(phase))
    if code!=5 or phase.value!=3 or memory[2]!=2:
        raise ValueError('native RAM without controller published a result')
    return dict(passed=True,words_verified=174,expired_refused=True,alias_refused=True,
        native_decode_verified=True,stale_done_refused_before_writes=True,missing_controller_refused=True,hardware_accessed=False,physical_communication_budget_passed=False)


def verify_build(root, *, release_contract=None):
    root=Path(root).resolve();path=root/REPORT;binary=root/OUTPUT/BINARY;assembly=root/OUTPUT/ASSEMBLY
    expected_builder=sha(__file__)
    if release_contract is not None:
        from public_live_contract import verified_asset
        verified_asset(release_contract,'native_readback_binary',binary)
        expected_builder=PUBLIC_ORIGINAL_BUILDER_SHA256
    for p in (path,root/SOURCE,root/OUTPUT,binary,assembly):
        if p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):raise ValueError('main build escaped')
    doc=json.loads(path.read_bytes())
    expected=dict(passed=True,words_verified=174,expired_refused=True,alias_refused=True,
        native_decode_verified=True,stale_done_refused_before_writes=True,missing_controller_refused=True,hardware_accessed=False,physical_communication_budget_passed=False)
    if (doc.get('schema')!='main_heart_native_snapshot_build_v1' or doc.get('complete') is not True
        or doc.get('source_sha256')!=sha(root/SOURCE) or doc.get('builder_sha256')!=expected_builder
        or doc.get('adapter_sha256')!=sha(root/'main_heart_readback.py')
        or doc.get('binary_sha256')!=sha(binary) or doc.get('assembly_sha256')!=sha(assembly)
        or doc.get('memory_test')!=expected or doc.get('hardware_accessed') is not False):
        raise ValueError('main native source/binary/RAM identity differs')
    elf(binary);check_assembly(assembly.read_text('utf-8'));return doc


def load_verified(root, *, release_contract=None):
    verify_build(root,release_contract=release_contract)
    library=SnapshotLibrary(C.CDLL(str((Path(root)/OUTPUT/BINARY).resolve())),require_arm=True)
    library.check_clock();return library


def build_native(root):
    if (sys.platform!='linux' or platform.machine()!='armv7l' or sys.byteorder!='little' or C.sizeof(C.c_void_p)!=4):
        raise RuntimeError('main native build only on little-endian ARM32; no installation')
    root=Path(root).resolve()
    if (root/REPORT).exists() or (root/OUTPUT).exists():raise FileExistsError('main build attempted; no overwrite/retry')
    sources={SOURCE:sha(root/SOURCE),'main_heart_readback.py':sha(root/'main_heart_readback.py')}
    output=root/OUTPUT;output.mkdir(exist_ok=False)
    report=dict(schema='main_heart_native_snapshot_build_v1',complete=False,hardware_accessed=False,
        source_sha256=sources[SOURCE],adapter_sha256=sources['main_heart_readback.py'],builder_sha256=sha(__file__),
        commands=[],error=None,physical_communication_budget_passed=False)
    try:
        compiler=shutil.which('arm-linux-gnueabihf-gcc-11') or shutil.which('gcc')
        if not compiler:raise RuntimeError('existing ARM compiler missing; not installing')
        compiler=str(Path(compiler).resolve(strict=True));report['compiler_sha256']=sha(compiler)
        common=[compiler,'-std=c11','-O2','-fPIC','-march=armv7-a','-marm','-mfpu=vfpv3-d16','-mfloat-abi=hard',
            '-DHMAIN_ARM_MMIO=1','-fno-tree-vectorize','-fno-tree-slp-vectorize','-fno-builtin',
            '-Wall','-Wextra','-Werror',str(root/SOURCE)]
        commands=[[compiler,'--version'],common+['-S','-o',str(output/ASSEMBLY)],common+['-shared','-o',str(output/BINARY)]]
        for i,command in enumerate(commands):
            report['commands'].append(command)
            run=subprocess.run(command,cwd=output,capture_output=True,text=True,timeout=60)
            with (output/f'compile-{i}.txt').open('x',encoding='utf-8') as stream:stream.write(run.stdout+run.stderr)
            if run.returncode:raise RuntimeError('main ARM compilation failed; preserve logs')
        report.update(check_assembly((output/ASSEMBLY).read_text('utf-8')));elf(output/BINARY)
        library=SnapshotLibrary(C.CDLL(str(output/BINARY)),require_arm=True)
        report.update(memory_test=memory_test(library),binary_sha256=sha(output/BINARY),assembly_sha256=sha(output/ASSEMBLY))
        if sources!={name:sha(root/name) for name in sources} or sha(__file__)!=report['builder_sha256']:
            raise ValueError('main native build inputs changed')
        report['complete']=True
    except BaseException as exc:report['error']=dict(type=type(exc).__name__,message=str(exc))
    with (root/REPORT).open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2,allow_nan=False)
    if not report['complete']:raise RuntimeError('main native build failed; preserve '+REPORT)
    verify_build(root);return report
