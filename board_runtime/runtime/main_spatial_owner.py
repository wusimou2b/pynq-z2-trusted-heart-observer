"""One retained owner for main heart SAMPLE, spatial v2 and original sensors."""
if __package__:
    from . import main_heart_owner as main
    from . import joint_owner as base
    from . import yuyv_owner as video
    from .main_heart_guard import verify_release
else:
    import main_heart_owner as main, joint_owner as base, yuyv_owner as video
    from main_heart_guard import verify_release

SPATIAL_VLNV = 'v3b25.local:vision:vision_spatial_axi_lite:2.0'


class Hardware(main.Hardware):
    def heart_iic(self):
        if not self.is_loaded():
            raise RuntimeError('integrated Overlay changed before IIC binding')
        return self._overlay.axi_iic_0


def validate_description(description):
    expected = {n:v for n,v in {**base.WINDOWS,**video.EXTRA_WINDOWS}.items() if n!='nlms_axi_0'}
    expected['vision_0'] = (0x43c80000,SPATIAL_VLNV)
    expected.update({n:(address,main.VLNV) for n,address in main.PORTS.items()})
    for name,(address,vlnv) in expected.items():
        item = description.get(name,{})
        if (item.get('phys_addr'),item.get('addr_range'),item.get('type')) != (address,65536,vlnv):
            raise ValueError('main/spatial metadata differs: '+name)
    # Reuse reviewed DMA parameter validation without treating a different
    # vision identity as equivalent: the actual vision was checked above.
    retained = dict(description)
    retained['vision_0'] = dict(description['vision_0'],type=base.WINDOWS['vision_0'][1])
    main.validate_description(retained)
    return dict(windows=16,spatial_version=0x20000,grid=[4,3],one_nlms_state=True,
                three_video_dma_preserved=True,main_sample_base=0x43ca0000)


class IntegratedOwner(main.MainOwner):
    def __init__(self,directory,hardware_factory=Hardware,lease=None,**kwargs):
        super().__init__(directory,hardware_factory,lease,**kwargs)

    def open(self):
        if self.state != 'new':
            raise RuntimeError('integrated owner already attempted')
        self.state = 'opening'
        verify_release(self.directory)
        self._lease.acquire();self._lease_held=True
        self._hardware=self._factory(self.directory/'heart_v3b25_main.bit')
        metadata=validate_description(self._hardware.description)
        self.download_attempts+=1;self._hardware.download();self._downloaded=True
        if not self._hardware.is_loaded():
            raise RuntimeError('integrated Overlay not current')
        for name in ('vision_0','vision_control',*video.DMA_CHANNELS,'yuyv_control','main_heart_sample'):
            self._io[name]=self._hardware.mmio(name)
        self._io['nlms_axi_0']=self._hardware.mmio('main_heart_nlms')
        identities={}
        for name,want in {'nlms_axi_0':(0x4e4c3304,0x10000),'vision_0':(0x56334232,0x20000),
                          'main_heart_sample':(0x484d3235,0x20000)}.items():
            actual=(int(self._io[name].read(0)),int(self._io[name].read(4)))
            if actual != want:
                raise RuntimeError('integrated silicon identity differs: '+name)
            identities[name]=dict(id=actual[0],version=actual[1])
        self._trusted=True
        halted=self._halt_paths()
        if not all(v['halted'] and not v.get('error_bits') for v in halted.values()):
            raise RuntimeError('integrated entry requires three DMA halted without errors')
        identities.update(metadata=metadata,vision_reset=self._hold_vision_reset(),stopped_dma=halted)
        self.state='bound'
        return identities

    def heart_ports(self):
        if self.state != 'bound' or not self._hardware.is_loaded():
            raise RuntimeError('integrated owner not bound/current')
        return dict(iic=self._hardware.heart_iic(),nlms_mmio=self._io['nlms_axi_0'],
                    fifo_mmio=self._hardware.mmio('axi_fifo_mm_s_0'))
