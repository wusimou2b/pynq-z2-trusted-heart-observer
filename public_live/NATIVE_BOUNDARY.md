# 公开 LIVE 副本的原生依赖边界

新入口通过显式 `release_contract` 选择本发布目录中的资产。契约只包含发布根目录和调用者提供的 manifest SHA256，能够作为普通字典传给新进程；父进程、PS 与 worker 分别完整核对清单、路径和原资产哈希。它不搜索旧工程目录，也不把校验和文件视为发布者身份证明。

统计扩展仍使用原 CPython 3.10 ARMv7 hard-float ABI，以及记录中的 NumPy 1.21.5 环境。二进制、C 源码、内部模块名和 `PyInit` 符号均保留原字节。新分支先核对发布清单与选定路径，再执行原扩展加载后的实现名和方法类型检查。宿主平台不匹配时会提前拒绝；本次软件测试没有加载该 ARM 扩展。

主链还保留 compact readback、原 readback、首个 SAMPLE 观察及 transaction scheduling 四个原 ARM 共享库。它们各有固定 SHA256，并在任何显式装载前独立检查完整发布契约。原来的资格报告语义、汇编屏障、ABI、clock、held-GIL、调度恢复与资源释放检查继续执行。新 loader 的身份由新 manifest 记录；历史报告中的 builder 哈希仍指原 builder，不能把新路径适配写成重新编译或重新资格通过。

`native_source/` 中保留的历史准备工具仍要求其原有私有输入与历史完整性证明。公开 LIVE 分支不调用该工具，不使用旧私有 ZIP、旧 prepared 报告或机器绝对路径来证明本次运行资格。`historical_numerical_qualification` 与 `new_release_board_verified` 不因文件齐备而变为真。未提供 `release_contract` 的历史默认分支继续执行原 guard。

只读源代码和资产逐件按 manifest 校验。仅 manifest 显式声明的结果文件或结果目录可新增；结果不能遮盖已列源码，不得藏入共享库、缓存、硬件资产或未列代码。结果 ZIP 中的源码副本必须与清单中同名源码哈希一致，嵌套 ZIP 按同一规则检查；所有结果归档均不作为导入路径。Notebook 在导入发布模块前关闭字节码写入，命令行使用 `python -B`，未列的缓存不会被忽略。

`PublicLive.ipynb` 使用明确的 `notebook-source-v1` 身份：参与长度和 SHA256 的是规范序列化后的 Notebook 版本、内核名称与语言、语言名以及按原顺序的单元类型、完整 source 文本、tags 和 attachments。代码空白不归一化；source 字符串列表仅原样连接。普通保存产生的 outputs、execution_count、cell id、trusted 及其他未列元数据不计入此身份。其他源码、配置和所有硬件/原生资产继续按原字节校验。此策略仅用于标准 Notebook，不替代依赖自定义执行元数据时应采用的更严格策略。

清单可明确声明唯一检查点映射 `.ipynb_checkpoints/PublicLive-checkpoint.ipynb → PublicLive.ipynb`。该副本出现时必须与已固定的 Notebook 源码身份完全相同；检查点改代码、增加其他 Notebook/脚本、symlink 或越界均拒绝，不忽略整个检查点目录。父进程和 worker 的发布检查还核对已加载核心与公共模块的文件及 spec 来源，拒绝旧私有目录的同名缓存；更换源码后应使用新内核。

标准库合成文件测试、参数边界测试及静态 ELF/哈希检查已有独立记录。真实冻结模块的无硬件导入检查单独报告其环境和结果，不从 stub 测试推断成功。没有综合、编译、采集、回放数值证明或新板测；这些软件检查不能替代后续真实板端环境与显式运行验收。

陌生临时目录的真实冷导入已按两种边界分别留证。未进入原 LIVE 作用域的初始检查在 `entry25_candidate → peak_chain → heart_v2.__init__ → dataset` 因缺少 `pandas` 停止。随后使用原 `main_ps_exit_worker.defer_offline_pandas` 作用域，四个真实核心模块全部导入成功，并用仅声明接口的 ARM core 测试对象创建了真实候选类；原生方法调用数为零，没有实例化处理链或执行 step。三份原受控模块的路径和固定哈希一致，延迟对象没有实际导入 Pandas，全局 import 函数未改，作用域退出后的 finder 已移除。没有安装或伪装 Pandas，也没有读取私有记录或访问设备。

这一既有作用域只延迟尚未使用的离线依赖：真正访问 Pandas 属性时仍要求安装真实库。例如原 `parse_boolean(optional=True)` 的非空 contact 分支会求值 `pd.NA`，不能把本次导入检查解释为所有在线分支均无需 Pandas。宿主 NumPy 2.2.3、SciPy 1.18.0 与 `scipy.signal` 实际可导入，但这些宿主版本不等于原 ARM 运行环境资格；Pandas 的目标版本及完整环境仍须以板端证据锁定。
