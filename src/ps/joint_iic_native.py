"""Narrow frozen SensorBus adapter; production per-byte work stays in C.

Overlay checks are at native-call boundaries, not each MMIO access. Never
reconfigure PL concurrently. A deadline is not a guarantee against stuck AXI
or a process not being scheduled. No hardware/scientific import at module load.
"""
from collections import deque
import copy
import ctypes as C
import operator
import threading
import time
if __package__:
    from .joint_iic import IicFault
else:
    from joint_iic import IicFault

ABI=0x4a490002
FIELDS=('reason','phase','started','completed','requested','received','address','register',
        'start_ns','deadline_ns','elapsed_ns','stop_done','quiesced','stop_reason','pending','closed',
        'cr','sr','isr','rx','raw_rx_reads')
REASONS={1:'timeout',2:'status_error',3:'controller_state',4:'argument',5:'clock_failure',6:'abandoned_selection'}
PHASES={1:'bus_free',2:'address',3:'bus_busy',4:'tx_empty',5:'repeat_ready',6:'read_address',
        7:'rx_full',8:'rx_data',9:'last_nack',10:'stop',11:'bus_released',12:'disable',
        13:'copy_complete_data',14:'abort',15:'quiesce'}


class NativeLibrary:
    def __init__(self,lib,*,identity):
        self.lib,self.identity=lib,copy.deepcopy(identity)
        lib.ji_abi.argtypes=[];lib.ji_abi.restype=C.c_uint32
        lib.ji_size.argtypes=[];lib.ji_size.restype=C.c_size_t
        lib.ji_init.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];lib.ji_init.restype=C.c_int
        lib.ji_send.argtypes=[C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32,C.c_uint32]
        lib.ji_receive.argtypes=[C.c_void_p,C.c_uint32,C.c_void_p,C.c_uint32]
        lib.ji_stop.argtypes=lib.ji_cancel.argtypes=[C.c_void_p]
        for name in ('ji_send','ji_receive','ji_stop','ji_cancel'):getattr(lib,name).restype=C.c_int
        lib.ji_get.argtypes=[C.c_void_p,C.c_uint32];lib.ji_get.restype=C.c_uint64
        if lib.ji_abi()!=ABI or not 64<=lib.ji_size()<=4096:
            raise ValueError('native IIC ABI/context size mismatch')

    def initialize(self,mmio):
        array=getattr(mmio,'array',None)
        if (array is None or getattr(getattr(array,'dtype',None),'str',None) not in ('<u4','=u4') or
            array.ndim!=1 or not array.flags.c_contiguous or not array.flags.writeable or
            array.nbytes<0x124 or array.ctypes.data%4):
            raise ValueError('IIC requires pinned aligned contiguous uint32 MMIO array')
        storage=(C.c_uint64*((self.lib.ji_size()+7)//8))()
        context=C.cast(storage,C.c_void_p)
        if self.lib.ji_init(context,C.c_void_p(array.ctypes.data),array.nbytes)!=0:
            raise ValueError('native context initialization rejected mapping')
        return storage,context,(mmio,array)

    def get(self,context,key):return int(self.lib.ji_get(context,FIELDS.index(key)))


class NativeIicTransport:
    def __init__(self,mmio,*,library,current=lambda:True,clock_ns=time.monotonic_ns):
        self.library,self.current,self.clock_ns=library,current,clock_ns
        self._storage,self._context,self._pins=library.initialize(mmio)
        self._lock=threading.Lock();self._owner=self._pending=None
        self._in_call=self._closed=self._overlay_invalid=False
        self._fault=self._quiescence=None
        self._trace=deque(maxlen=128);self._pointers=deque(maxlen=64);self._trace_seen=0

    def _get(self,key):return self.library.get(self._context,key)

    def _invoke(self,name,*args):
        if not self.current():
            self._overlay_invalid=True
            raise IicFault(dict(reason='overlay_changed',phase='native_entry'))
        code=getattr(self.library.lib,name)(self._context,*args)
        if not self.current():
            self._overlay_invalid=True
            raise IicFault(dict(reason='overlay_changed',phase='native_return'))
        if code!=0:raise RuntimeError('native IIC call returned fault')

    def _native_quiescence(self):
        return dict(iic_quiesced=bool(self._get('quiesced')),stop_attempts=self._get('stop_done'),
                    error=None if self._get('quiesced') else dict(type='IicFault',
                        message=REASONS.get(self._get('stop_reason'),'STOP not confirmed')))

    def _stop_once(self):
        if self._quiescence is not None:return self._quiescence
        if self._overlay_invalid:
            self._quiescence=dict(iic_quiesced=False,stop_attempts=self._get('stop_done'),
                error=dict(type='RuntimeError',message='Overlay changed; no cleanup MMIO'))
        elif self._get('stop_done'):
            self._quiescence=self._native_quiescence()
        else:
            try:self._invoke('ji_stop')
            except BaseException as exc:
                self._quiescence=dict(iic_quiesced=False,stop_attempts=self._get('stop_done'),
                    error=dict(type=type(exc).__name__,message=str(exc)))
            else:self._quiescence=self._native_quiescence()
        return self._quiescence

    def _record(self,output=None):
        sequence=self._get('started')
        if sequence==0 or sequence==self._trace_seen:return
        self._trace_seen=sequence
        self._trace.append(dict(transaction=sequence,address=self._get('address'),register=self._get('register'),
            requested_bytes=self._get('requested'),received_bytes=self._get('received'),
            elapsed_ns=self._get('elapsed_ns'),completed=self._get('reason')==0,
            reason=REASONS.get(self._get('reason')),phase=PHASES.get(self._get('phase'),'unknown')))
        if (output is not None and self._get('address')==0x57 and self._get('register')==4 and len(output)==3):
            self._pointers.append(dict(transaction=sequence,raw_bytes=list(output),
                                       completed_ns=self.clock_ns()))

    def _unlock(self):
        self._pending=self._owner=None;self._in_call=False
        self._lock.release()

    def _error(self,exc):
        if self._fault is None:
            reason=self._get('reason')
            details=dict(reason=REASONS.get(reason,'call_exception'),
                phase=PHASES.get(self._get('phase'),'python'),address=self._get('address'),
                register=self._get('register'),requested_bytes=self._get('requested'),
                received_bytes=self._get('received'),raw_rx_reads=self._get('raw_rx_reads'),
                consumed_ppg_unknown=self._get('address')==0x57 and self._get('register')==7,
                elapsed_seconds=self._get('elapsed_ns')/1e9,
                last_registers={hex(offset):self._get(key) for offset,key in
                    ((0x100,'cr'),(0x104,'sr'),(0x20,'isr'),(0x10c,'rx'))},
                exception_type=type(exc).__name__,exception_message=str(exc))
            if isinstance(exc,IicFault) and not reason:details.update(exc.details)
            self._fault=IicFault(details)
        # A native error already performed its one STOP attempt. Python-side
        # abandonment requires the same bounded stop but must not retry a fault.
        try:
            if not self._get('reason') and not self._overlay_invalid:
                try:self._invoke('ji_cancel')
                except BaseException:pass
            self._record();self._stop_once()
        finally:
            # An interrupt can land just after the success path released its
            # mutex. Do not replace that original interrupt with double-release.
            if self._owner==threading.get_ident():self._unlock()
        if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise exc
        raise self._fault from exc

    def _new(self):
        if self._fault:raise self._fault
        if self._closed:raise RuntimeError('native IIC already closed; no retry')
        if not self._lock.acquire(False):raise RuntimeError('IIC transaction outstanding; interleaving forbidden')
        self._owner=threading.get_ident();self._in_call=True

    @staticmethod
    def _address(address):
        value=operator.index(address)
        if value not in (0x57,0x68):raise ValueError('only MAX30102/MPU6050 supported')
        return value

    def send(self,address,data,length,option=0):
        if self._fault:raise self._fault
        address=self._address(address);length=operator.index(length);option=operator.index(option)
        if (length,option) not in ((2,0),(1,1)):raise ValueError('unsupported register send')
        payload=bytes(operator.index(data[i]) for i in range(length))
        cdata=(C.c_ubyte*length).from_buffer_copy(payload)
        self._new()
        try:
            self._invoke('ji_send',address,cdata,length,option)
            if option:self._pending=address;self._in_call=False
            else:self._record();self._unlock()
            return length
        except BaseException as exc:self._error(exc)

    def receive(self,address,data,length,option=0):
        if self._fault:raise self._fault
        address=self._address(address);length=operator.index(length)
        if operator.index(option)!=0 or not 1<=length<=192:raise ValueError('unsupported register receive')
        if self._pending!=address or self._owner!=threading.get_ident() or self._in_call:
            raise RuntimeError('receive requires originating thread and pending selection')
        self._in_call=True
        try:
            data[length-1]=data[length-1]
            output=(C.c_ubyte*length)()
            self._invoke('ji_receive',address,output,length)
            if self.clock_ns()>=self._get('deadline_ns'):
                raise IicFault(dict(reason='timeout',phase='copy_complete_data'))
            for index,value in enumerate(output):data[index]=value
            if self.clock_ns()>=self._get('deadline_ns'):
                raise IicFault(dict(reason='timeout',phase='copy_complete_data'))
            self._record(bytes(output));self._unlock()
            return length
        except BaseException as exc:self._error(exc)

    def quiesce(self):
        if self._quiescence is not None:return copy.deepcopy(self._quiescence)
        if self._pending is not None and not self._in_call and self._owner==threading.get_ident():
            self._closed=True;self._in_call=True
            try:self._error(IicFault(dict(reason='abandoned_selection',phase='quiesce')))
            except IicFault:pass
            return copy.deepcopy(self._quiescence)
        if self._in_call or self._pending is not None or not self._lock.acquire(False):
            return dict(iic_quiesced=False,stop_attempts=self._get('stop_done'),
                        error=dict(type='RuntimeError',message='IIC call/selection still owned'))
        try:self._closed=True;return copy.deepcopy(self._stop_once())
        finally:self._lock.release()

    def report(self):
        return dict(schema='v3b25_native_iic_v1',mode='normal_native_c',
            transaction_timeout_seconds=.050,stop_timeout_seconds=.050,
            overlay_check_scope='before_and_after_native_call_not_each_MMIO',
            transactions_started=self._get('started'),transactions_completed=self._get('completed'),
            active_call=self._in_call,register_selection_pending=self._pending is not None,
            stop_attempts=self._get('stop_done'),fault=copy.deepcopy(self._fault.details) if self._fault else None,
            quiescence=copy.deepcopy(self._quiescence),trace=copy.deepcopy(list(self._trace)),
            pointer_history=copy.deepcopy(list(self._pointers)),native_build=copy.deepcopy(self.library.identity))
