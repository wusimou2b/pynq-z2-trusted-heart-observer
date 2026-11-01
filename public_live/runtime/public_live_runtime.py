"""Public orchestration around the unchanged numeric and device lifecycle bodies.

Functions execute only when the four-stage entry invokes them. Import is stdlib.
"""
from functools import partial
import importlib
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time
import uuid

sys.dont_write_bytecode = True
_RETAINED_SHORT = []


def display_context(release_contract):
    from public_live_contract import activate_runtime
    released=activate_runtime(release_contract)
    root=Path(released['runtime_root'])/'frozen/base'
    dependencies=root/'deps'
    cached=importlib.import_module('run_v3a25_cached_live')
    if Path(cached.__file__).resolve()!=dependencies/'run_v3a25_cached_live.py':
        raise ValueError('mixed public cached renderer module')
    # Source/asset hashes were verified above. These are public release IDs,
    # not the private historical bundle's numerical-qualification receipts.
    release_root=Path(released['root'])
    manifest=json.loads((release_root/'public-live-manifest.json').read_text('utf-8'))
    tracked={str(release_root/item['path']):item['sha256'] for item in manifest['files']}
    context=dict(root=dependencies,effective_root=root,tracked_hashes=tracked,
        owner_manifest_sha256=released['manifest_sha256'],
        effective_manifest_sha256=released['manifest_sha256'],
        release_manifest_sha256=released['manifest_sha256'],
        historical_numerical_qualification=False)
    return context,cached


def short_target(connection,release_contract,run_id):
    from public_live_contract import activate_runtime
    context=activate_runtime(release_contract)
    from main_ps_exit_worker import defer_offline_pandas
    from main_heart_process import ps_worker
    # Reuse the existing local pandas deferral; never substitute a pandas stub.
    with defer_offline_pandas(context['runtime_root']):
        return ps_worker(connection,'python_fixed',root=context['runtime_root'],
            prepared_source=None,run_id=run_id,release_contract=release_contract)


def short(release_contract):
    from public_live_contract import verify_release
    context=verify_release(release_contract)
    ctx=mp.get_context('spawn');parent,child=ctx.Pipe()
    process=ctx.Process(target=short_target,args=(child,release_contract,uuid.uuid4().hex),
        name='trusted-heart-public-short-ps',daemon=False)
    ready=None;failure=None;started=False
    try:
        process.start();started=True;child.close()
        if not parent.poll(60.):raise TimeoutError('public PS READY60s exceeded')
        message=parent.recv()
        if len(message)!=3 or message[:2]!=(0,'ready'):
            raise RuntimeError('public PS short did not return READY: '+repr(message[:2]))
        ready=message[2]
        native=ready.get('native_statistics') or {}
        if (ready.get('release_manifest_sha256')!=context['manifest_sha256']
            or ready.get('historical_numerical_qualification') is not False
            or ready.get('worker_hardware_imported') is not False
            or ready.get('hardware_source')!='python_fixed'
            or ready.get('entry_confirmation_checks')!=6
            or ready.get('main_heart_mode')!='one_sample_continuous_v1'
            or ready.get('warmup_slots')!=700 or ready.get('warmup_raw')!=700
            or native.get('binary_sha256')!=context['assets']['native_binary']['sha256']
            or native.get('c_sha256')!=context['assets']['native_source']['sha256']):
            raise ValueError('public PS READY identity/warmup differs')
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
    finally:
        if started:
            try:parent.send((1,'close',None))
            except (OSError,EOFError,BrokenPipeError):pass
            process.join(1.)
        parent.close()
        if not started:child.close()
    natural=bool(started and not process.is_alive() and process.exitcode==0)
    exitcode=process.exitcode if started else None
    if started and process.is_alive():
        # No PL was authorized. Retain the owned PS process and refuse every
        # next stage; never claim exit or make an automatic second attempt.
        _RETAINED_SHORT.append(process)
        failure=failure or dict(type='RuntimeError',message='PS did not exit naturally within original1s close gate; process retained')
    elif started:process.close()
    verify_release(release_contract)
    return dict(schema='trusted_heart_public_short_v1',passed=bool(natural and failure is None),
        release_manifest_sha256=context['manifest_sha256'],ready_info=ready,error=failure,
        hardware_accessed=False,formal_steps=0,backend_requests=0,
        ready_timeout_seconds=60,warmup_slots=700,join_seconds=1,
        natural_exit=natural,exitcode=exitcode,forced_termination=False,
        cleanup_complete=natural,historical_numerical_qualification=False,
        new_release_board_verified=False)


def preview20(release_contract):
    from public_live_contract import verify_release
    from public_live_identity import require_short_receipt
    context=verify_release(release_contract)
    require_short_receipt(context['runtime_root'],release_contract)
    from compact_delivery_runtime import installed
    from compact_run_video_split import qualify20
    with installed(context['runtime_root'],context['manifest_sha256'],
                   video_only=True,release_contract=release_contract):
        return qualify20(hardware=True,confirmation='RUN-VIDEO-PROCESS20',
            expected_manifest_sha256=context['manifest_sha256'],release_contract=release_contract)


def prepare(release_contract):
    from public_live_contract import verify_release
    from public_live_identity import require_preview_receipt
    context=verify_release(release_contract)
    require_preview_receipt(context['runtime_root'],release_contract)
    from continuous_run import prepare as retained
    return retained(release_contract=release_contract)


def run(release_contract):
    from public_live_contract import verify_release
    from public_live_identity import require_preview_receipt
    context=verify_release(release_contract)
    require_preview_receipt(context['runtime_root'],release_contract)
    import continuous_run as parent
    from demo_continuous_runtime import start_owner
    from joint_startup import replace_attribute
    from video_split_guard import with_startup300
    expected=context['manifest_sha256']
    starter=partial(start_owner,demo_expected=expected,expected=expected,
        expected_split_manifest_sha256=expected,
        expected_journal_manifest_sha256=expected,
        expected_schedule_manifest_sha256=expected,
        expected_manifest_sha256=expected,run_epoch=uuid.uuid4().hex)
    # Preserve the already-qualified joint video startup300 wrapper. No time
    # limit, queue, quality or native-call protection is relaxed here.
    with replace_attribute(parent,'drive_owner',with_startup300(parent.drive_owner)):
        return parent.run(hardware=True,confirmation='RUN-CONTINUOUS25',
            release_contract=release_contract,owner_starter=starter)
