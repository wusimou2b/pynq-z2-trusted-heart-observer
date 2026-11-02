# 匹配原生依赖

当前完整运行集合位于 [../board_runtime/](../board_runtime/)，入口为 `runtime/ContinuousDemo25.ipynb`。`runtime/` 与 `v3b25 native100 heart video/` 保持同级，原 statistics 扩展、四个 readback／sample／scheduling 辅助库、C／汇编来源、准备／资格记录和 guard pin 均保留。使用原相对路径解析，不套用旧 `public_live` 包装，也不重新封装 guard 链。

现成库要求 ARM32 little-endian hard-float、CPython 3.10／`cpython-310-arm-linux-gnueabihf` 和 NumPy 1.21.5；源码要求 PYNQ 3.1.1。SciPy、pandas、OpenCV、IPython、ipykernel 和经典 Notebook 也用于相关运行路径。已知版本及尚未锁定的信息见[环境证据](environment_evidence_lock.md)，依赖检查与补包方法见[根 README](../README.md)。

运行所需的用户实测／派生输入、历史资格输入和 8 点无硬件预检输入依授权随原集合保留。已有 33.193811316 秒硬件运行证据与原资格记录分别报告；本次发布整理没有重新执行 ARM 库或启动板测。原始 `manual_session_passed=false` 及旧身份检查 false 保留，不能视为新系统全部验收。

组件许可见 [../licenses/native/](../licenses/native/)、[../licenses/hardware/](../licenses/hardware/) 和 [../src/licenses/](../src/licenses/)。同名或相似版本的另一个库不能替代原固定 SHA256 身份；重编译需独立建立并核验新身份。
