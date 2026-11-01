"""Bounded, narrow normal-mode AXI IIC transport for the frozen SensorBus.

Normal-mode register sequencing adapted from AMD/Xilinx embeddedsw
xilinx_v2024.1, xiic_l.c / xiic_l.h (not a claim about installed libiic.so).
Copyright (C) 2002 - 2021 Xilinx, Inc. All rights reserved.
SPDX-License-Identifier: MIT

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Deadlines bound software polling only while MMIO and OS scheduling respond.
No reset, FIFO drain, automatic retry, native XIic_Send/Recv, or hardware import.
"""
import copy
import operator
import threading
import time

CR, SR, TX, RX, ISR, RFD = 0x100, 0x104, 0x108, 0x10c, 0x20, 0x120
ENABLE, MASTER, TRANSMIT, NO_ACK, RESTART = 1, 4, 8, 16, 32
ARB_LOST, TX_ERROR, TX_EMPTY, RX_FULL, NOT_BUSY = 1, 2, 4, 8, 16
BUS_BUSY, RX_EMPTY, TX_FIFO_EMPTY = 4, 64, 128
TRANSACTION_SECONDS = .050
STOP_SECONDS = .050


class IicFault(RuntimeError):
    def __init__(self, details):
        self.details = details
        super().__init__('IIC '+details['reason']+' at '+details['phase'])


class AxiIicTransport:
    """send(register, RSTART) + receive is one 50ms transaction, not two.

    The nonblocking mutex remains held across that pair; only its originating
    thread may receive. An interloper is rejected without touching the bus.
    """
    def __init__(self, mmio, *, clock=time.monotonic, current=lambda: True):
        self.mmio, self.clock, self.current = mmio, clock, current
        self._lock = threading.Lock()
        self._owner = self._pending = None
        self._in_call = self._closed = False
        self._fault = self._quiescence = None
        self._phase = 'new'
        self._started = self._deadline = 0.
        self._context = {}
        self._last = {}
        self._completed = self._started_count = self._stop_attempts = 0

    def _check(self, phase):
        self._phase = phase
        if self.clock() >= self._deadline:
            raise IicFault(dict(reason='timeout', phase=phase))
        if not self.current():
            raise IicFault(dict(reason='overlay_changed', phase=phase))

    def _read(self, offset, phase):
        self._check(phase)
        value = int(self.mmio.read(offset))
        self._last[hex(offset)] = value
        self._check(phase)
        return value

    def _write(self, offset, value, phase):
        self._check(phase)
        self.mmio.write(offset, int(value))
        self._check(phase)

    def _clear(self, mask, phase):
        # IISR is toggle-on-write, NOT write-one-to-clear. Never set absent bits.
        present = self._read(ISR, phase) & mask
        if present:
            self._write(ISR, present, phase)

    def _wait_isr(self, ready, errors, phase):
        while True:
            flags = self._read(ISR, phase)
            if flags & errors:
                raise IicFault(dict(reason='status_error', phase=phase, interrupt_status=flags))
            if flags & ready:
                return flags

    def _wait_sr(self, busy, phase, *, errors=0):
        while True:
            status = self._read(SR, phase)
            if errors:
                flags = self._read(ISR, phase)
                if flags & errors:
                    raise IicFault(dict(reason='status_error', phase=phase, interrupt_status=flags))
            if bool(status & BUS_BUSY) == busy:
                return status

    def _new(self, address, register, length):
        if self._fault is not None:
            raise self._fault
        if self._closed:
            raise RuntimeError('IIC transport already closed; no retry')
        if not self._lock.acquire(False):
            raise RuntimeError('IIC transaction outstanding; interleaving forbidden')
        self._owner, self._in_call = threading.get_ident(), True
        self._started = self.clock()
        self._deadline = self._started+TRANSACTION_SECONDS
        self._context = dict(address=address, register=register, requested_bytes=length,
                             received_bytes=0, queued_data_bytes=0,
                             consumed_ppg_unknown=address == 0x57 and register == 7)
        self._started_count += 1
        self._quiescence = None

    def _unlock(self):
        self._owner = self._pending = None
        self._in_call = False
        self._lock.release()

    def _error(self, exc):
        if self._fault is None:
            details = dict(self._context, phase=self._phase,
                           elapsed_seconds=max(0., self.clock()-self._started),
                           last_registers=dict(self._last),
                           exception_type=type(exc).__name__, exception_message=str(exc))
            if isinstance(exc, IicFault): details.update(exc.details)
            else: details['reason'] = 'call_exception'
            self._fault = IicFault(details)
        self._quiescence = self._bounded_stop()
        self._unlock()
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise exc
        raise self._fault from exc

    @staticmethod
    def _address(address):
        address = operator.index(address)
        if address not in (0x57, 0x68): raise ValueError('only MAX30102/MPU6050 addresses supported')
        return address

    def send(self, address, data, length, option=0):
        if self._fault is not None: raise self._fault
        address = self._address(address)
        length, option = operator.index(length), operator.index(option)
        if (length, option) not in ((2, 0), (1, 1)):
            raise ValueError('only register write or repeated-start register selection supported')
        payload = bytes(operator.index(data[index]) for index in range(length))
        self._new(address, payload[0], length)
        try:
            status = self._wait_sr(False, 'bus_free')
            control = self._read(CR, 'bus_free')
            if status & (RX_EMPTY | TX_FIFO_EMPTY) != RX_EMPTY | TX_FIFO_EMPTY or control & (MASTER | RESTART):
                raise IicFault(dict(reason='unclaimed_controller_state', phase='bus_free'))
            self._write(TX, address << 1, 'address')
            self._clear(TX_EMPTY | TX_ERROR | ARB_LOST, 'address')
            self._write(CR, ENABLE | MASTER | TRANSMIT, 'address')
            self._wait_sr(True, 'bus_busy', errors=TX_ERROR | ARB_LOST)
            self._clear(NOT_BUSY, 'bus_busy')
            for index, value in enumerate(payload):
                self._wait_isr(TX_EMPTY, TX_ERROR | ARB_LOST | NOT_BUSY, 'tx_empty')
                last = index+1 == length
                if last and not option:
                    self._write(CR, ENABLE | TRANSMIT, 'send_stop')
                self._write(TX, value, 'tx_data')
                self._context['queued_data_bytes'] += 1
                if last and option:
                    self._clear(TX_EMPTY, 'repeat_ready')
                    self._wait_isr(TX_EMPTY, TX_ERROR | ARB_LOST | NOT_BUSY, 'repeat_ready')
                    status = self._read(SR, 'repeat_ready')
                    if not status & TX_FIFO_EMPTY or not status & BUS_BUSY:
                        raise IicFault(dict(reason='restart_not_ready', phase='repeat_ready'))
                    self._write(CR, ENABLE | MASTER | TRANSMIT | RESTART, 'repeat_ready')
                self._clear(TX_EMPTY, 'tx_data')
            if option:
                self._pending = address
                self._in_call = False
            else:
                self._finish_stop()
                self._completed += 1
                self._unlock()
            return length
        except BaseException as exc:
            self._error(exc)

    def _finish_stop(self):
        # Final transmit NACK/ARB_LOST must not turn into successful BNB.
        self._wait_isr(NOT_BUSY, TX_ERROR | ARB_LOST, 'stop')
        self._wait_sr(False, 'bus_released', errors=TX_ERROR | ARB_LOST)

    def receive(self, address, data, length, option=0):
        if self._fault is not None: raise self._fault
        address = self._address(address)
        length = operator.index(length)
        if operator.index(option) != 0 or not 1 <= length <= 192:
            raise ValueError('only complete 1..192-byte register reads supported')
        if self._pending != address or self._owner != threading.get_ident() or self._in_call:
            raise RuntimeError('receive requires same-thread outstanding register selection')
        # Reject a non-writable/short caller buffer before clocking additional bytes.
        try:
            data[length-1] = data[length-1]
        except BaseException as exc:
            self._in_call = True
            self._error(exc)
        self._in_call = True
        self._context.update(requested_bytes=length, received_bytes=0)
        try:
            self._check('receive_entry')
            self._clear(RX_FULL | TX_ERROR | ARB_LOST, 'read_address')
            self._write(RFD, 0, 'read_address')
            control = self._read(CR, 'read_address')
            if control & (ENABLE | MASTER | RESTART) != ENABLE | MASTER | RESTART:
                raise IicFault(dict(reason='restart_lost', phase='read_address'))
            control &= ~TRANSMIT
            if length == 1: control |= NO_ACK
            self._write(CR, control, 'read_address')
            self._write(TX, (address << 1) | 1, 'read_address')
            received = bytearray(length)
            for index in range(length):
                remaining = length-index
                # The receiver's normal last-byte NACK generates TX_ERROR.
                errors = ARB_LOST | NOT_BUSY | (TX_ERROR if remaining > 1 else 0)
                self._wait_isr(RX_FULL, errors, 'rx_full')
                control = self._read(CR, 'rx_data')
                if remaining == 1: self._write(CR, ENABLE, 'receive_stop')
                if remaining == 2: self._write(CR, control | NO_ACK, 'last_nack')
                received[index] = self._read(RX, 'rx_data') & 255
                self._context['received_bytes'] += 1
                self._clear(RX_FULL | TX_ERROR | ARB_LOST, 'rx_data')
            self._finish_stop()
            self._write(CR, 0, 'disable_after_receive')
            for index, value in enumerate(received):
                self._check('copy_complete_data')
                data[index] = value
            self._completed += 1
            self._unlock()
            return length
        except BaseException as exc:
            self._error(exc)

    def _bounded_stop(self):
        """One extra bounded attempt; never drain RX/TX or reset anything."""
        if self._quiescence is not None: return self._quiescence
        self._stop_attempts += 1
        result = dict(iic_quiesced=False, stop_attempts=self._stop_attempts, error=None)
        deadline = self.clock()+STOP_SECONDS
        def check():
            if self.clock() >= deadline: raise TimeoutError('IIC STOP/idle confirmation timeout')
            if not self.current(): raise RuntimeError('Overlay changed; no IIC cleanup writes')
        def read(offset):
            check(); value = int(self.mmio.read(offset)); check()
            return value
        def write(value):
            check(); self.mmio.write(CR, value); check()
        try:
            control = read(CR)
            write(ENABLE | (control & TRANSMIT))
            while True:
                status, control = read(SR), read(CR)
                if not status & BUS_BUSY and not control & (MASTER | RESTART):
                    if status & (TX_FIFO_EMPTY | RX_EMPTY) != TX_FIFO_EMPTY | RX_EMPTY:
                        raise RuntimeError('IIC FIFO not empty; do not drain or release')
                    write(0)
                    if read(CR) != 0: raise RuntimeError('IIC disable not confirmed')
                    result.update(iic_quiesced=True, status=status, control=0)
                    break
        except BaseException as exc:
            result['error'] = dict(type=type(exc).__name__, message=str(exc))
        return result

    def quiesce(self):
        if self._quiescence is not None: return copy.deepcopy(self._quiescence)
        if self._pending is not None and not self._in_call and self._owner == threading.get_ident():
            # An interrupt between the two public calls must not strand our own
            # held bus/lock. Other threads may not cancel an owned transaction.
            self._closed = True
            self._fault = IicFault(dict(self._context, reason='abandoned_selection',
                phase='quiesce', elapsed_seconds=max(0., self.clock()-self._started),
                last_registers=dict(self._last)))
            self._quiescence = self._bounded_stop()
            self._unlock()
            return copy.deepcopy(self._quiescence)
        if self._in_call or self._pending is not None:
            return dict(iic_quiesced=False, stop_attempts=self._stop_attempts,
                        error=dict(type='RuntimeError', message='IIC transaction still owned'))
        if not self._lock.acquire(False):
            return dict(iic_quiesced=False, stop_attempts=self._stop_attempts,
                        error=dict(type='RuntimeError', message='IIC call still active'))
        try:
            self._closed = True
            self._quiescence = self._bounded_stop()
            return copy.deepcopy(self._quiescence)
        finally:
            self._lock.release()

    def report(self):
        return dict(schema='v3b25_bounded_iic_v1', mode='normal',
                    transaction_timeout_seconds=TRANSACTION_SECONDS, stop_timeout_seconds=STOP_SECONDS,
                    transactions_started=self._started_count, transactions_completed=self._completed,
                    active_call=self._in_call, register_selection_pending=self._pending is not None,
                    stop_attempts=self._stop_attempts,
                    fault=copy.deepcopy(self._fault.details) if self._fault else None,
                    quiescence=copy.deepcopy(self._quiescence))
