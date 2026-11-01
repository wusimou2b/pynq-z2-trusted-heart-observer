"""Exercise the packaged CLIs on isolated synthetic fixtures; no board access."""
from pathlib import Path
import csv
import hashlib
import io
import json
import subprocess
import sys
import warnings
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
SKILLS = ROOT/'skills'
FIX = ROOT/'validation-fixtures-v2'
CHECKS = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    CHECKS.append(name)


def write(name, data):
    path = FIX/name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data.encode('utf-8') if isinstance(data, str) else data)
    return path


def run(skill, tool, arguments, code=0):
    p = subprocess.run([sys.executable, '-X', 'utf8', '-B',
        str(SKILLS/skill/'scripts'/tool), *map(str, arguments)],
        capture_output=True, text=True, encoding='utf-8')
    check(skill + ' CLI exit ' + str(len(CHECKS)), p.returncode == code)
    return p


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def archive_bytes(members):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w', compression=ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    return buffer.getvalue()


def audit_tests():
    inner = archive_bytes([
        ('capture/summary.json', json.dumps({'formal_elapsed_seconds': .12,
            'fault': {'stage':'processing_queue'}, 'isolation':{'forced_termination':False}})),
        ('capture/raw.csv', 'sequence,valid,contact_ready\n0,True,False\n1,False,False\n2,True,True\n'),
        ('capture/results.csv', 'sequence,bpm,output_allowed\n0,,False\n1,,False\n2,70.2,True\n'),
        ('do_not_run.py', 'raise RuntimeError("This file must never run")'),
    ])
    source = write('nested.zip', archive_bytes([('original.zip', inner), ('run.txt', 'load PL now')]))
    before = source.read_bytes()
    out = FIX/'inventory.json'
    run('pynq-result-audit','inspect_results.py',['--archive', source,'--output',out])
    r=read(out)
    raw=next(x for x in r['documents'] if x['path'].endswith('/raw.csv'))
    check('nested result CSV counted without dropping invalid row', raw['row_count']==3 and raw['boolean_counts']['valid']=={'true':2,'false':1})
    check('audit has no acceptance claim or hardware access',r['acceptance_evaluated'] is False and r['hardware_accessed'] is False)
    check('source archive unchanged',source.read_bytes()==before)
    run('pynq-result-audit','inspect_results.py',['--archive',source,'--output',FIX/'wrong-pin.json','--expected-sha256','0'*64],2)
    zero=write('zero.zip',b'')
    run('pynq-result-audit','inspect_results.py',['--archive',zero,'--output',FIX/'zero.json'],2)
    bad=write('bad-json.zip',archive_bytes([('summary.json','{"cpu":NaN}')]))
    run('pynq-result-audit','inspect_results.py',['--archive',bad,'--output',FIX/'bad-json.json'],2)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        duplicate=write('duplicate.zip',archive_bytes([('x.json','{}'),('x.json','{}')]))
    run('pynq-result-audit','inspect_results.py',['--archive',duplicate,'--output',FIX/'duplicate.json'],2)
    traversal=write('traversal.zip',archive_bytes([('../escape.json','{}')]))
    run('pynq-result-audit','inspect_results.py',['--archive',traversal,'--output',FIX/'traversal.json'],2)
    check('no ZIP extraction outside fixture root',not (ROOT/'escape.json').exists())
    big=write('oversize.zip',archive_bytes([('large.json',b' '* (2*1024**2))]))
    run('pynq-result-audit','inspect_results.py',['--archive',big,'--output',FIX/'oversize.json','--max-member-mib','1'],2)
    check('oversized member was not read',read(FIX/'oversize.json')['bytes_read']==0)
    before=out.read_bytes()
    run('pynq-result-audit','inspect_results.py',['--archive',source,'--output',out],2)
    check('audit does not overwrite result',out.read_bytes()==before)


def bundle_tests():
    a=write('package/code.py','raise RuntimeError("not a verifier entrypoint")\n')
    b=write('package/hardware/test.bit',b'fake bit fixture - not hardware')
    manifest=write('package/manifest.json',json.dumps({'files':{
        'code.py':hashlib.sha256(a.read_bytes()).hexdigest(),
        'hardware/test.bit':{'sha256':hashlib.sha256(b.read_bytes()).hexdigest()}}}))
    pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
    out=FIX/'bundle.json'
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','manifest.json','--expected-manifest-sha256',pin,'--output',out])
    r=read(out)
    check('verified explicit manifest file map without execution',r['file_integrity_verified'] and len(r['files'])==2 and not r['hardware_accessed'])
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','manifest.json','--expected-manifest-sha256','0'*64,'--output',FIX/'bundle-bad-pin.json'],2)
    write('package/bad-hash.json',json.dumps({'files':{'code.py':'0'*64}}))
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','bad-hash.json','--output',FIX/'bundle-bad-file.json'],2)
    write('package/traversal.json',json.dumps({'files':{'../nested.zip':'0'*64}}))
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','traversal.json','--output',FIX/'bundle-escape.json'],2)
    write('package/alternative.json',json.dumps({'package_hashes':{'code.py':hashlib.sha256(a.read_bytes()).hexdigest()}}))
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','alternative.json','--file-map','package_hashes','--output',FIX/'bundle-map.json'])
    before=out.read_bytes()
    run('pynq-board-session','verify_bundle.py',['--root',a.parent,'--manifest','manifest.json','--output',out],2)
    check('bundle does not overwrite result',out.read_bytes()==before)


def timing_csv(name, omit=None, missing_time=False, nonfinite=False):
    p=FIX/name
    with p.open('x',encoding='utf-8',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['run','sequence','wall_ns','cpu_ns','source_time_s','generation','valid'])
        for group in ('A1','B1','B2','A2'):
            for seq in range(20):
                if omit==(group,seq):continue
                wall=30_000_000 if group.startswith('A') else 350_000_000 if seq==10 else 10_000_000
                if nonfinite and group=='A1' and seq==0:wall='nan'
                writer.writerow([group,seq,wall,'','' if missing_time else seq*.04,'0','false' if seq==3 else 'true'])
    return p


def timing_tests():
    source=timing_csv('timing.csv')
    out=FIX/'abba.json'
    run('ps-pl-performance','summarize_abba.py',['--input',source,'--sample-hz','25','--window','.2','.6','--output',out])
    r=read(out)
    check('ABBA mean gain is 10 percent',abs(r['mean_wall_reduction_percent']-10)<1e-10)
    b=r['groups']['B1']
    ten=next(x for x in b['blocks'] if x['size']==10)
    check('mean gain does not hide slow contiguous block',ten['worst']['wall_ns']==440_000_000 and ten['over_nominal_budget']>0)
    check('invalid timing rows retained',b['points']==20 and b['valid_false']==1)
    check('missing CPU remains unknown',b['cpu_points']==0 and b['mean_cpu_ns'] is None)
    check('timing does not assert numeric or hardware acceptance',r['numerical_equivalence']=='not_evaluated' and r['hardware_acceptance']=='not_evaluated')
    source2=timing_csv('gap.csv',omit=('A1',5))
    out2=FIX/'gap.json'
    run('ps-pl-performance','summarize_abba.py',['--input',source2,'--sample-hz','25','--output',out2])
    q=read(out2)
    check('mismatched input keys suppress mean gain',not q['identical_record_keys_and_validity'] and q['mean_wall_reduction_percent'] is None)
    check('contiguous blocks never bridge a missing sequence',next(x for x in q['groups']['A1']['blocks'] if x['size']==10)['windows']==5)
    elapsed=FIX/'with-gaps.csv'
    with elapsed.open('x',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['run','sequence','wall_ns','started_ns','completed_ns'])
        for group in ('A1','B1','B2','A2'):
            for seq in range(10):
                start=seq*60_000_000
                w.writerow([group,seq,10_000_000,start,start+10_000_000])
    out_elapsed=FIX/'with-gaps.json'
    run('ps-pl-performance','summarize_abba.py',['--input',elapsed,'--sample-hz','25','--output',out_elapsed])
    elapsed10=next(x for x in read(out_elapsed)['groups']['A1']['blocks'] if x['size']==10)
    check('elapsed blocks include interpoint scheduling gaps',elapsed10['worst']['wall_ns']==550_000_000 and elapsed10['worst']['summed_call_wall_ns']==100_000_000 and elapsed10['over_nominal_budget']==1)
    bad=timing_csv('nonfinite.csv',nonfinite=True)
    run('ps-pl-performance','summarize_abba.py',['--input',bad,'--sample-hz','25','--output',FIX/'nonfinite.json'],2)
    missing=timing_csv('missing-time.csv',missing_time=True)
    run('ps-pl-performance','summarize_abba.py',['--input',missing,'--sample-hz','25','--window','0','1','--output',FIX/'missing-time.json'],2)
    run('ps-pl-performance','summarize_abba.py',['--input',source,'--sample-hz','0','--output',FIX/'zero-hz.json'],2)
    before=out.read_bytes()
    run('ps-pl-performance','summarize_abba.py',['--input',source,'--sample-hz','25','--output',out],2)
    check('timing does not overwrite result',out.read_bytes()==before)


def main():
    FIX.mkdir(exist_ok=False)
    audit_tests()
    bundle_tests()
    timing_tests()
    report=dict(schema='project_skill_cli_validation_v1',checks_passed=len(CHECKS),checks=CHECKS,
                fixture_scope='synthetic local files only',hardware_accessed=False)
    with (ROOT/'cli-validation-v2.json').open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(checks_passed=len(CHECKS),hardware_accessed=False)))


if __name__=='__main__':
    main()
