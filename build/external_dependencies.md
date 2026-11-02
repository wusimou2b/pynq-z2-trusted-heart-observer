# 外部依赖与源码重建边界

## 板端 Python 与原生库

使用[根说明](../readme.md)中的一次性部署映射，在新目录还原原运行链和约定文件名。原 958 个运行文件及保护策略保持原字节；新发布命名不等于改变 C 扩展 ABI、硬件 VLNV、寄存器映射或原身份 pin。

具体入口为 `python -B prepare_delivery.py runtime --output /fresh/path/runtime_bundle`；仓库内是规范化存储副本，执行该还原命令后才使用外部新目录中的原 Notebook。

现成原生库面向 ARMv7 little-endian Linux、32 位 hard-float ABI、CPython 3.10 和 NumPy 1.21.5。历史直接记录为 CPython 3.10.4、SciPy 1.8.0；源码要求 PYNQ 3.1.1，视频记录为 OpenCV 4.5.4。pandas、IPython、ipykernel、Notebook、SD 镜像和 Linux 内核的精确版本仍未全部锁定，不把普通 PC 环境视为板端兼容环境。见[原生依赖](../reproduction/native_dependency.md)和[环境证据](../reproduction/environment_evidence_lock.md)。

## 可执行的硬件构建依赖

构建入口和完整命令见 [readme.md](readme.md)。实际历史使用 Vivado **2024.1**、Vitis HLS **2024.1**、Zynq-7000 支持、`xc7z020clg400-1` 和 PYNQ-Z2。工具安装和 AMD catalog IP 由使用者按各自许可获取，不随项目源码整树打包。

`inputs/physical-inputs.json` 是新源码构建契约：109 个可公开随包输入，27 个固定 URL/commit/SHA256 的外部文件，两个从 BSD C++ 源本地生成的 HLS IP。公开 ZIP 与旧 206 项完整物理归档不同，旧归档 SHA 用于核对出处，不伪称两者相等。

- PYNQ 源固定到 `Xilinx/PYNQ@19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa`。构建入口获取 `axi_dynclk`、RGB2DVI、`color_swap`、TMDS 接口和 PYNQ 原许可；保留 MMCM 源原有的 Xilinx 器件使用限制。
- 板定义固定到 `xupsh/pynq-supported-board-file@e02d6a3866b5465218f777168cdc51344ac94e07`。仅下载经 SHA 校验的四个必需文件到外部构建目录，不把缺少明确再分发许可的板定义整树纳入公开源包。
- `color_convert`、`pixel_unpack` 保留公开 BSD C++ 源，Vitis HLS 在构建者本地生成 RTL/驱动/IP catalog。生成器检查 VLNV，再进入 Vivado；不把生成源代码改授 MIT。
- RGB2DVI 两份已审查覆盖文件保留 BSD 原许可，固定来源/修改前后哈希，避免恢复错误的历史上游时钟约束。详情在清单 `preserved_overrides`。

`inputs/input/design_1.bd` 是基础 BD；`inputs/final/design_1.bd` 是已部署 BD 参考，不互换。构建输出为全新文件，不能直接覆盖已配套 bit/HWH。所有硬件/原生许可分别见 [../licenses/hardware/](../licenses/hardware/) 和 [../licenses/native/](../licenses/native/)。

## 数学参考与旧辅助入口

`src/reference/main_heart_operators.py`、`main_heart_welch.py` 的 GNU C Library ARM libm/PocketFFT 数学参考仍保留其版本和许可边界。本次硬件构建使用已核对的 RTL/数学 ROM 源输入，不声称已在干净环境重新执行全部历史数学源生成器或重编译 ARM 库。

历史 `ps_core_placement`、`roi_motion_guard`、`roi_motion_runtime`、`run_nlms_rtl` 等辅助入口不是当前完整运行 API；部署应使用根说明的还原入口。许可、源码身份检查、C 仿真/综合、物理实现、板端行为分别报告，不能用任一阶段替代其他阶段。
