"""Independent25Hz40ms budget candidate; no automatic hardware entry."""
from contextlib import contextmanager
import csv
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
if not __package__:sys.path.insert(0,str(ROOT))
if __package__:
    from .run_gil_joint import verify_package as verify_base,write_new
    from .spatial_camera_guard import notebook_identity
else:
    from run_gil_joint import verify_package as verify_base,write_new
    from spatial_camera_guard import notebook_identity

MANIFEST='sample40-manifest.json'
BOOK='Sample40Joint25.ipynb'
ADDED={'sample40_runtime.py','run_sample40.py','README_SAMPLE40.md'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_package(root,expected=None):
    root=Path(root).resolve();checked=verify_base(root,expected);doc=json.loads((root/MANIFEST).read_bytes())
    if (doc.get('schema')!='sample40_warning20_delivery_v1' or set(doc.get('files',{}))!=ADDED
        or doc.get('base_gil_manifest_sha256')!=checked['gil_manifest_sha256']
        or doc.get('rates')!=[25,25,5] or doc.get('sample_hard_seconds')!=.040
        or doc.get('warning_seconds')!=.020 or doc.get('main_init_stop_seconds')!=.020
        or doc.get('other_protections_unchanged') is not True or doc.get('automatic_retry') is not False):
        raise ValueError('sample40 budget scope differs')
    for name,pin in doc['files'].items():
        p=root/name
        if p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):raise ValueError('sample40 escaped member')
        if sha(p)!=pin:raise ValueError('sample40 member differs: '+name)
    if notebook_identity(root/BOOK)!=doc.get('notebook_identity_sha256'):raise ValueError('sample40 Notebook source differs')
    return dict(checked,sample_hard_seconds=.040,warning_seconds=.020,main_init_stop_seconds=.020,
        sample40_manifest_sha256=sha(root/MANIFEST),sample40_live_verified=False)


@contextmanager
def delegate(*,owner=False):
    if __package__:
        from . import run_gil_joint as original,spatial_gil_worker
        from .sample40_runtime import start_owner
        from .joint_startup import replace_attribute
    else:
        import run_gil_joint as original,spatial_gil_worker
        from sample40_runtime import start_owner
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package):
        if owner:
            with replace_attribute(spatial_gil_worker,'start_owner',start_owner):yield original
        else:yield original


def short():
    verify_package(ROOT)
    with delegate() as original:return original.short()


def prepare():
    verify_package(ROOT)
    with delegate() as original:return original.prepare()


def analyze_stopped(root):
    root=Path(root);path=root/'continuous-result.json'
    complete=json.loads(path.read_bytes()) if path.is_file() else {}
    if not(complete.get('owner_exited') and complete.get('resources_released')
        and complete.get('artifact_audit',{}).get('checks',{}).get('writers_stopped')):
        raise ValueError('writers/resources not confirmed stopped; do not read journals')
    with (root/'continuous-results/capture/results.csv').open(encoding='utf-8',newline='') as stream:
        rows=list(csv.DictReader(stream))
    tails=[];processing=[];over40=0
    for row in rows:
        call=int(row['pl_call_ns']);elapsed=int(row['processing_finished_ns'])-int(row['processing_started_ns'])
        processing.append(elapsed);over40+=int(call>40_000_000)
        if call>20_000_000:
            tails.append(dict(sequence=int(row['sequence']),time_s=float(row['time_s']),pl_call_ns=call,
                processing_ns=elapsed,ps_processing_ns=int(row['ps_processing_ns']),
                processing_queue_wait_ns=int(row['processing_queue_wait_ns']),read_to_result_ns=int(row['read_to_result_ns'])))
    worst10=max((sum(processing[i:i+10]) for i in range(len(processing)-9)),default=None)
    return dict(schema='sample40_full_call_tail_analysis_v1',count=len(rows),over20_call_count=len(tails),
        over40_call_count=over40,over20_calls=tails,max_processing_ms=max(processing,default=0)/1e6,
        mean_processing_ms=sum(processing)/len(processing)/1e6 if processing else None,
        worst10_processing_ms=worst10/1e6 if worst10 is not None else None,
        full_result_csv_sha256=sha(root/'continuous-results/capture/results.csv'),
        acceptance_passed=False,scope='Original complete-call/PS/queue wall clocks,not pure FPGA/native40ms transaction time. Includes all successful-result full-call tails;failed call remains in owner fault record.')


def run(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-SAMPLE40-JOINT25':raise ValueError('explicit RUN-SAMPLE40-JOINT25 required')
    checked=verify_package(ROOT)
    write_new(ROOT/'sample40-attempt.json',dict(checked=checked,automatic_retry=False,
        original20ms_baseline_preserved=True,sample_only_budget_change=True))
    result=failure=analysis=analysis_error=None
    try:
        with delegate(owner=True) as original:result=original.run(hardware=True,confirmation='RUN-GIL-JOINT25')
    except BaseException as exc:failure=exc
    if result is not None:
        try:analysis=analyze_stopped(ROOT)
        except BaseException as exc:analysis_error=dict(type=type(exc).__name__,message=str(exc))
    final=dict(schema='sample40_joint_candidate_result_v1',checked=checked,result=result,tail_analysis=analysis,
        analysis_error=analysis_error,original_error=dict(type=type(failure).__name__,message=str(failure)) if failure else None,
        live25_acceptance_passed=False,strict_realtime_verified=False,full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'sample40-final.json',final)
        if analysis is not None:write_new(ROOT/'sample40-longtails.json',analysis)
        with ZipFile(ROOT/'sample40-results.zip','x',compression=ZIP_DEFLATED) as z:
            for n in (MANIFEST,'sample40-attempt.json','sample40-final.json','sample40-longtails.json','gil-joint-results.zip'):
                if (ROOT/n).is_file():z.write(ROOT/n,n)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    print('结果：sample40-results.zip；40ms候选不等于实采通过；首错保存，不自动重试。',flush=True)
    return final


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check-bundle',action='store_true');m.add_argument('--short',action='store_true');a=p.parse_args()
    if a.check_bundle:print(json.dumps(verify_package(ROOT),ensure_ascii=False))
    else:raise SystemExit(0 if short()['passed'] else 1)
