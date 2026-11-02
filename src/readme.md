> **2026-11-03 部署说明：** 当前仓库使用合规存储名称。本文件中的原 Notebook 名称及运行步骤仅适用于执行 `python3 -B prepare_delivery.py runtime --output ../trusted_heart_demo` 后生成的目录；请先按根目录 `readme.md` 完成准备与校验，勿直接运行仓库内的规范化副本。

# 设计源码与运行文件

当前板端入口是 [../board_runtime/runtime/ContinuousDemo25.ipynb](../board_runtime/runtime/continuousdemo25.ipynb)。`board_runtime/` 保留 958 个原运行文件、匹配 bit/HWH、原生库、数据依赖和 guard 链；其 `runtime/` 与 `v3b25 native100 heart video/` 必须同级，整体复制后运行。`src/` 供源码审查和重建参考，不作为另一套默认启动目录。

| 目录 | 内容与用途 |
|---|---|
| `rtl/` | 对应现有物理实现的 RTL 与数学 ROM，原数学 ROM 保持不变 |
| `ps/` | PS 源码及历史 Notebook；这些历史入口不能替代当前完整运行集合 |
| `reference/` | 数值算子、Welch、共享流程、小型心率程序和保护等参考／生成源；包含补回的 `small_heart_program.py` |
| `hls/` | 固定 PYNQ 上游版本的 color_convert／pixel_unpack C++、头文件、测试和 Tcl |
| `third_party/`、`licenses/` | PocketFFT、派生数学实现及对应许可声明 |
| `identity_reference/` | 经路径脱敏的历史身份参考，不是本目录的活动运行清单 |

`identity_reference/` 的历史文件与当前 `board_runtime/` 内原清单用途不同；当前运行以随包校验器和 guard 为准。公开运行集合依授权保留用户自行采集的数值实测、派生记录、历史资格输入和 8 点无硬件预检所需输入。

部分历史源生成器仍引用固定 ARM libm、PocketFFT 和历史目录。`small_heart_program.py` 是补齐的原参考源，不改变数学 ROM，也不构成全部生成器已在新目录从零运行的证明。完整源码重建的依赖及基础／部署 BD 区别见 [../build/README.md](../build/readme.md) 和[外部依赖](../build/external_dependencies.md)。

匹配 ARM 原生产物及其原 C／汇编来源保留在完整运行集合中；组件许可另存 [../licenses/native/](../licenses/native/) 和 [../licenses/hardware/](../licenses/hardware/)。原 ABI、VLNV、schema、兼容目录名及文件 pin 保留，产品简称为“可信心率观测系统”。
