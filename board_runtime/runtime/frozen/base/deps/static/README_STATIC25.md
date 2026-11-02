# 60秒静止实采：50Hz原始＋25Hz处理

仅一次无绘图静止小试，不是正式验收。固定原NLMS参数、原Overlay，DDR遗留告警仍未验收。关闭其他采集/硬件Notebook。不要运行checked中的旧命令，不覆盖任何旧目录。

## 解压与验包

在PYNQ Jupyter新建空目录（建议v3a25 static），上传session-20261010-rate25-static.zip，在同目录新建Python Notebook。运行：

```python
from pathlib import Path
from zipfile import ZipFile
assert not Path('pilot25-manifest.json').exists(), '已解压，不要覆盖'
with ZipFile('session-20261010-rate25-static.zip') as archive:
    archive.extractall('.')
import sys, subprocess
subprocess.run([sys.executable, 'run_v3a25_static.py', '--check-bundle'], check=True)
```

这一步只读、不加载Overlay、不采集。工作Notebook不参与哈希校验，可正常保存。

## 单次实采

验包无错误后放稳手指，保持传感器和手部静止。只运行以下一个单元，不画图、不运行其他采集。预热最多60秒另计，提示进入采集后正式60秒。

```python
import sys, subprocess, uuid
from pathlib import Path
from IPython.display import display, FileLink
out = Path('live_results') / ('static25-' + uuid.uuid4().hex[:8])
result = subprocess.run([sys.executable, 'run_v3a25_static.py',
                         '--static60', '--hardware', '--output', str(out)])
print('退出码：', result.returncode)
for name in ('run25.json', 'capture/raw.csv', 'capture/results.csv',
             'capture/events.jsonl', 'capture/summary.json'):
    path = out / name
    if path.is_file(): display(FileLink(str(path)))
```

回传以上五个文件。run25.json保留启动/结束错误，capture内是本次原四文件。预检失败可能仅有run25.json，这是没有进入正式采集，不补造空结果。如果有错误或未生成全部文件，把已有文件和输出交回，先不要重试。不要用重启/重新下载Overlay自动恢复错误。

如果提示清理尚未完成，不启动其他硬件程序，先保留输出；程序仅等待原线程收尾，不会重采。正常收尾释放锁。Ctrl+C/中断也请求收尾；强行终止内核或掉电可能无法保存最终报告。

## 报告边界

原始PPG/IMU仍50Hz，两个原始点产生一个25Hz处理槽，正常尾部可剩1点。原始安全快路、flush屏障、父进程唯一硬件、250原始单位队列和20ms完整PL期限不变。run25与summary中的static_pilot_completed只表示本次无绘图基础核对闭合；性能限值未冻结，端到端延迟和配对率仍须看完整记录。显示、真实运动效果、BPM参考误差和DDR未验收，所有正式总门仍false。
