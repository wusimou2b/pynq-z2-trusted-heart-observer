"""Cold, read-only identity checks for the saved 1504-point statistics experiment."""
import csv
import io
import json
from pathlib import Path
from zipfile import ZipFile

if __package__:
    from .ps_budget_guard import FLAGS, code_hash, digest, local, sha, write_new
else:
    from ps_budget_guard import FLAGS, code_hash, digest, local, sha, write_new

SOURCE_SHA = 'ce541ef001f327234c3a30b4275d14458c2b3ed670edb77a27f23d7e6be8893d'
RECORD_SHA = 'e49c3ac12ed0822be9987ad01eb2004a9811ae03608efdb94c3e1eb82238f1bb'
FILES = {'statistics25_core.py', 'statistics25_guard.py', 'statistics25_replay.py',
         'run_statistics25_replay.py', 'ps_budget_guard.py', 'ps_budget_runtime.py',
         'README_STATISTICS25.md'}


def read_recording(path):
    payload = Path(path).read_bytes()
    if digest(payload) != RECORD_SHA:
        raise ValueError('saved recording identity changed')
    with ZipFile(io.BytesIO(payload)) as z:
        if len(z.namelist()) != 21 or len(set(z.namelist())) != 21 or z.testzip() is not None:
            raise ValueError('recording members/CRC changed')
        data = {name: z.read(name) for name in z.namelist()}
    report = json.loads(data['joint_concurrent_result.json'])
    if report['package_manifest_sha256'] != SOURCE_SHA:
        raise ValueError('recorded source identity changed')
    for name, expected in report['input_sha256'].items():
        if digest(data[name]) != expected:
            raise ValueError('recording input hash changed: ' + name)
    summary = json.loads(data['capture/summary.json'])
    for name, suffix in [('raw','csv'), ('results','csv'), ('events','jsonl')]:
        if digest(data['capture/' + name + '.' + suffix]) != summary[name + '_sha256']:
            raise ValueError('recording summary hash changed: ' + name)
    raw = list(csv.DictReader(io.StringIO(data['capture/raw.csv'].decode())))
    rows = list(csv.DictReader(io.StringIO(data['capture/results.csv'].decode())))
    if len(raw) != 1504 or len(rows) != 1504 or any(summary[k] != 1504
            for k in ('read', 'processed', 'raw_saved', 'results_saved')):
        raise ValueError('recording count changed')
    for records in (raw, rows):
        if [int(r['sequence']) for r in records] != list(range(1504)):
            raise ValueError('recording sequence changed')
    invalid = [int(r['sequence']) for r in rows if r['slot_valid'] != 'True']
    numeric = sum(bool(r['bpm']) for r in rows)
    if invalid != [186,481,511,1003] or numeric != 623:
        raise ValueError('recording workload changed')
    return dict(raw=raw, results=rows, summary=summary, invalid_slots=4, numeric_rows=numeric,
                source_zip_sha256=RECORD_SHA)


def verify_package(root, source, recording):
    root, source = Path(root), Path(source)
    doc = json.loads(local(root, 'statistics25-manifest.json').read_text(encoding='utf-8'))
    if (doc.get('schema') != 'v3b25_statistics_batch_package_v1' or
            set(doc.get('files', {})) != FILES or doc.get('source_manifest_sha256') != SOURCE_SHA or
            doc.get('recording_sha256') != RECORD_SHA or doc.get('record_count') != 1504 or
            (doc.get('raw_hz'), doc.get('processing_hz'), doc.get('warmup_slots')) != (25,25,700) or
            doc.get('readonly') is not True or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('statistics package scope changed')
    for name, expected in doc['files'].items():
        if sha(local(root, name)) != expected:
            raise ValueError('statistics code changed: ' + name)
    if code_hash(local(root, 'Statistics25Replay.ipynb')) != doc['notebook_code_sha256']:
        raise ValueError('statistics Notebook code changed')
    if sha(local(source, 'browser-heart-manifest.json')) != SOURCE_SHA:
        raise ValueError('browser source manifest changed')
    files, books = doc['source_files'], doc['source_notebooks']
    if len(files) + len(books) != 292 or set(files) & set(books):
        raise ValueError('browser source file scope changed')
    for name, expected in files.items():
        if sha(local(source, name)) != expected:
            raise ValueError('browser source bytes changed: ' + name)
    for name, expected in books.items():
        if code_hash(local(source, name)) != expected:
            raise ValueError('browser source Notebook code changed: ' + name)
    if sha(recording) != RECORD_SHA:
        raise ValueError('saved recording identity changed')
    return dict(bundle_validated=True, files_verified=292, frozen_files_verified=197,
                package_manifest_sha256=sha(root/'statistics25-manifest.json'), readonly=True,
                hardware_accessed=False, **FLAGS)
