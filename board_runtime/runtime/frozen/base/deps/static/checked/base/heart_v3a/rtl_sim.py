"""真实Vivado工具入口；独立目录、子进程环境与严格通过标记。"""
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import subprocess
import uuid

DEFAULT_VIVADO = Path('E:/Xilinx/Vivado/2024.1')


def tool_environment() -> dict[str, str]:
    env = dict(os.environ)
    if 'PROCESSOR_ARCHITECTURE' not in env:
        if platform.machine() != 'AMD64':
            raise ValueError('未核实的Vivado运行架构')
        env['PROCESSOR_ARCHITECTURE'] = 'AMD64'
    return env


def source_hashes(paths):
    return {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in paths}


def run_tool(tool, arguments, directory, vivado_root=DEFAULT_VIVADO, *, timeout=120):
    """保留每次日志；超时只终止本次拥有的进程树。"""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    launcher = Path(vivado_root).resolve() / 'bin' / f'{tool}.bat'
    if not launcher.is_file():
        raise RuntimeError(f'工具不存在：{launcher}')
    arguments = tuple(map(str, arguments))
    if any(re.search(r'[&|<>^%\r\n]', arg) for arg in (str(launcher), *arguments)):
        raise ValueError('工具参数含命令解释字符')
    log = directory / f'{tool}-{uuid.uuid4().hex[:12]}.tool.log'
    command = [str(Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/cmd.exe'),
               '/d', '/c', str(launcher), *arguments]
    try:
        process = subprocess.Popen(command, cwd=directory, env=tool_environment(),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                subprocess.run([str(Path(os.environ.get('SystemRoot', 'C:/Windows')) /
                                    'System32/taskkill.exe'), '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=15)
            output, _ = process.communicate(timeout=15)
            log.write_bytes(output)
            raise RuntimeError(f'{tool}超时；日志：{log}')
    except OSError as exc:
        raise RuntimeError(f'{tool}启动失败：{exc}；目录：{directory}') from exc
    log.write_bytes(output)
    decoded = output.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '')
    if process.returncode != 0 or re.search(r'(?im)^(?:ERROR:|FATAL:|Fatal:|Error:)', decoded):
        raise RuntimeError(f'{tool}失败（{process.returncode}）；日志：{log}\n{decoded[-3500:]}')
    return {'returncode': process.returncode, 'log': str(log), 'stdout': decoded}


def compile_xsim(source_files: tuple[Path, ...], top: str, directory: Path,
                 vivado_root: Path = DEFAULT_VIVADO, *, libraries: tuple[str, ...] = ()) -> dict:
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', top):
        raise ValueError('非法仿真top')
    if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', library) for library in libraries):
        raise ValueError('非法仿真库')
    sources = tuple(Path(path).resolve() for path in source_files)
    if not sources or any(not path.is_file() for path in sources):
        raise ValueError('仿真源码缺失')
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / 'compile.json'
    if manifest.exists():
        raise ValueError('不可覆盖已有仿真构建')
    compiled = run_tool('xvlog', ('--sv', *map(str, sources)), directory, vivado_root)
    library_arguments = tuple(arg for library in libraries for arg in ('-L', library))
    elaborated = run_tool('xelab', (*library_arguments, top, '--snapshot', top), directory, vivado_root)
    result = dict(directory=str(directory), top=top, source_hashes=source_hashes(sources),
                  libraries=list(libraries),
                  compile_returncode=compiled['returncode'], elaboration_returncode=elaborated['returncode'],
                  compile_log=compiled['log'], elaboration_log=elaborated['log'])
    with manifest.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    return result


def simulate_xsim(top: str, directory: Path, plusargs: tuple[str, ...] = (),
                  vivado_root: Path = DEFAULT_VIVADO) -> dict:
    directory = Path(directory).resolve()
    manifest = directory / 'compile.json'
    if not manifest.is_file():
        raise RuntimeError('缺少成功展开记录')
    compiled = json.loads(manifest.read_text(encoding='utf-8'))
    if compiled['top'] != top or source_hashes(compiled['source_hashes']) != compiled['source_hashes']:
        raise RuntimeError('仿真top或源码身份已变化')
    native_log = directory / f'xsim-{uuid.uuid4().hex[:12]}.log'
    arguments = [top, '--R', '--log', str(native_log)]
    for arg in plusargs:
        if '"' in arg:
            raise ValueError('plusarg不可包含引号')
        # Vivado的批处理参数扫描会拆分未加引号的等号。
        arguments += ['--testplusarg', f'"{arg}"']
    try:
        simulated = run_tool('xsim', arguments, directory, vivado_root)
    except RuntimeError as exc:
        raise RuntimeError(f'仿真失败：{exc}') from exc
    matches = re.findall(r'(?m)^(V3A_(?:DIVIDER|CORE_SMOKE|GOLDEN|TIMING_FIXTURE)_PASS) checked=(\d+)'
                         r'(?: max_latency=(\d+))?[^\r\n]*$', simulated['stdout'])
    expected_marker = {'tb_round_div96': 'V3A_DIVIDER_PASS', 'tb_nlms_smoke': 'V3A_CORE_SMOKE_PASS',
                       'tb_nlms_vectors': 'V3A_GOLDEN_PASS',
                       'tb_nlms_timing_fixture': 'V3A_TIMING_FIXTURE_PASS'}.get(top)
    if len(matches) != 1 or (expected_marker and matches[0][0] != expected_marker) or int(matches[0][1]) <= 0:
        raise RuntimeError(f'仿真缺少完整通过标记和有效检查数量；日志：{simulated["log"]}')
    marker, checked, latency = matches[0]
    return {**compiled, 'simulation_returncode': simulated['returncode'],
            'simulation_log': simulated['log'], 'native_log': str(native_log),
            'pass_marker': marker, 'checked': int(checked), 'max_latency_cycles': int(latency or 0),
            'stdout': simulated['stdout']}


def run_xsim(source_files: tuple[Path, ...], top: str, directory: Path,
             plusargs: tuple[str, ...] = (), vivado_root: Path = DEFAULT_VIVADO,
             *, libraries: tuple[str, ...] = ()) -> dict:
    compile_xsim(source_files, top, directory, vivado_root, libraries=libraries)
    return simulate_xsim(top, directory, plusargs, vivado_root)
