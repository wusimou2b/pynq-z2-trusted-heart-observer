# 构建输入与复现范围

部署当前系统使用 [../board_runtime/](../board_runtime/)，入口为 `runtime/ContinuousDemo25.ipynb`；现成匹配 bit/HWH 和 ARM 原生库已随该完整集合提供，板端运行无需安装 Vivado。源码构建使用 **Vivado 2024.1**、Zynq-7000 器件支持和 `xc7z020clg400-1`／PYNQ-Z2 的对应板定义。

| 文件或目录 | 用途 |
|---|---|
| `inputs/input/design_1.bd` | 原基础 BD 输入 |
| `inputs/final/design_1.bd` | 已部署设计的 BD 原件参考，保留其来源用途，不替换基础 BD |
| `inputs/ip_repo/`、`inputs/pins.xdc` | 自研 IP 输入和约束 |
| `scripts/` | 原准备、布局布线和 bitstream 生成脚本 |
| `scripts/physical-postroute.tcl` | 补回的历史布局布线后检查脚本，需要对应 checkpoint 及原配套依赖 |
| `physical_summary.json` | 历史 Vivado 2024.1 实现摘要，保留未完成验收状态 |
| `rebuild.py` | 原构建包装源码，仍要求其原始完整 physical-input ZIP 及索引 |

这组公开源码与脚本用于核对实现来源。历史 `rebuild.py` 的完整输入契约不等于本目录现有文件集合；外部 PYNQ／视频 IP、板定义、AMD IP 和相应许可仍应按 [external_dependencies.md](external_dependencies.md) 准备。补回原件不代表本轮重新执行对应脚本，也不表示干净系统已完成综合布线或原生库重编译。

本次来源交付在独立目录完成了 Vivado 2024.1 工程准备及边界 RTL 仿真，保存了 91 项当前 PL 来源哈希一致的记录；完整物理实现报告属于历史证据。本次公开整理没有重新构建 PL、重编译 ARM 库或操作板卡。重新生成的 bit/HWH 和原生库需建立新身份与相应验证，不能仅替换清单哈希冒充原运行资格。

现有应用运行于 Linux/PYNQ，未把裸机 ELF 或 XSA 作为启动资产；应按实际流程使用匹配文件，保持 bit/HWH 成对。
