# Retry6实测数值数据

本目录来自用户自行采集并已授权公开的2026-11-02 continuous-capacity retry6记录。raw.csv与results.csv各含2905行，均从原始ZIP按原字节提取；未删行、未改数值、未改列名。原始30列及结果81列全部保留，逐列映射与SHA256见provenance.json。

已检查列名和所有不同的文本值：没有停止令牌、密码、会话ID列、用户名、绝对路径、邮件或URL；文本为质量、路由、运动、原因等受控枚举。generation、pl_epoch等为数值控制状态；时间列用于保存的名义/主机计时，不代表参与者身份或硬件绝对时间。2905是记录数，不是受试者人数。

## 原件与本提交副本

设计报告参考文献[9]中的data/baselines/frozen_retry6/continuous-results.zip是**原始交付工程中的来源路径**。原ZIP只读保留，包含停止请求与本机路径等元数据，未原样复制到本公开子集，也未创建一个同名“脱敏ZIP”冒充原件。

原始ZIP SHA256：
d4be2d7906cfcc2e44989f0a67d2ff4549616fbb3b51d33033e423e58708a0b7

本副本对应证据：
- data/measured_retry6_20261102/raw.csv
- data/measured_retry6_20261102/results.csv
- data/measured_retry6_20261102/provenance.json
- board/results/retry6_20261102/summary.json

summary.json明确标记为根据保存记录生成的公开派生摘要，不是原始JSON；原始false、超预算计数与范围条件保留。

## 统计口径

正式采集115.984024602秒，2905条读取、处理和保存，2904配对、1未配对，2125条允许发布；视频579个应用完成帧。发布行数不是精度或物理屏幕绘制次数，应用帧不是相机曝光或屏幕刷新计数。此处为一个历史窗口，不作全系统、严格实时或临床准确性验收结论。
