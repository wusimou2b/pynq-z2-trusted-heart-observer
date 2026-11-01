# 真正冷启动与退出记录

## 入口边界

离线 `verify` 仅检查文件。`spawn` 需要显式执行 flag 与预期 manifest 摘要，只调用已审阅的纯软件预检。示例使用普通数组求和；实际工程可在纯预检中检查配置解析、相对路径、纯算法构造和函数签名，但不能分配 CMA、访问设备或构造 Overlay。

不要把 `Overlay(download=False)`、导入成功或 `PURE_PREFLIGHT=True` 当作无硬件访问证明。真实 import 可能有副作用；工具拦截 pynq/cv2/serial/smbus/smbus2/usb/periphery 只是常见误用检测，不是完整隔离。

## Worker 参数

脚本采用真实 `multiprocessing.get_context('spawn')`。顶层 `verified_worker(connection, *, root, manifest_name, expected_sha256, run_id)` 通过 `functools.partial` 绑定 keyword-only 参数，Process 只传 connection。不要把签名不相容的 worker 直接塞进只传两个位置参数的既有 Bridge。

子进程先复查文件身份，再加载入口；不继承旧 Notebook 内核已经 import 的模块实例。声明的本地模块/顶层包如果与检查器启动时已导入模块重名，会明确拒绝，避免例如本地 math.py 被标准库 math 遮蔽。入口实际文件必须位于清单目录，再 `inspect.signature(...).bind(**kwargs)`，最后调用。

子进程在导入入口前将自己的工作目录设为 bundle 根目录，相对数据路径从此处解析；父进程目录不变。文件身份不替代所有传递依赖来源证明；需要固定 site-packages/原生库版本时另列环境约束。

时刻记录是从本次子进程起点累计的 perf_counter 纳秒，仅用于启动阶段定位，不跨进程直接相减。数据结果限 32 KiB JSON，回执带独立 run_id；不发送大型逐样本流。

## 退出和故障

父进程持有的 deadline 覆盖本次等待与自然退出，默认 10 秒，可按纯软件检查需要显式设置。函数已返回但非 daemon 线程阻止退出时，单列 exit 阶段超时。它不是项目的硬件保护时间，不应用来放宽实际采集。

worker 异常转换为有阶段的失败回执；退出后先保存 pid/exitcode/alive 状态，再关闭 Process。报告只读保存的标量，不读取已关闭 Process 对象的属性。

仅对本工具创建的纯软件子进程，超时才终止并标注 forced_termination=true；该结果不能称为自然退出通过。工具不会查杀其他内核，也不管理板级资源。持有 DMA 或映射的进程要走原所有者收尾。

通过条件为：父子身份检查成功、入口执行返回、无被吞掉的硬件导入尝试、JSON 回执身份匹配、子进程 exitcode=0 且自然退出。缺模块、错误 kwargs、取消/异常、超时分开保留；失败后不由这个工具自动重跑。

## 独立验证

测试覆盖 Notebook 仅保存输出、源码/顺序/kernel/tags/attachments 变动、额外源文件、运行目录隐藏代码、摘要不符先于导入、真实 spawn 参数绑定、缺依赖、硬件导入、超时、Process.close 后导出首因。

本地 Windows/Python 检查不代替 ARM/Linux 上的原生依赖和驱动 ABI 检查。板端纯软件预检应沿用同一命令与输入身份；之后再按本次授权进入硬件测试。
