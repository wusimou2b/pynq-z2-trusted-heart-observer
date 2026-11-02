"""V3-A独立定点主链离线回放，不加载板子、不修改V2。"""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
from run_main_chain import _load_source
from heart_v2.runtime_main_chain import replay_main_chain
from heart_v3a.runtime_pl_chain import replay_pl_chain

def run(source:Path,output_root:Path)->Path:
    source=Path(source).resolve();output_root=Path(output_root).resolve()
    frame,dataset,_=_load_source(source)
    fixed=replay_pl_chain(frame);floating=replay_main_chain(frame)
    forbidden=int((~fixed.output_allowed & fixed.bpm.notna()).sum())
    if forbidden: raise RuntimeError('阻断状态出现BPM，不能发布正常结果')
    delta=(fixed.nlms_candidate-floating.nlms_candidate).dropna()
    output_root.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix='ps-fixed-chain-',dir=output_root))
    fixed.to_csv(directory/'records.csv',index=False,encoding='utf-8-sig')
    summary=dict(source=str(source),source_sha256=dataset.source_sha256,samples=len(fixed),
        backend_source='python_fixed',board_tested=False,live_50hz_passed=False,auto_beta_effect_passed=False,
        forbidden_bpm_samples=forbidden,output_allowed_samples=int(fixed.output_allowed.sum()),
        route_counts={str(k):int(v) for k,v in fixed.selected_route.value_counts().items()},
        float_comparison=dict(samples=len(delta),candidate_max_abs_difference=float(delta.abs().max()),
            candidate_rmse=float(np.sqrt(np.mean(delta**2))),
            route_difference_samples=int((fixed.selected_route!=floating.selected_route).sum())),
        limitations_cn=['这是隔离定点软件后端，不是板上PL结果。',
            '同一联合许可选择器／接触／三级状态／质量与判峰门；量化后不要求端到端等于原浮点V2。',
            '使用既有数据做工程回归，不新增抗运动收益或准确率结论；混合支路不是纯NLMS。'])
    (directory/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return directory

def main(argv=None):
    p=argparse.ArgumentParser(description='V3-A定点软件后端离线回放')
    p.add_argument('source',type=Path);p.add_argument('--output',type=Path,default=Path('v3a_axi/results'))
    a=p.parse_args(argv);print('离线结果：',run(a.source,a.output));return 0

if __name__=='__main__': raise SystemExit(main())
