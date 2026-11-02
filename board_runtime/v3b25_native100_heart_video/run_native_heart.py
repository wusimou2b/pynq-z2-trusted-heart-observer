"""Manual Native100 addon to the unchanged browser/heart/video lifecycle."""
import argparse
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

sys.dont_write_bytecode=True
if __package__:
    from .native_heart_guard import verify_package,sha,write_new
    from .native_heart_prepare import validate_prepared
    from .joint_startup import replace_attribute
else:
    from native_heart_guard import verify_package,sha,write_new
    from native_heart_prepare import validate_prepared
    from joint_startup import replace_attribute

ROOT=Path(__file__).resolve().parent


def native_identity_check(isolation,prepared):
    d=isolation.get('native_statistics') or {}
    okay=(d.get('loaded') is True and d.get('implementation')==prepared['implementation']
        and d.get('binary_sha256')==prepared['binary']['sha256']
        and d.get('c_sha256')==prepared['c_sha256']
        and d.get('native_manifest_sha256')==prepared['native_manifest_sha256']
        and d.get('preparation_sha256')==prepared['preparation_sha256']
        and d.get('ps_pid')==isolation.get('worker_pid') and type(d.get('ps_pid')) is int
        and isolation.get('worker_hardware_imported') is False
        and isolation.get('warmup_raw')==isolation.get('warmup_slots')==700
        and isolation.get('entry_confirmation_checks')==6)
    return dict(passed=okay,ready_identity=d)


def export_final(root,final):
    root=Path(root);write_new(root/'native-heart-final.json',final)
    source=root/'browser-heart-results.zip';archive=root/'native-heart-results.zip'
    if source.is_file():
        with ZipFile(source) as old:
            if (len(old.namelist())!=len(set(old.namelist())) or old.testzip() is not None
                    or set(old.namelist()) & {'native-heart-final.json','native-prepare-results.zip'}):
                raise ValueError('original browser ZIP corrupt')
            with ZipFile(archive,'x',compression=ZIP_DEFLATED) as new:
                for n in old.namelist():new.writestr(n,old.read(n))
                new.write(root/'native-heart-final.json','native-heart-final.json')
                new.write(root/'native-prepare-results.zip','native-prepare-results.zip')
    return archive if archive.is_file() else None


def run_native60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-NATIVE-HEART60':
        raise ValueError('requires hardware=True and RUN-NATIVE-HEART60')
    checked=verify_package(ROOT);prepared=validate_prepared(ROOT,hardware=True)
    if any((ROOT/n).exists() for n in ('native-heart-final.json','native-heart-results.zip','joint-concurrent-attempt.json')):
        raise FileExistsError('已有实采尝试/结果，不覆盖、不重试')
    if __package__:
        from . import run_browser_heart as browser,browser_heart_worker as owner
        from .browser_heart_display import ready_bridge
        from .browser_heart_guard import assess_candidate as assess_browser
        from .native_heart_worker import start_owner
    else:
        import run_browser_heart as browser,browser_heart_worker as owner
        from browser_heart_display import ready_bridge
        from browser_heart_guard import assess_candidate as assess_browser
        from native_heart_worker import start_owner
    ready_bridge()
    result=None;failure=None;assessed=None
    def assess(directory,inherited,actual,**kwargs):
        nonlocal assessed
        r=assess_browser(directory,inherited,actual,**kwargs)
        assessed=native_identity_check((inherited.get('summary') or {}).get('isolation') or {},prepared)
        r['checks']['native100_ps_kernel']=assessed['passed']
        r.update(native100=assessed,native_manifest_sha256=checked['native_manifest_sha256'],
            joint_60s_pilot_completed=all(r['checks'].values()))
        return r
    print('本次原生统计在实际PS子进程启用；25/25Hz＋5fps，原保护与收尾不变。',flush=True)
    try:
        with replace_attribute(browser,'ROOT',ROOT),replace_attribute(browser,'verify_package',verify_package), \
                replace_attribute(browser,'assess_candidate',assess),replace_attribute(owner,'start_owner',start_owner):
            result=browser.run_browser60(hardware=True,confirmation='RUN-BROWSER-HEART60')
    except BaseException as exc:failure=exc
    final=dict(schema='v3b25_native_heart_final_v1',native_manifest_sha256=checked['native_manifest_sha256'],
        browser_manifest_sha256=checked['package_manifest_sha256'],prepared=prepared,native100=assessed,
        run_error=dict(type=type(failure).__name__,message=str(failure)) if failure else None,
        original_ps_exit_fixed=False,strict_realtime_verified=False,accuracy_verified=False,
        scope='Native PS statistics + original25/25Hz/5fps/browser; acceptance unchanged')
    try:archive=export_final(ROOT,final)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if archive:
        from IPython.display import FileLink,display
        print('请保留并回传 native-heart-results.zip；等原收尾，不自动重跑。',flush=True)
        display(FileLink(str(archive.relative_to(Path.cwd()))))
    else:print('结果ZIP未完整生成，保留本目录及输出，不要重跑。',flush=True)
    if failure is not None:raise failure
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle',action='store_true');mode.add_argument('--prepare-native',action='store_true')
    p.add_argument('--host-check',action='store_true');args=p.parse_args(argv)
    if args.check_bundle:print(json.dumps(verify_package(ROOT),ensure_ascii=False));return 0
    if __package__:from .native_heart_prepare import prepare
    else:from native_heart_prepare import prepare
    r=prepare(ROOT,host_check=args.host_check)
    return 0 if r['complete'] else 1


if __name__=='__main__':sys.exit(main())
