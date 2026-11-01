"""Complete register reads with pinned output and one returned state snapshot.

Original 50ms transaction/STOP deadlines, faults and ownership remain in the
audited core/base adapter. This reduces handoffs, not the protection interval.
"""
import ctypes as C
import operator

if __package__:
    from .joint_iic_native import NativeLibrary, NativeIicTransport, FIELDS, IicFault
else:
    from joint_iic_native import NativeLibrary, NativeIicTransport, FIELDS, IicFault

HANDOFF_ABI = 0x4a480001


class HandoffLibrary(NativeLibrary):
    def __init__(self, lib, *, identity):
        super().__init__(lib, identity=identity)
        lib.jih_abi.argtypes = []; lib.jih_abi.restype = C.c_uint32
        if lib.jih_abi() != HANDOFF_ABI: raise ValueError('IIC handoff ABI mismatch')
        snapshot = C.POINTER(C.c_uint64)
        lib.jih_read.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p, C.c_uint32, snapshot]
        for name in ('send', 'receive', 'stop', 'cancel'):
            getattr(lib, 'jih_' + name).argtypes = getattr(lib, 'ji_' + name).argtypes + [snapshot]
        for name in ('read', 'send', 'receive', 'stop', 'cancel'): getattr(lib, 'jih_' + name).restype = C.c_int


class HandoffTransport(NativeIicTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._returned_state = (C.c_uint64 * len(FIELDS))()
        self._complete_calls = self._split_receives = 0

    def _get(self, key): return int(self._returned_state[FIELDS.index(key)])

    def _invoke(self, name, *args):
        if not self.current():
            self._overlay_invalid = True
            raise IicFault(dict(reason='overlay_changed', phase='native_entry'))
        native = 'jih_read' if name == 'complete_read' else 'jih_' + name.removeprefix('ji_')
        if name == 'complete_read': self._complete_calls += 1
        if name == 'ji_receive': self._split_receives += 1
        code = getattr(self.library.lib, native)(self._context, *args, self._returned_state)
        if not self.current():
            self._overlay_invalid = True
            raise IicFault(dict(reason='overlay_changed', phase='native_return'))
        if code != 0: raise RuntimeError('native IIC call returned fault')

    def read_register_into(self, address, register, output, length):
        if self._fault: raise self._fault
        address = self._address(address); register = operator.index(register); length = operator.index(length)
        if not 0 <= register <= 255 or not 1 <= length <= 192: raise ValueError('unsupported complete register read')
        # Validate and pin before ji_send starts the original absolute deadline.
        target = (C.c_ubyte * length).from_buffer(output)
        self._new()
        try:
            self._invoke('complete_read', address, register, target, length)
            # C already copied into the caller's pinned buffer. Preserve the
            # Python return-boundary deadline check, including Overlay checking.
            if self.clock_ns() >= self._get('deadline_ns'):
                raise IicFault(dict(reason='timeout', phase='copy_complete_data'))
            self._record(bytes(target)); self._unlock()
            return length
        except BaseException as exc: self._error(exc)

    def report(self):
        result = super().report()
        result.update(complete_register_read=True, state_snapshot_fields=len(FIELDS),
            handoff_strategy='one_native_select_receive_direct_copy_and_state',
            complete_read_calls=self._complete_calls, split_receive_calls=self._split_receives,
            transaction_timeout_seconds=.050, stop_timeout_seconds=.050)
        return result


def sensor_bus_type(original):
    class CompleteReadSensorBus(original):
        def read_registers(self, address, register, length):
            if length <= 0: return b''
            length = int(length)
            received = self.ffi.new('unsigned char[]', length)
            buffer = self.ffi.buffer(received, length)
            count = self.iic.read_register_into(int(address), int(register) & 255, buffer, length)
            if count != length: raise IOError('complete IIC register read count mismatch')
            return bytes(buffer)
    return CompleteReadSensorBus
