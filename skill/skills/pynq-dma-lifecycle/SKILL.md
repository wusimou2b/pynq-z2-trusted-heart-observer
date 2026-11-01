---
name: pynq-dma-lifecycle
description: 分析 PYNQ 的 DMA/PynqBuffer 所有权、缓存同步、传输结束和资源释放。用于 DMA wait 卡住、缓冲区提前释放、跨进程交接、停止后资源仍占用等问题；提供离线事件审计，不绑定应用或板卡，明确区分 simple DMA、SG、cyclic 与 VDMA。
---

# PYNQ DMA 与缓冲区生命周期

先明确设备、驱动与传输模式，再判断何时可以读取、复用和释放缓冲区。

## 工作流程

1. 从 HWH、实际驱动和现有日志确认 DMA 类型、方向、数据宽度、DRE、地址位宽、长度上限、buffer dtype/字节数、coherent 属性。缺失值保持未知，不默认套用某块板的参数。
2. 为每个通道和分配明确所有者，为跨进程借用、切片/view 记录归还关系。普通 pickle 不保证 PynqBuffer 的设备映射和生命周期可跨进程传递。
3. 区分 CPU 写后向设备同步、设备写后向 CPU 同步。核对驱动已经执行的 flush/invalidate，不重复增加缓存同步成本。
4. wait 超时先查长度、地址、状态位、流背压、TLAST、时钟/复位及驱动契约。超时不等于已证明 TLAST 缺失，也不表示设备已经停止访问内存。
5. 收尾按实际数据流停止生产、停止新提交、等待完成或验证停止，再归还视图/借用并释放缓冲区。停止请求、DMA 停止、buffer 释放和进程退出分别记录。
6. 复用已保存记录进行离线审计。仅在真实接口需要时增加记录，避免把逐拍 JSON 导出加入实时热路径。具体事件格式见 [trace.md](references/trace.md)，模式差异与收尾见 [operations.md](references/operations.md)。

## 可运行工具

在本技能目录运行，使用新的输出文件名：

```sh
python scripts/audit_dma_trace.py --trace assets/simple-send.json --output send-audit.json
python scripts/audit_dma_trace.py --trace assets/simple-receive64.json --output receive-audit.json
python scripts/audit_dma_trace.py --trace assets/timeout-active.json --output timeout-audit.json
python -B -m unittest discover -s tests -v
```

前两个合成样例应退出 0；第三个是故障样例，应退出 2 并报告仍在途的传输/未释放缓冲区。退出码 0 只证明事件声明自洽，不能证明板端收尾已经完成。

## 工具 v1 支持范围

- 定长、整缓冲、`axi-dma-simple`；支持 32/64 位等显式地址约束、coherent/非 coherent、DRE 对齐、所有者/借用/view。
- 拒绝 SG、VDMA、cyclic 和部分区间传输；必须针对该模式补适配器及测试，不能删字段或改模式名称以通过检查。这是工具范围，不代表 PYNQ 本身只支持 simple DMA。
- 只读 JSON，不导入 PYNQ，不分配 CMA，不操作 DMA，不关闭进程。详见事件契约。

## 交付结论

同时给出首个事件错误、原故障、仍在途传输、未释放缓冲区和已知/未知的实际收尾状态。原故障不会因后续清理成功而消失。不要把进程退出、Notebook idle 或 timeout 当作资源已释放。

若结束访问尚未证明，保留所有者和相关缓冲区，不强制释放/杀进程后宣称成功；根据现有授权执行模式专用的恢复步骤。既有用户授权持续有效，无需为每次普通检查再确认。
