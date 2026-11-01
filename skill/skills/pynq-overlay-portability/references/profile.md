# Profile 与离线检查契约

工具需要 Python 3.10+，只用标准库。HWH 最大 32 MiB，JSON 最大 4 MiB；重复 JSON 字段、非有限数值和 XML DTD/entity 声明均拒绝。HWH 只接受 UTF-8（可带 BOM）的 `EDKSYSTEM`，不展开 XInclude。

本工具解析 `SYSTEMINFO`、`MODULES/MODULE` 的 FULLNAME/INSTANCE/VLNV 与直接 PARAMETERS，以及带 INSTANCE/BASEVALUE/HIGHVALUE 的寄存器 MEMRANGE。不是 PYNQ 完整 HWH 解析器：不能据此判断时钟、中断、复位、引脚、DDR 或驱动实现。特殊/新版格式须先扩展解析器和样例测试。

## Profile v1

```json
{
  "schema": "pynq-overlay-profile-v1",
  "target": {"DEVICE": "7z020", "PACKAGE": "clg400"},
  "required_ips": [{
    "role": "stream_transfer",
    "vlnv": "xilinx.com:ip:axi_dma:7.1",
    "instance": "stream/dma_a",
    "parameters": {"C_INCLUDE_SG": "0"},
    "address": {"address_bits": 32, "min_bytes": 4096}
  }]
}
```

根字段只接受 schema、target、required_ips、required_pynq_versions、artifact_sha256。

| 字段 | 契约 |
| --- | --- |
| target | DEVICE/PACKAGE 必填；可加 ARCH/SPEEDGRADE/BOARD；值为非空字符串，和 HWH 精确比较 |
| required_ips | 非空列表；role 唯一；精确四段 VLNV；instance 为去掉开头 `/` 的完整层次名 |
| parameters | 可选；字符串精确比较，不将 `0x20` 与 `32` 自动视为等价 |
| address | 可选；address_bits 为 1–64，min_bytes 为正整数；可加 master/slave 消除多地址窗口歧义 |
| required_pynq_versions | 可选字符串列表；明确接受的版本，不隐式比较版本大小 |
| artifact_sha256 | 可选 bit/hwh 的 64 位十六进制摘要；提供 pin 时必须有对应文件并匹配 |

没有给出的约束不会被自动证明。地址既不写死，也不因找到一个相似实例而猜测；多个匹配必须消除歧义。工具不保证 XML 中的连接拓扑实际可达。

## 环境与输出

`collect_environment.py --output environment.json` 读取包版本、Python/平台信息，不导入 PYNQ。检查器可加 `--environment environment.json`；缺少环境时版本检查列为 unknown，版本存在但不在明确接受列表时列为 error。

`--bit design.bit` 会计算摘要，并要求与 HWH 相邻且同名，这是普通文件形式 Overlay 的布局约定。工具不解析 bit 的配置内容。`both_artifact_pins_match=true` 仍不意味着构建来源可信。

报告 schema 为 `pynq-overlay-inspection-v1`。退出码 0 / status `metadata_only` 仅表示声明的文件约束无冲突；2 / `incompatible` 表示输入损坏或约束不满足。`unknowns` 必须随结论保留。既有报告不可覆盖。

`hardware_accessed`、`board_compatibility_verified`、`pair_provenance_verified`、`binding_executed` 固定为 false。不能拿退出码 0 自动串接电路下载。
