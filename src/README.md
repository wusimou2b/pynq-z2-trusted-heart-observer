# Design sources

`rtl/` 保留与当前物理实现对应的 RTL 和数学 ROM。`ps/` 为 387 份源码及从冻结归档导出的 39 份 Notebook，Notebook 仅清理输出与执行计数，原单元源码及保护未改。当前演示入口原名为 `ContinuousDemo25.ipynb`，其他入口为历史定位资料。

`identity_reference/` 中的 48 份 JSON 是经路径脱敏的历史身份参考，**不是本目录可直接使用的运行 manifest**。原固定身份关联的生理数据、资格 ZIP 和二进制未公开；将这些文件放回运行位置也不能使删减源码目录通过原验证。转换前后哈希分别记入根目录公开清单。

`hls/` 为固定 PYNQ 上游版本的 color_convert/pixel_unpack C++、头文件、测试和 Tcl，共八份输入加 BSD 许可证；未将工具生成 HDL/驱动整体改作 MIT 发布。`third_party/`、`licenses/` 保留 PocketFFT 和派生数学实现的许可说明。

部分源生成器仍引用历史 ARM libm/PocketFFT 输入位置，历史辅助入口也有未闭合的模块依赖。保留 ROM 可用于现有硬件综合输入；从算法参考重新生成全部 ROM 的可移植闭包尚未验证。详见 `../build/external_dependencies.md`。
