"""Cold release guard. No hardware imports or implicit hardware authorization."""
import hashlib
import json
from pathlib import Path

PAIR={'heart_v3b25_main.bit','heart_v3b25_main.hwh'}
GATES=('arm287_full_assessment','whole1504_algorithm_state','fault_stop_identity',
       'driver_process_lifecycle','joint_setup_hold','digital_interfaces','cdc_reset',
       'whole_transaction_20ms')


def sha(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():raise ValueError('release member missing/symlink')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_release(directory):
    root=Path(directory).resolve()
    manifest=json.loads((root/'main-heart-artifacts.json').read_bytes())
    if manifest.get('schema')!='v3b25_main_heart_artifacts_v1' or set(manifest.get('files',{}))!=PAIR:
        raise ValueError('main artifact schema/file map differs')
    release_file=root/'main-heart-release.json'
    if sha(release_file)!=manifest.get('release_sha256'):raise ValueError('main release identity differs')
    release=json.loads(release_file.read_bytes())
    if (release.get('schema')!='v3b25_main_heart_static_release_v1' or release.get('preboard_gate_passed') is not True
        or set(release.get('gates',{}))!=set(GATES) or any(release['gates'][k] is not True for k in GATES)
        or (release.get('core_id'),release.get('core_version'))!=(0x484d3235,0x20000)):
        raise ValueError('main preboard gate incomplete; bit generation is not qualification')
    if release.get('pair')!=manifest['files']:raise ValueError('main pair/release identity differs')
    for name,digest in manifest['files'].items():
        if sha(root/name)!=digest:raise ValueError('main hardware identity differs: '+name)
    return dict(pair_integrity_verified=True,preboard_gate_passed=True,hardware_accessed=False,
        files=dict(manifest['files']),release_sha256=manifest['release_sha256'],
        command_seconds=.020,shared_step_seconds=1.,live_25hz_passed=False,full_v3b_acceptance_passed=False)
