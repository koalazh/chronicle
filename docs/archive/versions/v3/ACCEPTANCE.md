# Chronicle V3 验收记录

> 历史归档。当前验收见 [`../../../ACCEPTANCE.md`](../../../ACCEPTANCE.md)；本文保留当时的现场证据和限制，不代表当前状态。

> 记录日期：2026-08-10。本文保留当时工作树中可以复核的检查、工件和边界；不记录 Provider API Key、World token 或完整模型正文。

> 第 4、5 节保留的是自动运行时引入前的现场取证，其中“手动启动”只说明当时的证据顺序，不是当前产品步骤。当前使用与恢复流程以 [运维](../../../OPERATIONS.md) 为准；自动生命周期尚未在本记录中获得新的真实 Provider 验收。

## 结论

V3 的本地确定性合同、中文页面旅程、Hermes 前置能力和一条同 Run 的 live Watch 业务链均有证据。这个结论不表示 Chronicle 已成为通用历史模拟器，也不包含山海关大规模战役结算、远程认证或多租户部署。

“完成”只表示下列证据同时存在；fixture、浏览器、Doctor 和 live business Run 不互相替代。

## 证据分层

| 层级 | 可以证明 | 不能单独证明 |
| --- | --- | --- |
| 内容与自动化 | Crisis/Source Pack、Host、API、迁移、权限、前端状态和失败路径符合测试合同 | Provider 响应或真实 Agent 业务成功 |
| 浏览器 | 当前版本页面可达、状态可读、布局和交互在指定视口成立 | Hermes Profile、MCP、Ledger 或消息送达 |
| Doctor | 当前 Gateway、Profile 路由、密钥隔离、MCP discovery、数据库/调度前置一致 | 一次 Wake 是否作出正确业务决定 |
| live business Run | 同一 Run 中的真实 Profile、fresh Session、World tools、Life State、后续 Wake、delivery、Replay 和 seal 能关联 | 其他 Provider、故障组合或历史争议已被穷尽 |

## 1. 可重复的本地检查

在当前工作树运行：

```text
uv run chronicle source validate
  Source Pack valid: 4 sources, 36 assertions, 36 events
uv run chronicle scenario validate
  Scenario valid: 3 Seats, 10 locations, 7 routes, fork=jiangnan-prince-command
uv run chronicle crisis validate
  Crisis Pack valid: 3 actors, 5 sources, 14 assertions, horizon 30 days
uv run pytest -q
  118 passed
uv run ruff check .
  All checks passed
node --check web/app.js
git diff --check
  exit 0
```

`scenario validate` 仍检查 V1/V2 Source Pack，`crisis validate` 检查 V3 Crisis Pack。三类 validator、测试、lint、JS 语法和 diff 检查说明本地合同成立，不说明 Provider 已响应。

## 2. 迁移副本

迁移验收针对旧库副本，不写入原始用户数据库。备份后缀取决于源 schema：v1→`.pre-v2.*`、v2→`.pre-v3.*`、v3→`.pre-v4.*`、v4/v5/v6→`.pre-v7.*`；一次打开只留下本次跨级迁移最早生成的那份 backup。

现场的 schema v2 副本包含一个 ACTIVE Canon 和一个已封存 Human Branch。副本先记录 SHA-256，再复制到 `/tmp` 并加入 sentinel 扩展表；打开后生成 `.pre-v3.*`，迁移到 schema v7，sentinel 表、未知表和旧数据仍存在，第二次打开保持 v7 且不重复迁移。这个副本不作为 `LEGACY_V2_SEALED` 的证据。

另一个从 schema v4 开始、含 ACTIVE `BRANCH` 的独立副本用于验证 legacy seal：打开时生成 `.pre-v7.*`，把该 Branch 和其 lifetime 封存，写入 `LEGACY_V2_SEALED`，并明确 `resumable_as_v3=false`。两组证据分别证明备份/未知表保留和 active V2 退出正式路径。

## 3. 浏览器与页面旅程

当前静态资源版本为 `web/app.js?v=20260810-v3-completion`。最终工件位于 `artifacts/v3-qa/`：`v3-completion-desk-1440.png`、`v3-completion-desk-records-1440.png`、`v3-completion-desk-390.png`、`v3-completion-desk-records-390.png`、`v3-completion-replay-1440.png`、`v3-completion-replay-390.png`。

在 1440、1280、768、390 宽度检查到：首页可到 Watch 和 Takeover，封存可到 Replay，Archive、History、Setup 均可达；桌面 Corridor 横向、390 宽度纵向，横向 overflow 为 0；Takeover 四个 Desk 区域持久存在，手机记录为单列；Watch Replay 默认“封存后全景”，Takeover Replay 默认“当时可见”；全景包含三位主体，当时视角不泄漏其他主体私下决定；主产品页面没有 Profile、Wake、Session、Memory、Worldline 等内部词。

此前修复过一个真实页面错误：决定按钮先 busy rerender，导致 textarea 被清空成 silence。当前 handler 在 rerender 前捕获文本，多动作决定可以把模拟日从 0 推进到 1。浏览器证据只证明当时本地 API/fixture 下的页面状态。

## 4. Doctor 前置能力

现场使用项目私有 Hermes Gateway v0.20.0、multiplex mode，在隔离 live Run 数据库上运行 `chronicle doctor` 得到 `READY`。结果包括：三个 Run-scoped Profile route 均为 200；有效 Profile key 为 200，cross-profile key 为 401；`/v1/toolsets` 对三个 Profile 都只报告 builtin `memory`；每个 Profile 都配置不同的 identity-specific World MCP；`hermes mcp test` 对三个 MCP 都发现且只发现四个工具：`act`、`communicate`、`schedule_followup`、`update_plan`。

同一 Doctor 检查还确认 schema v7、Profile identity、binding、非空唯一 token hash、genesis marker、initial Memory、runtime epoch、Wake/Session 与 Ledger/Snapshot 一致；没有 RUNNING/STAGED/FAILED Wake；Commitment 与 `COMMITMENT_DUE` Wake 在 actor/tick/trigger/status 上对应。`READY` 只证明能力、配置和隔离前置条件。

## 5. 同一 live Watch Run 的业务链

业务证据来自隔离临时数据库：`/tmp/chronicle-v3-complete.cMFT2Q/live.db`，Run 为 `run-11963d5f094b45b4`。该路径是现场取证位置，不是提交到仓库的用户数据。

运行顺序是“停止旧 Gateway → 创建 Run → 启动 Gateway → Doctor READY → 继续”。Run 从 tick 0 自然推进到边界前 tick 8，没有 SQL 改写、状态重置、Wake 重跑或 fixture fallback。

- 3 个独立 Agent Profile，30 个完成 Wake：3 `ORIENT`、8 `MESSAGE`、16 `COMMITMENT_DUE`、3 `REFLECTION`，全部 `source=hermes`；
- 30 个非空且互不相同的 fresh Session，Ledger 有 30 个对应完成事件；
- 118 次 World tool 尝试：65 `COMMITTED`、53 `REJECTED`；25 个 Wake 在拒绝后继续产生有效提交；
- 24 次 Plan update、16 个 Commitment、4 个合法 no-op；scheduler 只跳到消息、承诺和 Reflection 的第 1、3、4、5、6、7、8 日，没有 heartbeat；
- 2 封初始信和 6 封 Agent 新信完成真实投递，最短 transit 为 2 模拟日，没有同 tick 递归投递；
- 3 个 Reflection 使用 fresh Session，并合法选择 `NO_CHANGE`；三位主体各有 genesis Memory lineage；
- Replay 产生 94 个唯一产品事件，其中 90 个有自然语言 cause、89 条 parent edge 可解析；
- 存在 4 条可解析的“Plan → 发信 → 收信 → 收信人改 Plan”链，覆盖吴→李、多→吴、吴→多；
- Run 结果为 `SEALED`，3 条 Agent binding 均为 `REVOKED`。

这条链证明的是当前 Hermes/provider/config/version 下，Profile、Session、World tools、Ledger、Life State、simulated time、delivery 和 perspective isolation 能在同一业务对象上关联，不是证明所有模型在所有条件下都会作出相同选择。

## 6. 已知边界

- 当前只实现 `before-shanhaiguan` Crisis Pack；其 curated Resolution 只结算该危局的局部结果，30 日仅为内部 Safety Horizon，抵达时会产生延期 Outcome；
- SQLite/loopback 是本地单用户边界，没有远程认证或多租户合同；
- V1/V2 API 和存储是 legacy 兼容面，不是 V3 正式产品路径；
- Starlette TestClient 和 Pydantic settings 在当前依赖组合下各有一条第三方 warning；118 个测试与 lint/build checks 通过，但 warning 没有被误报为已消除；
- live 证据绑定到当时的 Provider、Hermes、模型和配置版本，换环境后必须重新取证。
