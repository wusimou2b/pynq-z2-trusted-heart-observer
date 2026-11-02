# 可信心率观测系统

基于FPGA的个体健康趋势预警——面向多模态感知的可信心率观测系统。

工程与Skills资料入口：[工程与Skills仓库](https://github.com/wusimou2b/pynq-z2-trusted-heart-observer)。配套运行与构建说明见仓库README，交付身份以工程manifest为准。

| 文件 | 用途 |
|---|---|
| technical_report_anonymous.pdf | 29页正式匿名设计报告，不含账号链接 |
| technical_report_anonymous.docx | 可编辑匿名设计报告 |
| technical_report_public.pdf | 29页公开设计报告，含真实仓库入口 |
| technical_report_public.docx | 含仓库入口的可编辑公开报告 |
| amd_health_poster_zh_submission.pdf | 一页中文匿名展示海报 |
| amd_health_poster_zh_submission.pptx | 一页中文匿名海报可编辑源文件 |
| amd_health_poster_en_submission.pdf | 一页英文匿名海报，供按规则打印提交 |
| amd_health_poster_en_submission.pptx | 一页英文匿名海报可编辑源文件 |
| llm_collaboration_record_anonymous.pdf | 8页独立大模型协作记录：真实提示、建议、纠错、验证及八项Skills |
| llm_collaboration_record_anonymous.docx | 可编辑匿名协作记录 |
| llm_collaboration_record_public.pdf | 8页公开协作记录，含真实仓库入口 |
| llm_collaboration_record_public.docx | 含仓库入口的可编辑协作记录 |
| usage_guide.md | 匿名板端使用与核验说明 |
| usage_guide_public.md | 含真实仓库入口的使用与核验说明 |
| README_submission.md | 不含账号链接的提交材料索引 |

当前板端部署以[根README](../../README.md)和[板端说明](../../board/README.md)中的 `board_runtime/runtime/ContinuousDemo25.ipynb` 为准；当前保存的33.193811316秒／832条／166帧记录与下述历史联合记录分别报告。

报告与海报保留一致的历史系统设计和测试口径：PPG/IMU 25 Hz、视频目标5 fps，联合运行测试约80.7 s，处理及保存2021条，配对2020条，1条未配对记录保留原因并禁止数值发布，视频输出403帧。联合PL使用Vivado 2024.1实现，主处理时钟100 MHz。设备本地运行不依赖大模型；八项Skills用于研发和核验。

报告图9A-1、图9B-1与图9c为项目对话的真实界面摘录，分别呈现人工约束或反馈及模型操作边界。原图9a、9b的原文摘录继续保留；图9c保留消息折叠标记，截图已裁去无关身份界面。图13a的设备识别码已隐去。原始测试记录、完整聊天、身份报名资料、签名、校徽展示稿和内部审计不在本目录中。

正式提交使用文件名含 `anonymous` 的报告及一页英文海报；本目录只发布独立的一页中文和一页英文正式海报；旧双页展示稿不纳入本发布集合。`technical_report_public` 为公开入口版本，其技术内容与匿名版一致，额外保留用户要求的真实仓库链接。使用说明覆盖配套板端环境中的操作，源码环境配置与构建步骤应与工程README、依赖及脚本共同使用。真实仓库链接含GitHub账号段；含链接的公开报告及README不能视为严格去账号匿名文件，互联网访问本身也不构成完全匿名。文件校验值见 `SHA256SUMS.txt`。

独立《大模型协作记录》展开主报告2.3.3的两组案例，附三张真实界面截图和人工主导工作流。它记录实际决策、来源纠正及验证范围；《八项Skills说明》用于查阅工具功能。公开入口版主报告第10页、公开使用说明及公开协作记录均提供同一工程入口。协作记录中的本地核验索引指向留存资料，完整聊天和内部核验文件不随公开材料上传；公开摘录、图示和验证范围已在记录正文中呈现。

海报采用所提供的AMD模板：RESULT第二图片位置为可编辑联合测试表，下方为结果解释、资源时序和组件对照，配有整机及板卡照片。本目录海报与正式归档中的当前中英文一页海报逐字节一致，匿名报告采用同轮稳定正式稿。
