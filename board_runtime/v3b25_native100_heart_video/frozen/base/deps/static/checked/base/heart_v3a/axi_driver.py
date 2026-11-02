"""有界、独占线程锁的PS邮箱驱动；任何设备故障锁定到显式reset。"""
import math
import threading
import time
from .axi_contract import (REGISTERS as R,SHADOW_OFFSETS,ID_VALUE,VERSION_VALUE,
    SUBMIT,ACK,SOFT_RESET,SNAPSHOT,NlmsReply,validate_packet,encode_signed24,decode_signed32)

class NlmsAxiDriver:
    source='pl_mmio'
    def __init__(self,io,*,timeout_s=.020):
        if isinstance(timeout_s,bool) or not isinstance(timeout_s,(int,float)) or not math.isfinite(timeout_s) or timeout_s<=0:
            raise ValueError('timeout_s必须为正有限秒数')
        self.io=io;self.timeout_s=float(timeout_s);self._lock=threading.RLock();self._fault=''

    def _read(self,name):
        value=self.io.read(R[name])
        if type(value) is not int or not 0<=value<=0xffffffff:
            raise RuntimeError(f'读寄存器{name}未返回32位无符号整数')
        return value

    def _healthy(self):
        if self._fault: raise RuntimeError('PL故障已锁定，须显式reset：'+self._fault)

    def identify(self):
        with self._lock:
            ident,version=self._read('ID'),self._read('VERSION')
            if ident!=ID_VALUE or version!=VERSION_VALUE: raise RuntimeError('NLMS ID／VERSION不匹配，禁止使用旧Overlay')
            return dict(id=ident,version=version)

    def transact(self,packet):
        packet=validate_packet(packet)
        with self._lock:
            self._healthy()
            stage='身份检查'
            try:
                self.identify();epoch=self._read('EPOCH')
                if self._read('STATUS')!=0: raise RuntimeError('邮箱忙或存在未确认旧结果')
                stage='写入完整输入包'
                words=(packet.sequence,packet.flags,encode_signed24(packet.desired_int),
                    *(encode_signed24(v) for v in packet.references),packet.beta_int)
                for offset,value in zip(SHADOW_OFFSETS,words): self.io.write(offset,value)
                if self._read('INPUT_WRITTEN')!=127: raise RuntimeError('输入包未完整写入')
                stage='提交／等待结果'
                self.io.write(R['COMMAND'],SUBMIT)
                deadline=time.monotonic()+self.timeout_s
                while True:
                    if time.monotonic()>=deadline: raise TimeoutError('PL调用超时；已提交样本不自动重投')
                    status=self._read('STATUS')
                    if status & ~3: raise RuntimeError('邮箱STATUS非法')
                    if status&2: break
                stage='读取／核对结果'
                reply=NlmsReply(self._read('RESULT_SEQUENCE'),self._read('RESULT_EPOCH'),
                    self._read('RESULT_BETA'),decode_signed32(self._read('CANDIDATE')),
                    decode_signed32(self._read('OUTPUT')),self._read('RESULT_STATUS'),self._read('RESULT_LATENCY'))
                if time.monotonic()>=deadline: raise TimeoutError('PL完整读回超时，不能返回半包')
                if reply.sequence!=packet.sequence or reply.epoch!=epoch or self._read('EPOCH')!=epoch:
                    raise RuntimeError('结果sequence／epoch不匹配')
                if reply.beta_int!=packet.beta_int: raise RuntimeError('结果实际β与提交值不符')
                if reply.status & ~15 or reply.status&8: raise RuntimeError('PL结果算术饱和或状态非法')
                if bool(reply.status&1)!=bool(packet.flags&1) or bool(reply.status&2)!=bool(packet.flags&1 and packet.flags&2):
                    raise RuntimeError('PL结果valid／update状态不符')
                if not 0<reply.latency_cycles<=2048: raise RuntimeError('PL核心延迟超出契约')
                self.io.write(R['COMMAND'],ACK)
                return reply
            except Exception as exc:
                self._fault=stage+'：'+str(exc)
                if isinstance(exc,TimeoutError): raise
                raise RuntimeError(self._fault) from exc

    def snapshot(self):
        with self._lock:
            self._healthy()
            try:
                self.identify()
                for _ in range(3):
                    self.io.write(R['COMMAND'],SNAPSHOT)
                    generation=self._read('SNAPSHOT_GENERATION');epoch=self._read('SNAPSHOT_EPOCH')
                    result={}
                    for key,stem in (('accepted','ACCEPTED'),('emitted','EMITTED'),('clipped','CLIPPED'),('saturated','SATURATED')):
                        result[key]=self._read(stem+'_LOW') | (self._read(stem+'_HIGH')<<32)
                    result['max_latency_cycles']=self._read('MAX_LATENCY')
                    if generation==self._read('SNAPSHOT_GENERATION') and epoch==self._read('EPOCH'):
                        return dict(result,epoch=epoch,generation=generation)
                raise RuntimeError('快照持续变化，三次核对均失败')
            except Exception as exc:
                self._fault='计数快照：'+str(exc)
                raise RuntimeError(self._fault) from exc

    def reset(self):
        with self._lock:
            try:
                self.identify();previous=self._read('EPOCH')
                self.io.write(R['COMMAND'],SOFT_RESET)
                deadline=time.monotonic()+self.timeout_s
                while self._read('STATUS'):
                    if time.monotonic()>=deadline: raise TimeoutError('PL软复位超时')
                epoch=self._read('EPOCH')
                if epoch!=(previous+1)&0xffffffff or self._read('INPUT_WRITTEN')!=0:
                    raise RuntimeError('PL软复位epoch／输入状态不符')
                self._fault=''
                return epoch
            except Exception as exc:
                self._fault='显式复位：'+str(exc)
                raise RuntimeError(self._fault) from exc
