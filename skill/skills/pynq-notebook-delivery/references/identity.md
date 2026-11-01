# 身份与包布局契约

JSON 使用 UTF-8，可带 BOM；拒绝重复键、非有限值和超过 16 MiB 的 JSON。相对路径必须为规范 POSIX 格式，拒绝绝对路径、盘符、`..`、反斜杠、symlink。工具不提取不可信 ZIP，也不是防恶意代码的沙箱。

## Spec / manifest

`delivery-spec.json` 示例：

```json
{
  "schema": "pynq-notebook-spec-v1",
  "files": {
    "delivery-spec.json": "bytes",
    "demo.ipynb": "notebook-source-v1",
    "demo_worker.py": "bytes"
  },
  "entry": {"module": "demo_worker", "callable": "ready", "kwargs": {"scale": 2}},
  "runtime_dirs": ["results"]
}
```

spec 本身必须按字节纳入清单。entry 目前支持根目录的单个顶层模块与函数名，kwargs 为 JSON 对象；包式入口需显式包装成这个顶层入口并列出全部本地依赖。

`seal` 计算文件身份，生成 `pynq-notebook-delivery-v1` manifest；files 的值变成 `{kind, sha256}`。manifest 本身不列入自身文件清单。生成摘要不代表已审查代码可信性。

源码目录除 manifest 外的文件必须完整匹配 files；不忽略旧 `.py`、`.pyc` 或旧 Notebook。runtime_dirs 只允许顶层、无点号、不以下划线开头的数据目录；其中 `.py/.pyc/.pyo/.so/.pyd/.dll/.ipynb/.bit/.hwh` 拒绝。其他运行数据不参与源码摘要。

本地 site-packages 的版本和依赖不自动封装；通过目标环境的真实冷启动检查，并在交付说明记录 Python/PYNQ/原生库版本。工具不会偷偷安装缺失依赖。

## notebook-source-v1 精确定义

要求 Notebook v4，显式 nbformat_minor、metadata.kernelspec.name/language、metadata.language_info.name。

参与 SHA256：

- 策略名、nbformat、nbformat_minor；
- kernel name/language、language name；
- 按原顺序的全部 code/markdown/raw cell；每个包含 cell_type、source、metadata.tags、attachments。

source 若为字符串列表，仅按原顺序连接；不改变换行、空白或源码内容。对象以 Unicode JSON、键排序和固定分隔符规范序列化；数组顺序保留。

不参与：输出、execution_count、cell id，以及上述未列出的 metadata（如 trusted、显示名、执行时间、widgets、Python 版本字符串）。因此普通保存输出不会使源码身份改变；代码、顺序、执行 tags、内嵌附件和 kernel identity 变化会被拒绝。

这是有明确边界的策略，不声称理解任意 Notebook 扩展。若执行依赖自定义 metadata、额外顶层字段或未纳入的参数，选择 `bytes`，或先定义/测试新版策略。不能静默删除实际影响执行的字段。

## 报告与失败

verify 不导入 payload。源文件不存在、0 字节 Notebook、JSON 损坏、缺依赖文件、额外源文件、身份不符均写失败报告。所有报告在 bundle 外创建，避免覆盖源码或改变后续清单。

`manifest_pin_matched` 与 `provenance_verified` 分开；本工具后者保持 false。bit/HWH 字节身份也不等于来自正确实现构建或适配当前板卡。
