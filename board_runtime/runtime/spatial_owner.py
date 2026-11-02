"""Distinct spatial pair owner, inheriting original three-DMA/retained-lease close."""
import json
from pathlib import Path

if __package__:
    from . import joint_owner as base
    from .yuyv_owner import YuyvOwner,Hardware,EXTRA_WINDOWS,DMA_CHANNELS
else:
    import joint_owner as base
    from yuyv_owner import YuyvOwner,Hardware,EXTRA_WINDOWS,DMA_CHANNELS

VLNV='v3b25.local:vision:vision_spatial_axi_lite:2.0'
PAIR_NAMES={'heart_v3b25_spatial.bit','heart_v3b25_spatial.hwh'}


def verify_pair(directory):
    directory=Path(directory);path=directory/'spatial-artifacts.json'
    if path.is_symlink():raise ValueError('spatial artifact symlink')
    m=json.loads(path.read_text('utf-8'))
    if (m.get('schema')!='v3b25_spatial_artifacts_v1' or m.get('purpose')!='controlled_static_board_trial_only'
        or set(m.get('files',{}))!=PAIR_NAMES or (m.get('magic'),m.get('version'),m.get('vision_base'))!=(0x56334232,0x20000,0x43c80000)
        or m.get('grid')!=[4,3] or m.get('pixel_count')!=19200 or m.get('roi')!=[80,60,240,180]):
        raise ValueError('spatial artifact identity/scope changed')
    for name,digest in m['files'].items():
        if base._hash(directory/name)!=digest:raise ValueError('spatial pair mismatch: '+name)
    return dict(pair_integrity_verified=True,files=dict(m['files']),hardware_accessed=False)


def validate_description(description):
    windows={**base.WINDOWS,**EXTRA_WINDOWS};windows['vision_0']=(0x43c80000,VLNV)
    for name,(address,vlnv) in windows.items():
        item=description.get(name,{})
        if (item.get('phys_addr'),item.get('addr_range'),item.get('type'))!=(address,65536,vlnv):
            raise ValueError('spatial runtime metadata mismatch: '+name)
    for name in DMA_CHANNELS:
        p=description[name].get('parameters',{})
        if name=='display_dma':expected=dict(C_INCLUDE_MM2S='0',C_INCLUDE_S2MM='1',C_INCLUDE_SG='0',C_M_AXI_S2MM_DATA_WIDTH='32',C_S_AXIS_S2MM_TDATA_WIDTH='32')
        else:
            expected=dict(C_INCLUDE_MM2S='1',C_INCLUDE_S2MM='0',C_INCLUDE_SG='0',C_M_AXI_MM2S_DATA_WIDTH='32',C_M_AXIS_MM2S_TDATA_WIDTH='32')
            if name=='hdmi_vdma':expected.update(C_NUM_FSTORES='4',C_MM2S_GENLOCK_MODE='1')
        if any(str(p.get(k))!=v for k,v in expected.items()):raise ValueError('spatial DMA parameters changed: '+name)
    return dict(windows=15,vdma_frame_stores=4,writeback_s2mm_only=True,spatial_version=0x20000)


class SpatialOwner(YuyvOwner):
    def open(self):
        if self.state!='new':raise RuntimeError('spatial owner already attempted')
        self.state='opening';self._event('checking_spatial_pair');verify_pair(self.directory)
        self._lease.acquire();self._lease_held=True
        self._hardware=self._factory(self.directory/'heart_v3b25_spatial.bit')
        validate_description(self._hardware.description)
        self.download_attempts+=1;self._event('explicit_spatial_download_attempt')
        self._hardware.download();self._downloaded=True
        if not self._hardware.is_loaded():raise RuntimeError('spatial Overlay not current after download')
        for name in (*base.IDS,'vision_control',*DMA_CHANNELS,'yuyv_control'):self._io[name]=self._hardware.mmio(name)
        identities={}
        for name,expected,version in (('nlms_axi_0',0x4e4c3304,0x10000),('vision_0',0x56334232,0x20000)):
            ident,actual=int(self._io[name].read(0)),int(self._io[name].read(4))
            if (ident,actual)!=(expected,version):raise RuntimeError('spatial silicon identity mismatch: '+name)
            identities[name]=dict(id=ident,version=actual)
        self._trusted=True
        halted=self._halt_paths()
        if not all(v['halted'] for v in halted.values()) or any(v.get('error_bits') for v in halted.values()):
            raise RuntimeError('all original three DMA paths must halt cleanly')
        identities.update(vision_reset=self._hold_vision_reset(),metadata=validate_description(self._hardware.description),stopped_dma=halted)
        self.state='bound';self._event('spatial_identity_bound')
        return identities
