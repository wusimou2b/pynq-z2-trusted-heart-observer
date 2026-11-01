"""Offline HWH/profile inspection. Does not import PYNQ or access a device."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def load_json(path):
    if Path(path).stat().st_size > 4 * 1024**2:
        raise ValueError('JSON exceeds 4 MiB inspection limit')
    return json.loads(Path(path).read_text('utf-8-sig'), object_pairs_hook=strict_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('non-finite JSON')))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def integer(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not an integer')
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16 if value.lower().startswith('0x') else 10)
    raise ValueError('expected integer or decimal/hex string')


def parse_hwh(path):
    if Path(path).stat().st_size > 32 * 1024**2:
        raise ValueError('HWH exceeds 32 MiB inspection limit')
    raw = Path(path).read_bytes()
    decoded = raw.decode('utf-8-sig')
    if '\x00' in decoded:
        raise ValueError('HWH must be UTF-8, not UTF-16/32')
    # Refuse declarations rather than expand entities. No XInclude execution.
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('DTD/entity declarations are unsupported')
    root = ET.fromstring(decoded)
    if root.tag != 'EDKSYSTEM':
        raise ValueError('unsupported HWH root/schema')
    infos = root.findall('./SYSTEMINFO')
    if len(infos) != 1:
        raise ValueError('one SYSTEMINFO is required')
    modules = []
    names = set()
    for node in root.findall('./MODULES/MODULE'):
        if node.get('IS_ENABLE') == '0':
            continue
        name = (node.get('FULLNAME') or node.get('INSTANCE') or '').lstrip('/')
        if not name or name in names:
            raise ValueError('empty/duplicate module identity')
        names.add(name)
        params = {}
        for p in node.findall('./PARAMETERS/PARAMETER'):
            key = p.get('NAME')
            if not key or key in params:
                raise ValueError('empty/duplicate parameter in ' + name)
            params[key] = p.get('VALUE')
        modules.append({'instance': name, 'vlnv': node.get('VLNV'), 'parameters': params})
    ranges = []
    for node in root.iter('MEMRANGE'):
        fields = node.attrib
        if fields.get('MEMTYPE') and fields['MEMTYPE'] != 'REGISTER':
            continue
        if not {'INSTANCE', 'BASEVALUE', 'HIGHVALUE'} <= fields.keys():
            continue
        base, high = integer(fields['BASEVALUE']), integer(fields['HIGHVALUE'])
        if base < 0 or high < base:
            raise ValueError('invalid memory range')
        row = {'instance': fields['INSTANCE'].lstrip('/'), 'base': base, 'high': high,
               'master': fields.get('MASTERBUSINTERFACE'), 'slave': fields.get('SLAVEBUSINTERFACE')}
        if row not in ranges:
            ranges.append(row)
    return {'system': dict(infos[0].attrib), 'vivado_version': root.get('VIVADOVERSION'),
            'modules': modules, 'register_ranges': ranges}


def inspect(hwh, profile_path, bit=None, environment=None):
    report = {'schema': 'pynq-overlay-inspection-v1', 'hardware_accessed': False,
              'board_compatibility_verified': False, 'pair_provenance_verified': False,
              'binding_executed': False, 'errors': [], 'unknowns': [], 'matches': []}
    try:
        profile = load_json(profile_path)
        if not isinstance(profile, dict) or profile.get('schema') != 'pynq-overlay-profile-v1':
            raise ValueError('unsupported profile schema')
        allowed = {'schema', 'target', 'required_ips', 'required_pynq_versions', 'artifact_sha256'}
        if set(profile) - allowed:
            raise ValueError('unknown profile fields: ' + str(sorted(set(profile) - allowed)))
        target = profile['target']
        if not isinstance(target, dict) or not {'DEVICE', 'PACKAGE'} <= target.keys():
            raise ValueError('target must explicitly include DEVICE and PACKAGE')
        if set(target) - {'DEVICE', 'PACKAGE', 'SPEEDGRADE', 'ARCH', 'BOARD'}:
            raise ValueError('unknown SYSTEMINFO target field')
        if not all(isinstance(v, str) and v for v in target.values()):
            raise ValueError('target values must be nonempty strings')
        required = profile['required_ips']
        if not isinstance(required, list) or not required:
            raise ValueError('required_ips must be nonempty')
        metadata = parse_hwh(hwh)
        report['metadata'] = metadata
        report['artifact_sha256'] = {'hwh': digest(hwh)}
        report['profile_sha256'] = digest(profile_path)
        for key, expected in target.items():
            actual = metadata['system'].get(key)
            if actual != expected:
                report['errors'].append(f'target {key}: expected {expected}, found {actual}')
        if bit is not None:
            report['artifact_sha256']['bit'] = digest(bit)
            if Path(bit).resolve().parent != Path(hwh).resolve().parent or Path(bit).stem != Path(hwh).stem:
                report['errors'].append('bit/HWH must be adjacent with the same stem for normal PYNQ loading')
        else:
            report['unknowns'].append('bit not provided; its bytes were not checked')
        pins = profile.get('artifact_sha256', {})
        if not isinstance(pins, dict) or set(pins) - {'bit', 'hwh'}:
            raise ValueError('artifact_sha256 supports bit/hwh only')
        for key, expected in pins.items():
            if not isinstance(expected, str) or re.fullmatch('[0-9a-fA-F]{64}', expected) is None:
                raise ValueError('invalid SHA256 pin')
            if report['artifact_sha256'].get(key) != expected.lower():
                report['errors'].append(key + ' SHA256 differs or artifact absent')
        report['both_artifact_pins_match'] = bool(set(pins) == {'bit', 'hwh'} and all(
            report['artifact_sha256'].get(k) == v.lower() for k, v in pins.items()))
        report['unknowns'].append('hash pins require independently trusted build provenance; bit payload/physical board not inspected')
        roles = set()
        for item in required:
            if not isinstance(item, dict) or set(item) - {'role', 'vlnv', 'instance', 'parameters', 'address'}:
                raise ValueError('unknown or malformed required IP fields')
            role, vlnv = item['role'], item['vlnv']
            if not isinstance(role, str) or not role or role in roles or not isinstance(vlnv, str) or len(vlnv.split(':')) != 4 or any(not part or part.strip() != part for part in vlnv.split(':')):
                raise ValueError('roles must be unique; exact VLNV required')
            roles.add(role)
            matches = [m for m in metadata['modules'] if m['vlnv'] == vlnv]
            if 'instance' in item:
                matches = [m for m in matches if m['instance'] == item['instance']]
            if len(matches) != 1:
                report['errors'].append(f'{role}: expected one IP, found {len(matches)}; supply exact hierarchical instance if ambiguous')
                continue
            module = matches[0]
            params = item.get('parameters', {})
            if not isinstance(params, dict) or not all(isinstance(v, str) for v in params.values()):
                raise ValueError('parameter expectations must be exact strings')
            for key, expected in params.items():
                if module['parameters'].get(key) != expected:
                    report['errors'].append(f'{role}: parameter {key} differs or absent')
            mapped = [r for r in metadata['register_ranges'] if r['instance'] == module['instance']]
            address = item.get('address')
            if address is not None:
                if not isinstance(address, dict) or set(address) - {'master', 'slave', 'min_bytes', 'address_bits'}:
                    raise ValueError('unknown address constraint fields')
                width, size = integer(address['address_bits']), integer(address['min_bytes'])
                if not 1 <= width <= 64 or size <= 0:
                    raise ValueError('invalid address width/minimum range')
                mapped = [r for r in mapped if all(k not in address or r[k] == address[k] for k in ('master', 'slave'))]
                if len(mapped) != 1:
                    report['errors'].append(f'{role}: address window absent or ambiguous; specify master/slave')
                elif mapped[0]['high'] >= 2**width or mapped[0]['high'] - mapped[0]['base'] + 1 < size:
                    report['errors'].append(f'{role}: address width/range constraint failed')
            report['matches'].append({'role': role, 'instance': module['instance'], 'vlnv': vlnv, 'register_ranges': mapped})
        versions = profile.get('required_pynq_versions', [])
        if not isinstance(versions, list) or any(not isinstance(v, str) or not v for v in versions):
            raise ValueError('required_pynq_versions must be a string list')
        if environment is not None:
            env = load_json(environment)
            if not isinstance(env, dict) or env.get('schema') != 'pynq-environment-v1':
                raise ValueError('unsupported environment schema')
            report['environment'] = env
            report['environment_sha256'] = digest(environment)
            if versions and env.get('pynq_version') not in versions:
                report['errors'].append('installed PYNQ version absent or outside explicit profile versions')
        elif versions:
            report['unknowns'].append('environment absent; required PYNQ version not checked')
        report['unknowns'].append('clock/reset/interrupt routing, electrical constraints, IP ABI and driver implementation need separate review')
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as exc:
        report['errors'].append(type(exc).__name__ + ': ' + str(exc))
    report['declared_metadata_matches'] = not report['errors']
    report['status'] = 'incompatible' if report['errors'] else 'metadata_only'
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hwh', required=True)
    p.add_argument('--profile', required=True)
    p.add_argument('--bit')
    p.add_argument('--environment')
    p.add_argument('--output', required=True)
    a = p.parse_args()
    inputs = [Path(v).resolve() for v in (a.hwh, a.profile, a.bit, a.environment) if v]
    if Path(a.output).exists() or Path(a.output).resolve() in inputs:
        p.error('output exists or aliases input; use a new output')
    result = inspect(a.hwh, a.profile, a.bit, a.environment)
    with Path(a.output).open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': result['status'], 'errors': len(result['errors']), 'hardware_accessed': False}))
    return 2 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
