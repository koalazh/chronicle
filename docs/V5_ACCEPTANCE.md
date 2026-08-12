# Chronicle V5 Acceptance Record

> 记录日期：2026-08-12
> 分支：`dev_v5`
> 状态：**NOT COMPLETE — P0–P5 与完整 live V5 业务链尚未通过**

本文是 V5 的唯一当前验收记录。它只记录已经执行、可以复核、没有泄漏 Secret 的证据；`PASS` 只对对应证据层有效，不向上推导为整卷产品完成。

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

当前实现已经固定了这条链的 deterministic Host/API/Archive 结构，但还没有用真实 V5 Hermes cognition 完整走通它。

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
| 12 | `f52ddf9` + `b287ee6` + `a569344` + `c2b19a9` + `8c1241e` + `2c99332` + `b8f22a4` + `d2cbeac` + `c47edf4` + `52b687b` + `dc26345` + `b51a075` + `235927e` + `7cc1a25` + `1280457` | V5 source-of-truth docs、Hermes `logical_intent` Wake bridge、协议 fail-closed/repair、live seal/cleanup、P0 正向候选与 fresh-session/title 修复、Archive/Ending 浏览器 proof、Volume 世界工具与共享北方 transport 进入 Pending Logical Moment、Offer/Agreement wake 时序修复、MCP evidence schema 修复、对抗性边界测试、连续 live 记录，以及离席后 Agent 接管 Pending Moment 的产品修复；P1–P5 与完整 live V5 业务链仍未完成 |

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
homepage → World（3 个 knots）→ Follow Wu → Inhabit Desk
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

### 真实 live Product Shell / API：port `18734`，Gateway `18735`

2026-08-12 在另一组隔离 SQLite、Hermes Home、runtime owner 和 loopback ports 上，以产品默认 `live=true` 走了真实浏览器链：

- 首页点击“开始这一卷”真实创建一个 VOLUME，并物化 6 个 Lifetime-scoped Hermes Profiles；浏览器页面只显示 Volume、World、Follow、Life Desk 等普通用户文案，没有 Agent/Profile/Session/Memory 内部术语；
- `Follow → Inhabit` 进入吴三桂的真实 Life Desk；tick 1 的真实 Human Wake 通过空白 wait 提交 `INTENT_COMMITTED → MOMENT_COMMITTED`，随后 Leave；
- 离席后真实 Hermes Profiles 在同一 Volume 继续：Dorgon tick 3、Wu tick 5、Dorgon tick 7、Wu tick 9 形成 fresh Session 与延迟消息；tick 9 historical Field 应用，tick 10 三个南方 Lifetime 收到跨 Knot 公开军情并分别选择 investigate / wait / operate，其中权限或可用性拒绝写成 `INTENT_REJECTED`，没有破坏 atomic Moment；
- 同一 live Worldline `worldline-52d33bd7ff68415c` 在本 slice 记录了 6 个 `MOMENT_FROZEN`、6 个 `MOMENT_COMMITTED`、8 个 `INTENT_COMMITTED`、9 个 `MESSAGE_DISPATCHED`、8 个 `MESSAGE_DELIVERED`，并在 tick 10 仍保持可继续的 ACTIVE Volume；第一 Crisis 在 Profiles 仍存活时 settlement，Worldline 继续保持 ACTIVE；随后两个 Crisis settlement、最后在途消息 delivery 和 boundary wait 将它推进到 tick 19；
- 新建的 fresh Browser tab 在 tick 10 能读到真实 World 页面；随后同一 live API 真实打开 Archive → Public Replay → 吴三桂 Lifetime Replay，四个 viewport 均无横向 overflow，浏览器 dev logs 为 `[]`。tick 19 的正式 `VOLUME_SEALED` 之后，6 个 bindings 变为 `REVOKED`、owned Profile 目录被清理、Gateway owner 被精确停止。

这条记录证明真实 live API 与用户可见 shell 已接通同一 Volume/Host/MCP 边界；它不把浏览器可见 tick 或一条 off-screen causal chain 误当成 P0–P5 全部通过。原运行资源在本记录完成后按精确 owner/runtime 归属停止并清理。

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

这为 P2 的 `A sends → B decides before arrival → arrival → B reconsiders` 提供了真实 live 候选，并证明到达前的冻结视角没有泄漏正文；也为 P1 的多主体不同 evidence/expectation/action 提供候选材料。P1 仍未正式通过，因为“同一第三方”的逐项证据映射与 exactly-once peer expectation 对照尚未独立完成；P2 仍未正式通过，因为 Human/Agent 同 slice 的执行顺序成对等价测试尚未在 live 上完成。所有临时 Gateway 均按 owner/runtime epoch 定向停止。

### P0 supplemental live slice：同一 Profile 的真实 Revisit/Human Wake

在独立临时 Volume、Hermes Home 和 loopback port `18719` 上重新跑了一个更窄的 controller/Wake slice，避免把没有 Pending Wake 的 controller switch 当作 Human action：

- tick 1：Wu 的真实 Hermes Wake 通过 Profile MCP 调用 `schedule_revisit`；随后同一 Lifetime 被 `inhabit` 为 Human；
- tick 3：Revisit 到期，Wu 确实进入 `REVISIT_DUE` Human Wake，提交带 `rationale_source=explicit` 的 `PLAN_UPDATED`，同时 Dorgon 真实调用 `investigate`；Wu 随后 `leave`；
- tick 5：Wu 再次被切为 Human 但该 tick 没有 Wu Pending Wake，未把它计作 Human action；
- tick 7：Wu 离席，Dorgon 真实提交 `manage_offer(PROPOSE)`；tick 8 Wu 以同一 Lifetime 的新 Hermes Session 真实 `manage_offer(ACCEPT)`，读取此前持久计划；tick 9 Agreement Change 后再次 `inhabit` Wu；
- presence ledger 记录 `AGENT → HUMAN → AGENT → HUMAN → AGENT → HUMAN` 的切换边界；Wu 持久状态为 `plan_count=1`、`revisit_count=1`、Hermes Session count `3`，Gateway owner 精确停止。

该 slice 补强了真实 Human Wake、同 Profile/fresh Session 和 plan/revisit 持久化证据，但没有完成 controller-label ablation，也没有证明每一次切换都伴随 Human action；P0 仍保持 PARTIAL。

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

### P2 live order-independence pair：ports `18722` / `18723`

两条独立 live Volume 使用相同 Pending Logical Moment，分别以 Human-first 与 Agent-first 顺序 staging；两边最终 semantic projection 相等：

```text
INTENT_COMMITTED, INTENT_COMMITTED, PLAN_UPDATED, MOMENT_COMMITTED
```

两边均为 tick 1、无遗留 pending moment、相同 seat/tool 结果，Gateway owner 均精确停止。它补上了 P2 的执行顺序 paired evidence，但仍与 port `18715` 的延迟消息时间序列分开，P2 保持 PARTIAL candidate。

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

### 隔离边界

以上 harness 使用独立临时 SQLite、Hermes Home、runtime owner 和 loopback 端口（历史真实 Wake 使用 `18647`，product API 使用 `18648`，P0 候选使用 `18649`，seal/cleanup 使用 `18650`；新增连续 live sample 使用 `18718`，Human Wake slice 使用 `18719`，memory pair 使用 `18720/18721`，order pair 使用 `18722/18723`，P1 directed candidate 使用 `18727`，undirected attempts 使用 `18732/18733/18737`，P4 undirected continuous sample 使用 `18740/18741`，P3 negative control 使用 `18748/18749` 与 `18750/18751`，P3 controlled positive pair 使用 `18752/18753` 与 `18754/18755`，live browser shell 使用 `18734/18735`），没有触碰项目现有 Hermes Home、数据库或其他监听服务；临时目录在 harness 结束后按精确路径清理。

## 6. P0–P5 Proof Gates

| Gate | 当前状态 | 证据与缺口 |
| --- | --- | --- |
| P0 Subject Proof | **PARTIAL（隔离正向候选）** | port `18668` 真实完成同一 Wu Profile 的 `AGENT → HUMAN → AGENT → HUMAN`；同 Profile、2 个 Session、Human plan、后续 Hermes plan/belief/evidence、Dorgon off-screen message 与最终 Human 均有 committed evidence。仍缺 controller-switch 对照，以及 obligations/plans/revisits 的严格逐项复核，因此不把 P0 正式 gate 标成 PASS。 |
| P1 Multi-Subject Proof | **PARTIAL（directed live candidate）** | port `18727` 已有两个真实 Profiles 针对同一 `fu-prince` 的不同 evidence hash、belief assessment、plan/action，并通过 atomic Moment；仍缺独立 controller/peer exactly-once 对照与非定向行为边界。 |
| P2 Temporal Proof | **PARTIAL（temporal candidate + order pair）** | port `18715` 已完成延迟消息时间序列，ports `18722/18723` 已完成 Human-first/Agent-first semantic equality；两类证据仍未在同一完整 acceptance Run 关联，故不标 PASS。 |
| P3 Learning Causality | **PASS（controlled live paired）** | ports `18752/18753` 与 `18754/18755` 从同一 tick 10 基线 clone，真实 Hermes fresh Session 在同一 tick 11 消息上分别检索 memory 并 `communicate` committed，或 memory 为空并 `investigate` rejected；Moment 两边均 atomic commit。 |
| P4 Game Proof | **PARTIAL（directed + undirected continuous candidates）** | port `18718` 提供 14 Wake/9 Moment 的 directed tool chain；port `18740/18741` 提供 14 Wake（13 Agent）/12 Moment 的无定向连续样本，但 communicate 占主导，未完成 successful Investigation/Agreement、唯一收敛、model-error tension 对照或 World/Knot 修正。 |
| P5 30-minute Product Proof | **NOT RUN** | 尚无真实用户试玩和独立 evaluator 对“他们在我离开后仍有下一步”的记录。 |

## 7. Live V5 acceptance checklist

计划要求同一真实 V5 中记录以下项目；当前均未形成完整可关联链：

- 4+ persistent Profiles（port `18718` materialize 6 个并使用其中 5 个完成真实 Wake；port `18734/18735` 另在产品浏览器中 materialize 6 个并完成真实 Human→Leave→off-screen chain；跨多次缺席的连续性仍未完整记录）；
- 初次 Human Life 的 dormant Profile；
- 0 mandatory ORIENT（已通过单次 live V5 创建与 Wake 证据）；
- 至少一条真实 `logical_intent` staging → `INTENT_COMMITTED` → `MOMENT_COMMITTED`（已通过单次 live V5 证据）；
- Human→Hermes handoff、same Profile、fresh Session（P0 隔离正向候选已通过：同一 Wu Profile、2 个 Session）；
- Human plan 进入后续 Hermes context，并在新 evidence 后形成不同的后续 plan/belief（P0 隔离正向候选已记录）；
- off-screen Dorgon Agent 产生 `MESSAGE_DISPATCHED`（P0 隔离正向候选已记录）；
- delayed message、operation/offer crossing through the shared Volume graph、off-screen Agent↔Agent causal chain（port `18718` 有 directed continuous coverage，port `18734/18735` 有真实产品 API 的 Agent↔Agent delayed-message chain，尚未形成同一条最终 seal acceptance chain）；
- evidence-backed past affecting future（P3 controlled live pair 已证明 memory 检索导致后续 `communicate`，而无 memory 分支选择 `investigate` 并按能力边界 rejected）；
- Crisis settlement 后 Profiles 仍存活（port `18734/18735` 在 tick 10 的第一 Crisis settlement 后仍保持 ACTIVE，随后同一 slice 才在 tick 19 seal）；
- second Crisis / later Knot continuation；
- later cross-crisis knowledge arrival；
- final Volume seal（port `18734/18735` 同一 live slice 在 tick 19 通过 boundary 后完成）；
- seal 之后才 revoke/clean owned Profiles（port `18734/18735` 记录了 `VOLUME_SEALED` 后 6 bindings revoke、owned Profile cleanup 和 Gateway stop；仍不等于 P0–P5 全部通过）。

当前不能用 preflight、fixture 或旧 V4 live runtime 填充这些空项。

## 8. 当前 blockers 与下一步

1. 完成仍未关闭的 P0、P1、P2、P4 instrumented gates，并把 evidence IDs、ticks、session/profile 状态和清理结果写入脱敏记录；P3 controlled live paired gate 已通过，P0 仍需 controller ablation/严格 obligations-plans-revisits 对照，P1/P2 仍需各自的 paired gate，P4 仍需成功世界行动/收敛与 model-error tension 对照。
2. 完成 P5 真实试玩和独立 evaluator 记录；不能用开发者主观感受替代。
3. 将 fixture Archive/Ending 浏览器证据与真实 live Volume/API 状态分开保留；port `18734/18735` 已补上同一 live 产品 slice 的 World/Follow/Desk/Leave、Archive/Ending、最终 seal 和 cleanup，但这仍不能替代 P0–P5 proof gates。

在以上 blocker 关闭前，不能把本文件状态改成 `COMPLETE`，也不能把 README、产品发布说明或 commit message 写成“V5 已完成”。
