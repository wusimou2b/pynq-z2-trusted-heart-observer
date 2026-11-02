# V3-A：独立Overlay上板回放说明

本包保持三轴×4抽头限幅NLMS，正常beta=0.03。PS负责采集、去直流／缩放、运动状态、三级质量、接触阻断、联合收益选择、最终BPM；PL只计算同一NLMS候选及控制／计数。本次不加摄像头、HDMI、新滤波算法、动态抽头或自动步长规则。

PC数值、接口和整板时序通过不等于上板成功。`manifest.json`中的板测、50 Hz实采和自动步长效果均为false。原V1／V2和失败结果保留。

## 风险与准备

原PS／板preset继承的四个DDR DQS-to-CLK值为-0.051／-0.006／-0.009／-0.033。它们没有修改，PSU-1～4原始严重告警仍保存在provenance中；PC发布仅采用已批准的精确继承例外。`board_ddr_verified=false`，不是已证明无害。

首次加载前记录板型、当前PYNQ镜像／启动状态，保留旧目录和旧运行截图；新包不能替代启动镜像或替你证明原镜像DDR配置。遇启动、内存、I²C或回放异常，立即停用新包、保存诊断，重启回原保底流程，不在同一内核混用旧Overlay。普通内存初检和黄金回放仅是初检，DDR风险状态不会因此自动改为已解决。

1. 停止所有旧monitor和采集任务，关闭相关Notebook内核；用新内核／终端独占新IP。禁止Run All或同时运行两个进程。
2. 将包完整上传并解压到独立目录，例如`/home/xilinx/jupyter_notebooks/heart_v3a`。不要只复制bit，不要覆盖旧`heart_axi`目录。
3. 包内保留相同名称的`heart_v3a.bit`／`heart_v3a.hwh`。Python、配置、golden、provenance和中文说明都须保留。
4. 使用板上已有Python 3、PYNQ、numpy、pandas、scipy、PyYAML、matplotlib和cffi。缺依赖先反馈，不自动安装或替换板上环境。

## 第一步：检查文件，不加载板子

在新目录打开Jupyter Terminal，运行：

```bash
cd /home/xilinx/jupyter_notebooks/heart_v3a
python3 run_v3a_board_replay.py --check-bundle
```

须显示`bundle_validated: true`、`golden_samples: 15942`。本步没有PYNQ import、Overlay下载或MMIO创建；检查失败不要继续。审计中原PC绝对路径是来源记录，检查实际只访问包内快照，可在Linux板上搬移。

## 第二步：只运行一次显式上板回放

先确认旧采集已停止、新包来源正确且知悉上述继承DDR风险，再运行：

```bash
python3 run_v3a_board_replay.py --hardware
```

本步加载一次新Overlay，核对NLMS／IIC／FIFO地址、NLMS ID／版本、传感器身份、50 Hz寄存器和旧FIFO startup回环，并做普通内存初检；然后分新epoch跑九例15942拍公开黄金和20拍控制序列。β边界／freeze／bypass／reset是接口测试，不是新增正常运动参数档位。非法AXI地址／RO写／WO读测试仅在PC仿真，板端不故意制造总线错误。

每例完成会显示检查数和实际PL最大周期；最终应退出0，mismatches=0、最大周期≤2048，最后一份真实case权重限幅99次。脚本检查candidate／output／status、sequence／epoch／实际β、β影子读回和累计计数；不声称板上读取了所有内部权重。只有真实硬件入口全数成功才写`board_replay_passed=true`。PC假设备结果永远不写板测通过。

出错立即停止，不自动重投或回退软件后仍标FPGA。`board_results/replay-...`保存summary.json及已完成actual.csv；将整个结果目录下载反馈。内核被重启／退出时，残留文件不等于完整通过，必须检查summary中的完整检查数和状态。

预检会配置传感器，但黄金回放不是实采，期间PPG FIFO可能积压；本次不以这段验证50 Hz丢样或实时显示。后续实时采集重新初始化并清FIFO，再按冻结采集门检查。

## 接口与控制

三个地址保持：IIC=0x41600000、FIFO=0x43C00000、NLMS=0x43C10000，每段64 KiB。NLMS ID=0x4E4C3304、VERSION=0x00010000。

主要偏移：COMMAND=0x08（提交1／ACK2／软复位4／快照8）；STATUS=0x0C；SEQ=0x10；FLAGS=0x14；PPG=0x18；XYZ=0x1C／20／24；BETA=0x28；结果SEQ／STATUS／candidate／output／β／周期=0x30／34／38／3C／40／44；epoch=0x48。完整唯一表在`heart_v3a/axi_contract.py`，驱动负责原子包、身份、超时、不重投及显式恢复。

输入为规范符号扩展的24位Q16；输出为32位Q16；β为32位无符号Q30，默认32212255。FLAGS低4位为有效／更新／清学习／旁路。freeze推进参考历史，bypass不冻结学习；参数在提交边界生效，改变影子值不污染在途样本。

## 本次之后

收到真实上板回放日志并通过后，才继续V3-A下一实采交付：采集线程→有界处理队列→PL候选／PS主链→低频显示与独立记录，逐项测试丢样、延迟、接触阻断及启停恢复。有限两档自动效果再单独验收，不满足则固定0.03并如实标未通过。摄像头／HDMI属于后续V3-B，不在本包。
