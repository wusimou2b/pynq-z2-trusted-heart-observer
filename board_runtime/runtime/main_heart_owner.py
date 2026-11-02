"""Only this trial's dual-port core and unchanged three video DMA paths.

The HWH, rather than PYNQ's choice of multi-slave dictionary key, binds both
raw apertures. The legacy mailbox remains at its real0x43c10000 address.
"""
from pathlib import Path
import time
import xml.etree.ElementTree as ET

if __package__:
    from . import joint_owner as base
    from . import yuyv_owner as video
else:
    import joint_owner as base
    import yuyv_owner as video

VLNV='v3b25.local:signal:main_heart_joint_axi:1.0'
PORTS={'main_heart_nlms':0x43c10000,'main_heart_sample':0x43ca0000}


def verify_release(directory):
    if __package__:from .main_heart_guard import verify_release as verify
    else:from main_heart_guard import verify_release as verify
    return verify(directory)


def validate_description(description):
    expected={k:v for k,v in base.WINDOWS.items() if k!='nlms_axi_0'}
    expected.update(video.EXTRA_WINDOWS)
    expected.update({n:(a,VLNV) for n,a in PORTS.items()})
    for name,(address,vlnv) in expected.items():
        item=description.get(name,{})
        if (item.get('phys_addr'),item.get('addr_range'),item.get('type'))!=(address,65536,vlnv):
            raise ValueError('main/video runtime metadata differs: '+name)
    for name in ('vision_dma','hdmi_vdma','display_dma'):
        params=description[name].get('parameters',{})
        wanted=dict(C_INCLUDE_MM2S='1',C_INCLUDE_S2MM='0',C_INCLUDE_SG='0',
            C_M_AXIS_MM2S_TDATA_WIDTH='32',C_M_AXI_MM2S_DATA_WIDTH='32')
        if name=='hdmi_vdma':wanted.update(C_NUM_FSTORES='4',C_MM2S_GENLOCK_MODE='1')
        if name=='display_dma':wanted=dict(C_INCLUDE_MM2S='0',C_INCLUDE_S2MM='1',C_INCLUDE_SG='0',
            C_M_AXI_S2MM_DATA_WIDTH='32',C_S_AXIS_S2MM_TDATA_WIDTH='32')
        if any(str(params.get(k))!=v for k,v in wanted.items()):raise ValueError('main retained DMA configuration differs: '+name)
    return dict(windows=16,main_sample_base=PORTS['main_heart_sample'],legacy_nlms_base=PORTS['main_heart_nlms'],
        one_nlms_state=True,three_video_dma_preserved=True)


class Hardware(video.Hardware):
    def download(self):
        # Recheck immediately after metadata construction while the original
        # owner lease is already held. Never displace an independently mapped
        # PL task that appeared while the cold PYNQ imports were running.
        if __package__:from .main_heart_preflight import require_pl_free
        else:from main_heart_preflight import require_pl_free
        self.occupancy_before_download=require_pl_free()
        super().download()

    def __init__(self,bit_path):
        super().__init__(bit_path)
        tree=ET.parse(Path(bit_path).with_suffix('.hwh')).getroot()
        module=tree.find("./MODULES/MODULE[@FULLNAME='/heart_main_0']")
        if module is None or module.get('VLNV')!=VLNV:raise ValueError('actual dual-port HWH identity differs')
        params={p.get('NAME'):p.get('VALUE') for p in module.findall('./PARAMETERS/PARAMETER')}
        if params.get('WATCHDOG_CYCLES')!='2000000':raise ValueError('actual whole20ms watchdog differs')
        instance=module.get('INSTANCE');ranges={}
        for item in tree.findall("./MODULES/MODULE[@FULLNAME='/processing_system7_0']/MEMORYMAP/MEMRANGE"):
            if item.get('INSTANCE')==instance:
                base_addr,high=int(item.get('BASEVALUE'),0),int(item.get('HIGHVALUE'),0)
                if item.get('MASTERBUSINTERFACE')!='M_AXI_GP0' or high-base_addr!=65535:
                    raise ValueError('actual dual-port aperture/master differs')
                ranges[item.get('SLAVEBUSINTERFACE')]=base_addr
        if ranges!={'N_AXI':PORTS['main_heart_nlms'],'S_AXI':PORTS['main_heart_sample']}:
            raise ValueError('actual dual-port address map differs')
        self.description=dict(self.description)
        for name,address in PORTS.items():self.description[name]=dict(phys_addr=address,addr_range=65536,type=VLNV)

    def mmio(self,name):
        if name in PORTS:return self._mmio_factory(PORTS[name],65536)
        return super().mmio(name)


class MainOwner(video.YuyvOwner):
    def __init__(self,directory,hardware_factory=Hardware,lease=None,**kwargs):
        super().__init__(directory,hardware_factory,lease,**kwargs)
        self.heart_backend=None

    def open(self):
        if self.state!='new':raise RuntimeError('main owner attempted already; no retry')
        self.state='opening';verify_release(self.directory)
        self._lease.acquire();self._lease_held=True
        self._hardware=self._factory(self.directory/'heart_v3b25_main.bit')
        metadata=validate_description(self._hardware.description)
        self.download_attempts+=1;self._hardware.download();self._downloaded=True
        if not self._hardware.is_loaded():raise RuntimeError('new main Overlay not current')
        for name in ('vision_0','vision_control',*video.DMA_CHANNELS,'yuyv_control','main_heart_sample'):
            self._io[name]=self._hardware.mmio(name)
        # Runtime alias only; this is the new core's old-compatible N_AXI port.
        self._io['nlms_axi_0']=self._hardware.mmio('main_heart_nlms')
        identities={}
        for name,wanted in {'nlms_axi_0':(0x4e4c3304,0x10000),'vision_0':(0x56334231,0x10000),
                            'main_heart_sample':(0x484d3235,0x20000)}.items():
            actual=(int(self._io[name].read(0)),int(self._io[name].read(4)))
            if actual!=wanted:raise RuntimeError('main silicon identity differs: '+name)
            identities[name]=dict(id=actual[0],version=actual[1])
        self._trusted=True;halted=self._halt_paths()
        if not all(v['halted'] and not v.get('error_bits') for v in halted.values()):
            raise RuntimeError('main entry requires all three DMA paths halted without errors')
        identities.update(metadata=metadata,vision_reset=self._hold_vision_reset(),stopped_dma=halted)
        self.state='bound';return identities

    def heart_mmio(self):
        if self.state!='bound' or not self._hardware.is_loaded():raise RuntimeError('main owner no longer current')
        return self._io['main_heart_sample']

    def close(self):
        if self._cleanup is not None:return self._cleanup
        heart=dict(quiescent=False,cleanup_complete=False)
        if not self.download_attempts:heart=dict(quiescent=True,cleanup_complete=True,no_download=True)
        elif self._trusted and self._hardware.is_loaded():
            try:
                if self.heart_backend is not None:heart=self.heart_backend.close()
                else:
                    io=self._io['main_heart_sample'];deadline=time.monotonic()+.020;io.write(8,8)
                    while True:
                        status,learning=io.read(12),io.read(52)
                        if status&64 and status&8 and not status&3 and learning&16:break
                        if time.monotonic()>=deadline:raise TimeoutError('main STOP not physically quiescent in20ms')
                    heart=dict(quiescent=True,cleanup_complete=True,status=status)
                heart['nlms_mailbox_status']=self._io['nlms_axi_0'].read(12)
                if heart['nlms_mailbox_status']!=0:heart['cleanup_complete']=False
            except BaseException as exc:
                heart=dict(quiescent=False,cleanup_complete=False,error=dict(type=type(exc).__name__,message=str(exc)))
        result=super().close();result['main_heart']=heart
        result['cleanup_complete']=bool(result['cleanup_complete'] and heart['cleanup_complete'])
        result['quarantine_required']=not result['cleanup_complete']
        return result
