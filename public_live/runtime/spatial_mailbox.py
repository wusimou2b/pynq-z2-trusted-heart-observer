"""Pure read-only v2 mailbox decoder; no PYNQ, configuration, ACK or classifier."""


def read_spatial_result(mmio):
    def word(offset):
        value=mmio.read(offset)
        if type(value) is not int or not 0<=value<=0xffffffff:
            raise ValueError('invalid uint32 mailbox word')
        return value
    if word(0)!=0x56334232 or word(4)!=0x20000:
        raise ValueError('new spatial magic/version required; no legacy fallback')
    if word(12)!=4:
        raise RuntimeError('spatial mailbox not in clean pending state')
    index,count,luma,diff,extrema,token,epoch=[word(o) for o in range(0x20,0x3c,4)]
    threshold,changed,area=[word(o) for o in (0x3c,0x40,0x44)]
    sums=[word(0x80+i*8) for i in range(12)]
    counts=[word(0x84+i*8) for i in range(12)]
    if (word(12),word(0x20),word(0x34),word(0x38),word(0x3c))!=(4,index,token,epoch,threshold):
        raise RuntimeError('spatial result changed during read')
    low,high,maximum=extrema&255,(extrema>>8)&255,(extrema>>16)&255
    valid=bool(extrema&(1<<24))
    if count!=19200 or area!=1600 or not 1<=threshold<=255 or extrema>>25:
        raise ValueError('spatial geometry/threshold/flags changed')
    if low>high or not low*count<=luma<=high*count:
        raise ValueError('spatial luma bounds inconsistent')
    if sum(sums)!=diff or sum(counts)!=changed or changed>count:
        raise ValueError('spatial global and block totals disagree')
    if valid:
        if (maximum==0)!=(diff==0) or maximum>diff or diff>count*maximum or (maximum<threshold and changed):
            raise ValueError('spatial difference maximum inconsistent')
        if maximum>=threshold and changed==0:
            raise ValueError('spatial threshold maximum without a counted pixel')
        for total,moving in zip(sums,counts):
            if (moving>area or total>area*maximum or moving*threshold>total
                or total>moving*255+(area-moving)*(threshold-1)):
                raise ValueError('spatial block bounds inconsistent')
    elif diff or maximum or changed or any(sums) or any(counts):
        raise ValueError('invalid pair contains spatial difference data')
    return dict(schema='v3b25_spatial_counts_v1',frame_index=index,source_sequence=token,epoch=epoch,
        grid=[4,3],roi=[80,60,240,180],pixel_count=count,block_pixel_count=area,pixel_threshold=threshold,
        luma_sum=luma,luma_min=low,luma_max=high,difference_valid=valid,
        diff_sum=diff if valid else None,diff_max=maximum if valid else None,
        changed_pixels=changed if valid else None,block_diff_sums=sums if valid else None,
        block_changed_pixels=counts if valid else None,motion_pixel_ratio=changed/count if valid else None,
        block_motion_pixel_ratios=[v/area for v in counts] if valid else None,
        block_mean_differences=[v/area for v in sums] if valid else None)
