"""Opt-in Overlay boundary; no sensor configuration, acquisition or retries."""
from pathlib import Path
import sys

from .delivery import validate
from .data import load_cases
from .reporting import output_directory, save
from .replay import new_report, replay_into, record_error


def run(root, output=None, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True才允许PL回放')
    root = Path(root).resolve()
    validate(root)
    cases = load_cases(root)
    directory = output_directory(root, output, 'pl25')
    report = new_report(root)
    lease = driver = None
    try:
        report['stage'] = 'platform'
        if sys.platform != 'linux': raise RuntimeError('真实PL回放仅限板端Linux')
        from heart_v3a.live.board import BoardLease
        lease = BoardLease()
        report['stage'] = 'hardware_lock'
        lease.acquire()
        report['stage'] = 'overlay'
        print('显式加载原Overlay；DDR遗留告警未验收。不采集传感器，不自动重试。', flush=True)
        from pynq import Overlay, MMIO
        overlay = Overlay(str(root/'base/heart_v3a.bit'))
        report['hardware_loaded'] = True
        expected = {'axi_iic_0':(0x41600000,'xilinx.com:ip:axi_iic:2.1'),
                    'axi_fifo_mm_s_0':(0x43c00000,'xilinx.com:ip:axi_fifo_mm_s:4.3'),
                    'nlms_axi_0':(0x43c10000,'heart.local:signal:nlms_axi_lite:1.0')}
        for name, (address, kind) in expected.items():
            ip = overlay.ip_dict.get(name, {})
            if (ip.get('phys_addr'),ip.get('addr_range'),ip.get('type')) != (address,65536,kind):
                raise RuntimeError('Overlay地址／IP版本不符：'+name)
        from heart_v3a.axi_driver import NlmsAxiDriver
        from heart_v3a.axi_contract import BASE_ADDRESS, ADDRESS_RANGE
        report['stage'] = 'nlms_identity'
        driver = NlmsAxiDriver(MMIO(BASE_ADDRESS, ADDRESS_RANGE))
        report['nlms_identity'] = driver.identify()
        replay_into(driver, cases, directory, report)
        report['board_pl25_replay_passed'] = report['public_replay_passed']
    except (Exception, KeyboardInterrupt) as exc:
        record_error(report, exc, driver)
    finally:
        report['board_tested'] = bool(report['hardware_loaded'] and report['attempted'])
        try:
            if lease is not None: lease.release()
            report['lock_released'] = True
        except Exception as exc:
            report['lock_released'] = False
            report['board_pl25_replay_passed'] = False
            if report['error'] is None:
                report['stage'] = 'lease_release'
                record_error(report, exc, driver)
    save(directory, 'pl25.json', report)
    print('报告目录：'+str(directory), flush=True)
    return report
