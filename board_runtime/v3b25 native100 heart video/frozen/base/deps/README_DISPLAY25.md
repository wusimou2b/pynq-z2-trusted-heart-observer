# 25Hz采集＋Notebook并发显示验证

这是一次新的60秒静止显示小试。上一包无显示静止采集已核验，本包还没有板端并发显示结论。原始采样仍50Hz、处理25Hz；旧V2、NLMS参数、RTL、队列和保护期限不变。DDR仍未验收，所有正式完成标志仍false。

## 上传与解压

在板端Jupyter新建空目录，建议 `v3a25 display`。上传 `session-20261010-rate25-display.zip`，点击确认Upload。在这个目录新建Python3 Notebook，使用新的内核。不要打开static/中的旧Notebook，不要同时运行其他采集/绘图；旧目录无需删除。

第一个单元，只解压和验包，不需要放手指、不加载Overlay：

```python
from pathlib import Path
from zipfile import ZipFile
import sys, subprocess

assert not Path('display25-manifest.json').exists(), '已经解压，不要重复覆盖'
with ZipFile('session-20261010-rate25-display.zip') as archive:
    archive.extractall('.')
subprocess.run([sys.executable, 'run_v3a25_display.py', '--check-bundle'], check=True)
```

看到bundle_validated=true和returncode=0后继续。硬件未加载和正式门false是预期，不是失败。不必重跑budget或PL检查。工作Notebook可随意命名和保存，不属于完整性manifest；真正运行的Python文件均在manifest内。

## 一次并发显示静止采集

放稳手指，保持页面打开。新建第二个单元，只运行一次：

```python
from run_v3a25_display import run_display60
report = run_display60(hardware=True)
```

不要加 `!`，不要用subprocess启动这一步。新入口在Notebook内核里运行，才能刷新本页；终端硬件启动被拒绝。同一单元会完成预热（最长60秒另计）、60秒正式采集、实时曲线/心率显示和收尾，不需要立即点击另一个单元。刚开始需要积累信号历史，N/A正常。

界面约每秒2次刷新，绘制最多500个25Hz槽的四条波形。请检查序号在增加；心率只显示当前规则允许的结果。接触无效、过期、停止会撤回成N/A。曲线是历史数据，不等于允许输出心率。页面暂停或网络断开时，旧画面可能停留；本包没有浏览器看门狗，不得把停住的数字当当前心率。

需要停止时点Notebook的停止/中断按钮，等待收尾提示，不要强杀内核或运行另一个硬件程序。显示错误也会停止本次小试并保留错误；不要自动重试。若提示“清理未完成”，继续等待原会话，不开始下一次采集。

## 回传文件

结束后输出五个下载链接：`run_display25.json`，以及capture中的 `raw.csv`、`results.csv`、`events.jsonl`、`summary.json`。下载并一并回传，最好再发一张显示截图。预检失败可能只有控制报告，回传它和错误即可，不伪造另外四个文件。

`display_pilot_completed`仅表示本次采集＋内核发送的基础核对；还需回传复核，且不等于完整25Hz实时/参考心率准确率/运动效果/DDR通过。报告中的显示延迟仅计“原始读取完成→Notebook内核发送完成”，不含网络或浏览器实际绘制，也不包含FIR约200ms信号群延迟。刷新跨度与间隔、全部显示尝试和撤销、故障细节保存在summary.display及控制报告中；没有因画图失败而删除原始记录。

完成时心率回到N/A，图仍可作为历史查看。若发送通道损坏导致最后清屏失败，会记录final_clear_published=false，界面不能被认为已安全更新。
