# 计时数据契约

`scripts/analyze_phases.py` 读取 UTF-8 JSON，拒绝重复键、非有限数（含 `1e400` 溢出）、负时间、重复/倒退序号与同域串行区间重叠。完整样例见 [阶段样例](../assets/synthetic_phase_profile.json) 与 [普通 ABBA 样例](../assets/synthetic_normal_timing.json)。脚本可以从任意工作目录通过绝对路径调用，也支持 `python -I -B`，不依赖其他技能目录。输出使用独占创建，路径已存在即失败；多文件 CLI 先检查全部目标，之后仍逐个独占创建，不覆盖输入或其他报告。

## 文件与运行

| 字段 | 含义 |
|---|---|
| `schema` | 固定 `pynq_ps_pl_trace_v1` |
| `measurement_kind` | `phase_profile` 或 `normal_timing` |
| `provenance` | `synthetic`、`host_execution` 或 `board_execution`；标签是来源声明，工具不能认证硬件 |
| `task_hz` | 正有限任务频率，供名义周期/吞吐预算计算，不自动代表输入采样率或 deadline |
| `block_sizes` | 不重复的正整数列表；按连续任务数计算滑动窗口 |
| `clocks` | 计时域 ID 到计时定义的映射 |
| `runs` | 按实际执行顺序保存的非空运行列表；ABBA 必须恰为 A1、B1、B2、A2 |

每个 run 必须包含 `name`、`implementation`、非空 `workload`、非空 `config`、`instrumentation`、非空 `records`。`implementation` 是稳定版本标识，同一 arm 两次须相同。`workload` 至少包含 `name`、`version`、`input_set_sha256`，最后一项为完整输入集规范序列化后的 SHA-256 小写十六进制串。

`config` 保存比较所需的实际配置，例如数值类型、形状/布局、批大小、任务模型、worker 数、进程与线程划分、CPU/PL 频率和来源、队列策略、传输大小、返回接口。板级输入还应记录硬件身份；有意变更的实现身份放入 `implementation`，其余配置差异不能隐藏。分析器对 `config`、`workload` 做整对象相等检查，但无法判断人工遗漏了什么。

`instrumentation` 在普通计时中固定为 `boundary_only`，在诊断计时中固定为 `phase_spans`。普通计时不接受非空 `spans` 或 `pl_samples`。可选 `collector` 保存 `capacity`、`recorded_tasks`、`rejected_tasks`、`rejected_spans`；发生容量拒绝的运行不参与 ABBA 改善计算。

## 时钟

每个 clock 有非空 `source`（实际计时函数/寄存器与读出位置）、`scope`（主机、进程/线程、IP、启动会话等），以及下列定义。

| `kind` | `unit` | 适用内容 |
|---|---|---|
| `monotonic_wall` | `ns` | 单调 wall 时间戳 |
| `process_cpu` | `ns` | 当前进程 CPU 时间；可能包含多个线程，不包含子进程 |
| `thread_cpu` | `ns` | 指定线程 CPU 时间；不能冒充进程 CPU |
| `pl_cycles` | `cycles` | 已处理回绕的 PL 周期计数 |

PL 时钟可同时携带正有限 `frequency_hz` 和非空 `frequency_source`；二者必须成对。缺失二者时保留原始周期，`duration_ns=null`，状态为 `unknown_frequency`。频率来源要说明配置值、寄存器读回、工具报告或实测；配置值不冒充运行实测值。一次区间中频率改变或计数器复位，需按明确边界拆开，不能套单一换算。

时钟 ID 表示同一实际域，不能因单位都叫 ns 就复用 ID。跨进程、跨设备、重启后的时间戳要按实际平台计时保证声明；本分析器不自动校准偏移、频漂或网络时钟。只有时钟 ID 完全相同的区间参与同域包含关系、任务间隙与 wall 归因。

## 记录

每条 record 必须包含：

| 字段 | 规则 |
|---|---|
| `sequence` | 非负整数；同 generation 内严格递增，不要求无缺口 |
| `generation` | 非空字符串；变化表示新的序列段，旧 generation 不能再次出现 |
| `record_id` | 非空输入记录 ID；同 generation 内唯一 |
| `input_sha256` | 该条实际输入的 SHA-256 小写十六进制串；不是输出哈希 |
| `valid` | `true`、`false` 或 `null`；缺字段报错，未知用 null |
| `wall` | `{ "clock": "wall", "start": 100, "end": 200 }`；时钟须为 monotonic_wall |
| `cpu` | 可选，同格式；时钟须为 process_cpu 或 thread_cpu |
| `spans` | 可选阶段区间列表，只允许在 phase_profile 中非空 |
| `pl_samples` | 可选已求同域差值的 PL 周期计数列表 |

时间戳必须为非负整数，`end>=start`。CPU 可以大于 wall，分析器不会由两者差值推断等待、调度、GIL、IPC 或子进程占用。`error` 等额外字段随原记录保留。

span 包含 `id`、`phase`、`clock`、`start`、`end`，可选 `parent` 指向本记录中的另一个 span ID。phase 名称来自测量协议，不能用名称替代证据。父子必须同域且子区间被父区间包含，不能循环。与任务 wall 同域的 span 必须在任务内；其他域的 span 只报告独立持续时间。

`pl_samples` 的每个元素为 `{ "phase": "pl_kernel", "clock": "pl", "cycles": 25 }`。cycles 是非负整数；计数开始/结束事件、回绕展开方法和频率来源写入 clock 定义或测量说明。PL 周期时间只独立报告，不从 host wall 中扣除。

采集器异常结束时把未闭合 span 原样保存在 `incomplete_spans`，其 `end` 为 null，任务 `valid=false`。这些 span 不参与区间计算，也不捏造结束时间；原始证据仍随记录输出。

## 输出与归因

输出为 `pynq_ps_pl_summary_v1`，保留时钟定义、运行身份、workload/config、每条原 record 与派生指标。CLI 同时记录输入文件 SHA-256。任务指标中的 `wall_attribution` 包含：

- `inclusive_spans`：每个 span 原始持续时间；不可直接求和。
- `exclusive_phase_ns`：仅同任务 wall 时钟的互斥阶段时间。边界划分后，活动 span 若形成单一父子链，则归给最深叶节点；若存在多个非祖先叶节点，则记作重叠未知。
- `ambiguous_overlap_ns`：非祖先 span 重叠的时间，只计一次。
- `unknown_unobserved_ns`：没有同域 span 覆盖的时间。

上述互斥阶段、重叠未知与未观测时间之和恰等于任务 wall 时间。父阶段的 exclusive 剩余只是该阶段未被子区间进一步细分的部分，不是自动测得的“框架开销”。阶段名称相同的独立 span 可汇总，但归因前不合并 inclusive 值。

每个连续块输出起止序号、record ID、无效/未知数、`elapsed_ns_including_gaps`、`summed_task_wall_ns` 和 `inter_task_gaps_ns`。前者为同域最后结束减最先开始，后者的差值只表示观测任务之间的间隙。不同域的块 elapsed/gaps 为 null，不用调用时间之和代替。序号缺口与 generation 变化打断窗口，首条和无效条仍参与统计。p50/p95/p99 用 nearest-rank，不从小样本外推罕见概率。

`complete_elapsed_ns` 表示全部已记录任务的时间域可以连起来时的观测跨度；它不认证任务序列无漏采，也不认证输入流完整。跨域间隙未知时为 null。名义预算等于 `size/task_hz`，不是 deadline 证明。`abba.eligible` 仅表示保存记录的普通 ABBA 具有可比元数据；无效记录仍参与时间统计并显式计数，不因此获得业务接受结论。

## 独立数值文件

`scripts/verify_outputs.py` 接受两个 `pynq_numeric_outputs_v1` 文件，各含 `workload`、`config` 和 `records`。每条记录复用 generation/sequence/record_id/input_sha256/valid，并包含一维、非空、有限实数 `values` 列表。无效或未知记录可以用 `values=null`；它们保留在报告中，整体状态为 incomplete，不能伪装全量通过。

比较要求完整 workload/config 对象和按序记录身份、输入哈希、有效性一致。数值判据为 `abs(reference-candidate) <= atol + rtol*abs(reference)`；容差必须显式传入。NaN/Inf、重复身份、错误形状或数值不匹配不能通过。每条均保留，输出 pass/fail/incomplete/incomparable；CLI 退出码依次为 0/1/2/2，格式或 I/O 错误为 2。此工具不比较时间，也不认证 FPGA 位精确等价或硬件运行。
