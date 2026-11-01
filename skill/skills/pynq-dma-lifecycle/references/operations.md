# 通道能力、缓存与收尾

## 适配模式

| 模式 | 必须核对 | v1 工具 |
| --- | --- | --- |
| AXI DMA simple | 方向、DRE/数据宽度、地址/长度位宽、TLAST、固定/变长契约 | 仅定长整缓冲 |
| AXI DMA SG | 描述符所有权、完成状态、环首尾、描述符缓存 | 需独立适配 |
| cyclic | 循环退出、生产/消费位置、停止后访问终止 | 需独立适配 |
| AXI VDMA / video | 帧存储、stride/尺寸、读写通道、停帧与缓冲租约 | 需独立适配 |

不要把 simple DMA 的 complete 或 halted 语义直接套给 VDMA。也不要把本工具不支持解释为 PYNQ 不支持。以部署版本和实际驱动为准。

## 分配与同步

PYNQ allocate 提供可供设备使用的缓冲区；使用实际 `device_address` 和 `coherent` 属性。CPU 虚拟地址、普通 NumPy 数组、共享内存对象不能自动当作 DMA 分配。跨进程仍需驱动/后端明确支持的映射与唯一释放协议。

用 itemsize、shape/stride、nbytes 与通道限制计算传输范围。切片可能共用分配；有活跃 view 时不能释放父分配。检查 DRE 与起始地址对齐；支持对齐重排不表示任意数据布局都有效。

核对实际驱动是否已在发送前 flush、接收完成后 invalidate。若已同步，记录其完成事实即可。不得为了审计重复同步，或把未完成接收缓冲区读成有效数据。

## 停止与释放

按实际连接图制定顺序：停止上游生产/新提交，完成或终止对应模式的 DMA，确认不会继续访问，归还 view/跨进程借用，释放分配，最后退出所有者进程。多通道系统根据上下游背压关系决定次序，没有通用的固定“三次 stop”。

只有 wait 超时、进程退出、Notebook idle、Python 对象析构或 stop 请求返回，都不能独自证明设备已停止访问。未知时保留资源并报告；不能通过强杀所有者、释放 CMA 或重复加载 Overlay 掩盖未完成收尾。

故障记录与清理记录分别保存，保持原首因。恢复/复位按该设备文档与用户现有授权执行，不擅自扩大到其他任务。

## 样例与验证

三个资产均为合成数据：数组发送、64 位 coherent 接收、超时保留在途资源。它们不包含本团队传感器或生理算法。测试覆盖缓存、地址、长度、所有权、视图、停止、异常退出等拒绝路径。

工具只检查声明的生命周期。实际板端应使用已知设计的有限 loopback/小数据传输核对数值、完成与停止回执；具体 bit 和执行次数按当前任务确定，不内置某块板的 Overlay。

## 官方参考

- [PYNQ 3.1 allocate](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/allocate.html)：Buffer、设备地址和同步。
- [PYNQ 3.1 DMA](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/dma.html)：DMA 使用和流结束要求。
- [PYNQ 3.1 Python Overlay API](https://pynq.readthedocs.io/en/v3.1/overlay_design_methodology/python_overlay_api.html)：缓冲区和驱动接口参考。

文档只作参考基线；模式支持、自动同步和停止实现须检查本机安装版本。
