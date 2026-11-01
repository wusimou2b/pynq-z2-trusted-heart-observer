# 会话与交付契约

## 身份链

源代码/数值政策 → 软件包manifest → 同源bit/HWH → 驱动ABI与寄存器映射 → 板端IP ID/version/epoch → 本次请求与结果身份。

文件哈希只证明字节与指定清单一致；未经可信来源确认的manifest不能自行证明来源可信。同名bit/HWH不能证明同源，PYNQ解析出的地址也不能代替实际IP身份读回。成功生成bit不等于板上已经下载。

`verify_bundle.py`接受明确的SHA256成员映射，只读校验。若Notebook已保存输出，原文件哈希可能变化；不要修改manifest来“修好”检查。读取该版本专用Notebook规范：通常核对cell_type、source、顺序及必要kernelspec，忽略哪些运行态字段必须有明确规则。此通用工具不会自动忽略Notebook差异。

## 运行状态

| 状态 | 可证明的事实 | 不可推导 |
|---|---|---|
| 文件检查通过 | 字节/成员身份匹配 | 硬件可用或板测成功 |
| prepare/READY | 指定准备流程完成 | 已进入正式采集 |
| 正式窗口 | 原正式标记及来源记录 | 用户屏幕实际有画面 |
| stop requested | 会话接受请求 | DMA停止、文件不再写 |
| workers exited | 指定进程/线程已退出 | 全部硬件资源释放 |
| hardware cleanup proven | 对应资源及实际租约已释放 | PS自然退出、算法准确率 |
| archived | 停写后的结果已归档 | 连续实时或完整验收 |

硬件租约是协作锁，旧入口可能不遵守它；不能只看锁是否空闲就加载新PL。Notebook标签页数量不等于运行内核数量；磁盘容量、RAM和swap是三个不同指标，按当前问题只读核实。

## 入口集成中已出现的具体陷阱

- `Bridge25`使用`Process(target=worker,args=(child,source))`的版本只能给worker两个位置参数；额外root/SHA/epoch须用顶层可pickle包装或`functools.partial`绑定，并做真实spawn短测。子进程只做warmup时，不能把它当作正式frontend已启用新政策。
- 原入口token及结果文件名前缀不会因外层包装自然改变。新runner必须明确谁执行循环、谁写attempt/final/ZIP，失败也要保留新前缀。
- `multiprocessing.Process.close()`后访问pid/is_alive/exitcode会抛异常。保存已验证的PID/退出证据，导出器不要让次生异常覆盖首因。
- 在父与child的板级导入前完成相应包身份检查；纯文件检查的模块顶层不应启动PYNQ、OpenCV、传感器或Overlay。
- 单次锁已消费、已有结果或故障锁定不能靠清变量/删目录绕过。经用户授权重测时先确认上次收尾，再从冻结包准备新目录。

## 本项目可定位的源码

在用户给定项目根内定位：

- `v3b25_integration/owner_delivery.py`：静态文件、新目录、包清单及ZIP回读检查示例。历史绝对路径需先参数化。
- `v3b25_integration/board/joint_owner.py`：无板级顶层导入、原硬件锁、IP窗口与DMA配置身份。它是早期版本，不能把其中地址/哈希直接用于新核。
- `v3b25_integration/board/README_CONTINUOUS.md`：会话专属停止请求、忙内核下正常停止和资源保留边界。
- `v3b25_integration/board/README_LEAN_PS.md`：用同一真实PS加载路径先做无硬件短退出，再进入联合实测。
- `v3b25_integration/board/joint_exit_report.py`：关闭Process对象后的匹配证据与自然退出/硬件清理分离。

这些是已发生的工程案例，具体常量随当前包冻结，不由skill固定。用户已有授权优先，不额外添加重复审批流程。
