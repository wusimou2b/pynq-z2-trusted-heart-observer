"""Immutable Lean319 plus exit observers and retained original ARM proofs."""
import io
import json
from pathlib import Path
from zipfile import ZipFile

if __package__:
    from .lean_ps_guard import verify_package as verify_lean, verify_source, local, sha, write_new, notebook_code_hash
else:
    from lean_ps_guard import verify_package as verify_lean, verify_source, local, sha, write_new, notebook_code_hash

LEAN_SHA = '00abc85b9a44c697bbec8bda1944d51bb601ae102b5b1d485569748b33b5fccb'
SHORT_SHA = '3d1ff2eabac854f66dcc0a8441f85753d97a82e4a5d7d2ed12df2fceebb4b8dd'
PLAIN_SHA = '5d60771ef80cff34bd80c1d89b17b91b6975dace184a952611dfe486e623aca1'
FILES = {'joint_exit_guard.py', 'joint_exit_worker.py', 'joint_exit_report.py', 'run_joint_exit.py',
         'README_JOINT_EXIT60.md', 'ps_exit_trace.py', 'ps_exit_finalizing.py',
         'proofs/lean-ps-short-results.zip', 'proofs/lean-exit-plain-results.zip'}
BOOK = 'JointExit60.ipynb'
MANIFEST = 'joint-exit60-manifest.json'


def verify_lean_bytes(root):
    """Validate old root without importing a second copy of its modules."""
    root = Path(root).resolve()
    if sha(local(root, 'lean-ps-manifest.json')) != LEAN_SHA:
        raise ValueError('reviewed Lean manifest changed')
    d = json.loads((root/'lean-ps-manifest.json').read_text('utf-8'))
    for n, h in {**d['base_files'], **d['files']}.items():
        actual = notebook_code_hash(local(root, n)) if n.endswith('.ipynb') else sha(local(root, n))
        wanted = d['base_notebook_code'][n] if n.endswith('.ipynb') else h
        if actual != wanted:
            raise ValueError('original Lean source changed: '+n)
    if notebook_code_hash(local(root, 'LeanPS60.ipynb')) != d['notebook_code_sha256']:
        raise ValueError('original Lean Notebook code changed')
    return root


def verify_package(root):
    root = Path(root).resolve()
    base = verify_lean(root)
    if base['lean_manifest_sha256'] != LEAN_SHA:
        raise ValueError('new root no longer copies the reviewed Lean')
    d = json.loads(local(root, MANIFEST).read_text('utf-8'))
    if (d.get('schema') != 'v3b25_joint_exit60_package_v1' or set(d.get('files', {})) != FILES
        or len(d.get('base_files', {})) != 319
        or [d.get(k) for k in ('raw_hz', 'processing_hz', 'video_fps', 'formal_seconds', 'ready_seconds', 'warmup_slots', 'join_seconds')]
           != [25, 25, 5, 60, 60, 700, 1]
        or any(d.get(k) is not False for k in ('algorithm_changed', 'gc_changed', 'limits_changed', 'automatic_retry'))):
        raise ValueError('joint exit60 package scope differs')
    for n, h in {**d['base_files'], **d['files']}.items():
        actual = notebook_code_hash(local(root, n)) if n.endswith('.ipynb') else sha(local(root, n))
        if actual != (d['base_notebook_code'][n] if n.endswith('.ipynb') else h):
            raise ValueError('joint exit60 file changed: '+n)
    if notebook_code_hash(local(root, BOOK)) != d['notebook_code_sha256']:
        raise ValueError('joint exit60 Notebook code changed')
    return dict(base, joint_exit_manifest_sha256=sha(root/MANIFEST))


def read_evidence(short_path, plain_path):
    def read(path, expected, member, count):
        if sha(path) != expected:
            raise ValueError('reviewed exit proof identity differs')
        with ZipFile(path) as z:
            if len(z.namelist()) != len(set(z.namelist())) or len(z.namelist()) != count or z.testzip() is not None:
                raise ValueError('retained exit proof ZIP corrupt')
            return json.loads(z.read(member))
    short = read(short_path, SHORT_SHA, 'lean-ps-short.json', 1)
    plain = read(plain_path, PLAIN_SHA, 'lean-exit-plain.json', 2)
    info = plain['isolation']
    if not (short['passed'] is True and short['error'] is None
        and short['host_check'] is False and short['forced_termination'] is False and short['exitcode'] == 0
        and plain['mode'] == 'plain' and plain['host_check'] is False
        and plain['replay_complete'] and plain['numeric_complete'] and plain['identity_passed']
        and plain['natural_exit'] and plain['ps_exit_proven'] and plain['cleanup_complete']
        and plain['forced_termination'] is False and plain['exitcode'] == 0
        and plain['error'] is None and plain['cleanup_error'] is None
        and plain['replayed_samples'] == info['completed_steps'] == info['pl_requests'] == 1505
        and plain['difference_count'] == 0 and plain['invalid_sequences'] == [136,137,482,1063,1255]
        and plain['reference_sha256'] == plain['replay_sha256']
        and all(plain[k] is True for k in ('inputs_unchanged','gc_unchanged','numpy_unchanged'))
        and all(plain[k] is False for k in ('hardware_accessed','capture_started','video_started','physical_pl_replies_replayed'))
        and short['prepared'] == plain['source_identity']):
        raise ValueError('retained ARM exit proof not complete')
    return dict(short=short, plain=plain, short_zip_sha256=SHORT_SHA, plain_zip_sha256=PLAIN_SHA)


def match_prepared(evidence, current, old_root):
    expected_old = dict(current, runtime_root=str(old_root))
    if evidence['short']['prepared'] != expected_old or evidence['plain']['source_identity'] != expected_old:
        raise ValueError('retained proof source differs beyond explicit runtime-root alias')
    return expected_old


def verify_evidence(root, native, *, hardware=False):
    root, native = Path(root).resolve(), Path(native).resolve()
    checked = verify_package(root)
    current = verify_source(root, native, hardware=hardware)
    old = verify_lean_bytes(root.parent/'v3b25 lean ps60')
    evidence = read_evidence(root/'proofs/lean-ps-short-results.zip', root/'proofs/lean-exit-plain-results.zip')
    expected_old = match_prepared(evidence, current, old)
    if (sha(old/'lean-ps-short-results.zip') != SHORT_SHA
        or sha(root.parent/'v3b25 lean exit replay/lean-exit-plain-results.zip') != PLAIN_SHA):
        raise ValueError('original returned proof changed')
    if __package__:
        from .run_lean_ps import require_short
    else:
        from run_lean_ps import require_short
    # Call the unchanged original gate BEFORE the run's scoped binding. The
    # expected old path is explicit; no report is rewritten to claim a new run.
    if require_short(old, expected_old) != evidence['short']:
        raise ValueError('original short report differs from retained proof')
    return dict(package=checked, prepared=current, original_root=str(old), evidence=evidence,
                reused_original_proof=True, new_short_test_run=False)
