# 本包当前步骤：只读等价与完整PS计时

本包保持原bit/HWH、三轴4抽头NLMS、参数、选路/接触/SQI规则、窗口长度和检查频率。仅新增live等价统计执行器：同序NumPy基元、同IBI统计复用、最多4个完整质量窗口结果复用。原进程隔离及硬件所有权不改。

先停止旧采集和旧work内核。在新空目录解压本完整ZIP，使用新内核。当前只运行下面两条，不点旧Notebook②/③，也不运行任何--hardware：

```python
import sys
!{sys.executable} run_v3a_isolated_live.py --check-bundle
!{sys.executable} run_v3a_statistics_check.py --output statistics_check.json
```

不需要手指，传感器不亮是正常的。只读程序先比较12种历史窗口、新旧1000点完整PS的公开输出及因果状态；零差异后交替计时新旧实现各两遍。软件NLMS只在准备阶段产生完整回复，计时回放核对相同请求，不进行NLMS计算，也不加载Overlay。每250点显示进度，请等待打印最终报告路径；不能把第一条身份检查成功当作第二条核验完成。

回传新目录的statistics_check.json。不要覆盖旧诊断、旧包或旧采集。已有同名报告时脚本会拒绝覆盖，需要保留原报告并指定另一个新文件名。

PC测试不是ARM等价/性能，也不是实采验收。直接PS计时不含IPC、真实PL、IIC、写盘或显示负载；即使成熟段平均低于20ms，也仍需后续真实60秒验证。当前live_50hz、auto_beta_effect、DDR、V3-A完成及限值批准均未通过。
