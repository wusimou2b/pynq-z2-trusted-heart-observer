# 验证链与接口约束

## 迁移边界表

为本次核建立简短表格：输入及来源、状态、输出、PS剩余规则、数值约定、频率/吞吐、总线搬运、取消/复位、验收证据。用已有性能数据选择粒度：历史窗口在PL内复用通常比逐次逐元素MMIO更合理，但实际收益仍需端到端计时。

| 核类型 | 必须写死的细节 |
|---|---|
| 历史相关/收益评估 | 窗长、lag、触发频率、有效历史、归约顺序、谱估计是否仍在PS、成熟/复位边界 |
| NLMS/滤波 | 初始状态、更新次序、量化、系数、限幅、异常复位、实际参考信号身份 |
| 峰值/IBI | 峰值确认延迟、不应期、时间单位、峰龄、缺测/复位、IBI与BPM换算及PS最终门控 |
| 视频统计 | BGR/YUYV布局、舍入顺序、ROI半开边界、首帧/缺号、帧差valid、计数宽度、帧所有权 |

Pan-Tompkins等其他算法不自动等价于当前PPG峰值链；迁移现有代码与替换检测算法是不同改动。

## AXI和所有权

- 流数据只在VALID且READY时推进；停顿时保持数据和SOF/EOL等边带。坏帧不可默默重同步成成功帧。
- 结果必须由同一事务锁存，并保持到消费/ACK；读完结果前不能覆盖下一结果。ARM时锁存配置和来源token，核编号、来源序号与epoch分开解释。
- AXI-Lite AW/W分别接受；已发B/R响应在背压与后续ACK/软复位期间保持。WSTRB、只读/只写、保留位和非对齐访问均有确定行为。
- 核软复位不天然停止外部DMA。协调层须撤销部分事务、建立新来源代号并处理已接受的总线响应。
- 看门狗分别注明PL周期、C/驱动截止和外层wall截止；改变任一边界，必须核对对应层，不用放宽保护掩盖协议或调度问题。

## 本项目可复用入口

从用户提供的项目根定位，下列模块有历史绝对路径或版本绑定，读参数与调用链后再复用，不直接假定适配新核：

- `v3b25_integration/vision_reference.py`、`generate_vectors.py`、`rtl_vectors.py`：整数灰度/平均/ROI参考及同源向量。
- `v3b25_integration/RTL_INTERFACE.md`、`AXI_LITE_INTERFACE.md`：反压、结果单槽、ARM/ACK、token/epoch与复位责任。
- `v3b25_integration/run_rtl.py`、`run_axi.py`、`run_spatial_rtl.py`、`run_spatial_axi.py`：实际Vivado仿真和结果核对入口；`sim/`有真实testbench。
- `v3b25_integration/main_heart_reference.py`、`main_heart_pipeline.py`、`main_heart_transaction.py`：心率参考与事务边界。
- `v3b25_integration/history100_online_final_qualification.py`：从原DCP重新核对最终route/timing/DRC/CDC。不能删除失败日志或把局部通过覆盖最终门。
- `v3b25_integration/whole_implementation.py`、`interface_review.py`、`bitstream_handoff.py`：整板实现、接口约束及同源bit/HWH。检查bit envelope只验证元数据，不证明payload物理行为。
- `v3b25_integration/board/joint_owner.py`：早期单所有者与实际IP窗口身份，常量必须改为当前核的正式契约。

## 证据等级

软件参考一致、真实RTL仿真一致、OOC时序、整板路由、bit/HWH身份、实际板端身份、静态功能、保存输入回放、传感器短测、完整联合负载分别报告。每一级不自动蕴含后一级。

视频提交帧数不替代实际HDMI动态画面；PL内部延迟不替代Python返回；无队列满不替代新鲜心率发布；软件计数连续不替代ADC FIFO连续。当前项目的研究候选/负结果应保留为边界案例，不写成已完成的通用方案。
