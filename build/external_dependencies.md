# 外部依赖与源码重建边界

## 板端 Python 与原生库

当前入口为 [../board_runtime/runtime/ContinuousDemo25.ipynb](../board_runtime/runtime/ContinuousDemo25.ipynb)。复制整个 `board_runtime/`，保留 `runtime/` 与 `v3b25 native100 heart video/` 同级。958 个原运行文件和 guard 链保持不变，五个匹配原生库、C／汇编来源及原准备／资格输入一同保留，未重新编译。

现成原生库面向 ARMv7 little-endian Linux、32 位 hard-float ABI、CPython 3.10／`cpython-310-arm-linux-gnueabihf` 和 NumPy 1.21.5。历史直接记录为 CPython 3.10.4、SciPy 1.8.0；源码要求 PYNQ 3.1.1，历史视频叙述记有 OpenCV 4.5.4。pandas、IPython、ipykernel 和经典 Notebook 也需安装，精确版本与原 SD 镜像、内核及浏览器快照尚未全部锁定。

在成功 Notebook 的同一解释器中按[根 README](../README.md)先查元数据和 `pip check`。缺包按成功环境的镜像、系统仓库或兼容 wheel 补齐，保留已知版本；使用 `python3 -m pip install --no-deps /path/to/matching_package.whl` 安装核对过的本地 wheel，再检查依赖。系统 OpenCV 可能没有 `opencv-python` 的 pip 元数据。没有未经验证的完整版本 lock，也没有将普通 PC 安装 PYNQ 视为兼容 ARM 运行环境。

原生构建历史记录为 GCC 11.2.0，并固定编译器可执行文件 SHA256；版本文字相同不足以替代原编译身份。详情见[原生依赖](../reproduction/native_dependency.md)和[环境证据](../reproduction/environment_evidence_lock.md)。

## 硬件工具与 IP

实际历史实现使用 Vivado **2024.1**、Zynq-7000 支持、`xc7z020clg400-1` 和 PYNQ-Z2。工具安装与 AMD catalog IP 是遵循各自许可的外部依赖。运行随包资产不需要安装 Vivado；从源码重建是独立步骤。

PYNQ 上游输入固定到 **Xilinx/PYNQ commit `19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa`**。`src/hls/` 保留 color_convert 和 pixel_unpack 的 C++／头文件／测试／Tcl 及 BSD-3-Clause 许可。使用匹配 HLS 工具生成兼容 `xilinx.com:hls:color_convert:1.0` 和 `xilinx.com:hls:pixel_unpack:1.0`；本轮未重新验证 HLS 再生成等价性。

BD 还使用 `axi_dynclk`、`rgb2dvi`、`color_swap`、TMDS 接口和 PYNQ-Z2 板定义。按固定上游来源取得对应文件并保留限制，包括 `mmcme2_drp.v` 的器件限制；并非所有上游目录都在这里整树重分发。硬件声明见 [../licenses/hardware/](../licenses/hardware/)。

`inputs/input/design_1.bd` 是基础 BD，`inputs/final/design_1.bd` 是已部署 BD 参考，两者不得混作相同构建输入。`scripts/physical-postroute.tcl` 是历史检查原件，需要对应 checkpoint 和原配套输入。`rebuild.py` 仍要求原完整 physical-input ZIP 及索引；公开输入子集不等于该归档，因此不声明该脚本可在此一键完成全部重建。当前 Linux/PYNQ 运行流程不要求另造裸机 ELF 或 XSA。

## 数学源与历史工具

`src/reference/main_heart_operators.py` 保留固定 GNU C Library ARM libm 运算语义，历史固定 ARM 库仍有外部来源要求。`main_heart_welch.py` 固定 PocketFFT，部分路径为历史位置；对应参考 Python、RTL、数学 ROM 和 LGPL／BSD 声明均保留。补齐 `small_heart_program.py` 原件后，原数学 ROM 不变；本轮没有完整重跑全部源生成器。

历史辅助入口涉及 `ps_core_placement`、`roi_motion_guard`、`roi_motion_runtime`、`run_nlms_rtl` 等依赖，不能当作当前完整运行 API。当前运行只按完整 `board_runtime/` 的原入口及校验链使用。新编译或新硬件生成物需重新验证，不改变原通过标志。

原生及数学组件分别见 [../licenses/native/](../licenses/native/) 和 [../src/licenses/](../src/licenses/)。产品命名不改变 C 扩展 ABI、硬件 VLNV、schema、原目录名称或固定身份 pin。
