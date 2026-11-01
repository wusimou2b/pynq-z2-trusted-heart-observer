"""Cold browser addon identity; preserve applicable inherited capture/video gates."""
import json
from pathlib import Path

if __package__:
    from .heart_video_guard import verify_package as verify_base,assess_candidate as assess_base
    from .joint_heart_guard import sha,write_new,notebook_code_hash
else:
    from heart_video_guard import verify_package as verify_base,assess_candidate as assess_base
    from joint_heart_guard import sha,write_new,notebook_code_hash

MANIFEST='browser-heart-manifest.json'
NOTEBOOK='BrowserHeartVideo60.ipynb'
BASE_MANIFEST_SHA='064cdd483305fb0941538f79489bfb033f05f8998ad2e7bd86a7829cd5901f2c'
ADDONS={'browser_heart_transport.py','browser_heart_display.py','browser_heart_client.js',
        'browser_heart_worker.py','browser_heart_guard.py','browser_heart_budget.py',
        'run_browser_heart.py','README_BROWSER_HEART.md'}


def verify_package(root):
    root=Path(root).resolve();original=verify_base(root)
    path=root/MANIFEST
    if path.is_symlink():raise ValueError('browser manifest symlink')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_browser_heart_package_v1'
            or set(doc.get('files',{}))!=ADDONS
            or doc.get('base_manifest_sha256')!=BASE_MANIFEST_SHA
            or sha(root/'heart-video5-manifest.json')!=BASE_MANIFEST_SHA
            or doc.get('renderer')!='browser_canvas_v1'
            or doc.get('history_capacity')!=500 or doc.get('refresh_period_ms')!=500
            or any(doc.get(k) is not False for k in ('algorithm_changed','runtime_limits_changed','board_tested'))):
        raise ValueError('browser package scope changed')
    for name,digest in doc['files'].items():
        if (root/name).is_symlink() or sha(root/name)!=digest:raise ValueError('browser source changed: '+name)
    if (root/NOTEBOOK).is_symlink() or notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):
        raise ValueError('browser executable Notebook changed')
    return dict(original,package_manifest_sha256=sha(path),browser_canvas_display=True)


def assess_candidate(directory,inherited,owner,**kwargs):
    result=assess_base(directory,inherited,owner,**kwargs)
    display=(inherited.get('summary') or {}).get('display') or {}
    state=display.get('cache') or {}
    result['checks']['browser_waveform_path']=(display.get('renderer')=='browser_canvas_v1'
        and state.get('history_objects_constructed')==0 and state.get('curve_reads',0)>0
        and state.get('status_reads',0)>0)
    result.update(browser_display=dict(renderer=display.get('renderer'),reader=state,
        browser_render_measured=False),joint_60s_pilot_completed=all(result['checks'].values()),
        strict_realtime_verified=False,accuracy_verified=False)
    return result
