"""隔离的定点软件后端；没有PL周期测量，不冒称FPGA。"""
from .axi_contract import NlmsReply,validate_packet
from .runtime_fixed_nlms import RuntimeFixedNlms4

class FixedNlmsBackend:
    source='python_fixed'
    def __init__(self):
        self.model=RuntimeFixedNlms4();self.epoch=0;self.last_packet=None
    def transact(self,packet):
        p=validate_packet(packet);self.last_packet=p
        s=self.model.step_int(p.desired_int,p.references,beta_int=p.beta_int,
            valid=bool(p.flags&1),update=bool(p.flags&2),reset=bool(p.flags&4),bypass=bool(p.flags&8))
        status=int(s.output_valid)|int(s.update_applied)<<1|int(s.weight_clipped)<<2|int(s.arithmetic_saturated)<<3
        return NlmsReply(p.sequence,self.epoch,p.beta_int,s.candidate_int,s.output_int,status,0)
    def reset(self):
        self.model.reset(clear_counters=True);self.epoch=(self.epoch+1)&0xffffffff
        return self.epoch
