# Chronicle · 甲申 V5

> 一个卷册，几段人生；每个人只活在自己收到的世界里。

Chronicle V5 把一段历史做成可回到的卷册：先看同一世界，再跟随其中一段已经发生过的人生；进入时只接过当前 Life 的下一步，离席后卷册继续推进，最终在结构性边界处封存并回看。

正式产品旅程是：

```text
Volume → World → Follow → Inhabit → Life Desk → Leave → Archive / Volume Ending
```

当前默认内容是 `jiashen` Volume「甲申」，包含 6 条 Volume Lifetime 和 3 个 Crisis knot。Crisis 是同一卷册中的局部因果密度，不再是正式产品的根目录。

## 当前状态

Phase 0–11 已按 V5 计划完成并分别提交；当前仓库已经有 V5 Volume、Global World Tick、Lifetime、Inhabit/Leave、Pending Logical Moment、Volume Boundary、Archive 和 Volume Ending 的 fixture/API 合同。Phase 12 的 Acceptance 与文档在 [V5 验收记录](docs/V5_ACCEPTANCE.md) 中逐项区分证据层。

这不等于“V5 的真实 Hermes 产品证明已经完成”。当前可以确认：

- Source Pack、Scenario Pack、Volume Pack、Python/JS 静态检查和确定性测试通过；
- 隔离临时目录中，Hermes v0.20.0 可以 materialize 6 个 Lifetime Profile，并通过私有 Gateway、Profile 路由、fresh Session 和真实 V5 `logical_intent` Wake 提交到原子 Logical Moment；
- 当前已验证一条真实 V5 Agent Wake 和 product router 的 live continue，但尚未完成跨 Human/Hermes、跨 Subject、学习、长期 Knot 和产品试玩证明；
- P0–P5 行为性验收、新 Archive/Ending 浏览器流程和 1440/1280/768/390 响应式证据尚未通过，因此不宣称 Definition of Done。

## 用户看到什么

| 入口 | 用户要回答的问题 |
| --- | --- |
| Volume | 这卷历史从哪里展开？ |
| World | 此刻哪些局势正在变得重要？ |
| Follow | 如果只跟着这段人生，我能看到什么？ |
| Inhabit | 我是否要接过这段人生的下一步？ |
| Life Desk | 当前人物收到什么、知道什么、还承担什么？ |
| Leave | 我是否把这段人生交还给世界？ |
| Archive / Volume Ending | 这卷历史如何结束，又如何回看？ |

用户不需要理解 Profile、Wake、Session、Memory 或 Runtime。它们是执行边界，不是页面心智模型。

## 本地运行

先做不触碰业务状态的确定性检查：

```bash
uv sync
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
uv run pytest -q
uv run ruff check .
node --check web/app.js
node --check web/router.js
node --check web/state.js
git diff --check
```

开发模式只在明确的临时数据库中开放 fixture：

```bash
CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL=sqlite:////tmp/chronicle-v5-dev.db \
CHRONICLE_HERMES_HOME=/tmp/chronicle-v5-hermes-home \
uv run chronicle serve --host 127.0.0.1 --port 8711
```

正式页面向 `POST /api/worldlines` 发送 `live: true`；开发模式才发送 `live: false`。不要把开发数据库、Hermes Home 或含 Secret 的 runtime 文件提交到 Git。`chronicle` 当前只允许 loopback 绑定，没有登录层，不要暴露到局域网或公网。

## V5 API 入口

正式 V5 API 使用 `/api/worldlines`，并以 Volume Worldline 为根：

```text
POST /api/worldlines
GET  /api/worldlines/active
GET  /api/worldlines
GET  /api/worldlines/{id}/world
GET  /api/worldlines/{id}/lifetimes
GET  /api/worldlines/{id}/follow/{lifetime_id}
GET  /api/worldlines/{id}/desk
POST /api/worldlines/{id}/inhabit
POST /api/worldlines/{id}/leave
POST /api/worldlines/{id}/continue
POST /api/worldlines/{id}/decision
GET  /api/worldlines/{id}/archive[?lifetime_id=...]
POST /api/worldlines/{id}/seal
```

`/world` 与 `/follow` 是公共可见投影；`/desk` 只返回当前 inhabited Lifetime 的私有上下文；Archive 默认只返回安全的公共回看，只有明确选择一个 Lifetime 时才增加该 Lifetime 的 selected replay。未送达消息、其他 Lifetime 的私有计划/信念和 Profile/runtime 内部字段不应通过产品 API 泄漏。

## 兼容边界

旧 `/api/runs`、`entry_id` 分支和 V4 Compare/legacy replay 仍保留用于已有数据和回归；它们不是 V5 产品 source of truth。V5 新建请求不应再以 Crisis/Run/Takeover 作为产品入口。迁移约束见 [V5 Migration](docs/V5_MIGRATION.md)。

## 证据边界

fixture、自动化测试、浏览器检查、Doctor、Hermes readiness 和真实业务 Run 是不同证据层：

- 测试通过只证明当前代码合同和失败路径；
- Doctor/Probe 只证明环境或路由可用；
- 浏览器截图只证明当时页面状态；
- 真实 chat preflight 不等于 V5 Subject continuity；
- 只有同一 live V5 Run 中可关联的 Profile、fresh Session、Perspective、World operation、消息因果、后续 Wake、Archive 和清理，才可支持真实产品结论。

完整矩阵、当前 blocker 和本轮命令证据见 [docs/V5_ACCEPTANCE.md](docs/V5_ACCEPTANCE.md)。

## 文档导航

| 目标 | 文档 |
| --- | --- |
| 产品旅程和范围 | [PRODUCT.md](PRODUCT.md) |
| Volume/Lifetime/Host/Archive 架构 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 页面、文案、隐私和 API 接缝 | [docs/FRONTEND.md](docs/FRONTEND.md) |
| 启动、隔离、迁移和排障 | [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| V5 验收矩阵与证据边界 | [docs/V5_ACCEPTANCE.md](docs/V5_ACCEPTANCE.md) |
| V5 迁移原则 | [docs/V5_MIGRATION.md](docs/V5_MIGRATION.md) |
| 历史来源与信息盲区 | [docs/HISTORY.md](docs/HISTORY.md) |
