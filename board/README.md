# 板端部署与操作

当前入口为 [../board_runtime/runtime/ContinuousDemo25.ipynb](../board_runtime/runtime/ContinuousDemo25.ipynb)。使用整个 `board_runtime/`，保留内部 `runtime/` 与 `v3b25 native100 heart video/` 同级及原兼容文件名。外层目录可以整体移动或改名；从 Notebook 所在的 `runtime/` 工作目录运行。958 个运行文件来自用户确认正常的相对路径包，原身份链保持不变。旧 `public_live` 封装已停止作为当前入口。

## 平台与接线

平台为 PYNQ-Z2／`xc7z020clg400-1`，32 位 ARM hard-float Linux、CPython 3.10、SOABI `cpython-310-arm-linux-gnueabihf`、NumPy 1.21.5，源码要求 PYNQ 3.1.1。历史记录为 CPython 3.10.4、SciPy 1.8.0，视频记录为 OpenCV 4.5.4；pandas、IPython、ipykernel 和经典 Notebook 也需齐备。原 SD 镜像及全部包版本尚未锁定，按[根 README](../README.md)在同成功环境核对并补包。

| 连接 | 板端与模块 |
|---|---|
| 供电 | 两模块 **3.3 V**，GND 与板卡共地 |
| SDA | Arduino **J3-10／P16**，同时接 MAX30102 和 MPU6050 的 SDA |
| SCL | Arduino **J3-9／P15**，同时接两模块的 SCL |
| 设备地址 | MAX30102 **0x57**，MPU6050 **0x68**（7 位地址） |
| 摄像头 | 板端 USB，兼容原运行配置的 YUYV 输入 |
| 显示 | 板端 HDMI 输出；电脑浏览器显示波形与停止按钮 |

## 按顺序执行四个代码单元

部署前从仓库根目录执行 `python3 -B board_runtime/verify_portable.py`，应返回 `complete=true`、`verified_members=957`。这是文件身份核查，不访问硬件。板端 Python 与 Notebook 内核应为同一套兼容环境。

1. 第一单元执行 `check(expected)` 与 `short(expected)`，核对原身份及无硬件短检查，等待正常返回；结果为 `demo-short-results.zip`。
2. 第二单元在其他硬件入口正常收尾后输入 **`RUN-DEMO-VIDEO20`**。检查 20 秒视频，确认画面和序号更新，等待资源清理；结果为 `demo-preview20-results.zip`。
3. 第三单元执行显示准备。等到绿色绘图就绪提示，保留“正常停止并导出”按钮可见。
4. 第四单元放稳手指和传感器后输入 **`RUN-DEMO-CONTINUOUS25`**。预热另计，随后进入连续采集；本入口不在 60 秒自动结束，固定审计容量和原故障保护仍生效。

使用经典 Notebook，逐单元运行，勿 Run All。运行时保留一个硬件所有者。结束时点击第三单元的**“正常停止并导出”**，等第四单元返回并核对导出、进程退出和资源释放；停止请求已提交不等于清理已经完成。

## 结果与核查

文件写在 Notebook 同目录 `board_runtime/runtime/`（外层改名时随之移动）：`demo-continuous-results.zip`、`continuous-results.zip`、`demo-continuous-final.json`、`continuous-result.json`，以及 `continuous-results/` 中的原始／处理 CSV、事件、视频和退出记录。失败时同样保留目录和输出，先核查首故障与清理状态再考虑新会话。

用户保存的本次运行为 **33.193811316 秒、832 条全部处理保存、830 配对＋2 未配对、166 帧**，手动停止，PS 自然退出，队列排空，资源和导出完成。旧聚合身份检查保留 false；详情见[运行闭包](../runtime_closure.md)。本次发布检查没有重跑硬件，也未证明新 SD 系统复现或全部验收通过。
