# 文档入口

这里的文档只回答“当前产品是什么、如何运行、如何验证”。历史实施过程、迁移边界和阶段性验收不会混入当前入口，而是统一放在 [`archive/`](archive/README.md) 中。

## 当前文档

| 目的 | 文档 |
| --- | --- |
| 产品旅程、用户价值和可见边界 | [`PRODUCT.md`](../PRODUCT.md) |
| Volume、Lifetime、Host、时钟和 Archive 的实现边界 | [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| 页面状态、API 接缝、文案和响应式要求 | [`FRONTEND.md`](FRONTEND.md) |
| 本地启动、隔离资源、Hermes、清理和检查命令 | [`OPERATIONS.md`](OPERATIONS.md) |
| 当前验收结论、证据分层和已知边界 | [`ACCEPTANCE.md`](ACCEPTANCE.md) |
| 史料来源、证据状态和 Perspective 规则 | [`HISTORY.md`](HISTORY.md) |
| 南京定策的史料与内容契约 | [`NANJING_SUCCESSION_RESEARCH.md`](NANJING_SUCCESSION_RESEARCH.md) |

## 阅读顺序

1. 先读根目录 [`README.md`](../README.md)，完成本地启动。
2. 再读 [`PRODUCT.md`](../PRODUCT.md)，理解用户旅程和产品边界。
3. 需要开发或排障时读架构、前端和运维文档。
4. 需要核对“完成”时读 [`ACCEPTANCE.md`](ACCEPTANCE.md)，不要把单个测试、浏览器检查或一次模型运行扩大解释。

## 文档维护规则

- 当前文档描述现在的代码和产品，不用历史版本名称组织章节。
- 阶段计划、迁移记录、旧验收和一次性 spike 进入归档后不再作为当前实现的规范来源。
- 每条“已支持”“已通过”“已清理”都必须能在源码、测试、运行记录或可读工件中复核；真人主观反馈没有收集时必须明确写出。
- 不在仓库保存 API key、Profile token、完整模型响应、private prompt 或临时运行数据库。
- 文档链接以当前文件为准；移动历史文件时同时修正相对链接，并运行链接检查。

历史目录和保留理由见 [`archive/README.md`](archive/README.md)。
