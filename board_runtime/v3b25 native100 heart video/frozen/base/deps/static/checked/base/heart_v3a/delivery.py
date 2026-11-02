"""同次整板产物与交付身份；HWH存在本身不是板端验收。"""
from pathlib import Path
import csv
import json
import shutil
import xml.etree.ElementTree as ET
from .rtl_sim import source_hashes

def inspect_hwh(hwh:Path)->dict:
    root=ET.parse(hwh).getroot()
    modules={m.attrib['INSTANCE']:m for m in root.findall('.//MODULE')}
    if 'nlms_axi_0' not in modules: raise RuntimeError('HWH缺少NLMS新IP')
    nlms=modules['nlms_axi_0']
    if nlms.attrib['VLNV']!='heart.local:signal:nlms_axi_lite:1.0': raise RuntimeError('HWH新IP版本不符')
    ranges={m.attrib['INSTANCE']:dict(base=int(m.attrib['BASEVALUE'],0),range=int(m.attrib['HIGHVALUE'],0)-int(m.attrib['BASEVALUE'],0)+1)
        for m in root.findall('.//MEMRANGE') if m.attrib.get('INSTANCE') in ('axi_iic_0','axi_fifo_mm_s_0','nlms_axi_0')}
    expected={'axi_iic_0':dict(base=0x41600000,range=65536),'axi_fifo_mm_s_0':dict(base=0x43c00000,range=65536),'nlms_axi_0':dict(base=0x43c10000,range=65536)}
    if ranges!=expected: raise RuntimeError('HWH外设地址不符')
    ports={p.attrib['NAME']:p for p in nlms.findall('./PORTS/PORT')}
    if ports['s_axi_aclk'].attrib['SIGNAME']!='processing_system7_0_FCLK_CLK0' or ports['s_axi_aresetn'].attrib['SIGNAME']!='rst_ps7_0_100M_peripheral_aresetn':
        raise RuntimeError('HWH时钟／复位关联不符')
    clocks=[p.attrib.get('VALUE') for p in nlms.findall('.//PARAMETER') if p.attrib.get('NAME')=='FREQ_HZ']
    if '100000000' not in clocks or ports['s_axi_aclk'].attrib.get('CLKFREQUENCY')!='100000000':
        raise RuntimeError('HWH缺一致的100 MHz时钟关联')
    return dict(addresses=ranges,vlnv=nlms.attrib['VLNV'],tool_version=root.attrib['VIVADOVERSION'])

def validate_handoff(bitfile:Path,hwh:Path,manifest:dict)->dict:
    bitfile,hwh=Path(bitfile).resolve(),Path(hwh).resolve()
    session=Path(manifest['session_dir']).resolve()
    if bitfile.parent!=session or hwh.parent!=session or bitfile.stem!=hwh.stem:
        raise RuntimeError('bit／HWH配对会话不一致')
    if not bitfile.is_file() or bitfile.stat().st_size<1024: raise RuntimeError('bit缺失或不完整')
    for path in (bitfile,hwh):
        if source_hashes([path])[str(path)]!=manifest['artifact_hashes'].get(str(path)):
            raise RuntimeError('产物SHA256哈希不符')
    facts=inspect_hwh(hwh)
    if facts['addresses']!=manifest['addresses'] or facts['tool_version']!=manifest['tool_version']:
        raise RuntimeError('HWH与本次实际构建身份不一致')
    return {**facts,'artifact_hashes':manifest['artifact_hashes'],'board_tested':False,'board_ddr_verified':False}

ROOT=Path(__file__).resolve().parents[1]
CSV_FIELDS=('sequence','flags','desired_int','ref_x_int','ref_y_int','ref_z_int','beta_int',
    'candidate_int','output_int','status')
RUNTIME_FILES=(
    'heart_v3a/__init__.py','heart_v3a/axi_contract.py','heart_v3a/axi_driver.py',
    'heart_v3a/runtime_backend.py','heart_v3a/runtime_fixed_nlms.py','heart_v3a/fixed_nlms.py',
    'heart_v3a/fixed_math.py','heart_v3a/runtime_pl_chain.py','heart_v3a/delivery.py','heart_v3a/rtl_sim.py',
    'heart_v2/__init__.py','heart_v2/dataset.py','heart_v2/runtime_main_chain.py',
    'heart_v2/contact.py','heart_v2/preprocess.py','heart_v2/nlms.py',
    'heart_v2/joint_benefit.py','heart_v2/aligned_metrics.py','heart_v2/metrics.py',
    'heart_v2/heartrate.py','heart_v2/runtime_state.py','config/arena_v2_primed.yaml',
    'run_main_chain.py','run_v3a_main_chain.py','run_v3a_board_replay.py')

def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def _digest(path):
    path=Path(path).resolve()
    return source_hashes([path])[str(path)]

def _write_csv(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=CSV_FIELDS,lineterminator='\n')
        writer.writeheader();writer.writerows(rows)

def _public_rows(case):
    from .axi_contract import BETA_DEFAULT,decode_signed32
    from run_nlms_rtl import read_case
    stimulus,expected=read_case(case)
    rows=[]
    for index,(stim,want) in enumerate(zip(stimulus,expected)):
        inputs=[decode_signed32(int(stim[i:i+8],16)) for i in range(0,40,8)]
        rows.append(dict(zip(CSV_FIELDS,(index,*inputs,BETA_DEFAULT,
            decode_signed32(int(want[48:56],16)),decode_signed32(int(want[56:64],16)),int(want[-8:],16)))))
    return rows

def _control_rows():
    from .runtime_fixed_nlms import RuntimeFixedNlms4
    from .axi_contract import BETA_DEFAULT
    model=RuntimeFixedNlms4();rows=[]
    # 这些是接口合法值测试，不是新的正常运动参数档位。
    for index in range(20):
        flags=index if index<16 else 3 | (4 if index==18 else 0)
        beta=BETA_DEFAULT if index<16 else (1,16106127,16106127,BETA_DEFAULT)[index-16]
        desired=(-1 if index%2 else 1)*60*65536
        refs=(65536,-65536,32768)
        step=model.step_int(desired,refs,beta_int=beta,valid=bool(flags&1),
            update=bool(flags&2),reset=bool(flags&4),bypass=bool(flags&8))
        status=int(step.output_valid)|(int(step.update_applied)<<1)|(int(step.weight_clipped)<<2)|(int(step.arithmetic_saturated)<<3)
        rows.append(dict(zip(CSV_FIELDS,(index,flags,desired,*refs,beta,step.candidate_int,step.output_int,status))))
    return rows

def create_bundle(build:dict,destination:Path)->dict:
    """仅从已验实际构建创建新目录；不操作板子、不带测试替身。"""
    from .overlay_build import validate_integrated_reports,verify_hashes
    from run_nlms_rtl import GOLDEN_ROOTS
    destination=Path(destination).resolve()
    if destination.exists(): raise ValueError('已有交付目录不得覆盖')
    manifest_path=Path(build['build_manifest'])
    provenance=_json(manifest_path)
    if not provenance['integrated_timing_passed'] or not provenance['bitstream_generated']:
        raise RuntimeError('构建没有通过发布门')
    metrics=validate_integrated_reports(Path(build['report_dir']))
    validate_handoff(Path(build['bitfile']),Path(build['hwh']),provenance)
    verify_hashes(provenance['source_hashes']);verify_hashes(provenance['original_hashes'])
    verify_hashes(provenance['checkpoint_hashes'])
    destination.mkdir(parents=True,exist_ok=False)
    def copy(source,relative):
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        return relative
    copy(build['bitfile'],'heart_v3a.bit');copy(build['hwh'],'heart_v3a.hwh')
    copy(manifest_path,'provenance/build-manifest.json')
    for name in RUNTIME_FILES: copy(ROOT/name,name)
    for name in ('heart_axi_live.py','heart_axi_capture_50hz.py'): copy(ROOT.parent/name,name)
    copy(ROOT/'docs/v3a-axi-overlay-usage-zh.md','使用说明.md')
    session=Path(build['session_dir']).resolve();source_map={};original_map={}
    for source in provenance['source_hashes']:
        relative='provenance/build_sources/'+Path(source).resolve().relative_to(session).as_posix()
        source_map[source]=copy(source,relative)
    for index,source in enumerate(provenance['original_hashes']):
        original_map[source]=copy(source,f'provenance/original_sources/{index:02d}-{Path(source).name}')
    for name in provenance['report_hashes']:
        if name!='routed.dcp': copy(Path(build['report_dir'])/name,'provenance/reports/'+name)
    cases=[]
    inputs=tuple(p.parent for root in GOLDEN_ROOTS for p in sorted(root.rglob('stimulus.mem')))
    for index,case in enumerate(inputs):
        rows=_public_rows(case);path=f'golden/case-{index:02d}/records.csv'
        _write_csv(destination/path,rows)
        cases.append(dict(path=path,name=f'{case.parent.name}/{case.name}',samples=len(rows),
            expected_clipped=sum(bool(r['status']&4) for r in rows),
            expected_saturated=sum(bool(r['status']&8) for r in rows),
            golden_source_hashes=source_hashes([case/'stimulus.mem',case/'expected.mem'])))
    if len(cases)!=9 or sum(c['samples'] for c in cases)!=15942:
        raise RuntimeError('黄金交付必须九例15942拍')
    _write_csv(destination/'controls.csv',_control_rows())
    verify_hashes(provenance['source_hashes']);verify_hashes(provenance['original_hashes'])
    files={p.relative_to(destination).as_posix():_digest(p) for p in destination.rglob('*') if p.is_file()}
    manifest=dict(schema='v3a_board_bundle_v1',build_manifest_sha256=_digest(manifest_path),
        file_hashes=files,build_source_map=source_map,original_source_map=original_map,cases=cases,
        golden_samples=15942,control_samples=20,addresses=provenance['addresses'],
        tool_version=provenance['tool_version'],timing={k:metrics[k] for k in
            ('wns_ns','whs_ns','tns_ns','ths_ns','clock_period_ns','drc_errors','unconstrained_internal_endpoints')},
        resources=metrics['resources'],integrated_timing_passed=True,bitstream_generated=True,
        board_tested=False,board_ddr_verified=False,board_replay_passed=False,
        live_50hz_passed=False,auto_beta_effect_passed=False,
        limitations_cn=['PC验证不代表上板或实采通过。','继承DDR负skew告警未解决，板端稳定性尚待检查。',
            '黄金仅公开candidate／output／status，不声称板上读取全部内部权重。'])
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return validate_bundle(destination)

def validate_bundle(bundle:Path)->dict:
    """可搬移校验：只访问包内文件，不要求板上存在原PC绝对路径。"""
    bundle=Path(bundle).resolve()
    manifest=_json(bundle/'manifest.json')
    if manifest.get('schema')!='v3a_board_bundle_v1': raise RuntimeError('交付schema不符')
    for key in ('board_tested','board_ddr_verified','board_replay_passed','live_50hz_passed','auto_beta_effect_passed'):
        if manifest.get(key) is not False: raise RuntimeError('PC交付不得预先宣称板测通过')
    def local(relative):
        path=(bundle/relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(bundle): raise RuntimeError('交付路径逃逸')
        return path
    for relative,digest in manifest['file_hashes'].items():
        path=local(relative)
        if not path.is_file() or _digest(path)!=digest: raise RuntimeError('文件缺失或SHA256哈希不符：'+relative)
    build_path=local('provenance/build-manifest.json')
    if _digest(build_path)!=manifest['build_manifest_sha256']: raise RuntimeError('实际构建身份哈希不符')
    build=_json(build_path)
    if not build['integrated_timing_passed'] or not build['bitstream_generated']:
        raise RuntimeError('实际构建未通过')
    for name,digest in build['report_hashes'].items():
        if name!='routed.dcp' and _digest(local('provenance/reports/'+name))!=digest:
            raise RuntimeError('报告与实际构建身份不符：'+name)
    if manifest['timing']!=_json(local('provenance/reports/timing_metrics.json')):
        raise RuntimeError('交付时序摘要与实际构建报告不符')
    for map_key,hash_key in (('build_source_map','source_hashes'),('original_source_map','original_hashes')):
        mapping=manifest[map_key]
        if set(mapping)!=set(build[hash_key]): raise RuntimeError('构建源闭包身份不完整')
        for source,relative in mapping.items():
            if _digest(local(relative))!=build[hash_key][source]: raise RuntimeError('实际构建源身份不符')
    for name in ('heart_v3a.bit','heart_v3a.hwh'):
        # Windows审计路径在Linux板上是文本，不交给Linux Path来重新规范化。
        candidates=[value for key,value in build['artifact_hashes'].items()
            if key.replace('\\','/').rstrip('/').endswith('/'+name)
            and key.replace('\\','/').rsplit('/',1)[0]==build['session_dir'].replace('\\','/').rstrip('/')]
        if len(candidates)!=1 or _digest(local(name))!=candidates[0]: raise RuntimeError('bit／HWH与实际构建身份不符')
    facts=inspect_hwh(local('heart_v3a.hwh'))
    if facts['addresses']!=manifest['addresses'] or facts['addresses']!=build['addresses'] or facts['tool_version']!=manifest['tool_version']:
        raise RuntimeError('HWH配套身份不符')
    if build['ddr_review']['values']!=['-0.051','-0.006','-0.009','-0.033'] or build['ddr_review']['board_ddr_verified']:
        raise RuntimeError('继承DDR风险记录不符')
    if len(manifest['cases'])!=9 or manifest['golden_samples']!=15942 or sum(c['samples'] for c in manifest['cases'])!=15942:
        raise RuntimeError('黄金清单不完整')
    for case in manifest['cases']:
        path=local(case['path'])
        if case['path'] not in manifest['file_hashes']: raise RuntimeError('黄金文件没有哈希')
        with path.open(encoding='utf-8',newline='') as stream:
            if sum(1 for _ in csv.DictReader(stream))!=case['samples']: raise RuntimeError('黄金记录数不符')
    return manifest
