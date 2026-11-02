# 25/25 最小所有者 GC 观测

这是观测包，不是修复。两次不带诊断运行都在约14秒出现约400ms停顿，带全诊断曾跑满60秒。当前只验证“所有者GC区间是否与停顿重合”，不自动判定根因。

## 不变的内容

- 有效原始25Hz、处理25Hz、原Overlay/bit/hwh、算法和NLMS参数均不变。
- 100ms状态保护、1秒结果保护、2秒父心跳、原队列容量及故障停止策略不变。
- 不关闭/强制GC，不修改阈值；不替换PS子进程目标，不加IPC消息。
- 不包装采样、算法、存盘、状态发布；只在所有者spawn目标上安装GC回调。
- Notebook/PS子进程不加GC观测。只有所有者事件写入4096条固定缓冲（192KiB），原owner完成清理后导出。
- 观测不是零开销；跑满不能证明无诊断版修复，GC重合不能单独证明因果。DDR/准确率/完整V3a均未验收。

## 解压与验包：不放手指、不加载硬件

停止其他采集，关闭旧采集Notebook内核。在刚刚运行有效25/25的目录（包含`effective25-manifest.json`和`run_effective25.py`）上传本ZIP，新建Python Notebook。不是旧50/25目录，也不是`live_results`子目录。

只复制代码框内部，不包含三个反引号。第一格：

```python
from pathlib import Path
from zipfile import ZipFile
import sys, subprocess

root = Path.cwd().resolve()
assert (root / 'effective25-manifest.json').is_file(), '请进入有效25/25包根目录'
with ZipFile('session-20261010-effective25-gc-probe.zip') as archive:
    for name in archive.namelist():
        target = (root / name).resolve()
        assert target.is_relative_to(root) and not target.exists(), '路径不符或已经解压，不要覆盖：' + name
    archive.extractall(root)

subprocess.run([sys.executable, 'run_effective25_gc_probe.py', '--check-bundle'], check=True)
```

显示`bundle_validated: true`、退出码0后才能执行下一格。已经解压则只运行`subprocess.run(...)`验包，不要删除/覆盖旧文件。

## 单次实采：此格要放稳手指

不运行旧Notebook第1格，不导入pynq，不运行旧诊断入口。独立所有者显式加载原Overlay，DDR仍未验收。预热另计，正式最多60秒，可能按原保护提前停止。页面保持打开，不同时运行其他采集、绘图或上传。

```python
from run_effective25_gc_probe import run_gc_probe60
report = run_gc_probe60(hardware=True)
```

不自动重试。若输出仍在等待清理，不重启内核或另开采集，保留错误并回传。

## 回传文件

在本次`live_results/gc-effective25-...`目录：

- `gc_probe.json`、`gc_probe.txt`、`owner_gc.json`
- 原有`run_effective25_display.json`、`owner_result.json`、`display_metrics.json`
- `capture`子目录的`raw.csv`、`results.csv`、`events.jsonl`、`summary.json`

只上传这一轮的文件。无论早停还是跑满都需要。`diagnostic_complete`仅表示所有者GC记录与相关原数据完整，不是实时性或准确率通过。没有额外显示判定探针，不能据此给出精确保护触发时刻。
