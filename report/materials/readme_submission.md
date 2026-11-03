> **2026-11-03 部署说明：** 当前仓库使用合规存储名称。本文件中的原 Notebook 名称及运行步骤仅适用于执行 `python3 -B prepare_delivery.py runtime --output ../trusted_heart_demo` 后生成的目录；请先按根目录 `readme.md` 完成准备与校验，勿直接运行仓库内的规范化副本。

# 可信心率观测系统：技术材料

作品名称：基于FPGA的个体健康趋势预警——面向多模态感知的可信心率观测系统。

系统采用PYNQ-Z2与PS/PL协同处理，结合PPG心率主链、惯性与视觉运动观察、本地显示及质量和来源保护。MAX30102和MPU6050以黑色绝缘胶带与魔术贴固定，主机支架、相机立柱与托盘组成集成原型。八项Skills支持人工主导的研发与证据核验，设备运行不依赖大模型推理。

| 材料 | 文件 |
|---|---|
| 33页新版匿名设计报告 | technical_report_anonymous.docx / technical_report_anonymous.pdf |
| 中英合并两页匿名海报 | amd_health_poster_bilingual_anonymous.pptx / amd_health_poster_bilingual_anonymous.pdf |
| 一页中文展示海报 | amd_health_poster_zh_submission.pptx / amd_health_poster_zh_submission.pdf |
| 一页英文海报 | amd_health_poster_en_submission.pptx / amd_health_poster_en_submission.pdf |
| 8页大模型协作记录 | llm_collaboration_record_anonymous.docx / llm_collaboration_record_anonymous.pdf |
| 板端使用和核验说明 | usage_guide.md |

当前公开部署入口为 `board_runtime/runtime/ContinuousDemo25.ipynb`，完整目录与环境说明见[根README](../../readme.md)和[板端说明](../../board/readme.md)。新版匿名报告以另一次115.984秒／2905条／579帧记录为主要实采案例；当前公开源码所附记录33.193811316秒／832条／166帧与旧报告80.652秒／2021条／403帧为不同运行，不应合并。运行时按使用说明依次完成四单元操作，结束时正常停止、保存与释放资源。软件对照、RTL核验、真实采集与PL资源时序分别列明测量范围。

本索引指向正式匿名技术材料。源码构建、环境依赖及工程目录对照应与工程附带README和构建脚本一并核验；本索引不替代工程从零复现步骤。

2026-11-04 更新：新版报告根据用户要求保留 GitHub 账号链接和图片内容，并遮盖设备条码及相应数字。文档发布副本已清理作者及办公软件用户标识；账号链接可能具有可追溯性，是否满足特定竞赛盲审要求须按实际规则另行确认。

两页合并海报与单页英文现场打印版分开使用；单页英文按适配A4打印。公开PPTX已清理非可视模板身份元数据，视觉内容保持；对应PDF保留原字节。非匿名海报及签名授权书只在本地交付目录中。

协作记录为独立补充材料，按需求、提示、模型建议、人工判断与纠错、验证结果及Skills沉淀组织；主报告的正式模板结构保持不变。
