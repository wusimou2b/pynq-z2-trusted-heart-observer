# 可信心率观测系统：环境版本证据

这是一份保存记录的静态证据锁，完整环境尚未锁齐。没有运行工程、编译、仿真、回放、登录板卡或执行环境收集器。机器可读记录见 [environment_evidence_lock.json](environment_evidence_lock.json)；所有版本均关联来源SHA256与JSON指针或行号。公开记录使用匿名来源编号；完整原路径仅在内部审计映射中保存。

| 组件 | 能确认的内容 | 证据层级与范围 |
|---|---|---|
| CPython | 3.10.4 | S01 `/environment/python`，历史板端保存输入回放。 |
| NumPy | 1.21.5 | S01 `/environment/numpy`及S02 `/build/numpy/version`。 |
| SciPy | 1.8.0 | S01 `/environment/scipy`，直接记录。 |
| 架构、系统族 | armv7l、Linux | S01 `/environment/machine`、`/environment/system`。 |
| Python SOABI | cpython-310-arm-linux-gnueabihf | S02 `/build/soabi`。 |
| Native编译器 | GCC 11.2.0，Ubuntu 11.2.0-19ubuntu1构建 | S03第1行；S02 `/build/tools/0/sha256`还记录了编译器二进制身份。编译器品牌不能据此锁定OS发行版。 |
| ARM字节序 | little | S08构建器守卫与S02完成准备记录；准备JSON没有直接字节序字段，因此与直接元数据区分。 |
| Vivado | 2024.1 | S04 `/tool_version`，历史整板物理实现；不是本次干净重建通过。 |
| PYNQ | 源码要求3.1.1，历史记录亦写3.1.1 | S05版本守卫、S06历史叙述；尚无直接安装元数据快照，不能标为完整环境锁定。上游源码标签与板上安装版本分开。 |
| OpenCV | 历史板测记录写4.5.4 | S06视频打包预检/视频单链试验叙述；没有在所查归档找到直接版本字段，不能推定为联合运行测试环境的完整快照。 |
| SD镜像文件/构建/哈希 | 未知 | 不按PYNQ版本或Python版本猜镜像。 |
| Linux内核、OS发行版 | 未知 | 已知Linux系统族，未取得内核release/build和os-release记录。 |
| Jupyter、Notebook/Server、IPython、ipykernel等 | 未知 | S07当前入口静态使用`IPython.display`，没有版本记录。 |
| 浏览器产品/版本 | 未知 | 板端Python的`platform=linux`不是客户端浏览器版本。 |
| Bokeh、ipywidgets、Matplotlib等 | 未知 | 历史UI分支有引用，不将它们一律写成当前入口已锁定的必需版本。 |

S01记录的是板端保存输入回放和只读比对：`hardware_loaded=false`、`pl_reexecuted=false`、`realtime_validated=false`、`accuracy_validated=false`、`board_ddr_verified=false`。不能将这个环境快照本身当作联合运行测试或全新SD复现通过。工作站软件试验、Skills合成夹具、上游参考资料的版本都未混入板端锁。

匹配原生库已由并行审计单独找回；代码RAR不分发该编译产物。本版本锁不再将其表述为本地无文件，产物身份与部署资格继续由对应交付清单管理。

## 用户在已有成功板环境补取

以下命令仅供用户自行运行，本审计没有执行它们。使用成功Notebook对应的同一Python解释器；不要为取版本启动工程或加载Overlay。

1. 在已有Notebook只读取解释器位置：`import sys; print(sys.executable)`。不导入PYNQ。
2. 用该解释器执行随附的标准库收集器。以下`python3`须替换为上一步的实际解释器；输出文件必须尚不存在：

```sh
python3 -B collect_environment_metadata.py --context "existing successful Notebook environment; operator to identify test" --output environment_metadata_new.json
```

收集器只读Python发行包元数据、`sysconfig`、`os.uname()`、`/etc/os-release`和选定`dpkg`记录；不导入PYNQ/NumPy/SciPy/OpenCV或工程模块，不启动子进程，不访问网络或设备。缺少发行包元数据时会明确记为未知，并检查只读apt包数据库。它只能说明采集时的环境；仍需用户确认与测试环境一致。

可单独补充的只读命令：

```sh
uname -srvm
python3 -m pip freeze --all
```

`pip freeze`不是成功测试证明，完整输出先保留在内部，公开前检查本机路径或私有来源URL。原始SD镜像只能由用户提供真实下载文件名、来源与校验值；若保留了原始镜像文件，可对该普通文件运行`sha256sum <actual_image_file>`。不要读取或镜像块设备，也不要根据当前系统反推原镜像哈希。

客户端浏览器版本从浏览器“关于”页据实记录；也可在已打开页面控制台读取`navigator.userAgent`。不需要刷新页面、登录新服务或执行网络请求。

## 收集器状态

[collect_environment_metadata.py](collect_environment_metadata.py)是未执行的草稿，使用Python标准库；只有用户显式运行并指定输出时才创建一个新JSON，拒绝覆盖已有文件。完成该补取后还需对应环境、产物与测试记录关联，不能因此宣称从零重建或板端复现已经通过。
