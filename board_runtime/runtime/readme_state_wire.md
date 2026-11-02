只运行StateWireLive60.ipynb；原605项静态成员原字节保留。
新增实际PS与视频子进程的manifest校验、PS固定字段编码接入以及与回放同字节的状态编码。
实采父进程替换compact_video_runtime.StateChannel；子进程校验真实类型和epoch/manifest，再进入原驱动。
没有合批/删点/改IMU，显示刷新与1秒保护不变。原1秒PS退出策略不变。
本次全程放稳手指60秒，静止先验证真实并发积压。失败保存、不自动重试。
结果state-wire-live60-results.zip，原始完整采集continuous-results.zip；原版本与失败证据保留。
