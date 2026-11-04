# Retry6运行证据公开派生摘要

summary.json由已核对的115.984秒历史联合实采记录生成，字段由原始ZIP及CSV复算支持。它明确标记document_kind=derived_public_summary_not_original_log；不是对原始日志的改名，也不是新增上板结果。

数值原件提取于data/measured_retry6_20261102/，来源成员、列映射、原字节SHA与文本字段检查见该目录provenance.json。报告[9]引用的原始data/baselines/frozen_retry6/continuous-results.zip留在原始交付工程，其SHA仅用作来源身份，不能视为本派生摘要的哈希。

摘要不含私有绝对路径、停止令牌、停止请求ID或用户身份。正式采集计数、处理/视频、队列、自然退出、资源释放、原始false、252次采集循环超预算、2次Python返回超过40ms及启动/停止边界均保留；停止时在途帧取消保留其“预期停止取消”上下文。

本目录整理未加载硬件、访问板卡或修改原工程。
