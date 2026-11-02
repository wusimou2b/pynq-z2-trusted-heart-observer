"""Only scalar IPC encoding changes; inherited publish/consume remain intact.

The channel is private to the already authenticated owner/video processes.
No sensor, pairing, IMU evidence key, refresh interval, queue or lock change.
Unknown JSON shapes retain the original codec. Never cache a current status.
"""
import math
import pickle
if __package__:
    from .video_split_state import StateChannel as Original, PACKET_BYTES
else:
    from video_split_state import StateChannel as Original, PACKET_BYTES

TAG='v3b25_video_scalars_binary_v1'
TOP=frozenset(('state','fault','safety','latest','published_ns','imu_observed_ns'))
ROW=frozenset(('raw','read_ns','finished_ns','epoch','generation','frame'))
ATOMIC=frozenset((str,int,bool,type(None)))


def flat(values):
    for value in values:
        kind=type(value)
        if kind is float:
            if not math.isfinite(value):return False
        elif kind not in ATOMIC:return False
    return True


def qualified(p):
    if type(p) is not dict or p.keys()!=TOP or type(p['safety']) is not dict:return False
    if not flat((p['state'],p['fault'],p['published_ns'],p['imu_observed_ns'])):return False
    if not flat(p['safety'].values()) or not all(type(k) is str for k in p['safety']):return False
    r=p['latest']
    if r is None:return True
    return (type(r) is dict and r.keys()==ROW and type(r['raw']) is dict and type(r['frame']) is dict
        and all(type(k) is str for k in r['raw']) and all(type(k) is str for k in r['frame'])
        and flat((r['read_ns'],r['finished_ns'],r['epoch'],r['generation']))
        and flat(r['raw'].values()) and flat(r['frame'].values()))


class StateChannel(Original):
    def _encode(self,packet):
        if not qualified(packet):return super()._encode(packet)
        data=pickle.dumps((TAG,self.run_epoch,self.manifest_sha256,packet),protocol=4)
        if len(data)>PACKET_BYTES:raise BufferError('video scalar packet exceeds fixed capacity')
        return data

    def _decode(self,data):
        if not data.startswith(b'\x80\x04'):return super()._decode(data)
        envelope=pickle.loads(data)
        if (type(envelope) is not tuple or len(envelope)!=4
                or envelope[:3]!=(TAG,self.run_epoch,self.manifest_sha256)):
            raise ValueError('video state identity mismatch')
        # Like the retained JSON decoder, verify the envelope here. Original
        # restore() still checks raw/frame fields before exposing any result.
        return envelope[3]
