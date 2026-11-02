---
name: pynq-ps-pl-profiler
description: 分析 PYNQ/Zynq 的 PS/PL 分阶段耗时、C 返回、IPC、任务间隙与连续块尾延迟，核对普通 ABBA 计时和独立数值结果。适用于定位处理链开销与验证性能改动，不负责部署 Overlay 或操作板卡。
---

# PYNQ PS/PL 分阶段计时

先使用已有记录回答“时间花在哪里、证据是什么、哪些仍未知”。技能可单独解压运行，仅依赖 Python 3.10+ 标准库；运行脚本不会导入 PYNQ、连接板卡或改动驱动。

## 选择入口

- 审查已有记录或接入新格式：读 [计时数据契约](references/schema.md)，用 `scripts/analyze_phases.py` 生成逐记录报告。
- 设计埋点、解释 C 返回或 IPC、安排优化验证：读 [测量与归因](references/measurement.md)。复用已有计数器和边界；确需新测量时再调整 `scripts/collector_template.py`。
- 核对算法结果：用 `scripts/verify_outputs.py` 对同一批保存输入的结果作独立比较；容差来自数值契约，不能因性能更好而放宽。

## 必须保持的判断

1. 区分普通计时 `normal_timing` 与诊断埋点 `phase_profile`。A1→B1→B2→A2 的普通计时只测任务边界；诊断埋点的加速比不能替代普通 ABBA 证据。
2. 每个区间声明实际时钟、计时源和作用域。只在同一时钟域内求差。PL cycles 转时间须有频率与来源；缺失时仅报告 cycles。CPU、PL、wall 分开报告，不能相减拼出“GIL”“IPC”“C 返回”或“纯 PL 等待”。
3. 只把有直接边界观测的时间归到具体阶段。嵌套 span 的 inclusive 值不能相加；分析器用最深阶段互斥归因，同级重叠标为 `ambiguous_overlap`，未覆盖部分标为 `unknown_unobserved`。
4. 保留首条、每个 sequence、无效与未知记录；不静默丢弃预热、超时、失败、异常或慢点。序号缺口与 generation 变化切断连续块。每个连续块使用同域首任务开始至末任务结束，包含中间间隙；Hz 与块大小由任务指定。
5. 只有输入记录、顺序、有效性、workload、配置与 wall 时钟一致时才比较 ABBA。仅允许 implementation 在 A/B 之间按设计变化；缺少事实写未知。数值、计时、硬件验收分别结论。
6. 采集器在测量前预分配固定容量，满则显式停止或结束为无效，不覆盖旧数据；导出、JSON、哈希、日志和图表在任务测量外完成。新增埋点会影响耗时，先用有限诊断运行定位，再关闭阶段埋点做普通计时。没有“零开销”承诺。

## 本地可运行示例

以下命令从本技能目录执行；输出写入当前目录，运行前可改成用户选定的结果目录。所有脚本拒绝覆盖现有报告或输入，重复运行请使用新输出路径；采集器在运行前同时检查主文件和各结果文件。

```powershell
python -B scripts/analyze_phases.py assets/synthetic_phase_profile.json --output phase-summary.json
python -B scripts/analyze_phases.py assets/synthetic_normal_timing.json --task-hz 500000 --block-sizes 2 3 5 --output abba-summary.json
python -B scripts/collector_template.py --workload moving_sum --count 12 --vector-size 64 --output host-abba.json
python -B scripts/analyze_phases.py host-abba.json --output host-summary.json
python -B scripts/verify_outputs.py host-abba-outputs-A1.json host-abba-outputs-B1.json --atol 0 --rtol 0 --output numeric-summary.json
python -B -m unittest discover -s tests -v
```

内置例子是整数向量能量与四点滑动和，没有业务或医学阈值。`assets` 的时间戳完全合成，其中的 25% 改善只验证计算逻辑；`collector_template.py` 是当前主机测量，也不是板级或真实应用性能证据。数值完整性需要再核对 A2、B2 与同一参考记录，而非只看命令中的单组示范。

## 交付结论

报告数据来源与配置、首条/总条数/无效数、wall/CPU/PL 独立指标、阶段覆盖和未知量、任务间隙及最坏连续块。指出可直接支持的瓶颈与尚需观测的边界；若只有 Python 包装调用总时间，就仅称调用端到端时间。给出一个与证据对应的改动，再以同输入数值核对及普通 ABBA 复测验证。不得把本地演示、名义任务周期或单个阶段改善写成硬件通过、实时截止期通过或整链提速。
