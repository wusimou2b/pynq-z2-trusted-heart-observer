# 可信心率观测系统

系统在 PYNQ-Z2 上联合处理 PPG、惯性和视频观测：PL 承担心率计算主链、视频颜色转换及 4×3 分块运动统计，PS 负责采集配对、质量判断、选路、进程通信与显示。PPG/IMU 采集及处理目标为 25 Hz，视频目标为 5 fps；视频和惯性提供运动背景，设备本地运行不依赖大模型推理。

当前运行入口是 [board_runtime/runtime/ContinuousDemo25.ipynb](board_runtime/runtime/ContinuousDemo25.ipynb)。本次以用户确认正常运行的相对路径包为来源，完整保留其中 958 个运行文件及原身份链。旧 `public_live` 封装有启动、退出问题，已由本入口取代；旧提交和旧 Release 文件属于历史版本。

| 目录或文件 | 用途 |
|---|---|
| [board_runtime/](board_runtime/) | 完整板端运行文件、匹配 bit/HWH、ARM 原生库、资格记录及校验器 |
| [board/README.md](board/README.md) | 接线、四单元操作、正常停止和结果位置 |
| [src/README.md](src/README.md) | RTL/ROM、PS、HLS 及算法参考源码 |
| [build/README.md](build/README.md) | BD、XDC、Tcl 及源码重建边界 |
| [skill/README.md](skill/README.md) | 八项完整工程 Skills、工具、样例、测试及许可 |
| [report/README.md](report/README.md) | 29 页设计报告、独立协作记录和中英文一页海报 |
| [runtime_closure.md](runtime_closure.md) | 当前运行集合的身份、实测及未验证项 |
| [reproduction/source_run_20261102.json](reproduction/source_run_20261102.json) | 本次保存运行的可发布摘要 |
| [data/README.md](data/README.md) | 用户实测数据及历史摘要的来源 |

## 硬件与系统条件

复现使用相同 PYNQ-Z2、兼容原生库的 32 位 ARM hard-float Linux 系统、相同传感器和接线。目标器件为 `xc7z020clg400-1`。现成原生库要求 CPython 3.10、SOABI `cpython-310-arm-linux-gnueabihf` 和 NumPy 1.21.5；源码要求 PYNQ 3.1.1。历史记录直接记有 CPython 3.10.4、SciPy 1.8.0，视频记录记有 OpenCV 4.5.4。pandas、IPython、ipykernel 和经典 Jupyter Notebook 也用于运行，但精确版本及原始 SD 镜像、Linux 内核和浏览器版本尚未全部归档；这些信息不能组成完整环境 lock。证据见 [环境版本说明](reproduction/environment_evidence_lock.md)。

两个传感器共用下列 I²C 总线，模块供电 **3.3 V 并共地**，按板上接口编号与模块丝印逐项核对。

| 信号或设备 | 连接／地址 |
|---|---|
| SDA | Arduino 接口 **J3-10**，FPGA 管脚 **P16** |
| SCL | Arduino 接口 **J3-9**，FPGA 管脚 **P15** |
| MAX30102 | SDA、SCL 接上述总线，7 位地址 **0x57** |
| MPU6050 | SDA、SCL 接上述总线，使用 **0x68** 地址配置 |
| USB 摄像头 | 板端 USB，支持原运行配置的 YUYV 视频输入 |
| 显示器 | PYNQ-Z2 的 HDMI 输出；浏览器用于四路波形和停止按钮 |

## 部署与依赖检查

下载本仓库或当前 Release 的源码／运行包，把**整个 `board_runtime/`** 复制到板端 Jupyter 根目录下的新目录。外层目录可以整体改名或移动；必须保留内部 `runtime/` 与 `v3b25 native100 heart video/` 两个同级目录及其中原文件名。后者是既有原生依赖的兼容名称，不是产品名称。只复制 Notebook 或 `runtime/` 会缺少原生依赖。

先在成功 Notebook 对应的 Python 环境中检查版本；下面的元数据检查不加载 Overlay：

```sh
python3 - <<'PY'
import sys, platform, sysconfig
from importlib import metadata
print(sys.version, platform.machine(), sysconfig.get_config_var('SOABI'))
for name in ('pynq', 'numpy', 'scipy', 'pandas', 'opencv-python', 'ipython', 'ipykernel', 'notebook'):
    try:
        print(name, metadata.version(name))
    except metadata.PackageNotFoundError:
        print(name, 'no distribution metadata; check system package installation')
PY
python3 -m pip check
python3 -B board_runtime/verify_portable.py
```

若改了外层目录名，将最后一行换成实际目录。校验器会核对 957 个清单成员和原身份链，不启动硬件。OpenCV 等系统安装的包可能没有同名 pip 元数据，应同时核对原系统包记录。

缺包时，在**同一个板端 Python 环境**中按成功环境的镜像、系统仓库或已保存 wheel 补齐 PYNQ、NumPy、SciPy、pandas、OpenCV、IPython、ipykernel 和经典 Notebook；保留上述已知版本，记录未锁定组件的实际版本。安装核对过的本地兼容 wheel 可用 `python3 -m pip install --no-deps /path/to/matching_package.whl`，再执行 `python3 -m pip check`。仓库没有凭空补全的完整 lock，也没有在新 SD 系统上完成安装验收。普通 PC 不具备这些 ARM 库的运行 ABI。

在经典 Notebook 中打开 `board_runtime/runtime/ContinuousDemo25.ipynb`，使工作目录为其所在的 `runtime/`。先核对包，再按以下顺序分别执行四个代码单元，勿使用 Run All。

| 单元 | 操作与继续条件 |
|---|---|
| 1：PS 短检查 | 执行 `check(expected)`、`short(expected)`，等待身份检查和无硬件短检查正常返回 |
| 2：20 秒视频检查 | 其他硬件入口正常收尾后，输入 **`RUN-DEMO-VIDEO20`**；确认画面和序号持续更新，等待检查及清理结束 |
| 3：浏览器准备 | 执行 `prepare(expected)`，看到绿色绘图就绪提示，并保留本单元的“正常停止并导出”按钮可见 |
| 4：连续采集 | 放稳手指和传感器，输入 **`RUN-DEMO-CONTINUOUS25`**；预热另计，随后进入采集 |

连续采集由第三单元的**“正常停止并导出”**按钮结束；点击后等待第四单元返回、导出完成和资源清理结果。它不会在 60 秒自动结束，原固定审计容量及故障停止保护仍有效。运行期间保持一个硬件所有者；停止未完成时保留现场与输出，先核对状态再启动其他入口。

结果写在入口所在的 `runtime/`：短检查为 `demo-short-results.zip`，视频检查为 `demo-preview20-results.zip`，正式结果为 `demo-continuous-results.zip`、`continuous-results.zip`、对应 JSON 及 `continuous-results/` 下的 CSV／日志。保留失败和正常停止结果，不用删除结果来恢复分发快照。普通文件按原清单校验，Notebook 源码身份按随包校验器策略处理；保留原下载包和工作副本便于回查。

## 本次实测与数据说明

本次已保存运行在 **33.193811316 秒**后手动停止，832 条原始记录全部处理并保存，830 条配对、2 条未配对，视频完成 166 帧，402 条结果允许发布心率。三类队列满计数均为 0，PS 自然退出，队列排空，相机、HDMI、缓冲区和租约收尾完成。这些是保存记录的核查结果，本次发布整理没有重新启动板端测试。

公开运行集合依用户授权保留其自行采集的数值实测及派生记录、历史资格验证记录和 8 点无硬件预检输入，以维持原检查与可复现性。8 点预检在无硬件进程中使用已保存的派生输入。本次原始和结果 CSV 在 [data/measured_20261102/](data/measured_20261102/)。旧报告中的 **80.652 秒、2021 条、403 帧**是另一轮历史联合运行，不能与本次记录合并。

原始 `manual_session_passed=false` 仍保留：旧 `video_original`、`original_binding` 检查不适配现有空间视频组合。分项运行、停止和资源清理事实分别列出，没有改成全部验收通过；这些记录也不证明医学准确率、严格实时、长期连续运行或干净系统完整复现。详见[运行闭包](runtime_closure.md)。

## 源码、许可与视频

运行使用随包匹配资产，无需安装 Vivado。PL 源码构建使用 Vivado 2024.1；基础 BD、已部署 BD 参考、历史 Tcl 和算法生成源的用途及外部依赖见 [build/](build/README.md)。现有 Linux/PYNQ 应用不以裸机 ELF 或 XSA 为运行入口，未加入不匹配的同名产物。

原生组件许可保留在 [licenses/native/](licenses/native/)，硬件组件许可保留在 [licenses/hardware/](licenses/hardware/)，数学源码声明在 [src/licenses/](src/licenses/)。原创部分、八项 Skills 和第三方组件分别遵循各自许可；根 MIT 许可不替代 BSD、LGPL 或其他原有条款。

演示视频正在修订接线画面。本次文档不把旧视频或尚未验收的修订视频作为完成版。
