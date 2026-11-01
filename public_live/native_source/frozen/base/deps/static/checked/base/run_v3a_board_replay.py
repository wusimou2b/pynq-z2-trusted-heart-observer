"""默认只检查交付；--hardware才加载一次新Overlay，无自动软件回退。"""
import argparse
import csv
import json
from pathlib import Path
from datetime import datetime
import uuid

from heart_v3a.delivery import validate_bundle,CSV_FIELDS
from heart_v3a.axi_contract import NlmsPacket,REGISTERS as R,BASE_ADDRESS,ADDRESS_RANGE
from heart_v3a.axi_driver import NlmsAxiDriver


def _rows(path):
    with Path(path).open(encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream)
        if tuple(reader.fieldnames or ())!=CSV_FIELDS: raise RuntimeError('公开黄金字段不符')
        rows=[{key:int(value) for key,value in row.items()} for row in reader]
    if not rows: raise RuntimeError('公开黄金不能为空')
    return rows


def _new_summary(hardware=False):
    return dict(schema='v3a_board_public_replay_v1',checked=0,controls_checked=0,mismatches=0,
        cases=[],resets=[],control_events=[],retry_count=0,public_replay_passed=False,
        backend_source='pl_mmio' if hardware else 'test_only',board_tested=False,board_replay_passed=False,
        board_ddr_verified=False,live_50hz_passed=False,auto_beta_effect_passed=False)


def _save(directory,result):
    (directory/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


def _execute_replay(driver,cases,output_dir,controls_path,*,hardware=False,preflight=None):
    """测试可注入驱动，但只有真实入口通过预检后才带hardware标记。"""
    directory=Path(output_dir).resolve();directory.mkdir(parents=True,exist_ok=False)
    result=_new_summary(hardware);result['preflight']=preflight or {}
    stage='身份检查';sequence=None
    try:
        result['identity']=driver.identify()
        paths=tuple(map(Path,cases))
        if len(paths)!=9 or sum(len(_rows(path)) for path in paths)!=15942:
            raise RuntimeError('板回放必须完整九例15942拍')
        with (directory/'actual.csv').open('x',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=('case','sequence','epoch','beta_int','candidate_int','output_int','status','latency_cycles'),lineterminator='\n')
            writer.writeheader()
            for index,path in enumerate((*paths,Path(controls_path))):
                control=index==len(paths);stage='控制回放' if control else f'黄金回放{index+1}'
                rows=_rows(path);epoch=driver.reset()
                result['resets'].append(dict(case=index,epoch=epoch))
                if driver.io.read(R['BETA'])!=32212255: raise RuntimeError('复位后β默认值不符')
                start=driver.snapshot()
                if any(start[k] for k in ('accepted','emitted','clipped','saturated')):
                    raise RuntimeError('新epoch计数未清空')
                delays=[];clips=sats=0;last_beta=None
                for row in rows:
                    sequence=row['sequence']
                    packet=NlmsPacket(sequence,row['desired_int'],tuple(row[f'ref_{axis}_int'] for axis in 'xyz'),row['flags'],row['beta_int'])
                    reply=driver.transact(packet)
                    if (reply.sequence,reply.epoch,reply.beta_int)!=(sequence,epoch,packet.beta_int):
                        raise RuntimeError('公开结果sequence／epoch／实际β不符')
                    if (reply.candidate_int,reply.output_int,reply.status)!=(row['candidate_int'],row['output_int'],row['status']):
                        result['mismatches']+=1;raise RuntimeError('公开candidate／output／status不符')
                    if not 0<reply.latency_cycles<=2048: raise RuntimeError('实际PL周期超出2048门')
                    if driver.io.read(R['BETA'])!=packet.beta_int: raise RuntimeError('β影子读回不符')
                    if control:
                        result['control_events'].append(dict(sequence=sequence,epoch=epoch,flags=packet.flags,
                            previous_beta=last_beta,beta_int=packet.beta_int,result_beta=reply.beta_int))
                        result['controls_checked']+=1
                    else: result['checked']+=1
                    last_beta=packet.beta_int;clips+=bool(reply.status&4);sats+=bool(reply.status&8)
                    delays.append(reply.latency_cycles)
                    writer.writerow(dict(case=index,sequence=sequence,epoch=epoch,beta_int=reply.beta_int,
                        candidate_int=reply.candidate_int,output_int=reply.output_int,status=reply.status,latency_cycles=reply.latency_cycles))
                counts=driver.snapshot()
                if (counts['accepted'],counts['emitted'],counts['clipped'],counts['saturated'],counts['epoch'])!=(len(rows),len(rows),clips,sats,epoch):
                    raise RuntimeError('实际算法累计计数不符')
                if counts['max_latency_cycles']!=max(delays): raise RuntimeError('实际最大周期快照不符')
                case=dict(index=index,samples=len(rows),counts=counts,epoch=epoch,
                    min_latency_cycles=min(delays),max_latency_cycles=max(delays),control_case=control)
                if control: result['control_summary']=case
                else: result['cases'].append(case)
                print(f'{stage}完成：{len(rows)}拍，最大{max(delays)}周期',flush=True)
        if result['checked']!=15942 or result['controls_checked']!=20:
            raise RuntimeError('检查数未覆盖完整交付向量')
        result['public_replay_passed']=True
        result['board_tested']=result['board_replay_passed']=bool(hardware)
    except Exception as exc:
        result['error']=dict(stage=stage,sequence=sequence,type=type(exc).__name__,message_cn=str(exc))
        print(f'回放停止：{stage}，{exc}。不自动重投。',flush=True)
    _save(directory,result)
    return result


def _sensor_preflight(overlay):
    """复用原驱动，仅检查采集配置与FIFO回环；不运行实时采集。"""
    from heart_axi_live import SensorBus,AxiFifoLoopback,_resolve_fifo_mmio,pack_sample
    from heart_axi_capture_50hz import validate_50hz_registers
    sensors=SensorBus(overlay.axi_iic_0)
    identities=sensors.verify_identities()
    configuration=sensors.configure(fifo_sample_average=1,mpu_sample_rate_hz=50,mpu_dlpf_cfg=4)
    validate_50hz_registers(configuration)
    fifo=AxiFifoLoopback(_resolve_fifo_mmio(overlay,'axi_fifo_mm_s_0'));fifo.reset()
    packet=pack_sample(0,0,0x12345,-1,2,-3)
    if fifo.round_trip(packet)!=packet: raise RuntimeError('旧FIFO startup回环失败')
    # 只使用本进程自己分配的普通内存，不写任意物理DDR地址。
    pattern=bytes(range(256))*4096
    for _ in range(16):
        memory=bytearray(pattern)
        if bytes(memory)!=pattern: raise RuntimeError('普通内存读回初检失败')
    return dict(max30102_id=identities[0],mpu6050_id=identities[1],registers=configuration,
        fifo_startup_loopback_passed=True,ddr_memory_smoke_passed=True,
        board_ddr_verified=False,limitations_cn='1 MiB普通内存初检及黄金回放不能证明DDR所有条件可靠。')


def run_board_replay(bundle:Path,cases:tuple[Path,...],output_dir:Path)->dict:
    """显式硬件动作入口；CLI在调用前必须已选--hardware。"""
    bundle=Path(bundle).resolve();directory=Path(output_dir).resolve()
    if directory.exists(): raise ValueError('已有回放目录不得覆盖')
    stage='交付身份检查'
    try:
        info=validate_bundle(bundle)
        expected=tuple((bundle/case['path']).resolve() for case in info['cases'])
        if cases and tuple(Path(p).resolve() for p in cases)!=expected:
            raise RuntimeError('只能回放本次交付的完整黄金清单')
        print('将加载独立新Overlay；继承DDR负skew告警仍未解决，遇异常立即停用新包。',flush=True)
        stage='加载新Overlay'
        from pynq import Overlay,MMIO
        overlay=Overlay(str(bundle/'heart_v3a.bit'))
        for name,address in info['addresses'].items():
            ip=overlay.ip_dict.get(name,{})
            if ip.get('phys_addr')!=address['base'] or ip.get('addr_range')!=address['range']:
                raise RuntimeError('实际Overlay外设地址不符：'+name)
        ip=overlay.ip_dict['nlms_axi_0']
        if ip.get('type')!='heart.local:signal:nlms_axi_lite:1.0': raise RuntimeError('实际Overlay NLMS版本不符')
        driver=NlmsAxiDriver(MMIO(BASE_ADDRESS,ADDRESS_RANGE));driver.identify()
        stage='传感器／50 Hz配置／FIFO及内存初检'
        preflight=_sensor_preflight(overlay)
    except Exception as exc:
        directory.mkdir(parents=True,exist_ok=False);result=_new_summary()
        result['error']=dict(stage=stage,type=type(exc).__name__,message_cn=str(exc))
        _save(directory,result);return result
    return _execute_replay(driver,expected,directory,bundle/'controls.csv',hardware=True,preflight=preflight)


def main(argv=None):
    parser=argparse.ArgumentParser(description='V3-A独立交付检查／显式上板黄金回放')
    parser.add_argument('bundle',nargs='?',type=Path,default=Path(__file__).resolve().parent)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--check-bundle',action='store_true')
    mode.add_argument('--hardware',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    if not args.hardware:
        info=validate_bundle(args.bundle)
        print(json.dumps(dict(bundle_validated=True,golden_samples=info['golden_samples'],
            board_tested=False,board_ddr_verified=False),ensure_ascii=False))
        return 0
    output=args.output or args.bundle/'board_results'/('replay-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    result=run_board_replay(args.bundle,(),output)
    print('结果目录：',str(output.resolve()))
    return 0 if result['board_replay_passed'] else 1

if __name__=='__main__': raise SystemExit(main())
