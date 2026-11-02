"""AXI邮箱v1唯一契约；非法输入不截断、无效载荷归零。"""
from dataclasses import dataclass, replace
from typing import Protocol

ID_VALUE=0x4E4C3304
VERSION_VALUE=0x00010000
BASE_ADDRESS=0x43C10000
ADDRESS_RANGE=65536
BETA_DEFAULT=32212255
SUBMIT,ACK,SOFT_RESET,SNAPSHOT=1,2,4,8
REGISTERS=dict(ID=0x00,VERSION=0x04,COMMAND=0x08,STATUS=0x0c,
    SEQUENCE=0x10,FLAGS=0x14,DESIRED=0x18,REF_X=0x1c,REF_Y=0x20,REF_Z=0x24,BETA=0x28,
    RESULT_SEQUENCE=0x30,RESULT_STATUS=0x34,CANDIDATE=0x38,OUTPUT=0x3c,
    RESULT_BETA=0x40,RESULT_LATENCY=0x44,EPOCH=0x48,RESULT_EPOCH=0x4c,
    ACCEPTED_LOW=0x50,ACCEPTED_HIGH=0x54,EMITTED_LOW=0x58,EMITTED_HIGH=0x5c,
    CLIPPED_LOW=0x60,CLIPPED_HIGH=0x64,SATURATED_LOW=0x68,SATURATED_HIGH=0x6c,
    MAX_LATENCY=0x70,SNAPSHOT_GENERATION=0x74,SNAPSHOT_EPOCH=0x78,INPUT_WRITTEN=0x7c)
SHADOW_OFFSETS=tuple(REGISTERS[n] for n in ('SEQUENCE','FLAGS','DESIRED','REF_X','REF_Y','REF_Z','BETA'))

@dataclass(frozen=True)
class NlmsPacket:
    sequence:int
    desired_int:int
    references:tuple[int,int,int]
    flags:int=3
    beta_int:int=BETA_DEFAULT

@dataclass(frozen=True)
class NlmsReply:
    sequence:int
    epoch:int
    beta_int:int
    candidate_int:int
    output_int:int
    status:int
    latency_cycles:int

class RegisterIo(Protocol):
    def read(self,offset:int)->int: ...
    def write(self,offset:int,value:int)->None: ...

class NlmsBackend(Protocol):
    source:str
    def transact(self,packet:NlmsPacket)->NlmsReply: ...
    def reset(self)->int: ...

def _integer(value,low,high,label):
    if type(value) is not int or not low<=value<=high:
        raise ValueError(f'{label}需要范围内整数，不能截断')
    return value

def encode_signed24(value:int)->int:
    return _integer(value,-(1<<23),(1<<23)-1,'24位输入') & 0xffffffff

def decode_signed32(word:int)->int:
    _integer(word,0,0xffffffff,'32位寄存器')
    return word-(1<<32) if word & (1<<31) else word

def validate_packet(packet:NlmsPacket)->NlmsPacket:
    if not isinstance(packet,NlmsPacket): raise ValueError('需要NlmsPacket')
    _integer(packet.sequence,0,0xffffffff,'sequence')
    _integer(packet.flags,0,15,'flags')
    _integer(packet.beta_int,1,1<<30,'beta_int')
    if not packet.flags & 1:
        return replace(packet,desired_int=0,references=(0,0,0))
    encode_signed24(packet.desired_int)
    if type(packet.references) is not tuple or len(packet.references)!=3:
        raise ValueError('需要三轴整数tuple')
    for value in packet.references: encode_signed24(value)
    return packet
