---
name: pynq-notebook-delivery
description: 整理 PYNQ Notebook 的独立交付包，区分源码身份与运行输出，检查依赖完整性和真实 spawn 冷启动。用于换目录后缺文件、保存输出导致校验失败、旧内核缓存掩盖导入或 worker 参数错误；默认只校验文件，可信纯软件预检需显式执行，实际硬件启动另行管理。
---

# PYNQ Notebook 交付与冷启动

让 Notebook 在新的目录和进程中找到同一套代码，并将源码校验失败、导入失败、参数失败和退出失败分别报告。

## 处理顺序

1. 从任务现有成功版确定输入文件，列出 Python 模块、Notebook、bit/HWH、数据和本机依赖。不要把旧 results、attempt 或内核缓存当作交付来源。
2. 为文件选择身份策略：普通文件按字节；标准 Notebook 可按 `notebook-source-v1`；使用特殊执行元数据/扩展时按字节或增加明确的新策略。完整规则见 [identity.md](references/identity.md)。
3. 建立显式文件清单，划分源码与数据输出目录。运行目录中的 Python、Notebook、bit/HWH 等可执行或硬件资产仍须纳入源码清单，不能藏在忽略目录。
4. 先 `seal` 创建 manifest，再 `verify` 检查。SHA256 pin 证明本次文件身份，不单独证明可信发布者。校验、上传、解包本身不启动采集。
5. 需要冷启动时，先审阅纯软件预检函数，然后用 `spawn` 子命令启动真正的新进程。子进程再次验证 manifest，随后才导入入口、绑定参数、调用函数。签名、partial 和进程关闭后的结果导出都要检查。
6. 最后交付源包摘要、实际命令、通过与待测阶段。板端真实驱动、PL/DMA 和采集的启动/收尾属于当前工程已有边界，不由这个工具替换。

## 可运行工具

`scripts/notebook_delivery.py` 只依赖 Python 3.10+ 标准库。先将 `assets/example` 复制到新的目录，避免改动安装包。

```sh
python scripts/notebook_delivery.py seal --root NEW_BUNDLE --output seal-report.json
python scripts/notebook_delivery.py verify --root NEW_BUNDLE --output verify-report.json
```

阅读 seal-report.json 的 `manifest_sha256`，在确认入口是可信纯软件函数后执行：

```sh
python scripts/notebook_delivery.py spawn --root NEW_BUNDLE --expected-manifest-sha256 ACTUAL_SHA256 --execute-trusted-pure-preflight --output spawn-report.json
python -B -m unittest discover -s tests -v
```

每个报告必须使用未存在的路径，并放在 bundle 外。命令成功退出 0，失败保存报告并退出 2。已存在的 manifest/报告不覆盖。

## 冷启动边界

`spawn` 会执行入口代码，仅用于已经审阅的 `PURE_PREFLIGHT=True` 纯软件函数。常见硬件模块导入被阻止，但这不是安全沙箱：ctypes、直接文件/设备访问或任意模块的副作用无法由标志证明不存在。不对不可信代码运行此命令。

工具只终止自己创建、超过本次时限的纯软件测试子进程，不能套用到持有 PL/MMIO/CMA 的进程。既有硬件保护、GC、启动顺序和资源所有者均由工程继续负责。详见 [cold-start.md](references/cold-start.md)。

沿用用户已有授权，不为普通离线检查增加审批；若尚未授权执行实际入口，先交付具体可审查的包。不要把一次项目的 token、超时或“失败不重试”政策固定成所有 PYNQ 工程的规则。

## 输出含义

文件检查通过不代表依赖都能导入；纯软件预检通过不代表 Notebook 所有分支或板端功能通过。输出保留 child 阶段错误、原异常、退出码、是否自然退出及是否强制终止。测试使用数组求和样例，不依赖特定板卡、IP 地址或传感器。
