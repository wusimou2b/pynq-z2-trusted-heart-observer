# Build sources and status

`inputs/input/design_1.bd`、`inputs/ip_repo/` 的六个自研 IP、`pins.xdc` 及 `scripts/` 来自已核对的物理输入，代码字节保持一致。`physical_summary.json` 是历史 Vivado 2024.1 实现摘要，包含未完成的外部接口与整机验收状态。

`rebuild.py` 原样保留，其输入契约仍要求原始 `inputs/physical-inputs.zip` 及配套索引。该归档包含未在本公开树重新分发的工具生成与第三方资料，所以这里没有提供它。该脚本是原构建入口的源码，不是对本公开目录可一键执行的承诺。不要为了通过检查去删除哈希或修改源保护。

从公开输入建立新工程之前，需要按 [external_dependencies.md](external_dependencies.md) 获取固定来源、生成 HLS IP、提供板定义与合法 AMD IP 环境，闭合文件引用并作新的干净构建。构建脚本应在独立新目录产出新的 bit/HWH 和回执；本次未执行这些步骤。
