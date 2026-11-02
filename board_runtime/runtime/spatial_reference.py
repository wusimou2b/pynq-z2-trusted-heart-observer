"""Offline integer golden for PL spatial counters; no classifier or live imports."""
from numbers import Integral

import numpy as np


def _image(value):
    if not isinstance(value,np.ndarray) or value.dtype!=np.dtype('uint8'):
        raise TypeError('uint8 array required')
    if value.ndim!=2 or min(value.shape)<=0 or value.shape[0]%3 or value.shape[1]%4:
        raise ValueError('ROI height divisible by3 and width divisible by4 required')
    return value


def spatial_stats(current,previous,*,threshold=8,compare_enable=True):
    """Row-major 4x3 grid; changed is abs(delta)>=threshold, not motion truth."""
    _image(current)
    if isinstance(threshold,(bool,np.bool_)) or not isinstance(threshold,Integral):
        raise TypeError('integer pixel threshold required')
    if not 1<=threshold<=255:
        raise ValueError('pixel threshold outside1..255')
    if type(compare_enable) is not bool:
        raise TypeError('boolean compare_enable required')
    if previous is not None:
        _image(previous)
        if previous.shape!=current.shape:
            raise ValueError('paired ROI geometry changed')
    valid=previous is not None and compare_enable
    result=dict(schema='v3b25_spatial_counts_v1',grid=[4,3],pixel_threshold=int(threshold),
        pixel_count=current.size,block_pixel_count=current.size//12,difference_valid=valid,
        diff_sum=None,diff_max=None,changed_pixels=None,block_diff_sums=None,block_changed_pixels=None)
    if valid:
        delta=np.abs(current.astype(np.int16)-previous.astype(np.int16))
        h,w=current.shape[0]//3,current.shape[1]//4
        blocks=delta.reshape(3,h,4,w).transpose(0,2,1,3)
        result.update(diff_sum=int(delta.sum(dtype=np.uint64)),diff_max=int(delta.max()),
            changed_pixels=int(np.count_nonzero(delta>=threshold)),
            block_diff_sums=blocks.sum(axis=(2,3),dtype=np.uint64).reshape(-1).tolist(),
            block_changed_pixels=np.count_nonzero(blocks>=threshold,axis=(2,3)).reshape(-1).tolist())
    return result
