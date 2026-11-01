# 迁移与驱动绑定

## 把变化放入 profile

换题目时替换 required_ips、参数和寄存器契约；换板时还须重新确认 DEVICE/PACKAGE、引脚约束、时钟、DDR/地址位宽、设备后端及 PYNQ 版本。bit/HWH 由目标设计共同生成；保留构建来源和 SHA256。不能仅改 profile 就复用不同器件的 bit。

## DefaultIP

先根据 HWH 和 IP 文档确认精确 VLNV/ABI，再定义或导入驱动，最后在授权范围内构造 Overlay。`assets/driver_factory.py` 返回一个带 `bindto` 的类：

```python
# 模板调用方式；真实 DefaultIP 的导入/实例化属于集成步骤。
Driver = make_driver(DefaultIP, vlnv=profile_vlnv,
                     readable_registers=reviewed_register_offsets)
```

模板先检查 description['type']、addr_range 和寄存器范围，然后才调用基类。读表由 IP 文档确定；不得把“只读访问”误解为“无副作用访问”。真实 PYNQ 基类构造和读寄存器可能访问设备。继承的 write 方法仍存在，模板不是权限隔离机制。

不要写固定物理基址；使用 PYNQ description 与 MMIO 映射。不要通过 `ignore_version=True` 把不同 ABI 的 IP 强行绑定。

## DefaultHierarchy

`assets/hierarchy_factory.py` 的 `make_hierarchy_driver(DefaultHierarchy, required_ips={...})` 检查 `description['ip']` 内直接子 IP 的精确 VLNV。不递归猜测孙节点、不匹配模糊名称。跨层次封装须按实际 description 定义并测试。

## 分阶段结论

1. 离线：profile/HWH/摘要通过，只记录 metadata_only。
2. 模拟：驱动参数、拒绝路径、调用次序通过，不声明实际 MMIO 正确。
3. 实板：核对当前 Overlay 与资源归属，按已授权操作加载同源 bit/HWH；读取文档明确无副作用的身份/状态，核对驱动类型，再做最小功能测试和收尾。

报告只列实际执行的阶段。另一块板需要该板的独立证据。已授权操作无需重复确认；授权缺失或确实有资源冲突时说明具体原因。

## 官方参考

- [Loading an Overlay，PYNQ 3.1](https://pynq.readthedocs.io/en/v3.1/pynq_overlays/loading_an_overlay.html)：bit/HWH 布局与加载。
- [Python Overlay API，PYNQ 3.1](https://pynq.readthedocs.io/en/v3.1/overlay_design_methodology/python_overlay_api.html)：DefaultIP/DefaultHierarchy 的绑定机制。

这些是接口参考版本；检查目标环境实际安装的驱动代码，不能仅凭文档版本推断行为相同。
