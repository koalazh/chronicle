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

启动页面：

```bash
uv run chronicle serve
```

服务默认在 <http://127.0.0.1:8711>。设置页的“保存并核对”先请求 Provider 的 `/models`，通过后才把配置写入 runtime env；原始 API Key 不回显。正式页面只创建 live Run，不能把未配置或失败的 live 请求静默改成 fixture。

## 3. 真实 Hermes 的启动顺序

V3 创建 live Run 时会立即创建该局所需的 Run-scoped Profiles，并为每个 Agent-controlled Actor 排入 `ORIENT` Wake。Gateway 必须在 Profile 注册写入项目私有 Home 之后启动，因此顺序固定为：

1. 找到并停止旧的项目私有 Gateway；未知或全局进程不要直接终止；
2. 在页面创建 live Watch 或 Takeover；
3. 使用项目私有 Hermes Home 启动 Gateway，使它加载本局 Profile/MCP 注册；
4. 运行 `uv run chronicle doctor`，确认状态为 `READY`；
5. 回到页面点击“继续”。

命令示例：

```bash
HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes gateway run --external-supervisor --accept-hooks
```

V3 不需要先运行旧 `bootstrap` 才能创建危局主体；`bootstrap` 只服务 legacy Profile 初始化路径。停止旧 Gateway 前先用 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 识别进程归属，未知服务保持不动。

## 4. READY 到底证明什么

对当前 live Run，`READY` 至少检查：Source、Scenario、Crisis Pack 和 schema v7 可加载；Snapshot tick/hash 与 Ledger cursor 对齐；每个 Agent binding 都对应存在的 Profile；Profile identity、Run/Actor marker、唯一 token hash、Memory lineage 与 Life State 对齐；没有 RUNNING/STAGED/FAILED Wake；已完成 Wake 的 Session 非空且唯一；Gateway health、Profile route、cross-profile key isolation 和四工具 MCP discovery 通过；Commitment 与 `COMMITMENT_DUE` Wake 一一对应。

`/v1/toolsets` 只报告 builtin `memory`，不能代替 `hermes mcp test`。READY 是能力与隔离前置条件，不证明任何一次 Agent Wake 已经完成，也不证明消息已经送达或 Run 已正确封存。

## 5. 数据迁移

schema v7 是 additive migration。对已有数据库，backup 后缀按源版本选择：v1→`.pre-v2.*`、v2→`.pre-v3.*`、v3→`.pre-v4.*`、v4/v5/v6→`.pre-v7.*`；系统保留已知和未知旧表，只有 `kind='BRANCH'` 且 `status='ACTIVE'` 的旧 V2 Worldline 才会封存为 `LEGACY_V2_SEALED`，ACTIVE Canon 不会被封存。随后增加 V3 Run/Wake/operation/Life State/binding revocation 结构，并建立“最多一个 active playable Run”的约束。

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
