# V3-A 进程隔离小试（不是正式验收）

本包新增独立入口，把完整PS计算放入spawn子进程；原主进程仍唯一控制传感器和PL。算法、固定β/抽头、配对政策、FIFO/驱动期限、队列和99.5%门不变。原 Notebook ②/③及 run_v3a_live.py 仍走旧线程入口，本次不要运行它们。

## 新目录操作

1. 停止旧采集和绘图，关闭旧work内核。将新ZIP上传到板端一个新的空目录，不覆盖旧目录或记录。
2. 在Jupyter新建Python3 Notebook，用下列单元解压当前目录中的ZIP；只在新空目录运行一次。

```python
from pathlib import Path
import zipfile
archives = list(Path.cwd().glob('session-20261009-live-isolated.zip'))
assert len(archives) == 1, '当前目录应只有本次ZIP'
assert not Path('heart_v3a').exists(), '请换新空目录，不要覆盖旧包'
with zipfile.ZipFile(archives[0]) as z:
    z.extractall(Path.cwd())
print('解压完成：', Path.cwd())
```

3. 关闭解压Notebook，打开解压出的 heart_v3a_live_work.ipynb。不要打开/修改模板 heart_v3a_live_notebook.ipynb，不要Run All。新建单元只运行：

```python
import sys
!{sys.executable} run_v3a_isolated_live.py --check-bundle
```

只有 bundle_validated=true 才继续。默认检查不加载硬件/不预热子进程，传感器不亮正常。

4. 接线保持原样，放稳手指，关闭其他采集/绘图。在work另一个新单元运行：

```python
!{sys.executable} run_v3a_isolated_live.py --hardware
```

先加载原Overlay，进行纯软件预热（最长60秒），再正式采集60秒；总等待比60秒长。一次结束后不要马上重复。异常时保留完整输出，不自行重跑/改驱动或阈值。

5. 在输出的 live_results/isolated-日期-编号 目录下载 raw.csv、results.csv、events.jsonl、summary.json，四份一起回传。若summary未生成，回传其他文件和单元输出。

## 结果口径

summary增加isolation：父/子PID、完整处理拍数、PL请求数、退出码、是否强制终止。cleanup_complete只有子进程实际退出且原会话收尾完成才成立。结果原PS墙钟包含进程通信，不是纯CPU耗时。失联1秒保护不是实时合格门；原PL读回期限不改，不自动重试/软件回退。

这次不绘图，因此display门仍false；所有50Hz、自动β、DDR及V3-A完整通过标志保持false。下一步由实际配对率、持续有效段、各队列、输出质量及处理延迟决定，不能用软件对照“0漏槽”代替实采验收。
