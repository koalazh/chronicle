# Chronicle V5 运维与验收

这是 V5 的本地 runbook。它把“服务能启动”“代码合同通过”“Hermes 环境可用”“真实 V5 业务成立”和“浏览器体验合格”分开记录。任何一层都不能替代另一层。

## 1. 安全边界

- 只绑定 `127.0.0.1`、`localhost` 或其他明确的 loopback 地址；当前没有登录层，不得暴露到局域网或公网；
- Provider URL 不嵌入凭据，不指向私网、link-local、metadata、reserved 或 multicast 地址；
- API Key 只写入被忽略且权限为 `0600` 的 runtime env/Profile env；日志和文档不记录 key、token、完整模型正文或 private response；
- V5 live acceptance 使用新临时 SQLite、新 Hermes Home 和独立 loopback 端口；不覆盖项目 `data/`、`.chronicle/`、全局 Hermes Home 或其他正在运行的服务；
- 不用 SQL 直接制造 `SEALED`、`READY` 或 successful outcome；不以删除目录“修复”未知归属；
- Profile/MCP/Gateway 清理只能在 Volume 已原子 seal 且 marker/owner 可证明属于该 Worldline 时执行。

## 2. 确定性检查

每次源码、内容或前端变更后先运行：

```bash
uv sync
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests
node --check web/app.js
node --check web/router.js
node --check web/state.js
git diff --check
```

本轮结果：Source Pack `4 sources / 36 assertions / 36 events`、Scenario Pack `36 canon events`、`jiashen` Volume `3 crises` 通过；完整 pytest、ruff、compileall、JS syntax 和 diff check 通过。测试中的依赖 deprecation warnings 不被升级成 V5 failure，但也不隐藏。

## 3. 本地服务与 fixture

CLI 入口：

```bash
uv run chronicle --help
uv run chronicle serve --host 127.0.0.1 --port 8711
uv run chronicle start --host 127.0.0.1 --port 8711
uv run chronicle doctor
```

`serve` 适合开发；`start` 保留启动时的旧兼容 runtime reconcile 行为。二者都只绑定 loopback。V5 页面通过 `/api/worldlines` 工作，正式环境要求 `live: true`；只有 `CHRONICLE_DEV=true` 才允许 `live: false` fixture 创建。

开发 fixture 必须使用临时状态：

```bash
V5_TMP="$(mktemp -d -t chronicle-v5-dev.XXXXXX)"
CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$V5_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$V5_TMP/hermes-home" \
uv run chronicle serve --host 127.0.0.1 --port 18711
```

fixture 只能替代模型输出；它仍必须走 Host、Global Tick、message delivery、Perspective、Pending Logical Moment、permission、idempotency、Ledger 和 Archive 代码。关闭服务后只清理由当前命令创建的临时目录，不删除广泛路径。

## 4. 当前 V5 live 边界

当前 `POST /api/worldlines` 的 `live: true` 路径会执行 Lifetime Profile materialization、绑定每个 Profile 的 World token、启动/复用私有 Gateway，并在真实 Agent Wake 中使用 fresh Session 和 Profile 专属 `logical_intent` MCP staging；随后由 V5 Host 完成 Pending Logical Moment 的 atomic commit。普通 Wake 的 Memory mutation 会 rollback，非结构化模型输出不会自动降级为 `wait`。这条最小链路已有单 Wake live 证据，但完整 P0–P5 仍未通过。

因此下面三件事必须分开：

| 检查 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| `chronicle doctor` | 配置、素材、数据库、Hermes CLI 和前置路由状态 | 一次 V5 业务因果链 |
| Hermes Probe / direct chat | Gateway、Profile、key isolation、fresh Session 和真实模型调用 | Human↔Hermes continuity、完整 Worldline 因果、P0–P5 |
| fixture/API tests | Host/DB/隐私/时钟/封存合同 | 真实模型是否产生正确主体行为 |

`chronicle start` 的旧 `LiveRuntimeManager` 不应被当作 V5 live bridge；V4 compatibility path 和 V5 product path 目前仍需分别验收。

## 5. 实际 preflight 记录（2026-08-12）

在独立临时 SQLite、临时 Hermes Home、`127.0.0.1:18642` 上执行了真实 Hermes preflight：

- 运行环境：Hermes Agent v0.20.0；
- V5 `live` 创建 materialized 6 个 Lifetime Profile；
- 私有 Gateway health：通过；
- 6 个 Profile route：均返回 `200`；
- 6 个 Profile toolset：均为 `memory`；
- valid Profile key：`200`；cross-profile key：`401`；
- fresh Session：成功；真实 chat：成功（只记录摘要 hash，不保存正文）；
- 项目工作树、项目数据库和默认 Hermes Home：未作为目标；
- V5 Wake：真实 Profile 通过 `logical_intent` MCP staging 一个意图，随后产生 `MOMENT_COMMITTED`；Gateway teardown 在定向校验 owner/PID 起始标识后 clean PASS。

这是一条真实 V5 最小业务链证据，不是完整 V5 live acceptance。后续隔离运行已补充 P0 正向候选、P2 延迟消息候选和同一 Knot 的 12 条 Hermes Wake 小样本：同一 Wu Profile 的 fresh Session handoff、A 先发消息/B 先决策/消息抵达后重新行动、tick 10 多主体不同计划，以及 `update_plan`/`message` 行为分布；但它们仍不能替代 P1/P3/P4/P5 的完整 proof。

## 6. Volume 运行生命周期

```text
VOLUME ACTIVE
  → Crisis Instance SETTLED/SUPPRESSED（Volume 仍 ACTIVE）
  → structural boundary ready
  → VOLUME_SEALED / ARCHIVED
  → revoke bindings + cancel queued wakes
  → cleanup owned Profiles/MCP entries
```

封存前必须通过 boundary policy：没有 pending moment、due wake、在途消息、待应用 Field Event 或 next tick，且所有 Crisis Instance 已有结果。Seal 失败只返回领域冲突，不改变状态。Seal 后的重复请求应为 idempotent，并只重试属于本卷册的清理。

如果清理失败：

1. 保留 sealed Worldline、Ledger、Snapshot 和 Archive；
2. 不把旧 Profile 加入下一卷册；
3. 记录可重试的 owner/cleanup 状态，不猜测未知进程归属；
4. 下一次明确的 recovery 操作只针对同一 Worldline。

## 7. 迁移与数据库

当前 schema version 为 `10`。V5 migration 继续 additive、先备份、保留未知表和旧字段；旧 V3/V4 Crisis 只走 legacy archive/replay，不热迁移成 V5 Volume。

对副本做检查：

```bash
CHRONICLE_DATABASE_URL=sqlite:////absolute/copy.db \
CHRONICLE_HERMES_HOME=/absolute/temp/hermes-home \
uv run chronicle doctor
```

不要在真实数据库上直接改 `status`、`runtime_phase`、`outcome_json` 或 binding 来制造验收结果。迁移规则、旧数据边界和 repeat-open 约束见 [V5_MIGRATION.md](V5_MIGRATION.md)。

## 8. 浏览器检查

浏览器验收至少覆盖 1440、1280、768 和 390 宽度：

- Volume、World、Follow、Inhabit、Desk、Leave、Archive、Ending 都能到达；
- 无横向溢出，World/Follow/Desk/Archive 在手机可读；
- Follow 和 public replay 不泄漏 private state；
- textarea 在 rerender 前被捕获，busy mutation 不能 double-submit；
- 页面不出现 Agent/Profile/Session/Memory、crisis dashboard、meter 或 AI thinking animation。

Phase 10 已有一条隔离浏览器流程，覆盖 V5 shell 的首页、World、Follow、Inhabit、Desk、Continue、Decision、Leave。2026-08-12 又在独立 fixture SQLite 上复核了 Phase 11 Archive/Ending：unsealed/sealed 两态、Archive → Public Replay → 明确选择 Lifetime Replay，以及 1440/1280/768/390 四种 viewport；检查记录了 no-overflow、按钮可聚焦/有可访问名称和空 dev logs。该证据仍是 fixture/API 的 UI proof，不替代真实 live API 下的最终状态表现，完整 P0–P5 仍未通过，详见 [V5_ACCEPTANCE.md](V5_ACCEPTANCE.md)。

## 9. 证据归档

每次 acceptance 记录只保留可复核且不含 Secret 的信息：commit、命令、退出码、validator 摘要、临时资源范围、Profile/Session 数量、事件类型、tick、状态和失败边界。不要保存 API key、Profile token、完整模型 response、private prompt 或原始 `runtime.env`。

逐项矩阵和 P0–P5 当前结果见 [docs/V5_ACCEPTANCE.md](V5_ACCEPTANCE.md)。
