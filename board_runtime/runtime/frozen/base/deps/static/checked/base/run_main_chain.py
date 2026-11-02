"""V2 主链 CSV 回放与中文结果入口。"""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import mkdtemp

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from heart_v2.dataset import load_capture
from heart_v2.joint_benefit import POLICY as JOINT_POLICY
from heart_v2.runtime_main_chain import ALGORITHM, replay_main_chain, runtime_config
from heart_v2.runtime_state import MOTION_POLICY, QUALITY_POLICY


MOTION_CN = {'static': '静止', 'light': '轻运动', 'heavy': '强运动'}
QUALITY_CN = {'good': '优', 'medium': '中', 'bad': '差'}
ROUTE_CN = {'raw': '原始基线', 'mean': '四点均值',
            'nlms': '联合许可混合输出', 'none': '无有效支路'}
SOURCE_FLAGS = ('pair_ok', 'accel_valid', 'pl_fifo_ok', 'contact_ok', 'error')
LIMITATIONS = [
    '本入口是 Python 离线回放／逐样本模型，未部署到 PL 或替换板端 Notebook。',
    '运动与 SQI 阈值是冻结工程默认值，未经临床标定；三级质量不是准确率百分比。',
    '记录间隔可能来自名义／重建时间轴，记录率不代表 ADC 物理时钟精度。',
    '取消了旧 22–38 秒学习掩码；旧收益与失败不能直接当作新入口的效果结论。',
    '三份核心文件均为已用数据回归，不是新的独立验证；无对齐外部读数时不计算 BPM 准确率。',
]


def _load_source(input_path):
    source_bytes = input_path.read_bytes()
    identity = hashlib.sha256(source_bytes).hexdigest()
    dataset = load_capture(input_path)
    if identity != dataset.source_sha256:
        raise ValueError('读取期间输入文件发生变化，请使用稳定的采集文件')
    # 保留 NA 等非空错误文字；旧加载器的数值校验仍复用。
    literal = pd.read_csv(BytesIO(source_bytes), keep_default_na=False)
    for key in ('sequence', 'ir_raw', 'time_s', 'timestamp_us'):
        if key in literal and any(isinstance(value, (bool, np.bool_)) for value in literal[key]):
            raise ValueError(f'{key} 不允许布尔值冒充数值')
    source = pd.DataFrame(dict(dataset.columns))
    for key in (*SOURCE_FLAGS, 'reset'):
        if key in literal:
            source[key] = literal[key]
    if 'contact_ok' in source:
        source['contact_ok'] = source.contact_ok.map(lambda v: None if v == '' else v)
    if 'time_s' in source:
        times = pd.to_numeric(source.time_s, errors='raise').to_numpy(dtype=float)
    else:
        times = source.timestamp_us.to_numpy(dtype=float)/1e6
    intervals = np.diff(times)
    if not len(intervals) or not np.isfinite(intervals).all() or np.any(intervals <= 0):
        raise ValueError('主链需要至少两行严格递增的时间')
    median_dt = float(np.median(intervals))
    if not .018 <= median_dt <= .022:
        raise ValueError('新入口只接收约 50 Hz 文件；旧 10 Hz 文件请用原工具')
    return source, dataset, median_dt


def create_run_directory(output_root):
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return Path(mkdtemp(prefix='v2-main-chain-', dir=root))


def _counts(values):
    return {str(key): int(count) for key, count in Counter(values).items()}


def _summary(source, dataset, frame, config, median_dt):
    allowed = frame.output_allowed
    previous_allowed = allowed.shift(fill_value=False)
    durations = float(frame.time_s.iloc[-1]-frame.time_s.iloc[0])
    pairing = 'recorded_pair_ok' if 'pair_ok' in source else 'finite_axes_inference'
    missing = [key for key in SOURCE_FLAGS if key not in source]
    limitations = list(LIMITATIONS)
    if pairing == 'finite_axes_inference':
        limitations.append('源文件缺少 pair_ok，仅由有限轴推断兼容配对；不能作为硬件同步证据。')
    if missing:
        limitations.append('源字段缺失：'+', '.join(missing)+'；可选故障标志使用接口默认值。')
    return dict(schema_version='v2_main_chain_v1', samples=len(frame),
        input=dict(path=str(Path(dataset.source_path).resolve()), sha256=dataset.source_sha256,
                   schema=dataset.source_schema),
        parameters=dict(**config, nlms=dict(ALGORITHM), joint_selector=dict(JOINT_POLICY),
                        motion=dict(MOTION_POLICY), quality=dict(QUALITY_POLICY),
                        learning_permission='valid_and_contact_update_allowed'),
        median_record_interval_s=median_dt, median_record_rate_hz=1./median_dt,
        elapsed_record_time_s=durations,
        span_record_rate_hz=(len(frame)-1)/durations if durations > 0 else None,
        pairing_source=pairing, missing_source_fields=missing,
        valid_samples=int(frame.valid.sum()), learning_update_samples=int(frame.learning_update.sum()),
        output_allowed_samples=int(allowed.sum()), output_coverage=float(allowed.mean()),
        hard_blocked_samples=int((~frame.valid).sum()),
        waiting_or_quality_blocked_samples=int((frame.valid & ~allowed).sum()),
        route_counts=_counts(frame.selected_route), motion_counts=_counts(frame.motion.fillna('not_ready')),
        quality_counts={key: _counts(frame[key+'_quality']) for key in ('raw','mean','nlms','joint')},
        branch_bpm_coverage={key: float(frame[key+'_bpm'].notna().mean()) for key in ('raw','mean','nlms','joint')},
        selected_quality_counts=_counts(frame.selected_quality),
        blocking_reason_counts=_counts(frame.loc[~allowed,'reason_cn']),
        route_switches=int(frame.selected_route.ne(frame.selected_route.shift(fill_value='none')).sum()),
        block_events=int((~allowed & previous_allowed).sum()),
        output_start_or_recovery_events=int((allowed & ~previous_allowed).sum()),
        segment_boundary_samples=int(frame.reset_reason.ne('').sum()),
        nlms_mixed_samples=int(frame.nlms_mix.gt(0).sum()),
        selected_nlms_samples=int(frame.selected_route.eq('nlms').sum()),
        joint_protection_samples=int(frame.joint_protection.sum()),
        joint_reason_counts=_counts(frame.joint_reason),
        forbidden_bpm_samples=int((~allowed & frame.bpm.notna()).sum()),
        replay_integrity_passed=bool((~allowed & frame.bpm.notna()).sum() == 0),
        research_acceptance_passed=False,
        research_status_cn='未宣称自动优于固定或轻运动可重复改善；原性能门槛与历史失败保留',
        limitations_cn=limitations)


def _configure_chinese_font():
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ('Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Micro Hei'):
        if name in available:
            plt.rcParams['font.family'] = name
            plt.rcParams['axes.unicode_minus'] = False
            return
    raise RuntimeError('缺少可用中文字体；主链结果不应交付为方框文字')


def _plot(frame, path):
    _configure_chinese_font()
    t = frame.time_s.to_numpy()
    fig, axes = plt.subplots(5, 1, figsize=(14, 14), sharex=True, constrained_layout=True)
    try:
        for key, name, color in [('raw','原始基线','#999999'), ('mean','四点均值','#df9b1c'),
            ('nlms_candidate','限幅 NLMS 纯候选','#247c9f'), ('joint_output','联合许可混合波形','#9467bd')]:
            axes[0].plot(t, frame[key], color=color, label=name, linewidth=.9, alpha=.8)
        axes[0].plot(t, frame.selected_signal, label='实际选路波形', color='#242424', linewidth=1.)
        axes[0].set(ylabel='归一化 PPG', title='V2 主链回放：纯候选与实际混合分开显示')
        axes[0].legend(loc='upper right', ncol=3)
        for key, name in [('raw','原始基线'), ('mean','四点均值'), ('nlms','NLMS 候选'), ('joint','联合混合')]:
            axes[1].plot(t, frame[key+'_bpm'], label=name, linewidth=.8, alpha=.5)
        axes[1].plot(t, frame.bpm, color='#c2185b', label='最终心率；断线表示 N/A', linewidth=1.8)
        axes[1].set(ylabel='心率（次／分钟）')
        axes[1].legend(loc='upper right', ncol=3)
        axes[2].step(t, frame.motion.map({'static':0,'light':1,'heavy':2}), where='post', label='运动状态')
        axes[2].step(t, frame.selected_quality.map({'bad':0,'medium':1,'good':2}), where='post', label='选路质量', alpha=.7)
        axes[2].set(ylabel='状态／质量', yticks=[0,1,2], yticklabels=['静止／差','轻运动／中','强运动／优'])
        axes[2].legend(loc='upper right')
        axes[3].step(t, frame.nlms_mix, where='post', label='NLMS 混合系数')
        axes[3].step(t, frame.contact_ready.astype(int), where='post', label='接触已就绪', alpha=.7)
        axes[3].step(t, frame.output_allowed.astype(int), where='post', label='最终输出许可', alpha=.7)
        axes[3].set(ylabel='系数／许可', ylim=(-.1, 1.15))
        axes[3].legend(loc='upper right', ncol=3)
        axes[4].step(t, frame.selected_route.map({'none':0,'raw':1,'mean':2,'nlms':3}), where='post', color='#242424')
        axes[4].set(ylabel='实际选路', xlabel='记录时间（秒）', yticks=[0,1,2,3],
                    yticklabels=['无有效支路','原始基线','四点均值','联合许可混合'])
        axes[4].set_title('N/A 的具体阻断／等待原因见逐样本结果 reason_cn；质量中仅表示允许输出估计', fontsize=10)
        for ax in axes:
            ax.grid(alpha=.2)
        fig.savefig(path, dpi=140)
    finally:
        plt.close(fig)


def _readme(summary):
    return '\n'.join([
        '# V2 主链回放结果', '',
        f"输入：{summary['input']['path']}",
        f"样本数：{summary['samples']}；有效心率输出率：{summary['output_coverage']:.1%}", '',
        '逐样本结果.csv 保留机器字段，追加中文状态。bpm 空值表示 N/A，不是 0 次／分钟。',
        'nlms_candidate 是纯限幅候选；joint_output 是联合选择器混合；selected_signal 是实际选路。',
        '原始／均值／NLMS 候选／联合混合使用相同判峰与质量规则；最终输出单独重建峰间隔。',
        '静止优先均值；运动只在联合收益许可且质量合格时采用混合，否则退回基线。',
        '接触、配对、采集错误或质量不足阻断心率；切路／恢复后等待两个新峰间隔。', '',
        '## 解释边界', '', *['- '+line for line in summary['limitations_cn']], '',
        summary['research_status_cn'], '',
        '本结果只证明该输入成功回放；完整工程验收还需合成测试及全项目回归证据。',
        '后续是 V3-A 定点／RTL／板端工程，不在此入口添加视频或新算法。', ''])


def run_capture(input_path, output_root):
    input_path = Path(input_path).resolve()
    source, dataset, median_dt = _load_source(input_path)
    config = runtime_config()
    frame = replay_main_chain(source, config)
    summary = _summary(source, dataset, frame, config, median_dt)
    frame['运动状态_cn'] = frame.motion.map(MOTION_CN).fillna('未就绪')
    frame['信号质量_cn'] = frame.selected_quality.map(QUALITY_CN)
    frame['选路_cn'] = frame.selected_route.map(ROUTE_CN)
    frame['接触状态_cn'] = np.where(~frame.contact_ok, '异常', np.where(frame.contact_ready, '已就绪', '恢复中'))
    # 标签仅附在结果供对照展示，不传给任何状态或算法决策。
    if 'phase' in source:
        frame['phase'] = source.phase.to_numpy()
    directory = create_run_directory(output_root)
    frame.to_csv(directory/'逐样本结果.csv', index=False, encoding='utf-8-sig')
    (directory/'summary.json').write_text(json.dumps(summary, ensure_ascii=False,
        indent=2, allow_nan=False)+'\n', encoding='utf-8')
    _plot(frame, directory/'主链回放.png')
    (directory/'使用说明.md').write_text(_readme(summary), encoding='utf-8')
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description='V2 50 Hz 主链离线回放，不改板端文件')
    parser.add_argument('input', type=Path, help='原始 50 Hz CSV')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'main_chain_closeout', help='新结果根目录')
    args = parser.parse_args(argv)
    try:
        directory = run_capture(args.input, args.output)
    except (ValueError, OSError, RuntimeError) as exc:
        print('主链回放失败：'+str(exc), file=sys.stderr)
        return 2
    print('主链回放已生成：'+str(directory))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
