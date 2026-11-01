"""Identity data for explicit public workers, without private replay claims."""
from pathlib import Path
import json
import platform
import sys
from public_live_contract import verify_release, native_context


def verify_boundary(root, release_contract):
    context = verify_release(release_contract)
    if Path(root).resolve() != Path(context['runtime_root']):
        raise ValueError('public worker runtime differs from verified release')
    return dict(schema='trusted_heart_public_worker_identity_v1',
                release_manifest_sha256=context['manifest_sha256'],
                asset_identity_verified=True,
                historical_numerical_qualification=False,
                hardware_accessed=False)


def public_prepared(root, release_contract, *, hardware=False, host_check=False):
    verify_boundary(root, release_contract)
    if hardware and (host_check or sys.platform != 'linux' or platform.machine() != 'armv7l'):
        raise RuntimeError('physical public LIVE requires the ARM Linux board, not host-check')
    return native_context(release_contract)


def public_bootstrap(base, release_contract, *, algorithm=False):
    from public_live_contract import activate_runtime
    context = activate_runtime(release_contract)
    release_root = Path(context['root'])
    runtime = Path(context['runtime_root'])
    expected = runtime / 'frozen/base'
    if Path(base).resolve() != expected:
        raise ValueError('public owner bootstrap base differs from release')
    manifest = json.loads((release_root / 'public-live-manifest.json').read_text('utf-8'))
    tracked = {str(release_root / row['path']): row['sha256'] for row in manifest['files']}
    if not tracked:
        raise ValueError('public owner requires complete tracked release files')
    identity = dict(root=expected / 'deps', effective_root=expected,
        tracked_hashes=tracked,
        owner_manifest_sha256=context['manifest_sha256'],
        effective_manifest_sha256=context['manifest_sha256'],
        release_manifest_sha256=context['manifest_sha256'],
        validation_scope='public_live_runtime_assets_v1',
        historical_numerical_qualification=False)
    return identity, None
