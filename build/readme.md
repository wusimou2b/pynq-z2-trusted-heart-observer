# 从源码构建与发布输入

本目录提供可执行的输入校验、固定来源获取、HLS 生成和 Vivado 构建入口。它不访问板卡，不替换 `board_runtime/` 中已配套的 bit/HWH 或 ARM 库。部署现成系统的方法见[根说明](../readme.md)。

仓库中的 `board_runtime/` 是规范化存储目录。先运行 `python -B prepare_delivery.py runtime --output /fresh/path/runtime_bundle` 在仓库外还原原运行目录，再按还原目录中的原 Notebook 操作；不要直接运行存储目录中的 Notebook。

## 所需环境

- Vivado 2024.1、Vitis HLS 2024.1，含 Zynq-7000/`xc7z020clg400-1` 器件支持。实际历史工具版本与指南推荐版本不同，故在此明确声明。
- Python 3.10 或更新版本，仅使用标准库；Windows 和 Linux 均提供命令行入口。
- 首次构建能访问 `raw.githubusercontent.com`。可先保存清单指定的外部文件，使用 `--external-cache` 离线构建；每个文件仍必须通过 SHA256 和大小校验。
- 使用 AMD 工具和第三方组件须遵守各自原许可，根 MIT 许可证不替代这些条款。

## 输入契约

`inputs/physical-inputs.zip` 包含 109 个项目 RTL/ROM/BD/约束、BSD 许可 HLS C++ 源及许可文件。ZIP 内部名称均为小写 ASCII。`inputs/physical-inputs.json` 固定每个成员、整个 ZIP 和五个 Tcl 脚本的 SHA256，同时列出 27 个外部文件的固定 Git commit URL、大小及 SHA256。

这是一份**新的源码输入契约**，不是对旧完整物理归档的改名。历史 206 项归档的 SHA256 为 `473e2510f7902e16a69c23b84d74c56f4b0cd1c2470546bd46e166e78bbe175e`；本次从中核对并恢复项目输入，但没有公开重发其中的 AMD 工具生成 RTL/驱动或整树板定义。

外部 PYNQ 输入固定到 `Xilinx/PYNQ@19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa`；板定义固定到 `xupsh/pynq-supported-board-file@e02d6a3866b5465218f777168cdc51344ac94e07`。取得的厂商文件在仓库外保持厂商原名称，包括 Vivado 要求的 `A.0` 和 HDL 大小写。原有 25 个未修改外部文件已与保存物理输入逐字节核对一致；另补取了原先缺少的 RGB2DVI PDF 和 PYNQ 许可。

保留了原 RGB2DVI `component.xml` 更新及 `rgb2dvi_clocks.xdc` 修正：实际 SerialClk/PixelClk 均由 MMCM 拓扑派生，不能恢复上游旧的 PixelClk→SerialClk 约束。两份覆盖文件的来源和前后 SHA256 记录在 `preserved_overrides` 中。

`color_convert`、`pixel_unpack` 的工具生成 RTL 不随源包重分发。构建时由已附 BSD C++ 源进行 C 仿真、HLS 综合及 IP 导出，并检查生成 IP 的 `xilinx.com:hls:<name>:1.0` 身份，然后交给 Vivado。

## 执行顺序

只核对随包输入，不联网、不启动工具：

```sh
python -B build/rebuild.py --check-only
```

输出构建阶段说明，不启动工具：

```sh
python -B build/rebuild.py --output /fresh/path/heart_build
```

完整构建（输出目录必须不存在，且必须位于仓库外）：

```sh
python -B build/rebuild.py --output /fresh/path/heart_build --execute --vivado /path/to/vivado --hls /path/to/vitis_hls
```

Windows 可分别传 `E:/Xilinx/Vivado/2024.1/bin/vivado.bat` 和 `E:/Xilinx/Vitis_HLS/2024.1/bin/vitis_hls.bat`，实际安装路径由使用者填写。若使用离线缓存，追加 `--external-cache /path/to/cache`；缓存目录按清单中 `external_files[].path` 存放文件，不能用未校验的任意同名文件替代。

若只需验证项目准备阶段，用 `--prepare-only` 替代 `--execute`。它仍会执行 HLS C 仿真/综合/导出和 Vivado BD 校验/生成，但不执行全设计布局布线。

流程依次为：版本核对 → 输入/外部文件核对 → 两个 HLS IP 生成 → 基础 BD 准备与空间视频核替换 → 全设计综合布局布线与基础报告 → 历史等价物理优化与独立报告 → 原时序/DRC门槛核对 → 新 bit/HWH 输出。新结果在 `artifacts/`，原随包运行资产不被覆盖。失败保留目录、阶段日志及 `build-result.json`，没有自动重试或已有目录覆盖。

## 结果含义与验证

`--check-only` 成功只证明随包源输入及脚本身份，不代表工具构建完成。完整流程只有生成 bit/HWH 并通过原门槛后才写 `clean_build_completed=true`；这仍不等于上板或完整系统验收。`build-result.json`、阶段日志和报告必须一起保留。

本次实际验证进度见 `validation.json`（如存在）。即使重新生成的硬件功能一致，也不保证布局布线产物逐字节等于历史 bit；新硬件文件需单独建立身份和板端资格，本任务没有替换运行版本。

运行无硬件回归：

```sh
python -B -m unittest discover -s build/tests -v
```

`physical_summary.json` 保留为历史证据，不把它冒充本次结果。历史最终实现使用的 `scripts/physical-postroute.tcl` 现纳入正式构建顺序：基础报告/检查点保持在根输出目录，优化报告/检查点另存 `postroute/`；最终 bit 必须从优化后的检查点生成，仍检查原 WNS/WHS ≥0、固定时钟与 DRC 零错误/零严重告警。现有应用运行于 Linux/PYNQ，未为了凑清单加入不匹配的裸机 ELF 或 XSA。

## 本次构建证据（2026-11-03）

已实际执行两项 HLS C 仿真/综合/导出、基础 BD 生成、全设计综合与布局布线。基础路线 WNS 为 -0.465 ns，原写 bit 门槛正确拒绝；发现旧入口遗漏了历史最终实现的物理优化阶段后，保留该失败目录，从同一次新生成的 DCP 在独立目录补执行历史 postroute，再由原门槛核对并生成 bit/HWH。发布入口现已纳入此阶段；验证记录如实标为补阶段续建，不声称原缺步骤的一次命令已成功。

最终 WNS **+0.012 ns**、WHS **+0.051 ns**、TNS/THS **0**，DRC Error/Critical **0**。AXI/Pixel/Serial 周期仍为 10/10/2 ns，逻辑及保护门槛未放宽。时序余量很小，本次构建成功不能替代后续板端资格或外部接口完整时序验收。

`evidence/` 同时保留基础与最终两套物理报告，以及 27 个固定 URL 的真实 HTTP 200/大小/SHA 核对结果。报告仅隐藏宿主名与本机路径、统一换行；`report_sources.json` 给出原始和公开文本 SHA256。新 bit/HWH 未加入或覆盖当前运行树，`validation.json` 只记录它们的哈希与构建证据。当前板端部署仍使用冻结运行资产。
