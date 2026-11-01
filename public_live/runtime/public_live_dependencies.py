"""Read-only module availability checks before any public hardware gate."""
import importlib.util
import importlib.metadata
import platform
import sys
import sysconfig


def dependency_report():
    modules=('numpy','scipy','pandas','cv2','pynq','IPython','ipykernel')
    available={}
    for name in modules:
        try:available[name]=importlib.util.find_spec(name) is not None
        except (ImportError,ValueError,AttributeError):available[name]=False
    versions={}
    for distribution in ('numpy','scipy','pandas','pynq','ipython','ipykernel','notebook'):
        try:versions[distribution]=importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:versions[distribution]=None
    abi=dict(platform=sys.platform,machine=platform.machine(),python=list(sys.version_info[:3]),
        soabi=sysconfig.get_config_var('SOABI'))
    return dict(schema='trusted_heart_public_dependencies_v1',modules=available,
        missing=[name for name,present in available.items() if not present],versions=versions,
        modules_available=all(available.values()),abi=abi,
        target_abi_matches=bool(sys.platform=='linux' and platform.machine()=='armv7l'
            and sys.version_info[:2]==(3,10)
            and sysconfig.get_config_var('SOABI')=='cpython-310-arm-linux-gnueabihf'),
        # Presence and saved versions are not a complete system qualification.
        full_environment_verified=False,pandas_required_for_live=True,
        project_or_driver_imported=False)


def require_dependencies():
    report=dependency_report()
    if not report['modules_available']:
        raise RuntimeError('public LIVE dependencies missing before hardware: '+', '.join(report['missing']))
    if not report['target_abi_matches']:
        raise RuntimeError('public LIVE requires CPython3.10 ARMv7 hard-float target ABI')
    if report['versions']['numpy']!='1.21.5':
        raise RuntimeError('public LIVE requires recorded NumPy1.21.5; do not silently upgrade')
    return report
