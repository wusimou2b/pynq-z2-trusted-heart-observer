"""Reference display-reader repair, scoped to the retained spatial hybrid run."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
if not __package__:
    sys.path.insert(0, str(ROOT))
MANIFEST = 'main-spatial-copy-manifest.json'
BOOK = 'MainSpatialCopy25.ipynb'
REVISION = 'bounded_copy_then_decode_v1'
READER_SHA = '6b5fc374972d896fde9a9427503d960f92715697c09018924fd7a9d00fa14796'


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def verify_package(root, expected=None):
    if __package__:
        from .main_spatial_guard import verify_package as original
        from .spatial_camera_guard import notebook_identity
    else:
        from main_spatial_guard import verify_package as original
        from spatial_camera_guard import notebook_identity
    root = Path(root).resolve()
    checked = original(root, expected)
    path = root/MANIFEST
    doc = json.loads(path.read_bytes())
    if (doc.get('schema') != 'main_spatial_reference_reader_port_v1'
        or doc.get('reader_revision') != REVISION
        or doc.get('integration_manifest_sha256') != checked['integration_manifest_sha256']
        or doc.get('files', {}).get('display_copy_transport.py') != READER_SHA
        or doc.get('rates') != [25, 25, 5] or doc.get('grid') != [4, 3]
        or doc.get('automatic_retry') is not False):
        raise ValueError('reference reader port identity differs')
    for name, pin in doc['files'].items():
        member = root/name
        if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or '\\' in name or member.is_symlink():
            raise ValueError('unsafe reader port member')
        if hashlib.sha256(member.read_bytes()).hexdigest() != pin:
            raise ValueError('reader port member differs: ' + name)
    if notebook_identity(root/BOOK) != doc.get('notebook_identity_sha256'):
        raise ValueError('reader port Notebook source differs')
    return dict(checked, display_reader_revision=REVISION,
                copy_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@contextmanager
def delegate(*, reader=False):
    if __package__:
        from . import run_main_spatial as original, browser_heart_transport
        from .display_copy_transport import CopyMailbox
        from .joint_startup import replace_attribute
    else:
        import run_main_spatial as original, browser_heart_transport
        from display_copy_transport import CopyMailbox
        from joint_startup import replace_attribute
    with replace_attribute(original, 'ROOT', ROOT), \
         replace_attribute(original, 'verify_package', verify_package):
        if reader:
            with replace_attribute(browser_heart_transport, 'BrowserMailbox', CopyMailbox):
                yield original
        else:
            yield original


def short():
    verify_package(ROOT)
    with delegate() as original:
        return original.short()


def prepare():
    verify_package(ROOT)
    with delegate() as original:
        return original.prepare()


def run(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-MAIN-SPATIAL-COPY25':
        raise ValueError('requires explicit RUN-MAIN-SPATIAL-COPY25')
    checked = verify_package(ROOT)
    write_new(ROOT/'main-spatial-copy-attempt.json', dict(
        checked=checked, automatic_retry=False, reader_revision=REVISION))
    result, failure = None, None
    try:
        with delegate(reader=True) as original:
            result = original.run(hardware=True, confirmation='RUN-MAIN-SPATIAL25')
    except BaseException as exc:
        failure = exc
    final = dict(schema='main_spatial_reference_reader_port_result_v1',
        checked=checked, reader_revision=REVISION, result=result,
        original_error=dict(type=type(failure).__name__, message=str(failure)) if failure else None,
        reference_short_trial_is_not_full_acceptance=True,
        strict_realtime_verified=False, full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'main-spatial-copy-final.json', final)
        with ZipFile(ROOT/'main-spatial-copy-results.zip', 'x', compression=ZIP_DEFLATED) as archive:
            for name in (MANIFEST, 'main-spatial-copy-attempt.json',
                         'main-spatial-copy-final.json', 'main-spatial-results.zip'):
                if (ROOT/name).is_file(): archive.write(ROOT/name, name)
    except BaseException as export_error:
        if failure is not None: raise failure from export_error
        raise
    if failure is not None: raise failure
    print('结果：main-spatial-copy-results.zip；原结果保留，不自动重试。', flush=True)
    return final


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check-bundle', action='store_true')
    modes.add_argument('--short', action='store_true')
    args = parser.parse_args()
    if args.check_bundle: print(json.dumps(verify_package(ROOT), ensure_ascii=False))
    else: raise SystemExit(0 if short()['passed'] else 1)
