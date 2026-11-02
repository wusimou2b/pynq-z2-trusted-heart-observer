# 25/25 单次所有者 GC 窗口对照

目的：检验“最小GC观测中约410ms所有者第二代GC，与约440ms采集间隔及显示过期同段出现”这一线索。相关性不是因果证明，本包不是永久修复或完整V3a验收。

## 范围

只在独立所有者完成原PS预热后、进入source.begin前暂停自动循环GC；原工作线程全部退出后，在原_finish收尾前恢复原启用状态。所有者finally再做幂等恢复兜底。暂停范围包括停止后的排空，不保证恰好60秒墙钟；断电或系统强杀无法执行Python finally，不会伪造恢复记录。

不调用gc.collect/freeze、不调GC阈值，不改变引用计数；Notebook、PS子进程GC不改。有效原始25Hz、处理25Hz、FIFO两点平均、NLMS/选路/门槛、位流、IIC及队列大小不改。原100ms状态门、1秒结果门、2秒父心跳、故障锁定和收尾策略不变。页面原始50Hz旧脚注本次故意保留，不改显示分配行为；本次实际有效原始仍25Hz。

仅记录所有者窗口前、恢复前、收尾后RSS和VmHWM。后者是进程生存期峰值，不是窗口峰值；没有周期性内存监控，也不据此证明长期内存稳定。窗口前读不到Linux内存信息则拒绝开始，不自动重试。保留原有界队列及单次60秒配置，不可把本实验作为长期关闭GC的方案。

## 放置与校验（不用放手指，不加载Overlay）

将ZIP上传到上次运行最小GC观测的 `/home/xilinx/jupyter_notebooks/v3a25_all`。需有原 `effective25-manifest.json` 及 `gc-probe-manifest.json`。关闭其他采集，确认旧采集已收尾；新建Python 3 Notebook，不运行旧启动单元。

在新单元粘贴以下代码正文，不要粘贴Markdown围栏：

```python
from pathlib import Path
from zipfile import ZipFile
import subprocess, sys

root = Path.cwd().resolve()
assert (root / "effective25-manifest.json").is_file(), "请回到v3a25_all目录"
assert (root / "gc-probe-manifest.json").is_file(), "缺少上次最小GC观测包"
with ZipFile("session-20261010-effective25-gc-window.zip") as archive:
    names = archive.namelist()
    expected = {"run_effective25_gc_window.py", "effective25_gc_window.py",
                "effective25_gc_window_report.py", "README_GC_WINDOW.md",
                "gc-window-manifest.json"}
    assert len(names) == len(expected) and set(names) == expected, "压缩包内容不符"
    for name in names:
        target = (root / name).resolve()
        assert target.is_relative_to(root) and not target.exists(), "已解压或同名文件存在，禁止覆盖"
    archive.extractall(root)
subprocess.run([sys.executable, "run_effective25_gc_window.py", "--check-bundle"], check=True)
```

已解压则不要重跑解压，可单独重跑subprocess校验一行。看到bundle_validated为true且returncode=0才继续。校验默认不启动硬件，不执行GC窗口。

## 单次实采

放稳手指，不同时采集、绘图或复制大文件。新建下一单元，运行一次：

```python
from run_effective25_gc_window import run_gc_window60
report = run_gc_window60(hardware=True)
```

仅所有者加载原Overlay，DDR仍未验收。预热最长60秒另计，正式目标60秒，曲线约2次/秒。保持单元和页面打开；不要重启/关闭内核打断收尾。如果提前结束，保留结果，不重复运行碰运气。

## 结果

新唯一目录 `live_results/gc-window-effective25-*`，不覆盖旧记录。请回传11份文件：

- gc_window.json、gc_window.txt、owner_gc_window.json、owner_gc.json
- run_effective25_display.json、owner_result.json、display_metrics.json
- capture/raw.csv、capture/results.csv、capture/events.jsonl、capture/summary.json

“对照证据完整”只表示本次GC干预和观测完整，提前故障也可能是完整的反例。“60秒显示基础小试完成”仍不是正式验收。GC日志的strategy_unchanged只比较起止状态；本次窗口内故意改变策略，不可解释为全程未改。若GC已恢复但仍卡顿，继续据证据排查别的停顿；不能为求通过放宽显示门槛。

代码包只新增五个文件，依赖的基础178文件和最小GC五文件不改。PC检查使用模拟传感器/发布器/内存快照，不是ARM实测或硬件验收。
