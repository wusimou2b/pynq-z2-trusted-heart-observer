> **2026-11-03 部署说明：** 当前仓库使用合规存储名称。本文件中的原 Notebook 名称及运行步骤仅适用于执行 `python3 -B prepare_delivery.py runtime --output ../trusted_heart_demo` 后生成的目录；请先按根目录 `readme.md` 完成准备与校验，勿直接运行仓库内的规范化副本。

# 当前运行文件与证据范围

入口为 [board_runtime/runtime/ContinuousDemo25.ipynb](board_runtime/runtime/continuousdemo25.ipynb)。当前发布恢复用户确认正常的相对路径运行集合，958 个运行文件保持来源字节，`verify_portable.py` 核验 957 个成员及原身份链。运行时保留 `runtime/` 和 `v3b25 native100 heart video/` 两个同级目录；外层可以整体移动，内部兼容名称、guard、bit/HWH、原生库、数据依赖及其 pin 不变。

旧 `public_live` 封装有启动和退出问题，本版采用上述原运行集合。针对旧封装的 81 项软件测试、6 项 JS 断言和 13 项迁移检查属于历史软件证据，不能作为本入口的新板测或全部验收证明。历史提交保留，当前部署按[根 README](readme.md)与[板端说明](board/readme.md)。

## 保存的本次实测

用户自行运行的正式窗口为 **33.193811316 秒**：832 条原始及结果全部处理保存，830 条配对、2 条未配对，402 条结果允许发布心率，视频完成 166 帧。三类队列满计数为 0；采集／视频 fault 为空，收到手动停止，PS 和所有者自然退出，队列排空，相机、HDMI、缓冲区及租约释放，导出完成。视频为应用完成帧计数，不等于曝光计数或物理屏幕刷新测量。

原始 `manual_session_passed=false` 与 `stopped_with_errors` 保留，顶层旧检查 `video_original`、`original_binding` 仍为 false。它们不适配现有空间视频组合，不能因为其余运行和收尾分项成立就改成全部通过。前两帧在清理后做过参考核对，未核对所有视频帧；医学准确率、严格实时、DDR、长期连续运行和干净系统完整复现未验证。旧 **80.652 秒／2021 条／403 帧**记录是独立历史运行。

公开集合依用户授权保留其自行采集的数值实测及派生记录、历史资格记录和 8 点无硬件预检输入，以维持原检查链。历史资格不等于本轮新验收，8 点预检不等于受试者数或新硬件采集。本轮对原运行链只做文件及保存记录核查，没有重新加载 ARM 库、下载 PL 或启动采集。

本次原始／处理 CSV 位于 [data/measured_20261102/](data/measured_20261102/)，摘要见 [reproduction/source_run_20261102.json](reproduction/source_run_20261102.json)。

## 身份与环境

原 runtime manifest SHA256：`4c92d15dae3410510c4f5e995d92d1e2a00d1c2b242623fd72ba837330311f02`。来源本地完整 ZIP SHA256：`455d1d62080b29bebb857233fde954a85800ae1446dc9e80470c010f6974d829`；源 manifest SHA256：`05eb947cc4aca61082c8d9a2f0d95d7e510ec20b543bd1df05475cf889c52119`。这些是来源身份，最终公开 Release ZIP 的 SHA256 应单独记录。

已知运行 ABI、Python／NumPy／SciPy／PYNQ／OpenCV 证据及尚未锁定的 SD 镜像、pandas、Jupyter／内核／浏览器版本见[环境证据](reproduction/environment_evidence_lock.md)。完整来源身份见 [reproduction/current_source_identity.json](reproduction/current_source_identity.json)，机器可读范围见 [runtime_closure.json](runtime_closure.json)。
