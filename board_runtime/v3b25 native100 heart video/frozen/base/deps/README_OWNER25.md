# 25Hz 三进程显示小试（不是正式验收）

原始50Hz、处理25Hz、60秒static/baseline，四曲线500点，普通2Hz刷新；所有旧算法、NLMS、RTL、安全门与99.5%配对门不变。新进程独占硬件，原PS算法是其子进程，Notebook仅显示缓存SVG。共享状态最长100ms有效，父端2秒无进展请求停机；不自动重试/恢复、不强杀硬件进程。DDR、准确率、正式live25/live50及V3a完成仍未验收。

## 放在哪里

上传ZIP到板端原 `v3a25 display` 根目录（能看到 `display25-manifest.json`、`cached-live25-manifest.json`、`run_v3a25_cached_live.py`、`v3a25_cached_display.py` 的一层）。不覆盖旧包，不删除数据。关闭旧采集，创建新的Python3 Notebook，别运行旧“第1单元”中的 `import pynq`。

## 解压与只读校验

```python
from pathlib import Path
from zipfile import ZipFile
import subprocess, sys

assert Path('display25-manifest.json').is_file(), '请进入原显示根目录'
assert not Path('owner-display25-manifest.json').exists(), '已解压，不要重复覆盖'
with ZipFile('session-20261010-owner-display25.zip') as archive:
    for name in archive.namelist():
        target = (Path.cwd()/name).resolve()
        assert target.is_relative_to(Path.cwd().resolve()), name
        assert not target.exists(), '目标已存在，不覆盖：'+name
    archive.extractall('.')
subprocess.run([sys.executable,'run_v3a25_owner_display.py','--check-bundle'],check=True)
```

只读校验不会让传感器亮。不用手指；通过也不是实采通过。上传的Notebook不绑定manifest。

## 一次实采

放稳手指，保持本页打开，只运行下一单元，不另开采集、绘图、上传/复制。不要 `!python` 或 `subprocess` 启动显示。

```python
from run_v3a25_owner_display import run_owner_display60
report = run_owner_display60(hardware=True)
```

预热另计（原PS最长60秒），打印正式开始后60秒。用户中断或显示失败会请求停止并等待清理；若持续提示清理未完成，不启动第二次，不反复中断，不拔传感器，保存消息回传。

返回五份：`run_owner_display25.json`、`capture/raw.csv`、`capture/results.csv`、`capture/events.jsonl`、`capture/summary.json`。另有 `display_metrics.json` 和 `owner_result.json`，内容已并入控制报告，保留原目录。

显示计时是内核发送完成，不是浏览器绘制回执。暂停/断连后旧网页画面不能当当前心率；无法承诺浏览器冻结期间主动清屏。PC回放不证明ARM实采配对率、时间预算或传感器测量准确率；板端结果回来前不要进入运动试验或宣告V3a完成。
