"""Stdlib-only identity and data checks for one frozen read-only PS replay."""
from collections import Counter
import csv
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import zipfile

ZIP_SHA='c6b001caef691d556a0994c5106e8d640a7780cfeec1f05adb6066cc79b1bd4c'
SOURCE_SHA='8a8fc4aa5f0f94c43f671296b6a2583a9340f9fa09ae99e4322934ef7a353a89'
FILES={'ps_budget_guard.py','ps_budget_runtime.py','run_ps_budget.py','README_PS_BUDGET.md'}
FLAGS=dict.fromkeys(('live_25hz_passed','live_50hz_passed','auto_beta_effect_passed','board_ddr_verified',
    'limits_frozen','run_acceptance_passed','v3a_complete','full_v3b_acceptance_passed',
    'accuracy_verified','strict_realtime_verified','concurrent60_passed'),False)


def digest(data):return hashlib.sha256(data).hexdigest()
def sha(path):return digest(Path(path).read_bytes())
def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def code_hash(path):
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    code=[''.join(c['source']) for c in d['cells'] if c['cell_type']=='code']
    return digest(json.dumps(code,ensure_ascii=False,separators=(',',':')).encode())


def local(root,name):
    if not isinstance(name,str) or not name or ':' in name or '\\' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
        raise ValueError('invalid source member')
    path=Path(root)/name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('source file missing or escaped: '+name)
    return path


def verify_source(root,doc):
    root=Path(root).resolve();files=doc['source_files'];books=doc['source_notebooks']
    if len(files)!=248 or len(books)!=7 or set(files)&set(books):raise ValueError('source 255-file scope changed')
    if sha(local(root,'joint-overlap-manifest.json'))!=SOURCE_SHA:raise ValueError('reviewed source manifest changed')
    for name,h in files.items():
        if sha(local(root,name))!=h:raise ValueError('source bytes changed: '+name)
    for name,h in books.items():
        if code_hash(local(root,name))!=h:raise ValueError('source Notebook code changed: '+name)
    return dict(files_verified=255,frozen_heart_files_verified=197,source_manifest_sha256=SOURCE_SHA)


def verify_package(root,source):
    root=Path(root);doc=json.loads((root/'ps-budget-manifest.json').read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_ps_budget_package_v1' or set(doc.get('files',{}))!=FILES or
        (doc.get('raw_hz'),doc.get('processing_hz'),doc.get('record_count'),doc.get('warmup_slots'))!=(25,25,1504,700) or
        doc.get('source_zip_sha256')!=ZIP_SHA or doc.get('source_manifest_sha256')!=SOURCE_SHA or
        any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('budget package scope changed')
    for n,h in doc['files'].items():
        if sha(local(root,n))!=h:raise ValueError('budget file changed: '+n)
    if code_hash(local(root,'PsBudget.ipynb'))!=doc.get('notebook_code_sha256'):raise ValueError('budget Notebook code changed')
    return doc,verify_source(source,doc)


def read_archive(data):
    if digest(data)!=ZIP_SHA:raise ValueError('original result ZIP identity changed')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or len(names)!=23 or z.testzip() is not None:
            raise ValueError('result ZIP member/CRC mismatch')
        if any(i.file_size>8_000_000 or i.filename.endswith('.py') for i in z.infolist()):raise ValueError('unexpected ZIP scope')
        members={n:z.read(n) for n in names}
    final=json.loads(members['joint_overlap_result.json'])
    if set(final['input_sha256'])|{'joint_overlap_result.json'}!=set(members):raise ValueError('result member set changed')
    for name,b in members.items():
        if name.endswith('.json'):
            for n,h in json.loads(b).get('input_sha256',{}).items():
                if n not in members or digest(members[n])!=h:raise ValueError('result input hash mismatch')
    raw=list(csv.DictReader(io.StringIO(members['capture/raw.csv'].decode('utf-8'))))
    rows=list(csv.DictReader(io.StringIO(members['capture/results.csv'].decode('utf-8'))))
    summary=json.loads(members['capture/summary.json'])
    if len(raw)!=1504 or len(rows)!=1504 or summary['read']!=1504:raise ValueError('result count changed')
    if [int(r['sequence']) for r in raw]!=list(range(1504)) or any(
        int(r['sequence'])!=i or int(r['source_first'])!=i or int(r['source_last'])!=i for i,r in enumerate(rows)):
        raise ValueError('record source order changed')
    bad=Counter(r['slot_reason'] for r in rows if r['slot_valid']=='False')
    unpaired=sum(r['pair_ok']=='False' for r in raw);numeric=sum(bool(r['bpm']) for r in rows)
    if bad!={'PPG／加速度未配对或无效':24,'原始序号／时间缺口':4} or unpaired!=24 or numeric:
        raise ValueError('reviewed invalid-point workload changed')
    if any(b and b['time_s'] and float(b['time_s'])<=float(a['time_s']) for a,b in zip(raw,raw[1:])):
        raise ValueError('record time order changed')
    return dict(raw=raw,results=rows,summary=summary,source_sha256=ZIP_SHA,invalid_points=28,
        unpaired_points=unpaired,numeric_bpm_rows=numeric)


def differences(row,values):
    out=[]
    for name,value in values.items():
        if name not in row:raise ValueError('record schema missing field: '+name)
        if name in {'backend_source','pl_latency_cycles'}:continue
        text=row[name]
        if value is None:equal=text==''
        elif type(value) is bool:equal=text==str(value)
        elif isinstance(value,(int,float)):
            try:equal=text!='' and math.isfinite(float(value)) and float(text)==value
            except ValueError:equal=False
        else:equal=text==value
        if not equal:out.append(dict(sequence=row.get('sequence'),field=name,recorded=text,replayed=value))
    return out
