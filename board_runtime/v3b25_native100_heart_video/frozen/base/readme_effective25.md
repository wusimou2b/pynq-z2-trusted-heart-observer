# 有效采集25Hz＋处理25Hz候选

这是新前端基线，不覆盖原50→25包。传感器内部ADC仍50sps、FIFO每两点平均后25sps；MPU输出25Hz；每条FIFO原始记录对应一条处理结果。不是把旧读取循环改慢。FPGA bit/hwh、固定NLMS参数、25Hz精细峰时刻主链保留。

接触幅度窗50点（2秒）、恢复25点（1秒）；幅度阈值/99.5%配对门/无效N/A/故障停止/原始先刷新后处理不放宽。不同步的PPG/IMU只作工程配对，多点FIFO批次旧点保留且标未配对。读时刻不是ADC真实中心；两点硬件平均不等同旧21tap抗混叠滤波，不继承旧≥40dB阻带证明。运动效果与准确率需要新验证，不能保证改成25后不再N/A。

## 先做板端只读检查

在板端新建**空目录**，上传`session-20261010-effective25.zip`；不要解压到旧目录。进入该目录新建Python3 Notebook，先运行：

```python
from pathlib import Path
from zipfile import ZipFile
import subprocess, sys

root = Path.cwd().resolve()
assert not (root / 'effective25-manifest.json').exists(), '已解压，不要覆盖'
with ZipFile('session-20261010-effective25.zip') as archive:
    for name in archive.namelist():
        target = (root / name).resolve()
        assert target.is_relative_to(root), '包内路径越界'
        assert not target.exists(), '目标已存在，不覆盖：' + name
    archive.extractall(root)
subprocess.run([sys.executable, 'run_effective25.py', '--check-bundle'], check=True)
```

然后新建单元：

```python
subprocess.run([sys.executable, 'run_effective25.py', '--software-check'], check=True)
```

无需手指，传感器不亮正常；不加载Overlay，不要运行旧Notebook的硬件单元。检查包含72/120/180BPM理想合成输入及完整PS直接/独立进程对照，可能需要几分钟。输出的`checks/software-.../effective25_check.json`回传即可。不自动重跑。

## 本轮边界

检查通过仅说明实现/通信检查通过；PC耗时不代表ARM，ARM无硬件耗时也不代表IIC/真实PL/落盘/显示并发性能。内部平均的量化、延迟、实际FIFO速率都需要板端读回与实采。各正式live25/live50/auto-beta/DDR/限值冻结/准确率/V3a完成标志保持false。

新硬件适配器、1:1会话和三进程显示入口`run_effective25.run_display60`已包含，但请先回传软件检查结果，再进行显式单次60秒实采；不要直接调用内部`effective25.board.prepare`绕过包身份检查或沿用旧50Hz入口。旧包仅放在deps作为冻结依赖，其历史通过记录不是新前端的验证证据。

硬件准备复用原Overlay/锁/身份检查，其中会短暂配置旧50Hz用于原预检，随后重新配置有效25Hz并严格读回；这时尚未启动正式采集。正式采集前预热和FIFO丢弃另计，正式记录只在新25Hz配置后开始。传感器是否真的达到25Hz须以板端报告确认。

配置依据：[MAX30102官方数据手册](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX30102.pdf)及[硬件平均后的有效速率说明](https://ez.analog.com/optical_sensing/a/documents/DO19535/if-i-enable-sample-averaging-in-max30101-max30102-and-keep-the-sampling-rate-setting-to-be-the-same-does-the-effective-sampling-rate-go-down)。
