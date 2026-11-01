"""Stdlib-only candidate assessment; never claims full-frame numerical checking."""
import json
from pathlib import Path
import statistics

if __package__:
    from .joint_video_guard import FLAGS,TOP_FILES,sha,write_new,verify_package,notebook_code_hash
else:
    from joint_video_guard import FLAGS,TOP_FILES,sha,write_new,verify_package,notebook_code_hash

BASE_SHA='429a52feda6ad5b5ee8258b0c2bec966489205d64d4472d515d7f8c79b525f7b'
EXTRAS={'joint_video_live.py','joint_video_live_guard.py','joint_video_live_worker.py','run_joint_video_live.py','README_VIDEO_LIVE.md'}
FILES=TOP_FILES|{'joint-video-manifest.json'}|EXTRAS
FIELDS={'pixel_count','luma_sum','luma_min','luma_max','difference_valid','diff_sum','diff_max','reason'}
PARTS={'precheck','camera','vision','verification_capture','hdmi'}
TRANSPORT={'pack_bgr','zero_x','flush','mmio_read','mmio_write','wait_sleep','other'}
MODE='two_frames_checked_only_after_hardware_cleanup'


def verify_live(root):
    root=Path(root);base=verify_package(root)
    if sha(root/'joint-video-manifest.json')!=BASE_SHA:raise ValueError('original video manifest changed')
    doc=json.loads((root/'video-live-manifest.json').read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_video_live_package_v1' or set(doc.get('files',{}))!=FILES
            or doc.get('formal_seconds')!=20 or doc.get('target_fps')!=15 or doc.get('reference_mode')!=MODE
            or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('live candidate scope/file/flag identity changed')
    for name,digest in doc['files'].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise ValueError('live file changed: '+name)
    if notebook_code_hash(root/'VideoLive.ipynb')!=doc.get('notebook_code_sha256'):
        raise ValueError('live executable Notebook changed')
    return dict(base,live_manifest_sha256=sha(root/'video-live-manifest.json'),reference_mode=MODE)


def assess(report):
    m=report.get('metrics') or {};c=report.get('cleanup') or {};j=c.get('joint') or {}
    identity=(report.get('identity') or {}).get('joint_identity') or {};post=report.get('post_verification') or {}
    n=m.get('completed_frames',0);dma=j.get('dma') or {}
    return dict(full_duration=report.get('stop_reason')=='duration_complete' and report.get('requested_formal_seconds')==20
        and (m.get('formal_elapsed_seconds') or 0)>=20,
        no_fault=report.get('fault') is None and report.get('publication_error') is None,
        joint_identity=(identity.get('nlms') or {}).get('id')==0x4e4c3304 and
            (identity.get('vision') or {}).get('id')==0x56334231 and (identity.get('metadata') or {}).get('windows')==13,
        one_download=j.get('download_attempts')==1,
        exact_counts=n>=3 and n==m.get('records_saved')==c.get('captured_frames')==c.get('submitted_frames')==c.get('vision_completed_frames'),
        reference_scope=report.get('reference_mode')==MODE and report.get('all_frames_reference_verified') is False
            and report.get('formal_reference_calls')==0,
        post_check=post.get('attempted') is True and post.get('after_hardware_cleanup') is True and
            post.get('sample_count')==2 and post.get('total_frames')==n and post.get('matched') is True
            and post.get('all_frames_verified') is False and post.get('images_saved') is False,
        cleanup=c.get('cleanup_complete') is True and c.get('quarantine_required') is False and
            j.get('cleanup_complete') is True and len(dma)==2 and all(v.get('halted') is True and v.get('error_bits')==0 for v in dma.values())
            and all(c.get(k) is True for k in ('buffers_released','lease_released','camera_release_returned','hdmi_close_returned')),
        inputs_unchanged=report.get('inputs_unchanged') is True,
        formal_flags_false=all(report.get(k) is False for k in FLAGS))


def audit_live(directory,report):
    checks=dict(parse_hash=False,counts=False,source=False,timing=False,transport=False,coverage=False,rate=False)
    result=dict(checks=checks,rows=0,timing_summary_ms={},transport_summary_ms={},error=None)
    try:
        data=(Path(directory)/'frames.jsonl').read_bytes()
        rows=[json.loads(s) for s in data.decode('utf-8').splitlines()];n=len(rows);result['rows']=n
        m=report.get('metrics') or {};post=report.get('post_verification') or {};samples=post.get('samples') or []
        checks['parse_hash']=bool(data.endswith(b'\n') and sha(Path(directory)/'frames.jsonl')==report.get('frames_sha256'))
        checks['counts']=n>=3 and n==m.get('completed_frames')==m.get('records_saved')
        times=[r['read_completed_ns'] for r in rows]
        checks['source']=bool(n and len({r['vision']['epoch'] for r in rows})==1 and all(
            r['source_sequence']==i and r['vision']['source_sequence']==i and r['vision']['frame_index']==i
            and r['vision']['timestamp_ns']==r['read_completed_ns'] and r['vision']['pixel_count']==19200
            and r['reference_checked'] is False and r['same_frame_equal'] is None and r['hdmi_submitted'] is True
            for i,r in enumerate(rows)) and all(b>a for a,b in zip(times,times[1:])))
        for i,r in enumerate(rows):
            v=r['vision'];delta=None if i==0 else times[i]-times[i-1]
            valid=i>0 and delta<=250000000
            checks['source'] &= (v['source_previous_sequence']==(i-1 if i else None) and v['pair_elapsed_ns']==delta
                and v['missed_frames']==0 and v['difference_valid']==valid and
                v['reason']==('first_frame' if i==0 else 'ok' if valid else 'timestamp_gap') and
                (valid or v['diff_sum'] is None and v['diff_max'] is None))
        checks['counts'] &= sum(r['vision']['difference_valid'] for r in rows)==m.get('valid_difference_frames')
        def partition(t,names):
            values=list(t['wall_ns'].values())
            return (set(t['wall_ns'])==names and isinstance(t['total_ns'],int) and not isinstance(t['total_ns'],bool)
                and all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in values) and t['total_ns']==sum(values))
        checks['timing']=bool(n and all(partition(r['timing'],PARTS) for r in rows))
        checks['transport']=bool(n and all(partition(r['transport_timing'],TRANSPORT) and r['transport_timing']['valid'] is True
            and set(r['transport_timing']['calls'])==TRANSPORT-{'other'}
            and all(isinstance(x,int) and not isinstance(x,bool) and x>=0 for x in r['transport_timing']['calls'].values())
            and all(r['transport_timing']['calls'][k]==1 for k in ('pack_bgr','zero_x','flush')) for r in rows))
        for flag,key,target,names in [('timing','timing','timing_summary_ms',PARTS),('transport','transport_timing','transport_summary_ms',TRANSPORT)]:
            if checks[flag]:
                for name in sorted(names|{'total'}):
                    values=[(r[key]['total_ns'] if name=='total' else r[key]['wall_ns'][name])/1e6 for r in rows]
                    result[target][name]=dict(count=n,mean=statistics.mean(values),median=statistics.median(values),maximum=max(values))
        checks['coverage']=bool(post.get('sample_count')==len(samples)==2 and post.get('total_frames')==n and
            post.get('after_hardware_cleanup') is True and post.get('all_frames_verified') is False and post.get('matched') is True and
            [s['source_sequence'] for s in samples]==[0,1] and all(s['read_completed_ns']==rows[i]['read_completed_ns']
            and set(s['expected'])==FIELDS and set(s['actual'])==FIELDS and
            s['actual']=={k:rows[i]['vision'][k] for k in FIELDS} and s['expected']==s['actual'] and s['matched'] is True
            and s['mismatches']=={} and len(s['bgr_sha256'])==64 for i,s in enumerate(samples)))
        elapsed=m.get('formal_elapsed_seconds') or 0
        checks['rate']=bool(elapsed>0 and abs(m['application_submit_fps']-n/elapsed)<1e-9 and
            report.get('target_15fps_observed')==(n/elapsed>=15))
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    return result
