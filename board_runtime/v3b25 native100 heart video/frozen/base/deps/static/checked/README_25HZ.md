# 独立25Hz检查包

本包不是实采包。先在新空目录解压，不覆盖旧50Hz目录。不要进入base子目录运行旧Notebook或旧采集命令。

默认 `python run_v3a25.py --check-bundle` 只核对文件身份，不访问硬件。

## 当前只做这一步：只读预算

1. 在PYNQ Jupyter中新建空文件夹（建议`v3a25 checks`），上传本ZIP，在该文件夹新建Python工作Notebook。
2. 在新单元用Python解压（中文文件名由zipfile正确处理），不要手动重命名base里的文件：

```python
from pathlib import Path
from zipfile import ZipFile
assert not Path('manifest25.json').exists(), '本目录已经解压，请不要覆盖'
with ZipFile('session-20261010-rate25-checks.zip') as archive:
    archive.extractall('.')
```

3. 再运行下面单元。不放手指、不导入pynq、不加载Overlay、不同时采集/绘图。独立进程预热另计，板上可能需要数分钟；期间不要重复启动。

```python
import sys, subprocess, uuid
from pathlib import Path
from IPython.display import display, FileLink
out = Path('checks') / ('budget-' + uuid.uuid4().hex[:8])
result = subprocess.run([sys.executable, 'run_v3a25.py', '--budget', '--output', str(out)])
print('退出码：', result.returncode)
report = out / 'budget25.json'
if report.is_file():
    display(FileLink(str(report)))
```

下载回传`budget25.json`。即使退出码非0，也先回传报告/错误，不自行重试或启动实采。本工具生成新报告文件，但对硬件和输入是只读的；传感器不亮是预期行为。

## 测量是什么

两组固定输入：1403点原实录→701槽+1尾点，2000点合成轻运动→1000槽。先在板上生成纯软件参考，严格核对固定整数NLMS输入/回复与本包一致，然后直接PS和独立进程PS各跑一遍、逐字段核对。合成输入只补充不同计算路径，不证明真人运动效果。

报告保留每个原始点的安全快路/FIR耗时、每槽PS调用耗时，以及两原始点+一槽PS的顺序相加值；成熟段从槽200开始。PS调用包含记录回复的服务开销/进程通信，软件参考生成、700槽纯软件进程预热和输出比对另计。没有真实IIC、PL事务、持续落盘或显示竞争；单看均值低于40ms不能标为实时通过。

为发现跨平台数值差异，板上参考必须精确匹配本包固定整数向量；如不一致，明确失败，不能放宽误差或偷偷重建黄金结果。BPM精度、真实运动NLMS效果和DDR仍未验收。

## 后续才运行：PL固定向量回放

等只读报告核对后再运行，不需要放手指。停止其他所有硬件Notebook/CLI；此操作会重新加载原Overlay，继承DDR告警仍未验收。

```python
import sys, subprocess
subprocess.run([sys.executable, 'run_v3a25.py', '--pl-replay', '--hardware'])
```

回传打印目录中的`pl25.json`和`actual25.csv`。只访问原NLMS IP，完整核对两组1701包的整数结果、epoch、状态、20ms完整读回期限和累计计数，不配置或采集传感器，不当成25Hz实时验收。遇错保存已收结果并停机，不自动重投或reset恢复。

## 保留的限制

原bit/HWH、V2、50Hz、三个25Hz阶段源文件保持原字节。base是冻结依赖和原交付证据，请勿打开或运行其中的旧Notebook；新工作Notebook在包根目录，不参与完整性哈希。新报告放checks的新子目录，绝不覆盖旧报告。

所有正式门初始false。通过本包的只读预算或PL回放也不会设置live_25hz_passed、live_50hz_passed、auto_beta_effect_passed、board_ddr_verified或v3a_complete。当前仍为V3-A第6项；摄像头、HDMI和动态参数档位不在本步范围。
