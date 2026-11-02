# 6次进入确认：独立25/25静止候选

这是实采试验包，不是上一只读包，也不是正式替换版。唯一算法变化为进入NLMS连续确认2次改6次；候选源与已通过ARM板端只读回放的源逐字节相同。保持25/25、原位流、beta、选路规则、退出、接触、质量、两个新心搏间隔及所有者GC窗口。该策略可能减少N/A和短暂切换，但同时减少NLMS使用机会，不代表准确率提升。

## 放置与检查

可把ZIP上传到现有v3a25_all目录。关闭其他采集，确认其已收尾，**新建Python 3 Notebook（新内核）**，不要运行旧的身份、采集或绘图单元。包有独立`entry25_live/`顶层，带完整冻结依赖；不需覆盖旧目录，不依赖上个只读目录。

下载ZIP后校验交付消息中的SHA256。解压前确认`entry25_live`不存在；检查成员全以`entry25_live/`开头、没有绝对路径或`..`，再解压。已有该目录则不要再次覆盖解压。

只读检查（不用放手指，传感器不亮是正常的）：

```python
from pathlib import Path
import subprocess, sys

root = Path("entry25_live").resolve()
subprocess.run([sys.executable, "-B", str(root / "run_entry25_live.py"),
                "--check-bundle"], check=True)
```

必须看到`bundle_validated: true`且returncode=0。此时硬件及小试完成标志仍False，不能当作实采已通过。

## 只运行一次60秒静止采集

放稳手指、保持传感器和IMU固定。不同时采集、绘图、上传或复制大文件；保持本单元和页面打开，直到清理结束。预热最长60秒另计，正式目标60秒。只有新所有者进程加载原Overlay；Notebook和PS子进程不加载硬件，DDR仍未验收。

```python
from pathlib import Path
import sys

root = Path("entry25_live").resolve()
sys.path.insert(0, str(root))
from run_entry25_live import run_static60
report = run_static60(hardware=True)
```

必须直接在新Notebook中调用，不能用`!python`或`subprocess.run`启动实采（后两者没有Notebook显示上下文）。首次只静止，不移手指、不做运动测试，不连续重复；提前停止也保留证据，不自动重试。

显示模板故意不改分配行为，其旧脚注可能仍写原始50Hz。本次ADC50Hz、硬件两点平均后FIFO/有效原始25Hz、处理25Hz，约2Hz显示。GC报告中的“算法不变”描述原组件；本次候选变化以`run_entry25_live.json`和PS的`entry_confirmation_checks: 6`为准。

## 结果和下一道门

结果在`entry25_live/live_results/entry6-static-...`，独立保存，绝不覆盖旧结果。原报告原样保留，另加候选身份/判定。结束后点击`entry25_results.zip`下载并回传这一份；它包含候选报告、所有者身份、GC报告、显示报告及raw/results/events/summary，不含程序或位流。

`candidate_static_pilot_completed`只表示这一次候选静止基础小试。运动效果、心率准确率、正式实时门、DDR和完整V3a均未验收。返回静止结果核对后，才决定下一次静止20秒→运动20秒→静止20秒；这里不会自动启动它。

GC只在原所有者完成预热后暂缓自动循环收集，工作线程退出后恢复。没有强制回收或阈值修改，PS与NotebookGC未变。原100ms状态门、1秒结果门、2秒父心跳、队列和停止策略均保留。故障、用户中断和异常不应标成成功；无法证明清理时禁止立即重采。

电脑检查使用记录回放或模拟物理边界，不能代替板上本次运行。不能依据只读回放总耗时判断实时预算。
