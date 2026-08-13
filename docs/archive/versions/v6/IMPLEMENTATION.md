# Chronicle V6 实施记录

> 历史归档。当前实现入口见 [`../../../ARCHITECTURE.md`](../../../ARCHITECTURE.md)，当前验收见 [`../../../ACCEPTANCE.md`](../../../ACCEPTANCE.md)。

## 开始信息

- start_commit: `13dcbe28ac781828f5553de918897ddd7f4e6e9e`
- branch: `dev_v6`
- date: 2026-08-13
- worktree: `/Users/koala/work/product/chronicle-v6`

## V5 baseline

当前 schema version 为 `10`。V5 的 Volume Worldline、Global World Tick、Persistent Lifetime、frozen Perspective、Pending Logical Moment、Profile/Session 边界、Ledger、Archive 与 cleanup 均是 V6 的既有基础。

2026-08-13 在干净 `dev_v6` worktree 上实际执行：

- `uv sync`：exit 0；
- `uv run chronicle source validate`：`4 sources / 36 assertions / 36 events`；
- `uv run chronicle scenario validate`：`3 Seats / 15 locations / 16 routes / fork=jiangnan-prince-command`；
- `uv run chronicle crisis validate`：`jiashen / 3 crisises`；
- `uv run pytest -q`：exit 0；`pytest --collect-only -q` 统计为 318 tests；
- `uv run ruff check .`、`uv run python -m compileall -q chronicle tests`、`node --check web/app.js`、`node --check web/router.js`、`node --check web/state.js`：均 exit 0；
- 初始源码树的 `git diff --check`：exit 0。

完整 pytest 保留 4 条既有依赖/框架 warning：Starlette TestClient/httpx deprecation、Pydantic settings incomplete field definition，以及 FastAPI `on_event` deprecation 两条；本阶段不修改它们。

根据 [`../v5/ACCEPTANCE.md`](../v5/ACCEPTANCE.md)，P0–P4 仅在各自所列证据层为 PASS；P5 是 `CANDIDATE`，仍缺真人试玩逐题回答与正式 Completion Challenge。V6 不改写这个事实。

## Phase 1 Characterization + seam

本阶段只新增 `tests/test_v6_characterization.py`，没有改变生产运行时语义。它固定当时 V5 的实际边界：

- `MESSAGE_DELIVERED` 会写入 recipient Knowledge，并立即产生 `OBSERVATION` Wake；
- `OPERATION_COMPLETED` 与 `OBSERVATION_OBTAINED` 分别会写入 Knowledge，并产生相应结果 Wake；
- `Lifetime.plan` 当前仅投影 `plan[0]` 为 Current Plan，`reconsider_when` 仍是 prose；
- Volume MCP 在同一 Wake 内拒绝第二个不同 idempotency key 的世界写入；
- 现有 `/continue` 每个 request 只调用一次 Global advance（一个 `TIME_ADVANCED`）。

2026-08-13 实际执行：`uv run pytest -q tests/test_v6_characterization.py` 为 6 passed；完整 `uv run pytest -q` exit 0（324 tests collected）；`uv run ruff check .` 与 `uv run python -m compileall -q chronicle tests` 均 exit 0。上述是 fixture / deterministic 证据，不构成 P6–P9 或 live Hermes 证明。

## Phase 2 Decision Horizon

`Lifetime.plan[0]` 现为唯一持久化的 Current Course；未新增 Horizon 表或平行 Runtime，数据库 schema version 仍为 `10`。新写入在保留 V5 `objective`、`steps`、`rationale` 与 `reconsider_when` 读取字段的同时，加入：

- `course_schema_version`、`course`、`status=IN_FORCE`；
- `established_tick` / `established_event_id`；
- 只接受 data-only typed `open_dependencies`（`DEADLINE`、`MESSAGE_FROM`、`OBSERVATION_FOR`、`OPERATION_OUTCOME`、`OFFER_CHANGE`、`AGREEMENT_CHANGE`、`ENTITY_OBSERVED_CHANGE`），拒绝 predicate / 任意代码字段；
- `explicit_rationale`、actor-known `evidence_event_ids`、`last_deliberated_tick` / `last_deliberated_event_id`。

每次首次建立或替换 Course 都仍在同一个 atomic Pending Logical Moment 内写入 `PLAN_UPDATED`，并追加 `DECISION_HORIZON_ESTABLISHED` 或 `DECISION_HORIZON_REVISED`。旧 V5 `plan_json` 不在 read 时被改写，而是在 Context 中投影为可读的 Course。`tests/test_v6_decision_horizon.py` 覆盖单 Course、typed dependency reject、tick / restart / HUMAN↔AGENT controller switch / fresh-session prompt continuity、revision 与 legacy read；定向 5 passed、完整 pytest exit 0（329 tests collected）、Ruff / compileall exit 0。

## Phase 3 Knowledge / Attention separation

新增 `chronicle/subject_attention.py`。`evaluate_attention(lifetime, new_known_events, projection)` 是不读 DB、不调用 LLM、不提交 World action 的 pure deterministic policy，并总是返回 `decision`、`reason_code`、`trigger_event_ids` 与 `matched_dependency_ids`。

- message delivery、operation completion 与 investigation observation 现在先写入 Knowledge，再在同一 tick 归并评估 Attention；`BACKGROUND` 只写 append-only `ATTENTION_EVALUATED` Ledger event，不创建 Wake；
- `MESSAGE_FROM`、`OBSERVATION_FOR`、`OPERATION_OUTCOME`、`ENTITY_OBSERVED_CHANGE` 和 Host-owned `DEADLINE` 可匹配已存在 typed dependency；其中 deadline 由 `DECISION_DEPENDENCY_DUE` 记录并进入 Knowledge，不是 wall-clock polling；
- 无 Current Course 的初始事实仍 `REOPEN`，以便建立首个判断；对已有 Course，预期操作完成和无关消息只作为 Background；
- `REOPEN` 保留 exact Wake identity 与原有来源 wake type，但 Wake 的 causal trigger 变为私有的 `ATTENTION_EVALUATED` event，包含实际进入 Knowledge 的事实 ID，而不是把任意 result 直接升级为 cognition。

Offer / Agreement 的事实 transport 仍是 Phase 8 的专门改动；本阶段未把现有 `tick+1` offer scaffold 伪装成 transport semantics。`tests/test_v6_attention.py` 覆盖无关已知消息、typed sender match、预期操作完成、deadline 与 pure policy；完整 pytest exit 0（334 tests collected），Ruff、compileall 和三项 content validator 均 exit 0。

## Phase 4 Context Compiler

现有 `LifetimeContextBuilder` 继续负责冻结、actor-scoped Perspective，并新增六个 reality-first section：

- `why_now`：当前 Wake / `ATTENTION_EVALUATED` 的 reason、匹配依赖和真正触发事实；
- `since_last_deliberation`：以 Course 的 `last_deliberated_tick` 为边界，汇总该 Lifetime Knowledge 中之后到达的事实，包括此前只产生 `BACKGROUND` 的事实；
- `binding_reality`：当前位置、authority、进行中的 operation / investigation / offer / agreement、commitments、owned assets 与 resources；
- `previous_course`：此前唯一 Current Course 的只读副本；
- `relevant_experience`：现有 bounded beliefs、evidence 与 private memory；
- `affordances`：Host 按主体和当前状态筛出的真实 operations、investigations 与 offer terms。

Reality sections 在 selective relevance / memory 之前生成，旧的 bounded `beliefs`、`relevant_evidence`、`subjective_memory` 字段继续保留给 V5 consumers。测试覆盖了“当前 Course 预期等待 Dorgon，但 Li 的公开东进事实仍进入 `since_last_deliberation`”以及 Nanjing 的主体私有 affordance 边界；不存在跨 Lifetime Knowledge 泄漏。定向 Phase 4 tests 2 passed，静态检查通过；完整回归和 content validators 将在本 Phase commit 前复跑。

## Phase 5 Deliberation Protocol

新增开发层 `commit_deliberation`，但不改变用户对 Chronicle 的概念模型。它在一个已冻结且绑定 exact `wake_id` 的 Pending Logical Moment 中提交完整 proposal：

```text
HOLD | REVISE
course
typed open_dependencies
evidence-backed belief_updates
0..1 world_actions
```

`HOLD` 是一等认知结果，不是一个 wait World action；它保留 Course，只更新 `last_deliberated_tick/event_id` 并追加 `DELIBERATION_COMMITTED` / `DECISION_HORIZON_HELD`。Agent 的 `REVISE` 必须引用 actor-visible `evidence_event_ids`（首次建立 Course 时可引用当前 Wake 的可见触发）；Human 仍可在明确输入下不受该 Agent 证据门槛约束。

World action 在 stage 时通过现有 Host / pack affordance 预校验，最多一个；任何 shape、权限、证据、typed dependency 或 action 错误都不会写入 staged operation。commit 时 proposal、Course、belief、action 和 `MOMENT_COMMITTED` 仍在一个 atomic DB moment 中收束，action 的 causal parent 是 `DELIBERATION_COMMITTED`。`tests/test_v6_deliberation.py` 覆盖 HOLD 零行动、REVISE + message、无证据拒绝、多个 action 原子拒绝及 restart/idempotent replay；定向 5 passed，完整回归在提交前复跑。

## Phase 6 Product Continuous Agency

`/continue` 现在在既有 Host-owned `advance_one` atomic boundary 之上循环：每次只推进一个 Global Tick，处理同 tick 的 Agent Wakes，并在 Human Attention、meaningful knot boundary、Volume structural boundary、无未来触发或安全 cap 出现时返回。当前 cap 为每次 request 最多 12 个 ticks、24 个 Agent deliberation、30 秒 wall time。达到 cap 时返回合法当前状态，不抛业务错误，也不启动后台 daemon。

`/decision` 保留 V5 显式 intent 兼容，同时将自然语言输入编译为 Human `REVISE` Deliberation；已有 Course 的等待输入编译为 `HOLD`。当 Human 当前没有 Attention 时，首次提交会在当前 tick 建立一次 Human-only voluntary reconsideration boundary；它不推进 World Time、不调用 Hermes。同一 tick 的重复 voluntary boundary 被拒绝，避免认知入口形成无限循环。

Life Desk 保留原页面和兼容字段，并新增用户语义投影：`current_course`、`since_last_deliberation`、`why_now`、`binding_reality` 与 `reconsideration`。前端没有新增 Planner / Decision Center / Agent Dashboard 页面，也不渲染 V6 内部协议名。

定向证据：`tests/test_v6_continuous_agency.py` 覆盖连续推进到 Human Attention、当前 tick voluntary reconsideration（无 `TIME_ADVANCED`）与 Life Desk 五段投影；product shell、frontend copy 和 syntax checks 仍通过。该证据是 fixture / deterministic product evidence，不构成 real Hermes、browser 多视口或真人验收证明。

## Phase 7 Agency Conservation

本阶段先做 World transition ownership audit，没有因为“看起来更完整”新增通用 agency layer。现有 Pack 已明确区分：主体自有或受托可见资产、Institutional procedure、Claimant entity 与 deterministic Resolution。`make_fu_backing_visible` 只由马士英作用于其拥有的 `jiangbei-military-backing` 抽象；`arrange_*_entry` 是有来源边界的有限程序动作，不创建福王/潞王 Persistent Lifetime；制度承认和公开文书只由韩赞周在明确 prerequisites / endorsement Agreement 满足后提交。

新增 `tests/test_v6_agency_conservation.py` 固定三条可复核边界：南京 operation actor 与 claimant/institution 分离、马士英越权提交制度承认在 staging 时被 `operation_authority_denied` 拒绝且不改变制度状态、主体拥有的行动效果保留 actor `seat_id` 与 completion causal parent。由于当前源码已满足审计结果，本阶段没有引入 generic Political DSL、额外 Agent 或无来源机制。

## Phase 8 Content / World Correctness

Offer / Agreement transport 现在复用同一个 Volume global clock 与既有 route graph。提案、回应、counter 都先以 `source=volume_offer` 的结构化在途消息写入 `MESSAGE_DISPATCHED`；收件方只有在 `MESSAGE_DELIVERED` 后才获得 `OFFER_CHANGED` Attention 事实。接受回应抵达前，原 Offer 仍是 `PROPOSED`，Agreement 不存在；抵达 tick 才追加 `OFFER_ACCEPTED`、`AGREEMENT_CREATED`，其 `effective_tick` 等于真实抵达 tick。可见性通过 offer 的 `visible_to` 控制，避免同一投影中的未抵达 Offer 提前进入另一主体的 affordance。

本阶段没有删除来源支持的山海关 `prepare_force` 或 `eastern-transit-window-narrows`：前者仍是三位主体各自自有兵力的 2 日固定操作，后者仍是 tick 5 的 `EXOGENOUS`、`scenario_assumption` 压力并带 `c015` 断言。南京的 backing、claimant entry 与 fragmented resolver 沿 Phase 7 的 source-bounded Pack 保持，不引入平衡成本或额外历史机制。

证据：`tests/test_v6_content_world.py` 覆盖远程 Offer / response 的路由延迟、Agreement 生效 tick、结构化 `OFFER_CHANGED` 触发与山海关压力/整备来源边界；Phase 7 agency tests、Volume offer、Attention 与完整回归均通过。该阶段仍是 deterministic fixture / source evidence，不替代 browser 或 real Hermes business chain。

## Phase 9 Harness Ablation

四项 ablation 按“先实验、后决定是否删除”执行：

- one-action：在不提供任何 prompt 帮助的直接 Host 调用中提交两个 blind-staged `world_actions`，staging 以 `at most one action` 拒绝，Wake 没有 operation 写入；保留 `0..1`。
- verbose prompt：promptless malformed proposal 同样由 `stage_deliberation` / Host schema 拒绝，说明低级 action 数量约束不应依赖模型记忆。真实 Hermes Provider 的“缩短 prompt 后自然成功率/重试率”实验尚未执行，因此保留 `wake_id`、tool target、offer schema 和 stop-after-tool 提示，不把静态 prompt 证据写成 live 结果。
- authored maneuvers：删除 `prepare_force` 的开发副本必须同步删除所有 conflict 引用；即便如此，`enter-shanhai-pass` 仍要求自有 force 为 `READY`，而没有任何剩余 source-defined operation 能生成该状态。该 maneuver 是 load-bearing 场景边界，不是 generic balance cost，保留。
- fixed pressure：Pack/pressure source test 保留 tick 5 `EXOGENOUS` pressure；没有 Provider/strong-agent 的情况下未宣称“禁用 pressure 后自主策略更好”的游戏结果，避免把静态状态差异冒充 trajectory ablation。

定向 ablation tests：`tests/test_v6_harness_ablation.py` 2 passed。上述结果只授权保留或删除 harness scaffold 的最小判断；未授权删除任何 frozen Perspective、private Knowledge、Host authority、atomicity、idempotency、causal parent、message latency 或 restart invariant。

## Phase 10 V6 Game Tests

新增 `tests/test_v6_game_proofs.py`，只做小而强的 deterministic probes，不建立 benchmark 平台：

- Perfect Wait：无主体行动的 Shanhai / Nanjing fixture 都能在有限 simulation boundary 内推进，不因“等待”死锁；
- Canonicality perturbation：只改变南京 actor-visible 的 court / recognition state，Han 的真实 operation affordance 随之变化，不机械复用原路径；
- Role-State Swap：同一 Attention policy 在相同 Course / Knowledge / dependency 下交换 seat label，结果保持一致，说明 policy 不以名字猜历史角色；
- Continuous Agency、Attention precision、Agency Conservation、Shanhai remote transport 与 Nanjing resolution 由各 Phase 专项测试共同覆盖。

Phase 10 定向测试 4 passed；证据仍是 fixture / Pack / pure policy，不等价于强模型真人试玩或 real Hermes trajectory。

## Phase 11 Archive / UX

Archive 的 selected Lifetime replay 现在从 append-only `DECISION_HORIZON_ESTABLISHED`、`DECISION_HORIZON_REVISED` 和 `DECISION_HORIZON_HELD` 重建 `judgment_history`。每个条目只投影已经落下的判断：此前的打算、这次决定、为什么在此刻重新判断、后来进入所知的事实和之后留下的公开后果；不存储或显示 chain-of-thought、候选方案、Wake/Profile/Session 等执行术语。

前端 Archive 将公共回看、人生回看和判断回看分层呈现，保留显式选择 Lifetime 才加载私有 replay。新增 `.judgment-history` 响应式布局，并在 1440、1280、768、390 宽度上验证 `document/body.scrollWidth == innerWidth`；页面文本未出现 `Profile`、`Session`、`Memory`、`Wake`、`Runtime`、`Agent is thinking` 等内部术语，也没有错误日志。

证据：`tests/test_v6_archive_history.py` 覆盖 Ledger 重建和内部字段隔离；完整 `uv run pytest -q` 为 357 tests passed，Ruff、compileall、JS syntax、diff check 均通过；隔离 fixture server `127.0.0.1:18880` 的 sealed Worldline `worldline-2d4eaec1219045d0` 通过 Archive → 吴三桂判断回看浏览器检查。该证据仍是 deterministic fixture/API 与浏览器产品证据，不替代 Phase 12 real Hermes 业务链。

## Phase 12 Real Hermes live acceptance

2026-08-13 在全新临时 SQLite、Hermes Home 与 `127.0.0.1:18882` Gateway 上执行 Volume acceptance，使用真实 Provider，但没有把凭据写入仓库或证据。`worldline-558ea78dc4154343` 的六个 Lifetime Profile 均 materialize；产品路径完成 Human 吴三桂建立 Course、Leave、无关消息进入 Knowledge 但形成 `BACKGROUND`、多尔衮真实独立 Deliberation、相关消息使吴 `REOPEN`、吴重新进入并 HOLD、山海关与南京 Crisis 结算、结构边界、Archive 与 Seal。

脱敏摘要：`ATTENTION_EVALUATED=12`、`DELIBERATION_COMMITTED=7`、`MESSAGE_DELIVERED=7`、`MESSAGE_DISPATCHED=7`、`TIME_ADVANCED=10`、`MOMENT_COMMITTED=5`；吴三桂 Attention 序列为 `REOPEN → BACKGROUND → REOPEN → BACKGROUND`，`wu_background_without_wake=true`、`wu_reopen=true`、`wu_v6_deliberation=true`、`dorgon_independent=true`。selected Wu Archive judgment history 为 3 条；最终 `SEALED`、bindings `REVOKED`，Profiles 与 Gateway owner 已清理，端口与临时目录无残留。

该运行证明的是一条隔离 real Hermes 业务链和 cleanup 闸门，不是 Provider 稳定性 benchmark，也不替代真人产品问卷。真人验收仍保持“未收集、不可伪造”的边界。

## V6 thesis

V5 让同一人跨离席、Session 与重启继续存在；V6 让该人已形成的判断跨时间继续有效。一个 Lifetime 的 Current Course 只有在 actor-known 的现实真正改变其基础时，才经 deterministic Attention 打开新的 Deliberation；信息进入 Knowledge 本身不等于重新计算。

## Non-goals

- 不重写 Volume Runtime、World、Hermes Profile/Session 或前端框架。
- 不增加平行 V6 Runtime、generic workflow/DSL、Attention Agent、Planner/World Master、Memory V2、评分/关系系统或在线自演化。
- 不用 fixture、health、静态页面或 Agent 自述替代 real Hermes / 真人验收事实。

## Phase status

| Phase | 状态 | 说明 |
| --- | --- | --- |
| 0 Baseline | COMPLETE | V6 文档、实际 V5 baseline 与 staged scope review 已完成；本 commit 只包含此 Phase |
| 1 Characterization + seam | COMPLETE | V5 wake、Current Plan、MCP 单写入与 `/continue` 单推进已由 6 项特征测试固定；未作生产语义变更 |
| 2 Decision Horizon | COMPLETE | `plan[0]` 原位升级为唯一 Course、typed dependencies、established/last-deliberated Ledger 边界与 V5 read compatibility 已验证 |
| 3 Knowledge / Attention | COMPLETE | Knowledge admission 与 deterministic BACKGROUND/REOPEN 已分离；无关消息与预期操作不再直接创建 Wake |
| 4 Context Compiler | COMPLETE | Frozen Perspective 增加 reality-first 六段；contrary background fact 保留，旧 V5 bounded context 与 privacy 边界保持 |
| 5 Deliberation Protocol | COMPLETE | `commit_deliberation` 支持 HOLD/REVISE、证据门槛、typed dependency update、0..1 action 与 restart-safe atomic commit |
| 6 Product Continuous Agency | COMPLETE | bounded `/continue`、Human voluntary reconsideration 与 Life Desk V6 投影已实现；定向 fixture/product checks 通过，live Hermes / browser acceptance 留在后续 gate |
| 7 Agency Conservation | COMPLETE | Source/Pack ownership audit 与越权/因果链测试通过；未发现需要生产语义修复的问题，因此不新增 architecture layer |
| 8 Content / World Correctness | COMPLETE | Remote Offer/Agreement obey route-delivery causality; Shanhai fixed operation/pressure and Nanjing source bounds have regression evidence |
| 9 Harness Ablation | COMPLETE | One-action and authored-maneuver ablations are source/Host bounded; prompt and autonomous fixed-pressure Provider experiments remain explicitly unrun |
| 10 V6 Game Tests | COMPLETE | Perfect Wait, canonicality perturbation, role-state swap and Shanhai/Nanjing causal probes pass; Phase 12 adds one isolated real Volume trajectory with 7 Deliberations |
| 11 Archive / UX | COMPLETE | Append-only judgment history projection, Chinese product copy, and 1440/1280/768/390 no-overflow/browser checks pass; evidence remains fixture/API/browser |
| 12 Real Hermes live acceptance | COMPLETE | Isolated six-Lifetime Volume run completed through Course/Leave, background Knowledge, independent real Deliberation, Attention reopen, Human re-entry, Shanhai/Nanjing settlement, Archive, Seal and exact cleanup; no secrets recorded |

## Open questions

- V6 typed dependency 最小集合将以现有甲申两类 Crisis 的实际事件/操作为准；不因预设清单而引入未使用类型。
- Phase 8 的 remote Offer/Agreement、fixed pressure 与南京 ownership 只在 source-first characterization/实验支持时改变。
- Phase 12 依赖可用 Provider/Hermes 环境；在运行前必须重新核对并隔离资源。

## Experiments

- Phase 9 已执行 Host one-action 与 authored-maneuver ablation；Prompt shortening 与 autonomous fixed-pressure trajectory ablation因当前无真实 Provider 证据而明确未运行，未据此删除保护或 content scaffold。

## Accepted decisions

- 复用 `Lifetime.plan[0]` 作为 V6 Current Course 的优先落点，先升级 schema，不新建 Horizon table。
- 保留 exact wake identity、frozen Perspective、Host authority、atomicity、idempotency、message latency 和 restart safety。
- 原工作树的 `tmp/` 不属于本任务；实现仅在干净 `dev_v6` worktree 进行。

## Rejected decisions

- 建立 `V6Runtime`、`ContinuousAgencyEngine`、`NewWorldRuntime`、`NewAgentRuntime` 或 `V6Worldline`。
- 用 LLM 判断 attention、世界效果或其他 Subject 的选择。
- 把 V5 P5 的缺失真人验收伪造为 PASS。

## Final repair delta — 2026-08-13

第二轮审查后的修复保持在现有 Volume Runtime、Host、MCP 与前端边界内，未新增平行 Runtime、DSL、Registry 或 World Master。新增的语义提交为：

- `8769013`：同一主体在同一 Logical Moment 收到 checkpoint 与 Attention Wake 时，`wake_id` 参与 intent event identity；两个合法 Wake 不再因同 seat/tick 冲突而破坏 atomic commit。
- `d2de819`、`bbaf2e9`：迟激活 Crisis 的 Operation/Investigation 先按 Crisis `local_tick` 校验，再换算回 Volume global tick；起始与 commit revalidation 使用同一规则。
- `67be2e2`：Nanjing 在 `URGENT` pressure 下仍保留首个合法召集程序；回归测试锁定该可达性。
- `28f1be1`、`6e0cdd5`、`aab002c`：真实 deliberation schema、Course/dependency 前置与结构化 evidence 示例与当前冻结上下文一致，不猜测 `event_id` 或使用未允许的 dependency type。
- `d356824`：初始 Human checkpoint 的 freeze 逻辑只在存在完整 Volume snapshot 时运行；缺少 snapshot 的旧最小 transition fixture 仍返回原 controller transition，不削弱 live Volume 的 fail-closed snapshot 合同。

## Final isolated real Hermes acceptance — r11

在最新源码上重新执行了独占临时 SQLite、Hermes Home、产品端口 `127.0.0.1:18786` 与 Gateway 端口 `127.0.0.1:18886` 的 real Hermes Volume。真实 Worldline 为 `worldline-f44420f2821e42b3`，未使用项目默认数据库、全局 Hermes Home、SQL 手工 mutation、直接消息注入或 acceptance-only `settle_crisis`。

- 浏览器先建立吴三桂的非空中文 Course，Leave 后重新 Inhabit，Course 与历史判断持续存在；Archive 页面显示“已封存”，打开公共回看并明确选择吴三桂后可看到判断回看。
- 六个真实 Hermes Subjects 都 materialize 并完成 fresh-session wake；最终 Ledger 有 `DELIBERATION_COMMITTED=25`、`ATTENTION_EVALUATED=32`、`DECISION_HORIZON_HELD=6`、`DECISION_HORIZON_REVISED=13`、`MESSAGE_DISPATCHED=8`、`MESSAGE_DELIVERED=8`、`OPERATION_STARTED=7`、`OPERATION_COMPLETED=7`、`AGREEMENT_CREATED=1` 和 `MOMENT_COMMITTED=13`。
- 吴三桂的可复核序列为 `BACKGROUND → REOPEN → HOLD`：无关已知事实没有制造 cognition，山海关结构压力打开 Attention，新的 real Hermes Wake 保留原 Course 并 HOLD。多尔衮与李自成分别在自己的事实边界中 REVISE；南京中韩、史、马主体独立完成召集、潞王入场、军政 backing、Offer/Agreement 与潞王监国程序。
- 同一 Volume 的三条 Crisis 均通过现有统一 Global/Local clock 与 deterministic resolution 到达结果：山海关 `WINDOW_EXPIRED_DEFERRED`（tick 5）、南京 `LU_RECOGNIZED`（tick 14）、南方 `JIANGBEI_COORDINATION`（tick 18）。不存在未结 Knot，boundary policy 返回 `structural_boundary` 后 Seal 成功。
- Seal 回执为 `VOLUME_SEALED`，Worldline 为 `SEALED/ARCHIVED`，六条 bindings 为 `REVOKED`；Profile 目录为空，Gateway owner 文件与 `18786/18886` 监听均不存在。可恢复的完整临时证据目录已移入 `/Users/koala/.Trash/chronicle-v6-live.r11-complete-20260813`，没有进入 Git。

上述是一条真实 Provider 轨迹，不是稳定性或统计 benchmark；没有保存 provider response、prompt、token 或 private Memory。真人产品五问仍为 `UNCOLLECTED`。

## Final evidence boundary

Phase 9 四组 ablation 现在均有可重跑的结果：`tests/test_v6_harness_ablation.py` 为 4 passed。one-action 与 authored-maneuver 证明生产约束应保留；prompt-complexity 与 fixed-pressure 在 Host/Pack 边界执行并证明约束/压力的 load-bearing 结果，未把它们升级为 Provider 成功率实验，因此协议提示、固定压力和所有永久安全 invariant 均保留。Phase 10 的 Perfect Wait、Canonicality perturbation、Role-State swap 为 deterministic probes；r11 提供同一 Volume 的 Shanhai/Nanjing real trajectory。它们共同满足 P9 的可复核分层证据，但不替代真人判断或多次 Provider benchmark。
