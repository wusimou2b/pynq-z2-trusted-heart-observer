"""Scalar-only feature collection; instructions never become predictions."""
import math
from statistics import median

if __package__:
    from .roi_motion_core import SourceAdapter,integer
else:
    from roi_motion_core import SourceAdapter,integer

PHASES=('STATIC','LIGHT','HEAVY','STATIC')
SPATIAL_FIELDS=('changed_pixels','block_diff_sums','block_changed_pixels','motion_pixel_ratio',
    'block_motion_pixel_ratios','block_mean_differences','max_block_mean_difference')


def checked_spatial(stats):
    sp=stats.get('spatial')
    if not isinstance(sp,dict) or sp.get('schema')!='v3b25_spatial_counts_v1':raise ValueError('spatial snapshot required')
    if any(sp.get(k)!=stats.get(k) for k in ('frame_index','source_sequence','epoch','pixel_count','luma_sum','luma_min',
        'luma_max','difference_valid','diff_sum','diff_max')):raise ValueError('spatial snapshot identity differs')
    if (sp.get('grid'),sp.get('roi'),sp.get('block_pixel_count'),sp.get('pixel_threshold'))!=([4,3],[80,60,240,180],1600,8):
        raise ValueError('fixed spatial grid/ROI/T8 changed')
    if not stats['difference_valid']:
        if any(sp.get(k) is not None for k in ('diff_sum','diff_max',*SPATIAL_FIELDS[:-1])):
            raise ValueError('invalid pair contains spatial features')
        return sp
    sums,counts=sp.get('block_diff_sums'),sp.get('block_changed_pixels')
    if not isinstance(sums,list) or not isinstance(counts,list) or len(sums)!=12 or len(counts)!=12:
        raise ValueError('twelve spatial counters required')
    maximum=integer(sp['diff_max'],'maximum',high=255)
    for total,count in zip(sums,counts):
        integer(total,'block sum',high=1600*maximum);integer(count,'block count',high=1600)
        if count*8>total or total>count*255+(1600-count)*7:raise ValueError('spatial threshold bounds differ')
    if sum(sums)!=sp['diff_sum'] or sum(counts)!=integer(sp.get('changed_pixels'),'changed_pixels',high=19200):
        raise ValueError('spatial total differs')
    for key,wanted in (('motion_pixel_ratio',sum(counts)/19200),('block_motion_pixel_ratios',[v/1600 for v in counts]),
        ('block_mean_differences',[v/1600 for v in sums])):
        if sp.get(key)!=wanted:raise ValueError('spatial ratio differs: '+key)
    return sp


class Features:
    def __init__(self):self.source=SourceAdapter()

    def consume(self,stats,*,elapsed_ns,now_ns):
        integer(elapsed_ns,'elapsed_ns',high=60_000_000_000-1)
        sp=checked_spatial(stats);source=self.source.consume(stats,now_ns=now_ns)
        index=elapsed_ns//15_000_000_000
        fields={name:None for name in SPATIAL_FIELDS}
        if source['valid']:
            fields.update({name:sp[name][:] if isinstance(sp[name],list) else sp[name] for name in SPATIAL_FIELDS[:-1]})
            fields['max_block_mean_difference']=max(sp['block_mean_differences'])
        return dict(source,**fields,pixel_threshold=8,phase_index=index,phase_label=PHASES[index],
            phase_remaining_seconds=math.ceil(((index+1)*15_000_000_000-elapsed_ns)/1e9),
            segment_part='transition' if elapsed_ns%15_000_000_000<2_000_000_000 else 'stable',
            classification_performed=False,freshness_checked_ns=now_ns)


def distribution(values):
    if not values:return dict(count=0,minimum=None,p10=None,median=None,p90=None,maximum=None)
    values=sorted(values)
    return dict(count=len(values),minimum=values[0],p10=values[math.ceil(len(values)*.1)-1],median=median(values),
        p90=values[math.ceil(len(values)*.9)-1],maximum=values[-1])


def summarize(rows,epoch_ns):
    integer(epoch_ns,'epoch_ns',1)
    if not rows or len(rows)>300:raise ValueError('finite nonempty feature journal required')
    replay=Features();groups=[[[],[]] for _ in PHASES];valid=0
    for i,row in enumerate(rows):
        ts=integer(row['admitted_ns'],'admitted_ns',epoch_ns)
        if (row['source_sequence']!=i or row['vision']['source_sequence']!=i or row['vision']['frame_index']!=i
            or row['read_completed_ns']!=ts or row.get('hdmi_submitted') is not True):
            raise ValueError('feature journal source/submission changed')
        wanted=replay.consume(row['vision'],elapsed_ns=ts-epoch_ns,now_ns=row['features']['freshness_checked_ns'])
        if row['features']!=wanted:raise ValueError('feature journal does not match PL snapshot/source/phase')
        groups[wanted['phase_index']][int(wanted['segment_part']=='stable')].append(wanted)
        valid+=int(wanted['valid'])
    def part(values):
        available=[v for v in values if v['valid']];reasons={}
        for v in values:
            if not v['valid']:reasons[v['reason']]=reasons.get(v['reason'],0)+1
        result=dict(total=len(values),valid=len(available),unavailable=len(values)-len(available),
            valid_coverage=len(available)/len(values) if values else None,unavailable_reasons=reasons)
        for key in ('score','motion_pixel_ratio','max_block_mean_difference'):
            result[key]=distribution([v[key] for v in available])
        return result
    return dict(schema='v3b25_spatial_feature_summary_v1',formal_records=len(rows),valid_features=valid,
        unavailable_features=len(rows)-valid,pixel_threshold=8,transition_seconds_per_phase=2,
        segments=[dict(index=i,instructed_label=label,transition=part(groups[i][0]),stable=part(groups[i][1])) for i,label in enumerate(PHASES)],
        classification_performed=False,thresholds_refitted=False,human_protocol_confirmed=None,screen_dynamic_observed=None,
        labels_scope='instructions only; not verified motion truth',three_class_acceptance_passed=False,
        accuracy_verified=False,board_ddr_verified=False,full_v3b_acceptance_passed=False)
