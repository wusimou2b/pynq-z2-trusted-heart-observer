"""有效输入25Hz/处理25Hz。默认只验包；软件检查不加载Overlay。"""
import argparse
from pathlib import Path
import json
import sys
import uuid
from effective25.identity import validate,bootstrap,write_new,FLAGS

ROOT=Path(__file__).resolve().parent


def run_display60(*,hardware=False,output=None):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    from effective25.display import run
    return run(ROOT,output,hardware=hardware)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--check-bundle',action='store_true')
    group.add_argument('--software-check',action='store_true')
    args=parser.parse_args()
    if not args.software_check:
        validate(ROOT)
        print(json.dumps(dict(bundle_validated=True,**FLAGS,hardware_loaded=False,
            raw_hz=25,processing_hz=25,adc_hz=50,fifo_sample_average=2,entry='effective25_new_frontend')))
        return
    context,cached=bootstrap(ROOT,algorithm=True)
    from effective25.checks import run_checks
    directory=ROOT/'checks'/('software-'+uuid.uuid4().hex[:12])
    directory.mkdir(parents=True,exist_ok=False)
    print('只读25/25检查：不放手指、不加载Overlay，请勿同时采集或绘图。',flush=True)
    report=run_checks()
    report['manifest_sha256']=context['effective_manifest_sha256']
    report['changed_files']=cached.changed_files(context)
    report['inputs_unchanged']=not report['changed_files']
    report['implementation_checks_passed'] &= report['inputs_unchanged']
    write_new(directory/'effective25_check.json',report)
    print('实现检查：',report['implementation_checks_passed'],'；不是板端实采／准确率验收。',flush=True)
    print('请回传：',directory/'effective25_check.json',flush=True)
    if not report['implementation_checks_passed']: raise SystemExit(2)


if __name__=='__main__': main()
