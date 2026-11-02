"""Single owner for the distinct YUYV pair, including S2MM stop and retained lock."""
import json
from pathlib import Path
import time

if __package__:
    from . import joint_owner as base
else:
    import joint_owner as base


EXTRA_WINDOWS={'display_dma':(0x44a10000,'xilinx.com:ip:axi_dma:7.1'),
               'yuyv_control':(0x41250000,'xilinx.com:ip:axi_gpio:2.0')}
PAIR_NAMES={'heart_v3b25_yuyv.bit','heart_v3b25_yuyv.hwh'}
DMA_CHANNELS={'vision_dma':(0,0x770),'hdmi_vdma':(0,0xff0),'display_dma':(0x30,0x770)}


def verify_pair(directory):
    directory=Path(directory)
    path=directory/'yuyv-artifacts.json'
    if path.is_symlink():raise ValueError('artifact manifest symlink')
    manifest=json.loads(path.read_text('utf-8'))
    if (manifest.get('schema')!='v3b25_yuyv_artifacts_v1' or manifest.get('purpose')!='controlled_board_trials_only'
        or set(manifest.get('files',{}))!=PAIR_NAMES):raise ValueError('unreviewed YUYV artifact map')
    for name,digest in manifest['files'].items():
        if base._hash(directory/name)!=digest:raise ValueError('YUYV artifact identity mismatch: '+name)
    return {'pair_integrity_verified':True,'files':dict(manifest['files']),'hardware_accessed':False}


def validate_description(description):
    base.validate_description(description)
    for name,(address,vlnv) in EXTRA_WINDOWS.items():
        item=description.get(name,{})
        if (item.get('phys_addr'),item.get('addr_range'),item.get('type'))!=(address,65536,vlnv):
            raise ValueError('new runtime control metadata mismatch: '+name)
    params=description['display_dma'].get('parameters',{})
    expected=dict(C_INCLUDE_MM2S='0',C_INCLUDE_S2MM='1',C_INCLUDE_SG='0',
                  C_M_AXI_S2MM_DATA_WIDTH='32',C_S_AXIS_S2MM_TDATA_WIDTH='32')
    if any(str(params.get(k))!=v for k,v in expected.items()):raise ValueError('writeback DMA configuration mismatch')
    return {'windows':15,'vdma_frame_stores':4,'writeback_s2mm_only':True}


class Hardware(base.PynqHardware):
    def mmio(self,name):
        if name in EXTRA_WINDOWS:return self._mmio_factory(EXTRA_WINDOWS[name][0],65536)
        return super().mmio(name)


class RetainedLease:
    def __init__(self,actual):self.actual,self.held=actual,False
    def acquire(self):self.actual.acquire();self.held=True
    def release(self):pass
    def finish(self):
        if self.held:self.actual.release();self.held=False


class YuyvOwner(base.JointOwner):
    def __init__(self,directory,hardware_factory=Hardware,lease=None,**kwargs):
        self.retained_lease=RetainedLease(lease if lease is not None else base.BoardLease())
        super().__init__(directory,hardware_factory,self.retained_lease,**kwargs)

    def open(self):
        if self.state!='new':raise RuntimeError('single owner already attempted')
        self.state='opening';self._event('checking_yuyv_pair')
        verify_pair(self.directory)
        self._lease.acquire();self._lease_held=True
        self._hardware=self._factory(self.directory/'heart_v3b25_yuyv.bit')
        validate_description(self._hardware.description)
        self.download_attempts+=1;self._event('explicit_yuyv_download_attempt')
        self._hardware.download();self._downloaded=True
        if not self._hardware.is_loaded():raise RuntimeError('download returned but YUYV Overlay not current')
        for name in (*base.IDS,'vision_control',*DMA_CHANNELS,'yuyv_control'):
            self._io[name]=self._hardware.mmio(name)
        identities={}
        for name,expected in base.IDS.items():
            ident,version=int(self._io[name].read(0)),int(self._io[name].read(4))
            if ident!=expected or version!=0x10000:raise RuntimeError('silicon identity mismatch: '+name)
            identities[name]={'id':ident,'version':version}
        self._trusted=True
        halted=self._halt_paths()
        if not all(v['halted'] for v in halted.values()) or any(v.get('error_bits') for v in halted.values()):
            raise RuntimeError('all three DMA channels must halt without entry errors')
        identities.update(vision_reset=self._hold_vision_reset(),metadata=validate_description(self._hardware.description),stopped_dma=halted)
        self.state='bound';self._event('yuyv_identity_bound')
        return identities

    def _halt_paths(self):
        result={}
        for name,(offset,mask) in DMA_CHANNELS.items():
            item={'halted':False};result[name]=item
            try:
                if not self._hardware.is_loaded():raise RuntimeError('Overlay changed; no halt writes allowed')
                io=self._io[name]
                io.write(offset,int(io.read(offset))&~1)
                deadline=time.monotonic()+self._halt_timeout
                while True:
                    status,control=int(io.read(offset+4)),int(io.read(offset))
                    if status&1 and not control&1:
                        item.update(halted=True,status=status,control=control,error_bits=status&mask);break
                    if time.monotonic()>=deadline:raise TimeoutError('DMA halt not confirmed: '+name)
                    time.sleep(.001)
            except Exception as exc:item['error']={'type':type(exc).__name__,'message':str(exc)}
        return result

    def _hold_vision_reset(self):
        result=super()._hold_vision_reset()
        if self._io['yuyv_control'].read(0)!=0:raise RuntimeError('color/broadcaster reset not confirmed')
        result['color_reset_held']=True
        return result

    def close(self):
        result=super().close()
        result['quarantine_required']=not result['cleanup_complete']
        result['actual_lease_released']=not self.retained_lease.held
        return result

    def release_after_buffers(self,*,buffers_released):
        if not self._cleanup or not self._cleanup['cleanup_complete'] or not buffers_released:
            raise RuntimeError('DMA halt and all buffer release must be confirmed before unlocking')
        self.retained_lease.finish()
        self._cleanup['actual_lease_released']=True
