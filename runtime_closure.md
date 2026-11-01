# 公开 LIVE 运行闭包

当前入口为 `public_live/PublicLive.ipynb`。它通过新的完整运行清单验证源码、相对路径、匹配bit/HWH和五个原生库；公开在线路径不读取私人实录ZIP，也不依赖旧prepared绝对目录。原私有回放工具和guard仍作为历史源参考，不作为新入口的运行资格证明。

已完成的81项软件单测、6项JS断言、13项真实整包迁移检查与实际板端验收分开。新入口未加载ARM库、未下载PL或采集，目标系统的完整环境与真实板端冷启动仍待核验；不能把原80.7秒记录改称本入口的新测试结果。

具体文件、范围及未验证项见 `runtime_closure.json`、`public_live/README_PUBLIC_LIVE.md` 和 `reproduction/public_live_software_checks.json`。
