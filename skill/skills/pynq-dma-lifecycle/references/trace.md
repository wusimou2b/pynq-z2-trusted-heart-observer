# 离线事件契约 v1

工具为标准库 Python 3.10+。输入最大 16 MiB、1–100000 条事件；拒绝重复 JSON 键、非有限数字、未知字段、跨 run_id 和序号缺口。不替缺失事件补成功回执。

## 根对象与声明

根字段：`schema="pynq-dma-trace-v1"`、非空字符串 `run_id`、非空 `buffers`/`channels` 数组、`events` 数组。

buffer 的字段必须完整且只有：

| 字段 | 含义 |
| --- | --- |
| id / owner | 唯一分配身份 / 负责释放的参与者，非空字符串 |
| nbytes / itemsize | 正整数；nbytes 必须是 itemsize 的整倍数 |
| device_address | 非负整数设备地址，不能用 CPU 虚拟地址代替 |
| coherent | 显式布尔值，来自实际 buffer/backend 契约 |

重叠物理分配拒绝；同一分配的别名用 view 表示。初始数据视为未初始化。v1 每次 CPU 读写和传输都针对整个 buffer，不追踪部分区间有效性。

channel 的字段必须完整且只有 `id, owner, kind, direction, data_width_bytes, address_bits, max_transfer_bytes, dre`。kind 只接受 `axi-dma-simple`；direction 为 send/receive；data_width_bytes 为正的 2 次幂；address_bits 为 1–64；max_transfer_bytes 为正整数；dre 为布尔值。参数由实际通道得出，不从示例复制。

## 事件

每条都有 `seq, ns, run_id, actor, event`。seq 从 0 连续递增；ns 是同一运行、同一单调时钟域的非负纳秒整数，可以相等但不能倒退。actor 为记录中的进程/组件身份，不能只凭可复用 PID 跨运行关联。

| event | 必需附加字段 | 含义/条件 |
| --- | --- | --- |
| cpu_write / cpu_read | buffer | 整缓冲读写，必须无在途 DMA；读要求数据已初始化且已同步 |
| sync_to_device / sync_from_device | buffer, via | via 为 driver 或 explicit；归属合法且无在途 DMA；invalidate 不得丢掉未同步 CPU 写 |
| borrow | buffer, borrower | 仅所有者授予借用；不能重复或授予已退出参与者 |
| return | buffer | 借用者归还，要求无在途 DMA 且已关自己的 view |
| view_open / view_close | buffer, view | view 在本 run 中唯一；关闭者必须为创建者 |
| transfer | buffer, channel, transfer, offset, nbytes | transfer 唯一；通道所有者操作已拥有/借用的 buffer；offset=0 且 nbytes=buffer.nbytes；检查长度/地址/元素/DRE 限制 |
| complete | channel, transfer, actual_bytes | 匹配在途事务；actual_bytes 必须等于请求长度，短包属于当前定长契约错误 |
| stop_request | channel | 只表示请求，不能清除在途状态 |
| halted | channel, driver_verified, active_access_ended | 两个字段都为 true；表示由对应模式驱动确认访问已结束；取消接收不产生有效数据 |
| wait_timeout | channel | 故障保留，在途访问仍保留 |
| channel_error | channel, message | 保存原故障文本 |
| free | buffer | 仅所有者；无在途传输、借用者、view |
| process_exit | 无 | 不能代替释放；仍拥有或借用未释放 buffer / 活跃 channel 时拒绝 |

`halted` 的两个布尔值是输入方提供的证据声明，审计器无法验证硬件状态。适配器必须引用真实驱动状态与设备访问终止证据，不得只看停止请求已返回。

非 coherent 的 send 在 CPU 写后必须记录已完成的 sync_to_device；receive 在 complete 后必须记录已完成的 sync_from_device 才能读。驱动内部已做同步时记录 via=driver，不能为凑事件再额外调用一次。coherent 仍须验证完成和有效数据。

## 输出

首条格式或次序错误后停止重建，保留此时未释放/在途状态。`trace_consistent`、`declared_resources_released` 与 `faults` 分开：故障后的正常清理可使声明资源全部释放，但不会抹除故障。

退出 0 / `consistent_closed`：声明一致、资源关闭且无故障。其余退出 2 / `needs_attention` 或 `invalid_input`。`hardware_cleanup_verified` 和 `hardware_accessed` 始终为 false。已有输出不可覆盖。
