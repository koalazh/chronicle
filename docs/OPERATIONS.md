# Chronicle V3 运维与验收

这是本地 runbook。先把服务安全地跑起来，再分别验证确定性合同、fixture、Doctor、浏览器和真实业务；健康检查从来不等于业务成功。

## 1. 安全边界

- Chronicle 只绑定 `127.0.0.1`、`::1` 或 `localhost`；当前没有登录层，不得暴露到局域网或公网；
- Provider URL 不得嵌入凭据，不得指向私网、metadata、link-local、保留或组播地址；远程 Provider 必须使用 HTTPS；
- Secret 只写入被忽略且权限为 `0600` 的 `.chronicle/runtime.env`、Profile `.env` 和项目私有 Hermes Home；
- 不提交 `.env`、`.chronicle/`、SQLite、完整模型正文、Profile 私钥或带凭据的日志；
- 迁移和试验使用副本或新路径，不删除真实数据库或 Hermes Home 来“重置”。

## 2. 确定性检查

修改源码、Scenario 或前端后运行：

```bash
uv sync
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
uv run pytest -q
uv run ruff check .
node --check web/app.js
git diff --check
```

启动正式体验：

```bash
uv run chronicle start
```

服务默认在 <http://127.0.0.1:8711>。`start` 会在页面服务启动时恢复同一局的本地运行资源；`serve` 仅用于开发，不承担这次启动时恢复。设置页的“保存并核对”先请求 Provider 的 `/models`，通过后才把配置写入 runtime env；原始 API Key 不回显。正式页面只创建 live Run，不能把未配置或失败的 live 请求静默改成 fixture。

## 3. 正常使用的本地生命周期

用户只需要运行 `uv run chronicle start` 并打开页面。创建 live Run 时，Chronicle 先持久化同一局的历史和主体身份，再建立该局的 Profile、写入当前局唯一的 MCP allowlist、启动项目私有 Gateway child，并完成初始 `ORIENT`。只有 `ORIENT` 已提交真实 World operation，页面才把这一局显示为可继续。

重启后，`start` 只恢复尚未封存的同一局；它不会新建 Profile、Wake、epoch 或复制旧 Session。运行资源的唯一持久化状态是下列 `runtime_phase`；Run 的历史状态仍然只有 `ACTIVE` 或 `SEALED`。

| 阶段 | 用户看到什么 | 系统做什么 |
| --- | --- | --- |
| `BOOTSTRAPPING` | 正在建立主体 | 验证或补齐同一局的资源，尚不允许推进或落笔。 |
| `READY` | 可以继续或落笔 | binding、初始行动和项目私有 child 都已通过当前局的核验。 |
| `RECONCILING` | 正在恢复这一局 | 重启后只核验同一局；未确认的运行中 Wake 不会盲目重投。 |
| `FAILED` | 可以重新准备或封存 | 保留同一局和无密钥失败码，不新建身份；无法核对的 Wake 只允许封存，不会重投。 |
| `SEALING` | 正在封存卷册 | 等待正在结束的时刻终结，拒绝新的写入。 |
| `CLEANUP_PENDING` | 已封存，可回看 | binding 已原子撤销；本地资源清理可安全重试。空失败码表示已经收束。 |

封存的原子边界先写入历史 seal、封存 Life State、撤销 binding 并取消尚未开始的 Wake；然后才停止 child、移除本局 root MCP/env 条目和带归属 marker 的 Profile。清理失败不会让旧主体回到新局 allowlist；下一次 `start` 或新开局前会重试。想重新选择时，先封存上一局，再创建全新的 Run/Profile/epoch，不能重入旧主体。

封存请求会立即打开回看；如果本地资源仍处于 `CLEANUP_PENDING`，封存卷册和回看页都提供“再次收束”，不会把清理失败藏在页面之外。

Chronicle 只复用或停止同时满足 owner record、项目私有 Hermes Home 的 PID metadata、进程启动时间和当前配置指纹的 child。记录不含密钥。任何一项无法确认、PID 已复用或端口被未知服务占用时，系统会失败关闭：不接管、不停止、不覆盖未知服务，并在页面保留“重新准备”入口。

## 4. 诊断与真实业务证据

`uv run chronicle doctor` 是故障诊断，不是正常页面流程的一步。它检查 Source、Scenario、Crisis Pack、数据库、Profile identity、密钥隔离和基础 Gateway/Profile 路由；它可以帮助定位配置问题，但不能替代当前 child 的业务调用证明。

运行时的 `READY` 比 Doctor 更窄也更实际：它要求当前局初始 `ORIENT` 已经留下 `update_plan` 的 committed World operation。这样可以阻止 memory-only 会话被当作成功启动。它仍不证明后续消息送达、长期推进或最终封存已经完成。

## 5. 数据迁移

schema v8 是 additive migration。对已有数据库，backup 后缀按源版本选择：v1→`.pre-v2.*`、v2→`.pre-v3.*`、v3→`.pre-v4.*`、v4/v5/v6→`.pre-v7.*`、v7→`.pre-v8.*`。系统保留已知和未知旧表，只有 `kind='BRANCH'` 且 `status='ACTIVE'` 的旧 V2 Worldline 才会封存为 `LEGACY_V2_SEALED`，ACTIVE Canon 不会被封存。v8 为 Crisis Run 增加无密钥的运行阶段和失败码；迁移到 v8 的旧 live Run 会在下一次 `start` 时重新核验或清理，不会被静默当作已就绪。

验证迁移时先复制数据库：

```bash
CHRONICLE_DATABASE_URL=sqlite:////absolute/copy.db uv run chronicle doctor
```

检查 backup、legacy seal、未知表和第二次打开的幂等性。不要在真实用户数据库上用 SQL 改写状态来制造验收结果。

## 6. Fixture 烟测

fixture 只在 `CHRONICLE_DEV=1` 的开发/自动化环境开放，只替代模型输出，不替代 scheduler、WorldService、Ledger、Life State 或权限校验。

最小 smoke 应覆盖：创建 `WATCH` fixture Run；连续调用 `/api/runs/{id}/continue`，确认无 trigger 不 Wake、未来 Commitment 会到期、信件会抵达；切换三位主体 perspective，确认未送达信息不泄漏；创建 fixture Takeover，确认活动期间 `/world` 和其他主体 perspective 返回 403；提交多动作决定和空文本沉默；seal 后读取 Replay、Archive 和 History。

fixture 通过只能写成“确定性合同通过”，不能写成“真实 Hermes 已通过”。

## 7. 真实业务验收

真实验收使用隔离的临时 SQLite，不覆盖用户数据。必须在同一 live Watch Run 中关联三条 identity binding、三个 Agent Profile、`ORIENT` 与后续 Wake 的 fresh Session、真实 World MCP 请求及其 operation/Ledger 记录、Plan/Commitment/Memory lineage、消息 transit 与 delivery、拒绝后修正或合法 no-op、cross-profile key/perspective isolation，以及 seal 后的 binding revocation 和 Replay/Archive。

健康探针、Doctor、fixture、截图和一段模型最终文本都不能替代这条关联链。安全报告只记录 Run ID、Profile 名、Session 是否独立、工具名、事件类型、tick、状态和计数，不记录 token、API Key 或完整模型正文。

## 8. 浏览器验收

至少检查 1440、1280、768 和 390 宽度：首页、Watch、Takeover Desk、回看、卷册、史实背景和设置均可达；桌面 Corridor 横向、手机 Corridor 纵向，无横向溢出；Takeover 文本在 busy rerender 前被捕获，多动作不会变成 silence；活动 Takeover 不显示世界全局或其他主体私态；Desk 四个区域持久可见，手机为单列；回看默认 lens、自然语言 cause、console 和内部词泄漏符合 [前端合同](FRONTEND.md)。

截图只证明当时本地 API/fixture 下的视觉与交互。业务证据和已知边界见 [验收记录](ACCEPTANCE.md)。
