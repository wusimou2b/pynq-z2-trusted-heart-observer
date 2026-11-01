"""Bounded, read-only result ZIP inventory. Never extracts or executes members."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from zipfile import ZipFile


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def strict_json(data):
    def invalid(value):
        raise ValueError('nonfinite JSON number: ' + value)
    return json.loads(data, parse_constant=invalid)


def json_facts(value, prefix='$', result=None):
    result = [] if result is None else result
    if len(result) >= 200:
        return result
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {'password', 'access_token', 'auth_token', 'authorization', 'cookie'}:
                item = '[redacted]'
            json_facts(item, prefix + '.' + str(key), result)
    elif isinstance(value, list):
        result.append({'field': prefix, 'list_length': len(value)})
    else:
        result.append({'field': prefix, 'value': value[:500] if isinstance(value, str) else value})
    return result


def csv_facts(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    headers = reader.fieldnames
    if not headers or len(headers) != len(set(headers)):
        raise ValueError('missing or duplicate CSV header')
    fields = [k for k in ('valid', 'pair_ok', 'contact_ready', 'output_allowed', 'published', 'display_allowed') if k in headers]
    booleans = {key: Counter() for key in fields}
    reasons = {key: Counter() for key in ('reason', 'invalid_reason') if key in headers}
    count = 0
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('CSV row width differs from header')
        count += 1
        for key in fields:
            raw = row[key].strip().lower()
            label = raw if raw in {'true', 'false'} else 'missing' if not raw else 'other'
            booleans[key][label] += 1
        for key in reasons:
            value = row[key].strip()
            if value:
                reasons[key][value[:200]] += 1
    return dict(row_count=count, headers=headers,
                boolean_counts={k: dict(v) for k, v in booleans.items()},
                reason_counts={k: dict(v.most_common(20)) for k, v in reasons.items()},
                interpretation='Raw counts only; no schema inference or acceptance decision.')


def inspect(archive, expected=None, max_depth=12, max_member=64 * 1024**2,
            max_total=512 * 1024**2, max_members=2000):
    path = Path(archive)
    report = dict(schema='pynq_result_inventory_v1', archive=str(path.resolve()),
                  hardware_accessed=False, members=[], documents=[], issues=[],
                  bytes_read=0, members_seen=0, acceptance_evaluated=False,
                  crc_scope='Only members actually read; skipped members are not CRC-verified.')
    if not path.is_file() or path.stat().st_size == 0:
        report['issues'].append({'path': str(path), 'error': 'missing or zero-byte archive'})
        return report
    report.update(bytes=path.stat().st_size, sha256=digest(path))
    if expected is not None and report['sha256'] != expected.lower():
        report['issues'].append({'path': str(path), 'error': 'expected archive SHA256 mismatch'})
        return report

    def problem(where, message):
        report['issues'].append({'path': where, 'error': str(message)})

    def walk(source, prefix, depth):
        if depth > max_depth:
            problem(prefix, 'nested archive depth limit; remaining members unread')
            return
        try:
            with ZipFile(source) as package:
                seen = set()
                for info in package.infolist():
                    report['members_seen'] += 1
                    where = prefix + '!' + info.filename
                    if report['members_seen'] > max_members:
                        problem(where, 'global member limit; remaining members unread')
                        return
                    name = info.filename
                    relative = PurePosixPath(name)
                    unsafe = (relative.is_absolute() or '..' in relative.parts or '\\' in name
                              or '\x00' in name or re.match(r'^[A-Za-z]:', name)
                              or stat.S_ISLNK(info.external_attr >> 16))
                    normalized = str(relative)
                    if unsafe or normalized in seen:
                        problem(where, 'unsafe or duplicate member name')
                        continue
                    seen.add(normalized)
                    item = dict(path=where, bytes=info.file_size, read=False)
                    report['members'].append(item)
                    if info.is_dir():
                        continue
                    suffix = relative.suffix.lower()
                    if suffix not in {'.zip', '.json', '.jsonl', '.csv'}:
                        item['skipped'] = 'non-data member; not executed'
                        continue
                    if info.file_size > max_member or report['bytes_read'] + info.file_size > max_total:
                        problem(where, 'read byte limit; member unread')
                        continue
                    try:
                        # ZipFile checks the CRC on a complete read. Metadata size is
                        # bounded before reading; this does not call extractall().
                        data = package.read(info)
                        report['bytes_read'] += len(data)
                        item.update(read=True, sha256=hashlib.sha256(data).hexdigest())
                        if suffix == '.zip':
                            walk(io.BytesIO(data), where, depth + 1)
                        elif suffix == '.json':
                            value = strict_json(data.decode('utf-8-sig'))
                            facts = json_facts(value)
                            report['documents'].append(dict(path=where, kind='json', facts=facts,
                                                            facts_limit=200, possibly_truncated=len(facts) >= 200))
                        elif suffix == '.csv':
                            report['documents'].append(dict(path=where, kind='csv', **csv_facts(data)))
                        else:
                            count = 0
                            for line in data.decode('utf-8-sig').splitlines():
                                if line.strip():
                                    strict_json(line)
                                    count += 1
                            report['documents'].append(dict(path=where, kind='jsonl', row_count=count))
                    except (ValueError, OSError, RuntimeError, UnicodeError, csv.Error) as exc:
                        problem(where, exc)
        except Exception as exc:
            problem(prefix, type(exc).__name__ + ': ' + str(exc))

    walk(path, path.name, 0)
    report['inspection_complete'] = not report['issues']
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--expected-sha256')
    p.add_argument('--max-depth', type=int, default=12)
    p.add_argument('--max-member-mib', type=int, default=64)
    p.add_argument('--max-total-mib', type=int, default=512)
    p.add_argument('--max-members', type=int, default=2000)
    a = p.parse_args()
    if Path(a.output).exists():
        p.error('output exists; preserve the previous report')
    if min(a.max_depth, a.max_member_mib, a.max_total_mib, a.max_members) <= 0:
        p.error('limits must be positive')
    if a.expected_sha256 and not re.fullmatch(r'[0-9a-fA-F]{64}', a.expected_sha256):
        p.error('expected SHA256 must contain 64 hex digits')
    report = inspect(a.archive, a.expected_sha256, a.max_depth, a.max_member_mib * 1024**2,
                     a.max_total_mib * 1024**2, a.max_members)
    with Path(a.output).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(report=a.output, documents=len(report['documents']),
                          issues=len(report['issues']), hardware_accessed=False), ensure_ascii=False))
    return 2 if report['issues'] else 0


if __name__ == '__main__':
    sys.exit(main())
