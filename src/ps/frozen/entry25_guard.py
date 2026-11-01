"""Standard-library identity checks for the separately installed static pilot."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

MANIFEST = 'entry25-live-manifest.json'
VARIANT = 'effective25_entry6_static_v1'
BASE_SHA = '400883a9049ad8684fbc15102032cfe8dc0a1daaabda8110423f31959ec054b1'
PROBE_SHA = '2c6b9098cf713937d84b1ee3c383746ebfd2eb031dc44b9c63ad08345c99e228'
WINDOW_SHA = '07c77d2c07b760d1ed626bac0e9742ac24cc066db90b29005949c85f83f6d783'
CANDIDATE_SHA = '8781385123c7a97c9273ee7aa69c27eaf2bb0f75655eb23a7f18a1ba323e8c47'
BOARD_SHA = '4eb23826ed23d16fec772eab490cdf35a43ad3e9b2ae642337c05cecb842efca'
BOARD_TEXT_SHA = 'ad7082a598cce2f0e45597ef63397615c538934fe52c4d2bc00bf1fa208defbc'
FLAGS = dict.fromkeys(('live_25hz_passed', 'live_50hz_passed', 'auto_beta_effect_passed',
    'board_ddr_verified', 'limits_frozen', 'run_acceptance_passed', 'v3a_complete'), False)
ENTRY_FILES = ('run_entry25_live.py', 'entry25_guard.py', 'entry25_worker.py',
               'entry25_report.py', 'README_ENTRY25_LIVE.md')
DEPENDENCIES = {'effective25-manifest.json': BASE_SHA,
                'gc-probe-manifest.json': PROBE_SHA, 'gc-window-manifest.json': WINDOW_SHA}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def document(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def local(root, name):
    root = Path(root).resolve()
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
        raise ValueError('包内路径非法')
    path = (root/name).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('包内路径逃逸')
    return path


def validate(root):
    root = Path(root).resolve()
    manifest = document(root/MANIFEST)
    if (manifest.get('schema') != 'entry25_live_bundle_v1'
            or manifest.get('variant') != VARIANT
            or (manifest.get('raw_hz'), manifest.get('processing_hz'),
                manifest.get('entry_confirmation_checks'), manifest.get('duration_seconds')) != (25,25,6,60)
            or manifest.get('candidate_static_pilot_completed') is not False
            or any(manifest.get(key) is not False for key in FLAGS)):
        raise ValueError('候选实采包范围或标志不符')
    files = manifest.get('files', {})
    required = set(ENTRY_FILES) | {'entry25_candidate.py', 'provenance/entry25_board_check.json',
                                  'provenance/entry25_board_check.txt'}
    for name, expected in DEPENDENCIES.items():
        path = root/'base'/name
        if not path.is_file() or sha(path) != expected:
            raise ValueError('冻结基础或GC清单不符：' + name)
        required.add('base/'+name)
        for relative, digest in document(path)['files'].items():
            target = local(root/'base', relative)
            if not target.is_file() or sha(target) != digest:
                raise ValueError('冻结依赖内容不符：' + relative)
            required.add('base/'+relative)
    if set(files) != required:
        raise ValueError('候选包文件集合不符')
    for name, expected in files.items():
        path = local(root, name)
        if not path.is_file() or sha(path) != expected:
            raise ValueError('文件缺失或哈希不符：' + name)
    for path in root.rglob('*.py'):
        if path.relative_to(root).as_posix() not in files:
            raise ValueError('出现清单外Python文件：' + str(path))
    for name, expected in (('entry25_candidate.py', CANDIDATE_SHA),
                           ('provenance/entry25_board_check.json', BOARD_SHA),
                           ('provenance/entry25_board_check.txt', BOARD_TEXT_SHA)):
        if sha(root/name) != expected:
            raise ValueError('候选或板端前置证据不符：' + name)
    proof = document(root/'provenance/entry25_board_check.json')
    if (proof.get('mode') != 'board-native' or proof.get('board_readonly_passed') is not True
            or proof.get('error') is not None):
        raise ValueError('缺少已通过的板端只读前置证据')
    return dict(files, **{MANIFEST: sha(root/MANIFEST)})


def activate(root):
    """Reject mixed frozen modules before modifying search paths; no runtime import."""
    root = Path(root).resolve()
    prefixes = ('effective25', 'heart_v2', 'heart_v3a', 'v3a_rate25', 'v3a_25hz_live',
                'rate25_tools', 'pilot25', 'display25', 'owner25')
    singles = {'peak_chain', 'peak_timing', 'entry25_candidate', 'heart_axi_live',
        'run_effective25_gc_probe', 'run_effective25_gc_window', 'effective25_gc_log',
        'effective25_gc_report', 'effective25_gc_window', 'effective25_gc_window_report'}
    for name, module in tuple(sys.modules.items()):
        if name.split('.')[0] in prefixes or name in singles:
            path = getattr(module, '__file__', None)
            if path is None or not Path(path).resolve().is_relative_to(root):
                raise ValueError('内核串包：'+name+'；请新建Notebook，不运行旧单元')
    for path in (root, root/'base'):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def changed(root, tracked):
    return [name for name, expected in tracked.items()
            if not (Path(root)/name).is_file() or sha(Path(root)/name) != expected]


def identity(root):
    return dict(entry_variant=VARIANT, entry_confirmation_checks=6,
                entry_candidate_sha256=CANDIDATE_SHA, entry_manifest_sha256=sha(Path(root)/MANIFEST))
