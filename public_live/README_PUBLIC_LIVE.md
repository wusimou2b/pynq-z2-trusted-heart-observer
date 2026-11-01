# 可信心率观测系统

面向多模态感知的可信心率观测系统。此目录是公开LIVE部署副本，保留匹配bit/HWH和原始ARM库，运行时验证整套文件、加载路径及原保护条件。私人生理实录与离线数值回放资格留在私有归档，公开入口使用独立结果schema。

该入口已经过静态检查和纯软件边界测试；本次没有重新载入ARM库、运行工程或上板。它解决了公开运行路径被历史私密实录清单阻断的问题，不能据此声称新入口在板端验收通过。原测试结果约80.7秒、2021条记录、2020条配对加1条无效撤回记录、403帧属于原基线。

## 系统与接线

使用同一目标PYNQ-Z2及项目实际接线：MAX30102、MPU6050、USB摄像头和HDMI显示。传感器供电、电平和引脚请按主仓库设计文档核对；不要根据线色猜引脚，也不要同时运行其他Overlay/采集入口。Notebook界面要求支持原经典Jupyter comm与浏览器交互，不把JupyterLab兼容性写成已验证。

板端必须使用CPython3.10的ARMv7硬浮点ABI、原NumPy1.21.5，以及PYNQ3.1.1和匹配的原视频驱动源码。保存记录还支持CPython3.10.4、SciPy1.8.0；OpenCV4.5.4来自历史板端记录。Pandas是完整LIVE需要的依赖，即使短导入可以延迟它；其实际版本、完整OS/内核、镜像来源/哈希和Jupyter栈尚未锁定。不得盲目升级NumPy或把新挑选的Pandas版本当作原板版本。

优先在原成功系统环境部署。缺包时从原镜像或已采集环境记录恢复；本目录没有伪造全环境lock。先在目标解释器查看版本，再按实际环境补依赖。只读元数据命令示例：

```python
import importlib.metadata as metadata
import platform, sys, sysconfig
print(sys.version, platform.machine(), sysconfig.get_config_var('SOABI'))
for name in ('pynq', 'numpy', 'scipy', 'pandas', 'notebook', 'ipykernel', 'ipython'):
    try:
        print(name, metadata.version(name))
    except metadata.PackageNotFoundError:
        print(name, 'no distribution metadata; inspect system package')
```

该片段只读取元数据，不加载Overlay或采集。OpenCV可能由系统包安装；请同时保存实际`cv2.__version__`。依赖安装需保持上述ABI及固定版本，并记录未锁项；本次未安装新板端软件。

## 目录与部署

完整解压到板端Jupyter可访问的普通新目录，保留如下相对布局，不混入旧尝试目录：

```text
PublicLive.ipynb
public-live-manifest.json
public-live-manifest.sha256
runtime/                  # Python、JS、静态配置、匹配bit/HWH与运行helper
native_source/            # 原统计库及对应C源
```

目录名称可更改，根路径由Notebook显式选择并验证；不再依赖旧prepared里的机器绝对路径。底层ABI/IP/schema技术标识为兼容而保留，不是产品名称。源码重建与八项Skills见主仓库根README；此包的板端运行不要求重编Vivado工程。Vivado2024.1重建和数学ROM再生成是另一层验证。

下载后先把`public-live-manifest.sha256`中的值与发布页独立公布的SHA256核对。Notebook还会校验该锚与manifest及全部运行文件；同目录的两个可同时改写文件不能单独证明发布者身份。不要手改manifest绕过校验，也不要换用另一个.so或bit/HWH。

标准Notebook采用显式`notebook-source-v1`身份：保存普通运行输出或执行计数不会改变源身份；代码/Markdown、单元tags与attachments、格式及指定kernel/language字段仍严格校验。对应checkpoint仅在源身份完全一致时接受，不宽泛忽略其他执行文件。带额外执行语义的未知扩展或特殊执行元数据尚未支持，不能当作默认兼容。

Notebook在导入入口前禁用字节码缓存，并为当前会话的spawn子进程设置`PYTHONDONTWRITEBYTECODE=1`；不会改系统环境设置。若使用命令行做文件/元数据检查，请使用`python3 -B`。清单不会把未知`__pycache__`当作可忽略文件。

## 四阶段运行与正常停止

1. 在该目录打开`PublicLive.ipynb`，运行第一个代码单元：完整文件与依赖检查，然后才是无硬件PS短检查。缺包、NumPy版本不符或CPU ABI不符时，在写attempt和启动原生后端之前拒绝继续；`check()`本身只报告状态。短检查保留700点预热、60秒READY与1秒自然退出门槛；失败不能继续。
2. 第二单元手动输入`RUN-PUBLIC-VIDEO20`，进行20秒视频所有权与释放检查。该阶段会接触硬件，但不会开始心率传感器实采。
3. 第三单元准备浏览器显示，等待绿色就绪，保持该单元输出可见。
4. 第四单元手动输入`RUN-PUBLIC-LIVE25`开始联合采集。预热另计；正式运行使用正常停止按钮结束。固定容量和满停保护仍在，不能理解为无限时长。

结束时点击第三单元输出中的“正常停止并导出”，等待“已停止并导出”和第四单元返回。不要中断内核、强杀owner或提前释放CMA。若DMA/相机/HDMI/PS退出或lease释放不能确认，原隔离与保留策略继续有效，不自动重试。结果位于`runtime/continuous-results.zip`及独立`public-*.json`；运行产生的数据属于用户自己的采集结果，不应自动提交到GitHub。

每个阶段attempt及结果只写一次。失败时保存原目录和输出，不能删除attempt文件后把同一会话当作首次启动；新的手动尝试使用完整解压的新目录和新内核。代码、库、bit/HWH或清单发生变化时，所有子进程都会拒绝混用身份。

## 无硬件边界测试

在包根执行`python3 -B -m unittest discover -s tests -v`，验证门控、身份失败、参数传递、来源与资源条件；测试只使用合成文件、受控进程/后端替身和AST，不加载ARM库或PYNQ。开发机已有Node.js时可另运行`node tests/test_public_stop_path.cjs`，核对公开Notebook目录下的正常停止路径。测试通过不替代实际PS数值或板端运行。

## 结果的含义

`asset_identity_verified`只表示文件身份；`historical_numerical_qualification=false`明确本入口没有执行私有1504条实录回放。新阶段记录与原记录分开，保留失败及无效门控，不把静态打包标成数值、实时、准确率或完整验收通过。真实目标环境冷启动、相同接线下的20秒视频、联合采集、停止释放及故障/容量保护仍需要实际板端证据。
