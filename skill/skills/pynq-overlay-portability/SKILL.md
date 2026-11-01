---
name: pynq-overlay-portability
description: 检查 PYNQ Overlay 的 bit/HWH、目标器件、IP 参数与驱动绑定，辅助更换题目、Overlay 或板卡。用于元数据不匹配、DefaultIP/DefaultHierarchy 未绑定、迁移地址或版本兼容性分析；提供不导入 PYNQ 的离线工具，不把文件检查当成上板通过。
---

# PYNQ Overlay 适配与驱动绑定

从目标能力和 IP 契约出发，避免依赖某个应用、板卡名称或固定寄存器地址。

## 输入与输出

收集 HWH、可选同名 bit、目标 profile，以及已知的 PYNQ/Python 版本。缺失信息先从现有文件获取；只询问仍影响结论的内容。

输出匹配的 IP/地址窗口、明确的不匹配项、未证明项和驱动绑定建议。元数据通过不等于电路可加载、接口可用或第二块板卡已验证。

## 执行流程

1. 先做离线检查。`scripts/inspect_overlay.py` 只读文件，拒绝不认识的 HWH/profile 格式，不导入 PYNQ、不构造设备。
2. 将器件、封装、IP VLNV、关键参数、地址位宽写入 profile；同 VLNV 有多个实例时指定完整层次名称。具体格式见 [profile.md](references/profile.md)。
3. 如需环境信息，运行 `scripts/collect_environment.py`；它只读取 Python 包元数据，不调用 Overlay。`Overlay(download=False)` 不能替代这一步的“无硬件访问”承诺：设备发现或驱动构造仍可能访问硬件。
4. 核对 bit/HWH 来源。相邻同名和 SHA256 匹配只证明文件身份，不能证明来自同一次正确构建；另核对构建记录、约束和目标器件。
5. 使用精确 VLNV 绑定 DefaultIP；使用明确的子 IP 能力绑定 DefaultHierarchy。先验证 description，再构造会映射寄存器的基类。不要用忽略 IP 版本来掩盖 ABI 不匹配。
6. 迁移或上板操作按用户已授权范围执行；核对现有资源所有者后再加载。未知时先报告具体缺项，不猜地址、不扫描有副作用的寄存器。详见 [binding.md](references/binding.md)。

## 可运行示例

在本技能目录执行，输出文件名必须未存在：

```sh
python scripts/inspect_overlay.py --hwh assets/example-zynq.hwh --profile assets/profile-zynq.json --output overlay-check.json
python scripts/inspect_overlay.py --hwh assets/example-ultrascale.hwh --profile assets/profile-ultrascale.json --output overlay64-check.json
python scripts/collect_environment.py --output environment.json
python -B -m unittest discover -s tests -v
```

检查器退出码 0 表示 `metadata_only`，2 表示输入/约束不通过。始终检查 `unknowns`；`board_compatibility_verified` 和 `pair_provenance_verified` 不会因文件匹配而变成 true。

## 可复用模板

- `assets/driver_factory.py`：注入 DefaultIP 类、精确 VLNV 和允许读取的寄存器表；不硬编码地址。
- `assets/hierarchy_factory.py`：注入 DefaultHierarchy 类和直接子 IP 的精确类型；拒绝不匹配层次。
- 两个模板导入时不需要 PYNQ。真实 PYNQ 类只能在已授权的集成阶段传入；动态生成驱动类可能触发驱动注册。

模板的读取表须来自 IP 文档，排除 read-clear 等副作用寄存器。它不是安全沙箱，不能阻止调用继承的写方法。

## 验证边界

样例为合成的流传输设计，覆盖 32/64 位地址及两种目标描述；测试使用模拟基类。换板复用的是流程、profile 与工具，bitstream 必须针对实际器件重新生成。真实驱动绑定、时钟/复位/中断、引脚电气和第二块板卡仍需单独验证。
