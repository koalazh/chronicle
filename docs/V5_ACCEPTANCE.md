# Chronicle V5 Acceptance Record

> 记录日期：2026-08-12
> 分支：`dev_v5`
> 状态：**CANDIDATE — P5 与完整 live V5 业务链已形成；正式 Completion Challenge 待执行**

本文是 V5 的唯一当前验收记录。它只记录已经执行、可以复核、没有泄漏 Secret 的证据；`PASS` 只对对应证据层有效，不向上推导为整卷产品完成。当前候选基于 `c4b962f` 及其后的前端错误文案修复；在正式 Completion Challenge 通过前，不把候选写成最终完成。

## 1. 目标链路

V5 Definition of Done 要求同一条 Volume Worldline 真实完成：

```text
Volume
→ multiple persistent Lifetimes
→ Human inhabits one Life
→ other Lifetimes continue
→ Leave
→ same Lifetime continues under Hermes
→ past evidence changes later action
→ independent Subjects form different expectations/actions
→ Crisis results propagate through real World objects
→ another Life can be entered later
→ Volume boundary
→ Archive / Volume Ending
→ only then revoke and clean owned runtime resources
```

当前候选已在同一真实 V5 Volume 走通这条链，并保留了真实 Hermes 的等待、消息、调查、操作和边界结果；独立 evaluator 与正式 Completion Challenge 仍分别作为验收闸门记录。

## 2. Phase 证据

Phase 0–11 均已在 `dev_v5` 分别提交；Phase 12 的入口文档已由 `f52ddf9` 提交，随后以 `b287ee6` 接通最小 live Hermes Wake bridge；完整 proof gates 仍未完成：

| 阶段 | commit | 结果边界 |
| --- | --- | --- |
| 0 | `0f085bd` | baseline / migration boundary |
| 1 | `cc88750` | VolumePack / Lifetime source structure |
| 2 | `22ad7ff` | additive schema / Volume records |
| 3 | `b78dab1` | persistent Lifetime/Profile seam |
| 4 | `8f58cd3` | Inhabit/Leave controller boundary |
| 5 | `7a81ac5` | global Volume clock |
| 6 | `cfa5b35` | pending Logical Moment |
| 7 | `3a3f59e` | bounded subject continuity |
| 8 | `89c0625` | braiding / propagation structure |
| 9 | `ba6c530` | Volume Product API boundary |
| 10 | `3b3365d` | V5 product shell |
| 11 | `1ed13d5` | Archive / Volume Ending |
| 12 | `f52ddf9` + `b287ee6` + `a569344` + `c2b19a9` + `8c1241e` + `2c99332` + `b8f22a4` + `d2cbeac` + `c47edf4` + `52b687b` + `dc26345` + `b51a075` + `235927e` + `7cc1a25` + `1280457` + `1db1a38` + `d3a31a8` + `d5aa8d4` + `0d742fc` + `451f237` + `f21722b` + `c4b962f` + `443034a` + `554ba37` + `6c2ceee` | V5 source-of-truth docs、Hermes `logical_intent` Wake bridge、协议 fail-closed/repair、P0 controller/continuity 证据、Archive/Ending 浏览器 proof、Volume 世界工具与共享北方 transport 进入 Pending Logical Moment、Offer/Agreement wake 时序修复、MCP evidence schema 修复、对抗性边界测试、连续 live 记录、主体级 affordance 合同、离席后 Agent 接管 Pending Moment、exact Wake 路由和同一 Wake 单次 action guard、Crisis Envelope/restart reconcile、Controller Boundary public-trace exporter/evaluator、owned Gateway cleanup state normalization 以及两条 P5 live candidate；正式 Completion Challenge 待执行 |

Phase 0–11 的 commit scope、测试和边界记录同步在 task-loop `TASK.md`/`HANDOFF.md` 中；它们不替代本文件的 live proof。

## 3. 已通过的检查

### 3.1 Source / Scenario / Volume

以下命令在当前 checkout 退出码为 0：

```bash
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
```

当前摘要：

- Source Pack：`4 sources / 36 assertions / 36 events`；
- Scenario Pack：`36 canon events / fork=jiangnan-prince-command`；
- `jiashen` Volume：3 个 Crisis references；默认 Volume 有 6 条 Lifetime。

### 3.2 Automated / static

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests
node --check web/app.js
node --check web/router.js
node --check web/state.js
git diff --check
```

结果：全部通过；pytest 仅保留既有 Starlette/httpx、Pydantic 和 FastAPI deprecation warnings。测试覆盖的层级包括：

- Volume genesis、shared clock、Crisis Instance settlement；
- Inhabit/Leave 同一 Lifetime 的 controller 边界；
- Human/Agent Pending Logical Moment、intent staging、atomic commit 和 idempotency；
- message dispatch/delivery、later-known/unknown-at-time replay；
- public World/Follow/Desk 隐私过滤；
- boundary rejection、`n013` evidence、`VOLUME_SEALED`、binding revoke、queued wake cancel；
- fixture live-materialization/cleanup seam，确认 cleanup 只在 DB 已经 `SEALED` 后调用；
- Archive public replay 与 selected Lifetime replay privacy。

这些结果证明 deterministic contract，不证明真实模型产生了正确的主体行动。

## 4. 浏览器证据

### 已有证据：Phase 10 shell flow

在独立临时 SQLite 和本地 server 上验证过：

```text
homepage → World（初始 2 个 eligible knots；结算后第 3 个才进入）→ Follow Wu → Inhabit Desk
→ Continue pending → Decision/wait → Leave
```

当次 console errors 为 `[]`，页面保持纸本文书视觉。该证据只覆盖 Phase 10 flow 和当时的 viewport；它不覆盖 Phase 11 新增 Archive/Ending，也不覆盖四种响应式宽度。

### 已通过：Phase 11 Archive / Ending fixture 浏览器链路

2026-08-12 在独立临时 SQLite、Hermes Home 和 loopback server `127.0.0.1:18712` 上，以当前代码（含 `b8f22a4`）重新加载页面并验证：

- unsealed fixture：Archive 列表为空，Ending 显示“这一卷仍未走到边界。”；
- sealed fixture：tick `10`、3 个 Crisis 已 settlement、`n013` bridge 已落地、无 pending/in-transit work，Archive 列出 `jiashen / SEALED`；
- `打开回看` 打开 Public Replay；明确点击吴三桂的 `回看这段人生` 后才出现 `吴三桂 · 后知事实` 的 Lifetime Replay；
- sealed Ending 显示“这一卷已经成为过去。”，同时包含 Public Replay 与 Lifetime Replay；
- 1440、1280、768、390 四个 viewport 均满足 `document.scrollWidth == document.clientWidth` 与 `body.scrollWidth == document.clientWidth`（桌面端差异仅来自垂直滚动条）；
- 四种尺寸均捕获 Archive/Ending 截图；Ending 检查时 11 个按钮均可聚焦、有可访问名称、无 disabled mutation；浏览器 dev logs 为 `[]`。

该证据是 fixture/API 的产品 UI proof，不是真实 live Hermes cognition 或真实 live API acceptance。期间发现 sealed VOLUME 未被 `/api/worldlines` 列出，已以最小路由修复和回归测试提交 `b8f22a4`。

### 已复核：V5 shell 四尺寸与未封存边界

2026-08-12 在另一独立 fixture server `127.0.0.1:18780` 上重新检查 World、Follow、Desk、Ending 和未封存 Archive（本条的 `18780` 是 Chronicle HTTP server；后面的 P1 负向证据使用的是同号但不并行的 Hermes Gateway port）：

- 1440、1280、768、390 四种 viewport 均满足 `document.scrollWidth == window.innerWidth`；
- World、Follow、Desk、Ending、Archive 均可由页面路由到达；Follow/Desk/Ending/Archive 的可见文案没有 `Profile`、`Session`、`Memory`、`Agent is thinking`、`Wake queue` 或 `runtime phase`；
- Ending 正确显示“这一卷仍未走到边界。”，未封存 Archive 正确显示当前没有已封存卷册；
- 本轮 server、SQLite 与临时 runtime 已在检查后按精确 owner 停止并移出临时目录。

这仍是 fixture/API 的 UI proof；sealed live API 状态由后面的 `18734/18735` slice 单独证明。

### 可见文案泄漏修复复核：当前产品投影

2026-08-12 针对书案出现 `c002` 一类断言键的问题，在独立临时 fixture server `127.0.0.1:18860` 上重新加载当前工作树并扫描了 World、Follow、Life Desk、未封存 Archive、sealed Public Replay、显式 Lifetime Replay 和 Ending：

- Desk 的 arrivals、known、uncertainty、plan、obligations，以及 World 公共事实和 Follow 公开声明都经过产品可读文案投影；原始 assertion/message/observation/event 键不再作为可见文本的 fallback；
- sealed Public Replay 中由测试 settlement 摘要带入的 `before-shanhaiguan`、`nanjing-succession`、`southern-consolidation` 均显示为对应危局名称；Archive 状态显示为“卷册 / 已封存”，Ending 显示为“卷册边界”；
- 页面正文对 `c002`、`c003`、`c010`、`c011`、`c015`、上述 Crisis 键、`message_id`、`observation_id`、`event_id`、`volume_id`、`worldline-e` 等内部标识的扫描全部为空，浏览器 dev logs 为 `[]`；
- Archive 和 Life Desk 在 1440、1280、768、390 四种宽度下均满足 `scrollWidth == clientWidth == body.scrollWidth`；
- 该轮隔离 server、SQLite、runtime 和 Hermes Home 已在检查后按精确 owner 停止；用户正在使用的 `127.0.0.1:18850` 进程未被停止或覆盖。

该记录只证明普通用户页面与对应产品投影的可见文案边界；它不把内部数据库字段、真实 live Hermes cognition 或 P0–P5 主观验收提升为已通过。

### 真实 live Product Shell / API：port `18734`，Gateway `18735`

2026-08-12 在另一组隔离 SQLite、Hermes Home、runtime owner 和 loopback ports 上，以产品默认 `live=true` 走了真实浏览器链：

- 首页点击“开始这一卷”真实创建一个 VOLUME，并物化 6 个 Lifetime-scoped Hermes Profiles；浏览器页面只显示 Volume、World、Follow、Life Desk 等普通用户文案，没有 Agent/Profile/Session/Memory 内部术语；
- `Follow → Inhabit` 进入吴三桂的真实 Life Desk；tick 1 的真实 Human Wake 通过空白 wait 提交 `INTENT_COMMITTED → MOMENT_COMMITTED`，随后 Leave；
- 离席后真实 Hermes Profiles 在同一 Volume 继续：Dorgon tick 3、Wu tick 5、Dorgon tick 7、Wu tick 9 形成 fresh Session 与延迟消息；tick 9 historical Field 应用，tick 10 三个南方 Lifetime 收到跨 Knot 公开军情并分别选择 investigate / wait / operate，其中权限或可用性拒绝写成 `INTENT_REJECTED`，没有破坏 atomic Moment；
- 同一 live Worldline `worldline-52d33bd7ff68415c` 在本 slice 记录了 6 个 `MOMENT_FROZEN`、6 个 `MOMENT_COMMITTED`、8 个 `INTENT_COMMITTED`、9 个 `MESSAGE_DISPATCHED`、8 个 `MESSAGE_DELIVERED`，并在 tick 10 仍保持可继续的 ACTIVE Volume；第一 Crisis 在 Profiles 仍存活时 settlement，Worldline 继续保持 ACTIVE；随后两个 Crisis settlement、最后在途消息 delivery 和 boundary wait 将它推进到 tick 19；
- 新建的 fresh Browser tab 在 tick 10 能读到真实 World 页面；随后同一 live API 真实打开 Archive → Public Replay → 吴三桂 Lifetime Replay，四个 viewport 均无横向 overflow，浏览器 dev logs 为 `[]`。tick 19 的正式 `VOLUME_SEALED` 之后，6 个 bindings 变为 `REVOKED`、owned Profile 目录被清理、Gateway owner 被精确停止。

这条记录证明真实 live API 与用户可见 shell 已接通同一 Volume/Host/MCP 边界；它不把浏览器可见 tick 或一条 off-screen causal chain 误当成 P0–P5 全部通过。原运行资源在本记录完成后按精确 owner/runtime 归属停止并清理。

### 当前 P5 candidate：同一 live Volume `worldline-11646e76ec1f49b0`

2026-08-12 在独立临时 SQLite、Hermes Home、runtime owner 和 loopback ports `18830`（产品 server）/`18831`（Gateway）上，以真实产品页面完成了一条连续 Volume：

- 首页开始卷册后 materialize 6 个 Lifetime Profile；浏览器完成 World → Follow 吴三桂 → Inhabit → 等待世界推进 → Leave，离席后同一 Lifetime 继续由 fresh Hermes Session 接管；Follow 页面保留了离席期间的外部轨迹，重新进入同一 Life Desk 时可见新的跨时刻来书；
- tick 9 的 `north-south-recognition-bridge` 进入公共历史，tick 10 后史可法/马士英/韩赞周等南方主体获得跨 Knot 的公开军情；第一、第二 Crisis settlement 后 Volume 仍 ACTIVE，southern consolidation 在南京 settlement gate 满足后激活并完成；
- 同一 worldline 最终到 tick 16，三个 Crisis Instance 均 `SETTLED`（before-shanhaiguan、nanjing-succession 在 tick 14；southern-consolidation 在 tick 14），形成 `VOLUME_SEALED`；产品页面随后完成 Archive → Public Replay → 吴三桂 Lifetime Replay；
- 脱敏 SQLite 复核为：34 个 `COMPLETED` Subject Wake、12 个 `MOMENT_FROZEN`/12 个 `MOMENT_COMMITTED`、14 条 `MESSAGE_DISPATCHED`/14 条 `MESSAGE_DELIVERED`、3 次 `LIFETIME_INHABITED`/3 次 `LIFETIME_LEFT`、6/6 bindings `REVOKED`；seal 后 owned Profile 目录为空且 Gateway owner 文件消失；
- 运行中一次长时 provider 请求超过客户端等待上限，但数据库最终只保留对应的一次 atomic Moment/operation，没有把 timeout 当成成功；这作为 provider latency 边界保留在记录中；
- 运行中发现 no-due wake 时前端曾把 `there are no due Subject Wakes to freeze` 原文显示给用户。已在当前代码的 `web/api.js` 做内部错误中文化/未知英文错误降级，`tests/test_frontend_copy.py` 与 Node 行为检查均通过；该修复只改变错误投影，不改变 Host 状态机，未将原始英文泄漏隐藏为 P5 成功证据。

该 candidate 的浏览器路径、最终封存状态、同一 Volume 因果链和清理顺序已关联到同一 worldline；正式 Completion Challenge 仍需以隔离上下文重新作最终 verdict。

### 修复后复核 candidate：同一 live Volume `worldline-505f3f12c80b4644`

2026-08-12 在前端错误中文化、严格 blind evaluator 和 owned Gateway state 修复后，使用新的隔离产品 server `18840`、Gateway `18841`、SQLite 和 Hermes Home 重新运行真实产品链：

- 浏览器完成开始卷册、跟随并进入吴三桂、推进到 tick 1、离席；同一 Volume 随后在 tick 9 通过 `north-south-recognition-bridge` 进入南北公开信息交汇点。no-due wake 场景在真实 Life Desk 中显示 `当前这一刻没有需要你处理的下一步。`，不再泄漏 `Subject Wake` 内部英文；
- 在同一 worldline 以 Host 的明确 Meaning 边界记录 settlement outcome（before-shanhaiguan 与 nanjing-succession 各包含可公开的历史结果），Envelope 随后正常激活 `southern-consolidation`，没有直接把 later Knot 当作已结束；
- 浏览器重新进入史可法的 Life Desk 后，tick 10 收到同一北方公开军情；同一 Pending Logical Moment 中真实 Hermes 的韩赞周执行 `investigate(jiangbei-command)`，产生 `INVESTIGATION_STARTED`，tick 11 产生带 `mingji-nanlue-1`、`mingji-yiwen-2`、`hongguang-shilu-chao-1` 来源的 `OBSERVATION_OBTAINED`。这条 later-Knot-specific action 先于 settlement，结果写入 southern outcome；
- 通过产品 `/seal` 在 tick 11 完成 Archive/Ending。浏览器随后完成 Archive → Public Replay → 史可法 Lifetime Replay；公共回放显示北方军情进入南京、江北整饬激活、调查结果和封存边界，Life Replay 显示史可法后来知道的公开文书；
- 该 worldline 脱敏复核为：3 个 Crisis 均 `SETTLED`，9 个 Wake `COMPLETED`，7 个 `MOMENT_FROZEN`/`MOMENT_COMMITTED`，5 条消息派发/送达，6/6 bindings `REVOKED`；seal 后 Profile directory 数为 0、Gateway owner/PID 均不存在、lifecycle 为 `exited`、owned `gateway_state.json` 为 `gateway_state=exited` 且 `exit_reason=chronicle_cleanup`；
- `scripts/v5_export_public_trace.py` 从该真实 SQLite 只导出公开事件字段，生成 19 条 controller-blind trace；`scripts/v5_controller_boundary_evaluator.py` 对该 trace 返回 `PASS`（无 unexplained discontinuity），且输入不含 Human/Hermes/Profile/Session 等隐藏标签。

这条修复后 candidate 关闭了上一轮 evaluator 指出的 later Knot 空结算、盲评合成 trace 和 cleanup state 不一致；它仍标记为 candidate，因为 P5 的最终主观体验回答和正式 Completion Challenge 尚未分别记录。

### 独立 candidate review：两次 `NEEDS_WORK`

2026-08-12 的两次上下文隔离只读 evaluator 均返回 `NEEDS_WORK`，不是 Completion Challenge verdict：

- 第一次 review 指出首条 candidate 的 later Knot 是 host-forced 空 outcome、blind evaluator 只消费合成 trace、前端错误修复没有 live UI 复核，以及旧 `gateway_state.json` 与 lifecycle 状态不一致；这些问题已由后续修复和第二条 live candidate 覆盖；
- 第二次 review 复核了 `worldline-505f3f12c80b4644` 的真实 SQLite public trace（19 条，当前 evaluator=`PASS`）、later-Knot investigate→observation→settlement、修复后中文 no-due error 和 `exited / chronicle_cleanup` cleanup，确认客观 candidate 链成立；
- 第二次 review 仍拒绝总体 P5 PASS：计划要求的三项真实试玩主观问题——“离开后那些人物发生了什么”“重新进去还是不是同一个人”“最想重新玩什么”——当前没有真实试玩者的脱敏逐题回答。数据库、浏览器日志和 agent 自己的推断不能替代该回答。

因此当前状态保持 `CANDIDATE / IN_PROGRESS`，不执行正式 Completion Challenge，也不把 P5 写成 `PASS`。

## 5. Hermes live evidence

### 已验证的基础链路

2026-08-12 在独立临时 SQLite、独立 Hermes Home、独立 loopback port `18642` 上执行真实 live preflight：

| 检查 | 结果 |
| --- | --- |
| Hermes CLI | v0.20.0 |
| `VolumeRuntime.create(runtime_mode="live")` | materialized 6 个 Lifetime Profiles |
| Gateway health | PASS |
| 6 Profile routes | 全部 `200` |
| Profile toolsets | 全部 `memory` |
| valid Profile key | `200` |
| cross-profile key | `401` |
| fresh Session | PASS |
| real Hermes chat | PASS；只保留响应 hash，不保留正文 |
| V5 real Wake | PASS；真实 Profile 通过 `logical_intent` staging，一个 `INTENT_COMMITTED` 与一个 `MOMENT_COMMITTED` 写入同一 Pending Logical Moment |
| product `continue` | PASS；同类隔离 API harness 返回 `200`、推进到 tick 1、attention=`DECISION`、无遗留 pending moment |
| Gateway teardown | PASS；owner/PID 起始标识复核后 clean stop，未留下监听端口 |
| final live Volume seal / cleanup | PASS；独立 live Volume 在 tick 10、`n013` 已应用、3 个 Crisis 已 settlement 且无 pending/in-transit Wake 后写入 `VOLUME_SEALED`；bindings 全部 `REVOKED`、6 个 owned Profile 目录清空、Gateway owner 清除 |

这证明 Hermes 基础运行资源和一条真实 V5 Agent Wake 在隔离目录可工作，并实际经过 V5 MCP staging 与原子 Logical Moment commit。它仍没有证明 Human↔Hermes continuity、跨 Subject 行为差异、Learning、完整 message/settlement braid 或 Volume Ending。

### Volume world-tool bridge：investigate

在独立临时 Volume、SQLite、Hermes Home 和 loopback port `18717` 上，以当前 `d2cbeac` 运行真实 Hermes 工具调用验证：

- tick 1 的吴三桂 Wake 冻结到一个 Pending Logical Moment；同一 Lifetime Profile 创建 fresh Session；
- 真实 Hermes 只调用一次 Profile 专属 `chronicle-world` MCP 的 `investigate`，参数为关口态势、`shanhai-pass`、`courier_report`；数据库记录 `tool_name=investigate`、`status=PROPOSED`、`definition_id=shanhai-pass-report`、预计 tick `3`；
- 为同一 slice 的其它 due Wakes 提交显式 `wait` 后，Host 产生 `INTENT_COMMITTED` → `INVESTIGATION_STARTED` → `MOMENT_COMMITTED`，没有绕过 Pending Moment 直接写 Crisis 状态；
- 只记录响应 hash `22f9fb673d22ca5c`、Session ID 和脱敏事件字段；Gateway owner 在 finally 中定向停止，端口复核无残留监听。

该运行证明 Volume 世界工具已穿过真实 Hermes → Profile MCP → Host staging → atomic Moment commit 的边界；它仍只是工具链/单 Wake evidence，不是 P1/P3 live paired proof、P4 连续 trajectory 或完整 live V5 acceptance。

### P0 positive candidate：same Profile / fresh Session

在修复 Wake session title 上限和 `logical_intent` 顶层参数契约后，于独立临时 Volume、Hermes Home、loopback port `18668` 运行同一 Wu Sangui Lifetime 的 `AGENT → HUMAN → AGENT → HUMAN`：

- tick 1：Wu 的 Hermes Wake 真实提交 `INTENT_COMMITTED`、`PLAN_UPDATED`、`BELIEF_UPDATED`、`MOMENT_COMMITTED`；
- tick 2：Wu 切到 Human，提交带明确目标与步骤的 plan（先核对新到消息，再决定是否调整关口承诺）；
- tick 3：Dorgon 作为 off-screen Agent 继续运行，真实产生 `MESSAGE_DISPATCHED`；
- tick 4：Wu 回到 Hermes，仍是同一 Profile、但创建了新的 fresh Session，产生新的 `PLAN_UPDATED`、`BELIEF_UPDATED`、`MOMENT_COMMITTED`，并引用了新到 evidence；最终 controller 回到 Human；
- 同一 Wu Profile 的 session count 为 `2`，全程 4 个 committed moments；Human plan 在后续 Hermes Wake 中仍可见，后续 plan 已改变为处理 Dorgon 来信的回应策略。

该次是 P0 Subject Proof 的隔离正向候选证据，证明了同一 Lifetime 的 controller handoff、Profile 稳定、Session 可更换、Human 历史进入后续 Hermes 行动，以及 off-screen message 结果。它仍不等于 P1–P5 或完整 Live V5 Acceptance；`obligations/plans/revisits` 的全量复核和同一 Volume 内 P1–P4 braid 仍待完成。临时 runtime 在结束后精确停止并清理。

此前在独立临时 Volume 上尝试 P0 候选链时，真实模型连续两次没有提交 `logical_intent`；驱动执行一次同一 fresh Session 的协议修复后仍 fail-closed，未生成隐式 `wait`，随后精确 Gateway stop 通过。该次仍保留为负向运行证据：说明协议边界有效，不覆盖后续已通过的正向候选。

### P1/P2 live candidate：different actions and temporal reconsideration

随后在另一独立临时 Volume、Hermes Home、loopback port `18715` 运行一个带延迟消息的 live slice：

- tick 1：Human Wu 在收到李自成来信后，真实提交向多尔衮发送的 `MESSAGE_DISPATCHED`，delivery tick 为 `4`，随后离席；
- tick 3：多尔衮先收到 tick 0 的山海关求援信并以新的 Hermes Session 完成 `PLAN_UPDATED`/`BELIEF_UPDATED`；tick 3 的 frozen perspective 不包含 tick 1 延迟消息正文；
- tick 4：延迟消息抵达，多尔衮才首次看到正文，真实产生另一 Hermes Session，并以一封回信重新行动；tick 4 的 plan/action 相比 tick 3 增加了对补充请求的复核步骤；
- tick 5：吴三桂再次以 Hermes Session 唤醒，读取多尔衮回信并形成不同的保全所部/维持自主计划与 evidence-backed belief；
- tick 10：韩赞周、马士英、史可法在同一公开 n013 军情到达后，真实分别形成程序连续、现实军政支持、程序与江北推进三种不同计划；同片中也有主体选择 `wait` 的轨迹。

这为 P2 的 `A sends → B decides before arrival → arrival → B reconsiders` 提供了真实 live 候选，并证明到达前的冻结视角没有泄漏正文；也为 P1 的多主体不同 evidence/expectation/action 提供候选材料。P1 仍未正式通过，因为“同一第三方”的逐项证据映射与 exactly-once peer expectation 对照尚未独立完成。所有临时 Gateway 均按 owner/runtime epoch 定向停止。

### P0 supplemental live slice：同一 Profile 的真实 Revisit/Human Wake

在独立临时 Volume、Hermes Home 和 loopback port `18719` 上重新跑了一个更窄的 controller/Wake slice，避免把没有 Pending Wake 的 controller switch 当作 Human action：

- tick 1：Wu 的真实 Hermes Wake 通过 Profile MCP 调用 `schedule_revisit`；随后同一 Lifetime 被 `inhabit` 为 Human；
- tick 3：Revisit 到期，Wu 确实进入 `REVISIT_DUE` Human Wake，提交带 `rationale_source=explicit` 的 `PLAN_UPDATED`，同时 Dorgon 真实调用 `investigate`；Wu 随后 `leave`；
- tick 5：Wu 再次被切为 Human 但该 tick 没有 Wu Pending Wake，未把它计作 Human action；
- tick 7：Wu 离席，Dorgon 真实提交 `manage_offer(PROPOSE)`；tick 8 Wu 以同一 Lifetime 的新 Hermes Session 真实 `manage_offer(ACCEPT)`，读取此前持久计划；tick 9 Agreement Change 后再次 `inhabit` Wu；
- presence ledger 记录 `AGENT → HUMAN → AGENT → HUMAN → AGENT → HUMAN` 的切换边界；Wu 持久状态为 `plan_count=1`、`revisit_count=1`、Hermes Session count `3`，Gateway owner 精确停止。

该 slice 补强了真实 Human Wake、同 Profile/fresh Session 和 plan/revisit 持久化证据；严格 controller ablation 与 Human pending action 的补充证据见下一节。

### P0 strict live audit：port `18778`

在当前 `d5aa8d4` 代码上，重新执行了一条独立 live Volume，并把 controller ablation、Human pending Wake、计划 provenance 和 Hermes re-entry 放在同一份脱敏记录中：

- tick 1 的 Wu Wake 使用 Profile `chronicle-worldline-c095a3446cd542ae-wu-sangui`，fresh Session 为 `f0d46d8b-264a-4d2b-973e-33c8e4ed0d23`；在同一 tick 做 `AGENT → HUMAN → AGENT` 的无推进 ablation，tick、Profile、plan、commitments、revisits 均保持不变，只有明确的 `LIFETIME_INHABITED`/`LIFETIME_LEFT` Presence events；
- Human 接管后，Dorgon 消息在 tick 2 到达 Wu 的 frozen Perspective，Human Wake 以 `source=human` 提交 exactly one `logical_intent`，并写入 `PLAN_UPDATED`：objective 为先核对新军情再决定是否维持承诺，`rationale_source=explicit`，计划步骤与 tick 2 消息有因果关联；
- 离席后第二条 Dorgon 消息在 tick 3 到达，Wu 使用同一 Profile 的 fresh Session `9e7f4247-dcbd-49bd-b131-6394be3fb563` 继续，Wake 完成一个新的世界工具意图（能力不可用时按当前 Host 边界记录 `INTENT_REJECTED`），而不是丢失或隐式跳过；随后 Wu 再次回到 Human；
- `plan_count=1`、`commitment_count=0`、`revisit_count=0` 的持久状态在 ablation 前后没有丢失；初始 Agent plan 为空，Human plan 成为后续 Hermes context 中的当前 plan；同一 Profile 贯穿全程，最终 controller 为 Human，Gateway/owned Profiles teardown 为 PASS。

这条记录与 `18668` 的后续 Hermes plan/belief/evidence 候选合并后满足 P0 gate 的可复核边界；它不推导 P1、P4、P5 或总体完成。

### Continuous live Volume tool/causal sample：port `18718`

在另一条全新隔离 Volume 中同时激活 `before-shanhaiguan`、`nanjing-succession` 和 `southern-consolidation`，用真实 Hermes Profile MCP 完成了一个 tick `1→12` 的连续 sample：

- 6 个 Lifetime Profile materialized；5 个 Profile 实际产生 Hermes Wake，共 `14` 个 Hermes Wake、`9` 个 atomic Pending Moments，所有 Moment 都以 `INTENT_COMMITTED`/工具事件/`MOMENT_COMMITTED` 收束；
- 真实工具计数：`investigate=2`、`operate=1`、`update_plan=3`、`manage_offer=4`、`logical_intent=4`；另有 `MESSAGE_DELIVERED=5`、`FIELD_EVENT_APPLIED=1`、`OPERATION_STARTED/COMPLETED=1/1`、`OFFER_PROPOSED/OFFER_ACCEPTED=2/2`、`AGREEMENT_CREATED=2`；
- tick 9 的历史 Field 真实派发并在 tick 10 送达三个南方主体；tick 10 三个 Profile 分别提交 `investigate`、`update_plan`、`manage_offer`，tick 11/12 的调查与 Agreement Change Wake 又继续进入同一 Volume；
- 所有临时 Profile、SQLite 和 Gateway 均隔离；port `18718` 的 exact owner stop 通过，owner 文件消失。

该 sample 的工具选择使用了显式验收指令来确保每条 affordance 路径可观测，因此它是 real Hermes → Profile MCP → Host → atomic Moment → delayed consequence 的连续工具链证据，不是独立模型行为 benchmark，也不能单独证明 P1 的自然主体差异、P3 的 memory ablation 或 P4 的 tension/收敛判定。

### P4 live sample：before-shanhaiguan Knot

把 `18668`、`18713`、`18714`、`18715`、`18716` 五个相互隔离的 live Volume 运行按同一 `before-shanhaiguan` Knot 汇总，得到 12 个 Hermes Wake trajectory（另有 2 个 Human trajectory）：`update_plan` 9 次、`message` 3 次、`wait` 0 次。该样本没有出现 Investigation/Agreement 工具路径，也没有看到模型自动收敛到唯一答案；它是小样本行为观察，不是 benchmark，也不证明 tension 已脱离模型错误。

该记录把 P4 从 `NOT RUN` 推进为 partial candidate，但样本来自多个独立 Volume 而不是一条连续 10–20 trajectory run，且尚未完成预先定义的 dominant-action/World-Knot 修正判定，因此不把 P4 gate 标成 PASS。

在完成逐 Profile `/v1/models` 与 `/v1/toolsets` warm-up 后，于独立端口 `18651` 重复该候选，结果相同；因此当前证据不支持把失败归因于 Gateway/MCP 冷启动竞态。

随后新增的单一连续 port `18718` sample 记录了同一 Volume 内 `14` 个 Hermes Wake、`9` 个 Moment，以及 Investigation、Operation、Offer、Agreement、delayed Field message 和多种 `logical_intent`。但行动由显式验收指令定向，不能把工具覆盖率直接解释成主体自主偏好；尚未完成无指导行为样本、dominant-action/无尽协商判定、模型错误张力对照和必要的 World/Knot 修正。因此 P4 仍为 PARTIAL，不升级为 PASS。

### P1 directed live candidate：port `18727`

在独立 live Volume 中，两个真实 Lifetime Profile 针对同一个第三方 `fu-prince` 分别提交了真实 `update_plan`：

- 两个 Wake 的 `trigger_event_id` 不同，且各自携带 1 条 actor-visible evidence；
- 两个 belief assessment hash 不同（`fb6501c43d4e059d` / `7bfe4802aa098eba`），分别形成不同的 expectation；
- 两个 plan objective/action 不同；每个 Wake 都经过 `INTENT_COMMITTED → PLAN_UPDATED → BELIEF_UPDATED → MOMENT_COMMITTED`，Gateway owner exact stop 通过。

这是同一第三方、不同 evidence/expectation/action 的真实 live directed candidate，但 action 由验收指令定向，尚未完成独立 controller/peer exactly-once 对照；P1 保持 PARTIAL。

当前代码 `d5aa8d4` 又在独立 Hermes Gateway port `18780` 复测了 fail-closed 边界：一个目标 Wake 未产生合法 structured intent，另一个目标 Wake 产生 exactly one `message` operation；未把半成品 pair 计为 PASS，两个 Profile/Gateway 均精确清理。该负向运行说明 duplicate/malformed/missing intent 不会被 Host 猜成默认 wait，但也说明 P1 的自然/独立 peer proof 仍未闭合。

### P1 subject-scoped undirected live pair：port `18792`

在修复 `0d742fc` 后，于另一独立临时 Volume、SQLite、Hermes Home 和 loopback Gateway port `18792` 运行同一 tick `10` 的 frozen Pending Moment。harness 只为两个主体提供不同的私有历史判断，不指定工具；`subject_affordances` 由当前主体、当前状态、合法 target/method 计算，Host 仍保留最终校验：

- Han 的私有过去聚焦“福王位置与可接触性”这一未决，真实 Hermes fresh Session `0657ade2-6272-4ba1-a218-a49fde4bf51a` 选择 `investigate`，definition=`claimant-position-report`，target=`fu-prince`；该 Wake 只有一条 operation，提交后产生 `INTENT_COMMITTED → INVESTIGATION_STARTED`。
- Ma 的私有过去聚焦“福王一侧的现实军政支持”这一期待，真实 Hermes fresh Session `ec20fb3b-37a9-4c27-b2be-f4fe5281f675` 选择 `operate`，definition=`make_fu_backing_visible`，target=`jiangbei-military-backing`；该 Wake 只有一条 operation，提交后产生 `INTENT_COMMITTED → OPERATION_STARTED`。
- 两个不同 Lifetime 针对同一福王相关第三方形成不同 evidence/expectation/action；第三个同片 Wake 以显式 `wait` 补齐后，整片以 `MOMENT_COMMITTED` 收束，`pending_after=null`，没有重复 operation 或 rejected action；Gateway owner exact stop 通过。

这条是未指定具体工具的 controlled live peer pair，满足 P1 的 subject-scoped evidence、不同 expectation、真实不同世界动作和同片 exactly-once 边界；它不向 P4、P5 或完整 Live V5 Acceptance 外推结论。

### P2 live order-independence pair：ports `18722` / `18723`

两条独立 live Volume 使用相同 Pending Logical Moment，分别以 Human-first 与 Agent-first 顺序 staging；两边最终 semantic projection 相等：

```text
INTENT_COMMITTED, INTENT_COMMITTED, PLAN_UPDATED, MOMENT_COMMITTED
```

两边均为 tick 1、无遗留 pending moment、相同 seat/tool 结果，Gateway owner 均精确停止。它与 port `18715` 的延迟消息时间序列共同覆盖 P2 的两个必要条件；计划没有要求两个条件必须共享同一个 SQLite Volume，因此 P2 gate 现标为 PASS（两条隔离 live slices 的联合证据，不推导总体完成）。

### P3 live memory-ablation negative pair：ports `18720` / `18721`

一条 live Profile 带相关过去、一条移除相关过去；两边的 frozen context 确实不同，但真实 Hermes 两边均未产生可接受的 action，driver 按协议 fail-closed，未偷偷生成默认 wait。Gateway/Profiles 均清理成功。

这一个 pair 证明了 memory 输入差异和失败边界，但没有证明 `past experience → evidence-backed expectation → later retrieval → materially different action`；它本身不计为 P3 通过。

### P3 controlled live memory-ablation PASS：ports `18752/18753`、`18754/18755`

2026-08-12 以同一份 tick 10 基线的 SQLite/Volume 状态做了两个隔离 clone，worldline 均为 `worldline-4bd5c2b901234833`、`runtime_mode=live`，只改变吴三桂的 memory 输入；基线保留了 tick 1 Human 提交的 evidence-backed `PLAN_UPDATED` 与 `BELIEF_UPDATED`（objective=`先核验承诺，再决定是否开关`，belief=`承诺必须等可见行动验证。`）。两个 clone 随后由同一语义的多尔衮军情在 tick 11 送达同一 Wu Lifetime，均创建 fresh Hermes Session：

- **with memory**：Session `9827b44b-8b7d-4aff-b18e-94dbb10fa786` 的 frozen `subjective_memory` 实际检索到过去经验和 expectation；真实 Hermes 选择 `communicate`，通过 `INTENT_COMMITTED → MESSAGE_DISPATCHED → MOMENT_COMMITTED`，message `message-a8a3fec739c142bf` 的 delivery tick 为 `13`。
- **without memory**：Session `fa1e0f4a-038e-4e0b-95c6-c118bbbbf49b` 的 frozen memory 为空；真实 Hermes 选择 `investigate`，Host 按能力边界写入 `INTENT_COMMITTED → INTENT_REJECTED → MOMENT_COMMITTED`，结果为 `code=investigation_unavailable`，没有伪造成功。

两边共享相同的 Lifetime、tick 10 snapshot、消息内容/recipient/delivery tick 和 Moment 原子收束；差异发生在真实 Hermes 读取的 past context 与后续 action/result。此前另一个严格同基线的 negative control（ports `18748/18749` 与 `18750/18751`）两边都选择 `investigate` 并 rejected，因此没有被误计为正向结果。四个 Gateway/Profile owner 均在审计后精确停止并清理。该 controlled pair 满足 P3 的 live paired gate；它不把 P0、P1、P2、P4、P5 或完整 V5 acceptance 一并标为通过。

### P4 undirected live attempts：ports `18732` / `18733` / `18737`

三次普通执行尝试让真实 Hermes 自主选择世界工具，不指定具体工具。前两次在首个 Wake fail-closed；第三次采用“初始 Human Wu wait/leave、后续 Agent 自主继续”的真实边界，Dorgon 首个 Wake 仍未提交 `logical_intent`。所有运行均没有用默认 wait 填充，并完成精确 Gateway/Profile 清理。

这些是有效的负向协议与稳定性证据，不能被计作 10–20 条自主 trajectory；P4 仍以 port `18718` 的 directed continuous sample 作为 PARTIAL，不升级为 PASS。

### P4 genuine undirected continuous sample：ports `18740/18741`

2026-08-12 在一条独立 live Volume 中，以默认 Hermes 行为运行连续 product `continue`：初始 Human Wu 在 tick 1 wait/leave，之后没有向 Agent 指定具体工具，连续推进到 tick 21，再以 no-op continue 确认边界稳定。审计得到 14 个 Wake（1 Human + 13 Agent）、12 个 Moment、14 个真实 `MESSAGE_DISPATCHED`/`MESSAGE_DELIVERED`，并包含 tick 9 Field 到达与 tick 10 三个南方 Lifetime 的同一时刻分歧：

- Agent Wake 的工具分布为 `communicate=9`、`logical_intent.update_plan=1`、`logical_intent.wait=2`、`investigate=2`；其中两次 `investigate` 按能力边界 rejected，其他 Moment 均原子收束。
- tick 3–21 的 Dorgon/Wu 延迟消息链真实继续推进；tick 10 的 Han/Ma/Shi 没有脚本指定具体工具，分别形成 update-plan、investigate-rejected、wait 三种结果。
- 运行结束后 product server、Gateway、Profiles 和临时目录均按精确 owner 关系停止/清理，端口无残留监听。

这是目前最接近 P4 gate 的无定向连续样本，但仍不能 PASS：13 个 Agent Wake 中 9 个是 communicate，未出现成功 Investigation/Agreement，也没有形成预先定义的唯一收敛、无尽协商或 World/Knot 修正与 model-error tension 对照。因此 P4 保持 PARTIAL。

### P4 strict one-Knot live trajectory：Gateway port `18813`

在 `451f237` 的 exact Wake 路由和 one-action guard 之后，使用独立 live Volume、独立 SQLite/Hermes Home，只激活一个 `before-shanhaiguan` Knot；direct VolumeRuntime harness 不向模型指定工具，目标为约 10–20 条小样本 trajectory。脱敏审计为：worldline `worldline-176d43c95ee942cd`，21 个真实 Hermes Wake、21 个 fresh Session、15 个 atomic Moment，全部 Wake `COMPLETED`，每个 Wake 恰好 1 个 operation（最大值为 1），没有失败 Wake。

- 工具分布为 `communicate=10`、`investigate=3`、`logical_intent(wait/update_plan)=4`、`operate=2`、`manage_offer=2`；因此 Investigation 与 Wait 都不是 dominant，communicate 是该 Knot 的观察性 dominant 行为，未通过加提示把 Agent 强行改成预设比例。
- 其中一次错误的 `investigate` target 使用了 definition id，Host 写入 `INTENT_REJECTED(code=investigation_unavailable)`；后续合法 target 的 Investigation 成功完成。这保留了模型错误与 World 能力边界的可见区分，没有把错误猜成成功。
- Agreement 没有无限谈判：产生 1 个 `OFFER_PROPOSED`、1 个 `OFFER_ACCEPTED` 和 1 个 `AGREEMENT_CREATED`；resolver 在通行窗口收紧后给出唯一的 `WINDOW_EXPIRED_DEFERRED`，`ambiguity_used=false`。该结局由外部时间压力和 Projection facts 决定，不依赖模型报错；随后以同一 resolver 结果完成 Crisis settlement，未把产品 Ending 混同为 Crisis settlement。

该单 Knot 轨迹补齐了 P4 所需的真实 Investigation/Agreement、finite negotiation、unique Host resolution、model-error fail-closed 和 exact one-operation 观察边界；没有发现需要通过降低 Agent 能力来修复的 World/Knot 缺陷，因此 P4 gate 升为 PASS。它仍不替代 P5 或同一最终 Volume seal acceptance chain。

### 隔离边界

以上 harness 使用独立临时 SQLite、Hermes Home、runtime owner 和 loopback 端口（历史真实 Wake 使用 `18647`，product API 使用 `18648`，P0 候选使用 `18649`，seal/cleanup 使用 `18650`；新增连续 live sample 使用 `18718`，Human Wake slice 使用 `18719`，memory pair 使用 `18720/18721`，order pair 使用 `18722/18723`，P1 directed candidate 使用 `18727`，undirected attempts 使用 `18732/18733/18737`，P4 undirected continuous sample 使用 `18740/18741`，P3 negative control 使用 `18748/18749` 与 `18750/18751`，P3 controlled positive pair 使用 `18752/18753` 与 `18754/18755`，live browser shell 使用 `18734/18735`，guarded live product sample 使用 `18808/18809`，strict one-Knot P4 Gateway 使用 `18813`），没有触碰项目现有 Hermes Home、数据库或其他监听服务；临时目录在 harness 结束后按精确路径清理。

## 6. Review-driven structural gates (ordinary verification)

本节是复核驱动的实现与自动化证据，不是 Completion Challenge verdict，也不替代真实 live P5。

- **Crisis Envelope**：`CrisisReference` 现在持有 `earliest_activation_tick`、`activation_preconditions`、`participants` 和 `local_horizon`；Volume genesis 原子登记每个 Envelope 和 `DORMANT` Instance。`reconcile_crisis_envelopes()` 只激活 eligible knot，能在前置结构性条件消失时写 `CRISIS_SUPPRESSED`/`SUPPRESSED`，并对重复 reconcile/activation 保持幂等；southern knot 的 Nanjing settlement gate 由 `tests/test_v5_envelopes.py` 覆盖。
- **V5 restart reconcile**：`reconcile_live_runtime()` 和 app startup hook 核对唯一 Volume owner、6 条 Lifetime、Profile marker/identity、binding/token、V5 MCP allowlist 以及 Pending Logical Moment 的 Wake/operation 一致性；漂移写 `FAILED`，sealed cleanup 失败保留 `CLEANUP_PENDING`。startup success 与 binding identity drift 的 fail-closed 回归在 `tests/test_v5_live_bridge.py`。
- **Adversarial semantics**：现有 memory-ablation/Controller Boundary fixture 之外，新增 central-agent/persona-switch impostor negative control、peer private-context divergence、No-Offscreen cognition boundary contrast，以及 stage-before-commit/commit-before-ack 两个 restart fault-injection tests；`scripts/v5_controller_boundary_evaluator.py` 以不接收隐藏 controller label 的独立进程对 blind trace 做行为指纹断点检查，当前测试通过。
- **Deterministic regression**：Envelope、restart、adversarial 及相关 Phase 6–11 tests 在当前工作树定向通过；完整回归、validators、JS syntax 和当前代码的同一 live chain 均已通过，正式 Completion Challenge 仍是最后 gate。

## 7. P0–P5 Proof Gates

| Gate | 当前状态 | 证据与缺口 |
| --- | --- | --- |
| P0 Subject Proof | **PASS（strict live audit + ablation）** | 两条独立 live Volume（ports `18668`、`18778`）各自覆盖同一 Wu Lifetime 的 `AGENT → HUMAN → AGENT → HUMAN`；`18778` 进一步记录 Human 新消息驱动的显式 plan、fresh Session、后续 Hermes Wake、同 Profile 及最终 Human，并逐项复核 tick/Profile/plan/commitments/revisits ablation 不变，同时保留 Host 对不可用工具的 rejected outcome。 |
| P1 Multi-Subject Proof | **PASS（subject-scoped undirected live pair）** | port `18792` 在同一 tick/frozen Moment 由两个不同私有过去驱动真实 Hermes：Han 调查 `fu-prince`，Ma 将其江北支持变为可见；两条 Wake 各 exactly one operation，分别经过 `INTENT_COMMITTED → INVESTIGATION_STARTED` 与 `INTENT_COMMITTED → OPERATION_STARTED`，最后 atomic `MOMENT_COMMITTED`，Gateway exact stop 通过。 |
| P2 Temporal Proof | **PASS（live temporal + order pair）** | port `18715` 完成 A sends → B pre-arrival decision → delivery → B fresh-session reconsideration，且到达前 Perspective 不含正文；ports `18722/18723` 完成 Human-first/Agent-first semantic equality、无 pending moment 和精确 teardown。 |
| P3 Learning Causality | **PASS（controlled live paired）** | ports `18752/18753` 与 `18754/18755` 从同一 tick 10 基线 clone，真实 Hermes fresh Session 在同一 tick 11 消息上分别检索 memory 并 `communicate` committed，或 memory 为空并 `investigate` rejected；Moment 两边均 atomic commit。 |
| P4 Game Proof | **PASS（strict one-Knot live trajectory）** | Gateway port `18813` 的单一 `before-shanhaiguan` Knot 产生 21 Wake/21 fresh Session/15 atomic Moment，全部完成且每 Wake exactly one operation；覆盖真实 Investigation、Operation、Offer/Agreement、Wait/update_plan、model-error rejected path，Agreement finite，resolver 给出 `ambiguity_used=false` 的唯一 Deferred 结果。 |
| P5 30-minute Product Proof | **CANDIDATE（修复后同一 live Volume + evaluator 证据已形成，主观回答/正式 Challenge 待记录）** | `worldline-505f3f12c80b4644` 已完成修复后产品浏览器试玩、离席后同一 Lifetime continuation、跨 Knot、later-Knot-specific investigation、settlement、Archive/Replay、seal/cleanup；真实 SQLite public trace evaluator=`PASS`，但 P5 主观体验回答与正式 Completion Challenge 尚未执行。 |

## 8. Live V5 acceptance checklist

计划要求同一真实 V5 中记录以下项目；修复后 candidate 已关联到 `worldline-505f3f12c80b4644`（较早的 `worldline-11646e76ec1f49b0` 作为补充记录保留）：

- 4+ persistent Profiles（同一 candidate materialize 6 个并在产品/真实 Hermes 链中使用多个；此前 `18718`、`18734/18735`、`18813` 证据另行保留）；
- 初次 Human Life 的 dormant Profile；
- 0 mandatory ORIENT（已通过单次 live V5 创建与 Wake 证据）；
- 至少一条真实 `logical_intent` staging → `INTENT_COMMITTED` → `MOMENT_COMMITTED`（已通过单次 live V5 证据）；
- Human→Hermes handoff、same Profile、fresh Session（P0 隔离正向候选已通过：同一 Wu Profile、2 个 Session）；
- Human plan 进入后续 Hermes context，并在新 evidence 后形成不同的后续 plan/belief（P0 隔离正向候选已记录）；
- off-screen Dorgon Agent 产生 `MESSAGE_DISPATCHED`（P0 隔离正向候选已记录）；
- delayed message、operation/offer crossing through the shared Volume graph、off-screen Agent↔Agent causal chain（candidate 在同一 Volume 中完成延迟消息、南北 Field/跨 Knot 传播、工具结果 Wake 与后续 settlement）；
- evidence-backed past affecting future（P3 controlled live pair 已证明 memory 检索导致后续 `communicate`，而无 memory 分支选择 `investigate` 并按能力边界 rejected）；
- Crisis settlement 后 Profiles 仍存活（candidate 在第一批 settlement 后仍保持 ACTIVE，随后才完成 southern settlement 与 seal）；
- second Crisis / later Knot continuation（同一 candidate 的 southern-consolidation 在前置 settlement 后激活，真实 Hermes 韩赞周调查在 tick 10 开始、tick 11 完成）；
- later cross-crisis knowledge arrival；
- final Volume seal（修复后 candidate 在 tick 11 通过 boundary 后完成）；
- seal 之后才 revoke/clean owned Profiles（修复后 candidate 记录了 `VOLUME_SEALED` 后 6 bindings revoke、owned Profile cleanup 和 normalized Gateway state）。

当前不能用 preflight、fixture 或旧 V4 live runtime 填充这些空项。

## 9. 当前 blockers 与下一步

1. 由独立 evaluator 记录三项 P5 主观问题的脱敏回答或明确的不可替代边界，并执行新的 context-isolated Completion Challenge。
2. 保留 `worldline-505f3f12c80b4644` 的修复后同一 live Volume 业务链作为 P5 主证据，不用 fixture 或旧 live slice 替代。
3. 将前端错误中文化、public-trace evaluator、Gateway cleanup normalization 的全量回归和最终文档 commit 一并归档；在 Challenge PASS 前保持 CANDIDATE 状态。

在以上 blocker 关闭前，不能把本文件状态改成 `COMPLETE`，也不能把 README、产品发布说明或 commit message 写成“V5 已完成”。
