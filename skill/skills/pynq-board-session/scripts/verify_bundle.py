"""Verify an explicit manifest SHA256 file map without importing board code."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def member_path(root, name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('invalid relative member name')
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or re.match(r'^[A-Za-z]:', name):
        raise ValueError('member escapes package root')
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink member or parent')
    if not path.resolve().is_relative_to(root):
        raise ValueError('resolved member escapes package root')
    return path


def verify(root, manifest, file_map='files', expected_manifest=None):
    report = dict(schema='pynq_bundle_files_v1', root=str(Path(root).resolve()),
                  hardware_accessed=False, files=[], errors=[], provenance_verified=False,
                  runtime_acceptance_evaluated=False)
    try:
        raw_root = Path(root)
        if raw_root.is_symlink() or not raw_root.is_dir():
            raise ValueError('package root must be an existing non-symlink directory')
        root = raw_root.resolve()
        path = member_path(root, manifest)
        report['manifest_sha256'] = sha(path)
        if expected_manifest is not None:
            if report['manifest_sha256'] != expected_manifest.lower():
                raise ValueError('expected manifest SHA256 mismatch')
            report['provenance_verified'] = True
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        for key in file_map.split('.'):
            value = value[key]
        if not isinstance(value, dict) or not value:
            raise ValueError('selected file map must be a nonempty object')
        seen = set()
        for name, expected in value.items():
            try:
                item = member_path(root, name)
                canonical = item.relative_to(root).as_posix()
                if canonical in seen:
                    raise ValueError('duplicate normalized member')
                seen.add(canonical)
                expected = expected.get('sha256') if isinstance(expected, dict) else expected
                if not isinstance(expected, str) or not re.fullmatch('[0-9a-fA-F]{64}', expected):
                    raise ValueError('member digest must be SHA256 or an object with sha256')
                actual = sha(item)
                row = dict(path=name, bytes=item.stat().st_size, sha256=actual,
                           matches=actual == expected.lower())
                report['files'].append(row)
                if not row['matches']:
                    report['errors'].append(dict(path=name, error='SHA256 mismatch'))
            except Exception as exc:
                report['errors'].append(dict(path=name, error=type(exc).__name__ + ': ' + str(exc)))
    except Exception as exc:
        report['errors'].append(dict(path=manifest, error=type(exc).__name__ + ': ' + str(exc)))
    report['file_integrity_verified'] = bool(report['files']) and not report['errors']
    report['scope'] = 'Explicit file map only; no hardware, ABI, notebook normalization, extra-file or runtime acceptance check.'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    p.add_argument('--manifest', required=True, help='Path relative to package root')
    p.add_argument('--file-map', default='files', help='Dot-separated object path')
    p.add_argument('--expected-manifest-sha256')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    if Path(a.output).exists():
        p.error('output exists; preserve the previous report')
    if a.expected_manifest_sha256 and not re.fullmatch('[0-9a-fA-F]{64}', a.expected_manifest_sha256):
        p.error('expected SHA256 must contain 64 hex digits')
    report = verify(a.root, a.manifest, a.file_map, a.expected_manifest_sha256)
    with Path(a.output).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(report=a.output, checked_files=len(report['files']),
                          errors=len(report['errors']), hardware_accessed=False), ensure_ascii=False))
    return 0 if report['file_integrity_verified'] else 2


if __name__ == '__main__':
    sys.exit(main())
