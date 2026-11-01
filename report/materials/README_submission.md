# 可信心率观测系统：技术材料

作品名称：基于FPGA的个体健康趋势预警——面向多模态感知的可信心率观测系统。

系统采用PYNQ-Z2与PS/PL协同处理，结合PPG心率主链、惯性与视觉运动观察、本地显示及质量和来源保护。MAX30102和MPU6050以黑色绝缘胶带与魔术贴固定，主机支架、相机立柱与托盘组成集成原型。八项Skills支持人工主导的研发与证据核验，设备运行不依赖大模型推理。

| 材料 | 文件 |
|---|---|
| 23页设计报告 | technical_report_anonymous.docx / technical_report_anonymous.pdf |
| 一页中文展示海报 | amd_health_poster_zh_submission.pptx / amd_health_poster_zh_submission.pdf |
| 一页英文海报 | amd_health_poster_en_submission.pptx / amd_health_poster_en_submission.pdf |
| 8页大模型协作记录 | llm_collaboration_record_anonymous.docx / llm_collaboration_record_anonymous.pdf |
| 板端使用和核验说明 | usage_guide.md |

运行入口为ContinuousDemo25.ipynb，按使用说明依次完成四单元操作，结束时正常停止、保存与释放资源。联合运行测试在PPG/IMU 25Hz及视频目标5fps下记录约80.7秒，处理保存2021条、配对2020条、1条未配对记录禁止数值发布、视频403帧。软件对照、RTL核验、真实采集与PL资源时序分别列明测量范围。

本索引指向正式匿名技术材料。源码构建、环境依赖及工程目录对照应与工程附带README和构建脚本一并核验；本索引不替代工程从零复现步骤。

协作记录为独立补充材料，按需求、提示、模型建议、人工判断与纠错、验证结果及Skills沉淀组织；主报告的正式模板结构保持不变。
