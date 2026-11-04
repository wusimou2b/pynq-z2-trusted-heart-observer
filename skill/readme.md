> Install with `python3 -B prepare_delivery.py skills --output ../trusted_heart_skills` from the repository root. The generated `skill/skills/` restores original `SKILL.md` and example names. Lowercase `skill.md` files here are storage/review copies; all 66 Skill files retain their exact original bytes.

# Eight PYNQ engineering Skills

All eight directories under `skills/` include their original `SKILL.md`, references, tools and MIT license. Four framework skills also include independent unit tests and synthetic examples. Source contents are preserved; Git checkouts may normalize line endings. This export did not run the tests.

| Skill | Review/use scope |
|---|---|
| [pynq-overlay-portability](skills/pynq-overlay-portability/skill.md) | HWH/profile compatibility and driver-binding metadata |
| [pynq-dma-lifecycle](skills/pynq-dma-lifecycle/skill.md) | Offline DMA ownership, cache and release event audit |
| [pynq-notebook-delivery](skills/pynq-notebook-delivery/skill.md) | Source identity, seal/verify and reviewed pure-software spawn |
| [pynq-ps-pl-profiler](skills/pynq-ps-pl-profiler/skill.md) | Explicit-clock phase timing, ABBA and numerical comparison |
| [pynq-result-audit](skills/pynq-result-audit/skill.md) | Read-only ZIP/CSV/JSON result and cleanup evidence |
| [pynq-board-session](skills/pynq-board-session/skill.md) | Package identity, single ownership and deployment evidence |
| [ps-pl-performance](skills/ps-pl-performance/skill.md) | Ordinary ABBA CSV and contiguous-block latency review |
| [fpga-kernel-verification](skills/fpga-kernel-verification/skill.md) | Numerical/RTL/interface/implementation/board evidence levels |

Read the chosen Skill before use; it defines inputs, limitations and examples. Skills are not automatically installed. Copy this directory to a fresh scratch location before running checks so the published snapshot remains unchanged. For each framework skill, run `python -B -m unittest discover -s tests -v` from its own directory when software test execution is authorized. The unchanged `legacy_cli_check.py` in this directory generates synthetic fixtures and checks the original three CLIs; it does not access hardware or network.

`historical_validation.json` records the same **31+37+37+29=134 unit cases** in original and isolated extraction checks; repeated runs are not additional unique cases. `historical_cli_validation.json` records **38 shared synthetic CLI assertions**, a separate category. The FPGA workflow skill has no independent RTL unit-test count. These historical results are not newly executed export tests and do not prove ARM, second-board or medical accuracy performance.

Local source manifests, original ZIP copies, absolute machine paths, generated test logs and private provenance have been excluded. Individual Skill source/docs/examples/tests remain complete. No board operation is authorized by reading or publishing a Skill.

## Project entry

The project example is `../board_runtime/runtime/ContinuousDemo25.ipynb`. First run the root `prepare_delivery.py runtime` command and use the generated `board_runtime/` directory, where original names are restored. See the root README and `../board/README.md` for versions, four-cell operation and normal stop. The eight Skill source directories remain unchanged. Historical Skill tests and the superseded `public_live` wrapper tests are separate from the saved 33.19-second board run and do not establish a new hardware acceptance.


## 八项技能的提炼、使用与验证边界

以下说明的是工程研发与证据核查技能，并非设备实时运行的组成部分。发布包中请先从工程根目录执行 `python3 -B prepare_delivery.py skills --output ../trusted_heart_skills`，再进入生成的 `trusted_heart_skills/skill/skills/<技能名>/`。各技能的 `SKILL.md`、`references/` 及相关工具是完整使用说明；命令的输出请使用尚不存在的新文件。涉及真实硬件的步骤须结合当次授权和实际设备状态执行。

| 技能与适用输入 | 提炼的观察、使用方法 | 已有验证与边界 |
|---|---|---|
| `fpga-kernel-verification`：待迁移算法、黄金向量、RTL/AXI、综合实现与上板资料 | 针对软件结果、仿真、实现和板测容易被混为一谈的问题，按数值与状态契约→真实 RTL/AXI→实现时序→同源 bit/HWH→分阶段板测组织证据；阅读 `references/verification.md` 并按实际核填写契约。 | 提供审查流程和检查要点；没有独立 RTL 单元测试数量可报告。仿真或 bit 文件存在不等于真实上板、实时性或医疗准确性通过。 |
| `ps-pl-performance`：同一输入的 A1/B1/B2/A2 计时 CSV，必要时附来源时间 | 针对平均值改善但尾部积压仍可能恶化、CPU 与等待时间容易混淆的问题，固定版本和负载后先核对数值，再用 `scripts/summarize_abba.py --input normalized.csv --sample-hz 25 --output NEW-abba.json` 评估普通 ABBA、成熟段与连续块。 | 历史 `historical_cli_validation.json` 包含该工具的合成 CSV、10% 均值差异和异常退出检查，属于三个 CLI 共 38 项合成断言的一部分；不是板端收益证明。缺少同钟起止时不能由调用时间之和推断完整吞吐；未经分段观测不能把剩余时间直接称为 IPC 或 GIL。 |
| `pynq-board-session`：完整候选包、manifest、bit/HWH 身份及会话/资源记录 | 针对结果目录重复使用、空闲内核仍保有硬件映射、停止请求与资源释放不同步等现象，先在隔离目录准备包，再以 `scripts/verify_bundle.py` 核对清单，并区分所有者退出、DMA/相机/租约释放及结果归档。 | 历史 CLI 合成断言覆盖清单身份、异常和不覆盖结果，计入上述 38 项；这不是实际板卡收尾证明。文件校验不会加载 PL，也不能单独证明 bit/HWH 来自同次构建或设备已释放。 |
| `pynq-dma-lifecycle`：含通道、缓冲区、借用和完成/停止事件的 JSON 轨迹 | 针对 DMA 等待超时后仍可能有在途访问、进程退出不等于缓冲区安全释放的问题，先确认模式与所有权，再用 `scripts/audit_dma_trace.py` 检查发送、接收或故障样例。 | 历史记录中有 **37 项本地单元测试**；示例用于检查声明的事件自洽性，不操作真实 DMA。工具 v1 面向整缓冲 simple DMA；SG、VDMA、cyclic 或部分区间需单独适配和验证。 |
| `pynq-notebook-delivery`：Notebook、依赖、源码清单、可信的纯软件预检 | 针对换目录缺文件、Notebook 输出改变导致身份校验失效、旧进程缓存掩盖冷启动问题，以 `scripts/notebook_delivery.py` 依次 `seal`、`verify`，仅对已审阅的纯软件入口进行真实 `spawn` 预检。 | 历史记录中有 **37 项本地单元测试**，还包含合成样例的 seal/verify/真实 spawn 检查。哈希证明文件身份，不证明可信发布者；纯软件冷启动不证明板级驱动、Overlay、DMA 和采集通过。 |
| `pynq-overlay-portability`：HWH、目标 profile、可选 bit 及环境元数据 | 针对目标器件、IP 参数、地址或驱动绑定不一致的问题，先用 `scripts/inspect_overlay.py` 离线比对 HWH/profile，再检查同源构建和精确 VLNV；工具与示例不导入 PYNQ。 | 历史记录中有 **31 项本地单元测试**，合成示例覆盖 32/64 位地址及目标描述；环境信息工具只读软件元数据。元数据匹配不能证明电路能在第二块板加载、引脚电气正确或驱动实际可用。 |
| `pynq-ps-pl-profiler`：声明时钟域、输入身份和阶段边界的计时记录，以及独立输出 | 针对阶段嵌套重复计时、任务间隙被忽略和未知等待被误归因的问题，先用 `scripts/analyze_phases.py` 分析普通计时或阶段轨迹，再用 `scripts/verify_outputs.py` 核对数值，必要时参考有界采集模板。 | 历史记录中有 **29 项本地单元测试**；合成和本地主机样例只验证分析逻辑，不代表板级吞吐。CPU、墙钟、PL cycles 不能跨时钟域直接相减，缺少边界的部分保留为未知。 |
| `pynq-result-audit`：停止写入后的结果 ZIP、JSON、CSV 和可选可信 SHA256 | 针对启动失败、波形断点、N/A、首故障与后续退出异常容易混淆的问题，用 `scripts/inspect_results.py --archive INPUT.zip --output NEW-inspection.json` 做只读清单，再按版本和序号分别核对采集、配对、处理、发布及资源状态。 | 历史合成 CLI 检查包含嵌套记录、无效行和边界错误，计入上述 38 项；工具不执行结果包、不加载 PL。显示提交帧不等于屏幕持续动态画面，进程退出也不等于 DMA 等资源已释放。 |

测试数量来自随包 `historical_validation.json` 和 `historical_cli_validation.json`：31、37、37、29 项合计 **134 项不同的本地单元测试**；隔离解压后的重复运行不是新增测试。三项 CLI 的 **38 项**为独立合成断言。以上是历史验证，不冒充本次新运行、第二块板卡验证或整机验收；各技能的新输入、新设备仍需按其契约重新检查。
