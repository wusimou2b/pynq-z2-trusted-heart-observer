# 可信心率观测系统

**基于 FPGA 的个体健康趋势预警——面向多模态感知的可信心率观测系统**

项目入口：[https://github.com/wusimou2b/pynq-z2-trusted-heart-observer](https://github.com/wusimou2b/pynq-z2-trusted-heart-observer)。

系统以 PYNQ-Z2 联合处理 PPG、惯性和视频观测。PL 承担心率计算主链、视频颜色转换及4×3分块运动统计；PS 负责采集配对、质量判断、选路、进程通信和显示。PPG/IMU采集与处理目标25Hz，视频目标5fps。视频提供运动背景，不宣称用视频估计心率或完成临床风险预测。

| 入口 | 用途 |
|---|---|
| [public_live/PublicLive.ipynb](public_live/PublicLive.ipynb) | 新公开 LIVE 四单元入口，含匹配 bit/HWH 与五个原生库 |
| [public_live/README_PUBLIC_LIVE.md](public_live/README_PUBLIC_LIVE.md) | 板端前提、依赖检查、启动与正常停止 |
| [src/](src/README.md)、[build/](build/external_dependencies.md) | RTL/ROM、PS、HLS、BD/XDC/Tcl 与源码构建依赖 |
| [skill/](skill/README.md) | 八项完整 Skills，含 SKILL.md、工具、样例、测试与许可 |
| [report/](report/README.md) | 23页设计报告、8页独立大模型协作记录及正式中英文海报 |
| [reproduction/](reproduction/public_live_software_checks.json) | 环境证据、软件验证范围及待验证事项 |

## 下载部署

使用PYNQ-Z2及原匹配的32位ARM系统和接线。运行栈要求CPython3.10、PYNQ3.1.1、NumPy1.21.5，并需要SciPy、pandas、OpenCV、IPython与ipykernel。保存记录中SciPy为1.8.0、OpenCV为4.5.4；完整SD镜像身份及pandas/Jupyter精确版本尚未全部归档。不要在普通PC上安装PYNQ后尝试加载ARM库，也不要整体升级原板端NumPy/PYNQ来消除提示。

1. 下载项目后，把完整 `public_live/` 放入板端Notebook目录。保持其中 `runtime/`、`native_source/` 与Notebook的相对布局；可整体改放目录，不依赖原私有路径。
2. 对照独立发布值核验清单 SHA256：`67c4785d718c16618e85ea7278aea1848200dfd1dc035df70d76342d6b311b00`。`public_live/public-live-manifest.sha256`提供同一校验值；校验和本身不证明发布者身份。
3. 在板端新内核打开 `public_live/PublicLive.ipynb`，先读部署说明。第一单元核验完整文件与依赖，再进行PS短测；依赖不齐或ABI不符时在写attempt前停止。按检查报告在同一板端Python环境补齐依赖，保留固定NumPy/PYNQ版本。
4. 分别执行20秒视频检查、显示准备和实际运行单元。硬件阶段需要输入各自确认字符串；不要使用Run All。
5. 点击第三单元输出的“正常停止并导出”，等待第四单元返回并确认资源释放。失败时保留结果目录，不自动重试、不以强杀进程或中断内核代替收尾。

新入口使用完整运行清单及显式路径校验，在线启动不要求私人实录ZIP或旧prepared绝对路径。bit/HWH、五个原生库和C来源保持原始哈希，SQI、新鲜度、无效输出撤回、队列容量、时序及资源所有权保护保留。底层ABI、VLNV、schema等必要兼容标识按用户同意保留，产品名称采用本页标题。

Notebook采用明确的 `notebook-source-v1` 身份：正常保存输出和执行计数不改变源码身份；源码、顺序、tags、内核与附件变化会失败。仅允许与已封存源码相同的指定checkpoint；结果目录不能藏入新代码或替换硬件/原生资产。运行产生的个人记录仅留板端，不作为开源文件提交。

## 软件验证与测试结果

在独立发布副本执行的81项无硬件单元验证全部通过；另有6项停止路径JS断言、13项真实封存包迁移/保存/篡改检查通过。四个真实冻结核心模块在陌生目录下使用原LIVE延迟依赖作用域成功导入。测试未加载ARM库、未下载PL、未采集数据，不能替代真实PYNQ-Z2冷启动和板端验收；当前PC的依赖检查按事实报告不满足目标环境。

根目录 `verify_public_source.py` 用于解压后、首次运行前的分发快照校验。实际运行使用 `public_live` 的独立运行清单与Notebook源身份策略；保留生成结果，不为恢复分发快照而删除结果。

可在开发机从项目根执行软件测试：

```sh
python -B -m unittest discover -s public_live/tests -v
node public_live/tests/test_public_stop_path.cjs
```

历史联合运行测试约80.7秒，采集/处理/保存2021条，其中2020条配对、1条无效且撤回数值发布，视频403帧；历史 `manual_session_passed=false` 保留。这是原基线证据，不是新公开入口的板测结果，也不证明心率准确率、严格实时或长期运行能力。

## 源码重建与许可

运行使用随包匹配资产，不要求安装Vivado。PL从源码构建使用Vivado2024.1及相应工具/板定义/IP；见构建目录的真实依赖边界。公开集合保留自研源及可分发组件，部分完整历史物理输入/私有数值回放资料不公开，不宣称一键clean build已经验证。重建原生库或硬件后需建立新身份和相应验证，不能只改哈希冒充原资格。

原创部分与第三方材料分别遵循所在许可；MIT不替代BSD、LGPL、CPython、NumPy、GCC或AMD相关条款。必要权利人署名保留。签名授权、报名身份材料、私人聊天全文及原始生理记录不在仓库中。账号URL和no-reply仍关联公开GitHub账号，不能保证互联网层面不可关联。

演示视频正在按用户要求修订，当前未发布最终视频；完成后将以同一仓库Release附件提供准确链接。
