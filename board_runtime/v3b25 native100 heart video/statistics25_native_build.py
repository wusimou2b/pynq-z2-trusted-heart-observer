"""Build only with existing compiler and headers, into a new owned directory."""
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig

MODULE='_v3b25_statistics_dot'
COMPILER=Path('/usr/bin/arm-linux-gnueabihf-gcc-11')
COMPILER_SHA='cd46fd90d695d44919374848e89e89630807e1171d491a91dcdc6156a051d9d0'


def identity(path):
    path=Path(path).resolve(strict=True)
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def build(source,output):
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    report=dict(complete=False,error=None,output=str(output),commands=[],source=identity(source),
                soabi=sysconfig.get_config_var('SOABI'),python=sys.version,machine=platform.machine())
    binary=output/(MODULE+sysconfig.get_config_var('EXT_SUFFIX'))
    try:
        import numpy as np
        include=Path(sysconfig.get_paths()['include']);numpy_include=Path(np.get_include()).resolve(strict=True)
        report['numpy']=dict(version=np.__version__,include=str(numpy_include))
        headers=[include/'Python.h',Path(sysconfig.get_config_h_filename()),*sorted(numpy_include.rglob('*.h'))]
        if not (numpy_include/'numpy/arrayobject.h').is_file():raise RuntimeError('NumPy headers missing; no install')
        report['headers']=[identity(path) for path in headers]
        if sys.platform=='win32':
            vc=Path('C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.41.34120')
            sdk=Path('C:/Program Files (x86)/Windows Kits/10');version='10.0.22621.0'
            cl=vc/'bin/Hostx64/x64/cl.exe';link=vc/'bin/Hostx64/x64/link.exe'
            includes=[include,vc/'include',*[sdk/'Include'/version/name for name in ('ucrt','shared','um')]]
            libs=[Path(sys.base_prefix)/'libs',vc/'lib/x64',sdk/'Lib'/version/'ucrt/x64',sdk/'Lib'/version/'um/x64']
            if not all(path.exists() for path in [cl,link,*includes,*libs]):raise RuntimeError('existing compiler/header missing')
            obj=output/'statistics25_native.obj';tools=[cl,link]
            commands=[[str(cl),'/nologo','/c','/O2','/fp:strict','/MD','/W4','/WX',
                '/external:I'+str(include),'/external:I'+str(numpy_include),'/external:W0',
                *('/I'+str(path) for path in includes[1:]),'/Fo'+str(obj),str(source)],
                [str(link),'/NOLOGO','/DLL','/OUT:'+str(binary),*('/LIBPATH:'+str(path) for path in libs),str(obj)]]
        else:
            if sys.platform!='linux' or platform.machine()!='armv7l' or sys.byteorder!='little':
                raise RuntimeError('only existing Windows or ARMv7 build supported')
            if identity(COMPILER)['sha256']!=COMPILER_SHA:raise RuntimeError('verified ARM compiler identity differs')
            tools=[COMPILER]
            commands=[[str(COMPILER),'--version'],[str(COMPILER),'-std=c11','-shared','-fPIC','-O2',
                '-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror',
                '-isystem',str(include),'-isystem',str(numpy_include),str(source),'-o',str(binary)]]
        report['tools']=[identity(path) for path in tools]
        for index,command in enumerate(commands):
            item=dict(argv=command,returncode=None,error=None);report['commands'].append(item)
            try:
                result=subprocess.run(command,cwd=output,stdin=subprocess.DEVNULL,capture_output=True,
                                      text=True,errors='replace',timeout=60,shell=False)
                item['returncode']=result.returncode;log=result.stdout+result.stderr
            except BaseException as exc:
                item['error']=str(exc);log=repr(exc)
                for stream in (getattr(exc,'stdout',None),getattr(exc,'stderr',None)):
                    if stream:log+='\n'+(stream.decode(errors='replace') if isinstance(stream,bytes) else stream)
            with (output/('command-'+str(index)+'.log')).open('x',encoding='utf-8') as f:f.write(log)
            if item['error'] or item['returncode']!=0:raise RuntimeError('compiler failed; log preserved')
        report['binary']=identity(binary)
        if identity(source)!=report['source']:raise RuntimeError('C source changed')
        report['complete']=True
    except BaseException as exc:
        report['error']=dict(type=type(exc).__name__,message=str(exc))
    with (output/'build.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    return report
