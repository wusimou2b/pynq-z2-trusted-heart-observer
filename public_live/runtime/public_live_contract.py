"""Standard-library identity and path contract for the explicit public LIVE copy.

This verifies release bytes, not a publisher, numerical qualification, or hardware.
The caller supplies the expected manifest digest. No historical directory search,
private input proof, native import, or device access occurs here.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import sys
from zipfile import ZipFile

MANIFEST = 'public-live-manifest.json'
CHECKSUM_ANCHOR = 'public-live-manifest.sha256'
SCHEMA = 'trusted_heart_public_live_release_v1'
CONTRACT_SCHEMA = 'trusted_heart_public_live_contract_v1'
NOTEBOOK_SOURCE = 'notebook-source-v1'
FIXED_ASSET_SHA256 = {
    'bit': '0a91f3f16740edb5fb7f947945fa5c965b83efd298df9e00250c9934087a8f7c',
    'hwh': 'b652e060e8954e480ca03be4f90c239a83b0b131e6503fccf504d64d000a626a',
    'native_binary': '4dc17698315564f4d2ac50b5e3d1607fecfe12f2520dafa9f4aaa40ff4e50c78',
    'native_source': 'a3758e091fbb66ab5fd9817c847dee44a294c34a07bd56ac04e2a42621ee0b59',
    'main_native_binary': '61ccbec43c8f7b610ea2ec08d6b4ac139db2000b006a91c4e0ae6c9cfd128840',
    'native_readback_binary': '48667f6655746ebe490a8bb1c5baaa9c61e148031ebac451e8f3fc9cc49fde85',
    'sample_entry_binary': 'd3d51ac5a9a6f9f83703f8e32fb693cbfa1bbf4e8f2f64f0bdd59b7c1f963dac',
    'schedule_binary': 'f0bacc84eddeaeb7c520d90c3ec74d693a918ecaa064899420267f92bd4a5d88',
}
REQUIRED_ASSETS = frozenset(FIXED_ASSET_SHA256) | {'arm_sos'}
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_CODE_SUFFIXES = frozenset(('.py', '.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib',
    '.exe', '.o', '.a', '.bin', '.bit', '.hwh', '.ipynb', '.js', '.mjs', '.cjs',
    '.ts', '.tsx', '.jsx', '.sh', '.bash', '.ps1', '.bat', '.cmd', '.c', '.h',
    '.cc', '.cpp', '.hpp', '.tcl', '.v', '.sv', '.vhd', '.vhdl', '.xdc', '.mem', '.s'))
_BINARY_SUFFIXES = frozenset(('.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib',
    '.exe', '.o', '.a', '.bin', '.bit', '.hwh'))


def _digest(value):
    if not isinstance(value, str) or _HEX.fullmatch(value) is None:
        raise ValueError('expected SHA256 must be 64 lowercase hexadecimal characters')
    return value


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or name != PurePosixPath(name).as_posix() or name.startswith('/')
            or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('release paths must be canonical relative POSIX paths')
    return name


def _local(root, name):
    name = _relative(name)
    path = root
    for part in name.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError('release member or parent is a symlink: ' + name)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('release member is not a contained regular file: ' + name)
    return resolved


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key in release contract')
        result[key] = value
    return result


def _notebook_identity_bytes(data):
    if len(data) > 16 * 1024 ** 2:
        raise ValueError('Notebook JSON exceeds 16 MiB')
    def finite_float(token):
        value = float(token)
        if not math.isfinite(value):
            raise ValueError('nonfinite Notebook JSON number')
        return value
    def nonfinite(token):
        raise ValueError('nonfinite Notebook JSON number')
    notebook = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique_object,
                          parse_float=finite_float, parse_constant=nonfinite)
    if (not isinstance(notebook, dict) or type(notebook.get('nbformat')) is not int
            or notebook['nbformat'] != 4 or type(notebook.get('nbformat_minor')) is not int
            or notebook['nbformat_minor'] < 0):
        raise ValueError('Notebook v4 with explicit minor version required')
    metadata = notebook.get('metadata')
    if not isinstance(metadata, dict):
        raise ValueError('Notebook metadata must be an object')
    kernel = metadata.get('kernelspec')
    language = metadata.get('language_info')
    if not isinstance(kernel, dict) or not isinstance(language, dict):
        raise ValueError('Notebook kernel and language identity required')
    for value in (kernel.get('name'), kernel.get('language'), language.get('name')):
        if not isinstance(value, str) or not value:
            raise ValueError('explicit Notebook kernel and language identity required')
    if not isinstance(notebook.get('cells'), list):
        raise ValueError('Notebook cells must be a list')
    cells = []
    for cell in notebook['cells']:
        if not isinstance(cell, dict) or cell.get('cell_type') not in ('code', 'markdown', 'raw'):
            raise ValueError('unknown Notebook cell type')
        source = cell.get('source')
        if isinstance(source, list) and all(isinstance(part, str) for part in source):
            source = ''.join(source)
        if not isinstance(source, str):
            raise ValueError('Notebook source must be a string or string list')
        cell_metadata = cell.get('metadata', {})
        if not isinstance(cell_metadata, dict):
            raise ValueError('Notebook cell metadata must be an object')
        tags = cell_metadata.get('tags', [])
        attachments = cell.get('attachments', {})
        if (not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)
                or not isinstance(attachments, dict)):
            raise ValueError('invalid Notebook tags or attachments')
        cells.append(dict(cell_type=cell['cell_type'], source=source,
                          tags=tags, attachments=attachments))
    identity = dict(policy=NOTEBOOK_SOURCE, nbformat=4, nbformat_minor=notebook['nbformat_minor'],
                    kernel_name=kernel['name'], kernel_language=kernel['language'],
                    language_name=language['name'], cells=cells)
    return json.dumps(identity, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _identity_data(data, kind):
    if kind == 'bytes':
        return data
    if kind == NOTEBOOK_SOURCE:
        return _notebook_identity_bytes(data)
    raise ValueError('unknown release member identity policy')


def identity_bytes(path, kind='bytes'):
    """Return the exact bytes seal/verify hash under the declared identity policy.

    notebook-source-v1 preserves source whitespace, cell order, tags, attachments
    and kernel/language identity. Saved outputs and non-execution metadata are
    excluded by this explicit policy; no Notebook or source is executed.
    """
    return _identity_data(Path(path).read_bytes(), kind)


def make_contract(root, expected_manifest_sha256):
    """Return only serializable data; the caller's digest remains explicit."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('release root must be an existing directory')
    return dict(schema=CONTRACT_SCHEMA, root=str(root),
                expected_manifest_sha256=_digest(expected_manifest_sha256))


def _check_elf(path, *, statistics):
    data = path.read_bytes()
    if (len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01'
            or struct.unpack_from('<HH', data, 16) != (3, 40)):
        raise ValueError('native asset must be a little-endian ELF32 ARM shared object')
    if statistics and b'PyInit__v3b25_statistics_dot\x00' not in data:
        raise ValueError('statistics extension does not expose the preserved Python ABI name')


def _code_name(name):
    return (Path(name).suffix.casefold() in _CODE_SUFFIXES
            or '__pycache__' in PurePosixPath(name).parts)


def _output_rules(manifest, files):
    rules = manifest.get('mutable_outputs', {'files': [], 'directories': []})
    if not isinstance(rules, dict) or set(rules) != {'files', 'directories'}:
        raise ValueError('mutable outputs must declare exact files and directories')
    if any(not isinstance(rules[key], list) for key in rules):
        raise ValueError('mutable output declarations must be lists')
    declared = rules['files'] + rules['directories']
    if len({name.casefold() for name in declared if isinstance(name, str)}) != len(declared):
        raise ValueError('duplicate mutable output paths')
    for name in declared:
        _relative(name)
        if (_code_name(name) or name in (MANIFEST, CHECKSUM_ANCHOR)
                or '.ipynb_checkpoints' in PurePosixPath(name).parts):
            raise ValueError('mutable output cannot name code, asset, or manifest')
        if name in files or any(path.startswith(name + '/') for path in files):
            raise ValueError('mutable output overlaps immutable release members')
    for directory in rules['directories']:
        if any(name != directory and name.startswith(directory + '/') for name in declared):
            raise ValueError('mutable output declarations overlap')
    return rules


def _checkpoint_rules(manifest, files):
    copies = manifest.get('notebook_checkpoint_copies', {})
    allowed = {'.ipynb_checkpoints/PublicLive-checkpoint.ipynb': 'PublicLive.ipynb'}
    if not isinstance(copies, dict) or copies not in ({}, allowed):
        raise ValueError('only the explicit PublicLive Notebook checkpoint mapping is allowed')
    for destination, source in copies.items():
        _relative(destination)
        _relative(source)
        if (destination in files or source not in files
                or files[source].get('identity', 'bytes') != NOTEBOOK_SOURCE):
            raise ValueError('checkpoint must copy an immutable source-identity Notebook member')
    return copies


def _verify_loaded_module_origins(root, files):
    """Reject old Notebook-kernel aliases before their cached objects can be used."""
    runtime = root / 'runtime'
    frozen = runtime / 'frozen'
    prefixes = ('effective25', 'heart_v2', 'heart_v3a', 'v3a_rate25', 'v3a_25hz_live',
                'rate25_tools', 'pilot25', 'display25', 'owner25')
    singles = {'peak_chain', 'peak_timing', 'entry25_candidate', 'entry25_guard',
               'entry25_worker', 'heart_axi_live', 'run_effective25_gc_probe',
               'run_effective25_gc_window', 'effective25_gc_log', 'effective25_gc_report',
               'effective25_gc_window', 'effective25_gc_window_report'}
    top_modules = {PurePosixPath(name).stem: root / name for name in files
                   if PurePosixPath(name).parent.as_posix() == 'runtime' and name.endswith('.py')
                   and PurePosixPath(name).stem != '__init__'}
    for name, module in tuple(sys.modules.items()):
        is_core = name.split('.')[0] in prefixes or name in singles
        expected = top_modules.get(name)
        if not is_core and expected is None:
            continue
        location = getattr(module, '__file__', None)
        if location is None:
            raise RuntimeError('loaded release module has no file origin: ' + name)
        location = Path(location).resolve(strict=True)
        if ((is_core and not location.is_relative_to(frozen))
                or (expected is not None and location != expected.resolve(strict=True))
                or not location.is_relative_to(root)
                or location.relative_to(root).as_posix() not in files):
            raise RuntimeError('mixed cached release module origin: ' + name)
        spec = getattr(module, '__spec__', None)
        origin = getattr(spec, 'origin', None)
        if origin is not None and Path(origin).resolve(strict=True) != location:
            raise RuntimeError('loaded release module file/spec origins disagree: ' + name)


def _check_output_magic(header, name):
    if (header.startswith((b'\x7fELF', b'MZ', b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',
                           b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'))
            or header.startswith(b'\x00\x09\x0f\xf0\x0f\xf0\x0f\xf0')):
        raise ValueError('executable or hardware bytes disguised as result data: ' + name)
    if header.startswith((b'PK\x03\x04', b'PK\x05\x06')) and Path(name).suffix.casefold() != '.zip':
        raise ValueError('ZIP bytes disguised as another result type: ' + name)


def _check_result_archive(archive, files):
    seen = set()
    for member in archive.infolist():
        member_name = member.filename.rstrip('/') if member.is_dir() else member.filename
        _relative(member_name)
        if member_name.casefold() in seen or ((member.external_attr >> 16) & 0o170000) == 0o120000:
            raise ValueError('duplicate or symlink member in result ZIP')
        seen.add(member_name.casefold())
        if member.is_dir():
            continue
        suffix = Path(member_name).suffix.casefold()
        if suffix in _BINARY_SUFFIXES or '__pycache__' in PurePosixPath(member_name).parts:
            raise ValueError('binary or cache member in result ZIP: ' + member_name)
        with archive.open(member) as stream:
            _check_output_magic(stream.read(12), member_name)
        if _code_name(member_name):
            data = archive.read(member)
            matches = [record for rel, record in files.items()
                       if PurePosixPath(rel).name == PurePosixPath(member_name).name
                       and record['sha256'] == hashlib.sha256(
                           _identity_data(data, record.get('identity', 'bytes'))).hexdigest()]
            if not matches:
                raise ValueError('unlisted or changed source member in result ZIP: ' + member_name)
        elif suffix == '.zip':
            with archive.open(member) as stream:
                with ZipFile(stream) as nested:
                    _check_result_archive(nested, files)


def _check_output(path, name, files):
    if _code_name(name):
        raise ValueError('executable or hardware asset in mutable output: ' + name)
    with path.open('rb') as stream:
        _check_output_magic(stream.read(12), name)
    if path.suffix.casefold() == '.zip':
        with ZipFile(path) as archive:
            _check_result_archive(archive, files)


def verify_release(contract):
    """Verify the full explicit file set and original qualified asset identities.

    Run Python with -B, or set sys.dont_write_bytecode before importing release
    modules. An unlisted cache or executable is rejected, never silently ignored.
    Results are allowed only at manifest-declared exact output paths. They never
    replace a pinned source member or become an import path.
    """
    if not isinstance(contract, dict) or set(contract) != {
            'schema', 'root', 'expected_manifest_sha256'}:
        raise ValueError('release contract fields differ')
    if contract['schema'] != CONTRACT_SCHEMA:
        raise ValueError('release contract schema differs')
    expected = _digest(contract['expected_manifest_sha256'])
    if not isinstance(contract['root'], str) or not Path(contract['root']).is_absolute():
        raise ValueError('release contract root must be an explicit absolute path')
    root = Path(contract['root']).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('release root is not a directory')
    manifest_path = _local(root, MANIFEST)
    if _sha(manifest_path) != expected:
        raise ValueError('public LIVE manifest SHA256 differs from caller expectation')
    manifest = json.loads(manifest_path.read_text('utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA:
        raise ValueError('public LIVE manifest schema differs')
    records = manifest.get('files')
    if not isinstance(records, list) or not records:
        raise ValueError('public LIVE manifest has no explicit file records')
    files = {}
    casefolded = set()
    for record in records:
        if (not isinstance(record, dict) or not {'path', 'bytes', 'sha256'}.issubset(record)
                or not set(record).issubset({'path', 'bytes', 'sha256', 'identity'})):
            raise ValueError('public LIVE member fields differ')
        name = _relative(record['path'])
        if name in (MANIFEST, CHECKSUM_ANCHOR) or name.casefold() in casefolded:
            raise ValueError('duplicate, case-colliding, or self-referential release member')
        if type(record['bytes']) is not int or record['bytes'] < 0:
            raise ValueError('release member byte count is invalid')
        _digest(record['sha256'])
        kind = record.get('identity', 'bytes')
        if kind not in ('bytes', NOTEBOOK_SOURCE) or kind == NOTEBOOK_SOURCE and not name.endswith('.ipynb'):
            raise ValueError('invalid identity policy for release member')
        files[name] = record
        casefolded.add(name.casefold())
    output_rules = _output_rules(manifest, files)
    checkpoint_copies = _checkpoint_rules(manifest, files)
    actual = set()
    for path in root.rglob('*'):
        if (path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)
                or getattr(path, 'is_junction', lambda: False)()):
            raise ValueError('release tree contains a symlink, junction, or escaped path')
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name not in (MANIFEST, CHECKSUM_ANCHOR):
                if name in files:
                    actual.add(name)
                elif name in checkpoint_copies:
                    source = files[checkpoint_copies[name]]
                    data = identity_bytes(_local(root, name), NOTEBOOK_SOURCE)
                    if len(data) != source['bytes'] or hashlib.sha256(data).hexdigest() != source['sha256']:
                        raise ValueError('Notebook checkpoint source differs from pinned PublicLive source')
                elif (name in output_rules['files'] or any(name.startswith(directory + '/')
                        for directory in output_rules['directories'])):
                    _check_output(path, name, files)
                else:
                    actual.add(name)
    if actual != set(files):
        raise ValueError('public LIVE complete file set differs; missing=' +
                         repr(sorted(set(files) - actual)) + '; unlisted=' +
                         repr(sorted(actual - set(files))))
    for name, record in files.items():
        path = _local(root, name)
        data = identity_bytes(path, record.get('identity', 'bytes'))
        if len(data) != record['bytes'] or hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('public LIVE release member identity differs: ' + name)
    _verify_loaded_module_origins(root, files)
    assets = manifest.get('assets')
    if not isinstance(assets, dict) or not REQUIRED_ASSETS.issubset(assets):
        raise ValueError('public LIVE required asset roles are missing')
    resolved_assets = {}
    seen_asset_paths = set()
    for role, name in assets.items():
        name = _relative(name)
        if name not in files or name in seen_asset_paths:
            raise ValueError('release asset is unlisted or reused under another role')
        seen_asset_paths.add(name)
        record = files[name]
        if record.get('identity', 'bytes') != 'bytes':
            raise ValueError('runtime and native assets require exact byte identity')
        if role in FIXED_ASSET_SHA256 and record['sha256'] != FIXED_ASSET_SHA256[role]:
            raise ValueError('fixed original asset SHA256 differs: ' + role)
        resolved_assets[role] = dict(record, relative_path=name, path=str(_local(root, name)))
    for role in FIXED_ASSET_SHA256:
        if role.endswith('_binary'):
            _check_elf(Path(resolved_assets[role]['path']), statistics=role == 'native_binary')
    return dict(schema=SCHEMA, root=str(root), runtime_root=str(root / 'runtime'),
                native_source_root=str(root / 'native_source'),
                manifest_sha256=expected, assets=resolved_assets,
                historical_numerical_qualification=False, hardware_accessed=False)


def activate_runtime(contract):
    """Reverify, reject mixed frozen imports, then expose this release's PS code."""
    context = verify_release(contract)
    frozen = Path(context['runtime_root']) / 'frozen'
    prefixes = ('effective25', 'heart_v2', 'heart_v3a', 'v3a_rate25', 'v3a_25hz_live',
                'rate25_tools', 'pilot25', 'display25', 'owner25')
    singles = {'peak_chain', 'peak_timing', 'entry25_candidate', 'entry25_guard',
               'entry25_worker', 'heart_axi_live', 'run_effective25_gc_probe',
               'run_effective25_gc_window', 'effective25_gc_log', 'effective25_gc_report',
               'effective25_gc_window', 'effective25_gc_window_report'}
    for name, module in tuple(sys.modules.items()):
        if name.split('.')[0] in prefixes or name in singles:
            location = getattr(module, '__file__', None)
            if location is None or not Path(location).resolve().is_relative_to(frozen):
                raise RuntimeError('mixed frozen release module: ' + name)
    paths = (frozen, frozen / 'base', frozen / 'base/deps',
             frozen / 'base/deps/static', frozen / 'base/deps/static/checked',
             frozen / 'base/deps/static/checked/base')
    for path in reversed(paths):
        if not path.is_dir():
            raise ValueError('required frozen import directory is missing: ' + str(path))
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return context


def native_context(contract):
    """Return explicit selected native bytes without any private preparation proof."""
    context = verify_release(contract)
    binary = context['assets']['native_binary']
    return dict(binary=dict(path=binary['path'], sha256=binary['sha256']),
                c_sha256=context['assets']['native_source']['sha256'],
                release_manifest_sha256=context['manifest_sha256'],
                historical_numerical_qualification=False,
                native_manifest_sha256=None, preparation_sha256=None)


def verified_asset(contract, role, expected_path):
    """Reverify before a native loader uses its explicitly selected local path."""
    context = verify_release(contract)
    if role not in context['assets']:
        raise ValueError('required selected native role is absent: ' + role)
    selected = context['assets'][role]
    if Path(expected_path).resolve(strict=True) != Path(selected['path']):
        raise ValueError('native loader path differs from selected release asset: ' + role)
    return selected


def read_sections(contract):
    context = verify_release(contract)
    document = json.loads(Path(context['assets']['arm_sos']['path']).read_text('utf-8'),
                          object_pairs_hook=_unique_object)
    values = document.get('native_sos_hex') if isinstance(document, dict) else None
    if (not isinstance(values, list) or not values
            or any(not isinstance(row, list) or len(row) != 6 for row in values)
            or any(not isinstance(value, str) for row in values for value in row)):
        raise ValueError('native SOS coefficient document shape differs')
    sections = tuple(tuple(float.fromhex(value) for value in row) for row in values)
    if not all(math.isfinite(value) for row in sections for value in row):
        raise ValueError('native SOS coefficients must be finite')
    return sections
