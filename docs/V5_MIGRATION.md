# Chronicle V5 Migration Boundary

本文档是 V5 Phase 0 的迁移边界，不是第二套产品设计。它把
`/Users/koala/study/note/work/product/历史模拟/Chronicle-V5.md` 中的
KEEP / GENERALIZE / REPLACE / DEFER 固化为当前仓库可以逐阶段验证的约束。

## Phase 0 baseline

基线建立于 `dev_v5`，HEAD 为 `0cc445daa9c57b6f2db97b135aea09d38d07802d`。基线前工作树干净，未先修改功能。

以下检查均以当前仓库执行并以退出码 0 结束：

- `uv run chronicle source validate`
- `uv run chronicle scenario validate`
- `uv run chronicle crisis validate`
- `uv run pytest -q`
- `uv run ruff check .`
- `git ls-files '*.js' | xargs -n1 node --check`
- `git diff --check`

validator 输出确认当前 Source Pack、Scenario Pack 和 `jiashen` Volume 有效；pytest 通过但保留既有依赖/框架 deprecation warnings，它们不属于本阶段 V5 改动。

## KEEP

V4 已经验证的基础继续作为唯一权威实现，不另建平行系统：

- append-only Ledger、完整 World Snapshot、causal parent edges；
- deterministic WorldService、Host validation、Agent/Human 共用世界写入口；
- tool request staging、idempotency、atomic moment commit；
- message travel、Investigation、Offer/Agreement、Operation、Pressure、Revisit；
- frozen Perspective、Agent↔Agent same logical moment concurrency、Reflection Memory rollback；
- Resolution Contract、SPATIAL/POLITICAL surface renderer；
- current Desk 文书式 UI、live Gateway ownership/reconcile/fail-closed；
- loopback/local single-user boundary、vanilla ES modules、input capture、mutation lock、unknown-result reconciliation。

V5 不重写 `WorldService`、Resolution resolver 或前端框架。若需要结构调整，先用 characterization tests 固定现有语义，再做最小抽取。

## GENERALIZE

### CrisisPack → VolumePack + CrisisEnvelope

`VolumePack` 成为 Volume-level content owner，承载 Lifetimes、shared world、shared routes、historical field events、crisis envelopes 和 volume boundary。现有 `CrisisPack` 保留为 crisis-local owner，继续承载 operations、investigations、offers、pressures、surface、resolution 和 crisis-local content。

### Actor → Lifetime

Crisis 只引用 `lifetime_id`。稳定的 genesis、起始知识/信念、资源、authority 和长期主体状态归 Volume Lifetime；危局特有的职责、压力和语境只作为 Crisis Context 注入 Perspective，不写回 SOUL 或重新 genesis 人物。

### Crisis time → Global World time

一个 Volume Worldline 只有一个 authoritative world tick。Crisis Instance 保存 `activation_tick`、`local_origin_tick` 和 phase；`local_tick` 只是派生值。Ledger 和事件排序始终使用 world tick，不能从代码方便虚构史料不支持的小时级先后。

### Run-oriented runtime → Volume-oriented runtime

保留现有物理表和兼容 abstraction 的可复用部分，但正式 V5 的生命周期根是 Volume Worldline。Crisis 只是其中一个 dense causal knot，不能拥有 Profile、World 或 cleanup 的最终所有权。

## REPLACE

### Worldline kind and Crisis Instance

- 新 V5 只创建 `VOLUME` worldline；旧 `CRISIS` worldline 仅用于 V4 archive/replay compatibility。
- 新增 Crisis Instance，状态至少覆盖 `DORMANT`、`ACTIVE`、`RESOLUTION_PENDING`、`AFTERMATH`、`SETTLED`、`SUPPRESSED`。
- Crisis settlement 只更新 Instance、持久化 world effects 和 Meaning；不得调用 worldline seal。只有 Volume archive/seal 才结束 Lifetimes、撤销 bindings、停止 Gateway 和清理 Profiles。

### Lifetime-scoped Profile

Profile 身份根改为 `worldline_id + lifetime_id`，marker 绑定 Volume content/version、genesis hash、runtime epoch 和 ownership。相同 Lifetime 跨 Crisis 复用同一个 Profile；不同 Worldline 永不共享 Profile 或 Memory。所有核心 Lifetime 在 Volume genesis materialize Profile，Human-controlled Life 的 Profile 也只是 dormant，不因 Human 而缺失。

### Cognition readiness

删除 mandatory ORIENT bootstrap 及 `initial_orient_completed` readiness 语义。Profile、Gateway、MCP ready 之后允许 0 次 LLM cognition；只有真实 trigger 才 queue wake。每次 Wake 继续使用 fresh Session，长期连续性来自 durable Lifetime state，而非聊天记录。

### Controller and presence

Human 与 Hermes 是同一 Lifetime 的互斥 Controller。Inhabit/Leave 只写 runtime/provenance metadata，不触发 wake、reflection、plan、belief、memory 或 simulation time。若离席时原 trigger 等待 Human，只能把同一 trigger 交给 Hermes。一个仍 ACTIVE Knot settle 前，已 inhabit 过其中 Participant A 的用户不得偷窥/进入 Participant B；其它独立 Knot 仍可进入。

### Human/Agent causal slice

世界时刻 T 先应用 deterministic due effects，再冻结 World@T 和每个需认知 Lifetime 的 Perspective。包含 Human 时，Human 与 Agent 均从同一 frozen world 解释并 stage，最终由 Host atomic commit；Human 不能先写世界让后续 Agent 看到违反因果的状态。Wall time 不计入 simulation time。

### Knowledge, learning and context

继续分离 Truth、Visibility、Knowledge、Belief、Plan 和 Memory。`belief_updates` 必须引用当时该 Lifetime 合法可见/可知的 evidence event；未明确的 Human 心理保持未知。使用 bounded `LifetimeContextBuilder`，只重建当前 trigger、角色 authority、义务、plan、due revisits、相关 beliefs/evidence 和有限近期知识，不 dump 全人生，不创建 Vector DB、Skill Evolution、Relationship score 或 Theory-of-Mind graph。

### Product and API ownership

正式 V5 语义从 Volume Home 进入 World、Follow、Inhabit、Life Desk、Leave、Archive；Crisis 不再是独立游戏目录。正式 API 使用 `/api/worldlines/...` 和当前 Human Lifetime 派生的 private desk，不让客户端任意传 `actor_id`。Legacy router 继续可读旧数据，新的 product/dev/legacy router 先分层，不把迁移 cleanup 与 domain rewrite 混在一起。

## DEFER

以下事项不是 V5 第一版 blocker，不能提前扩大范围：

- Session reuse/Hot Episode；
- 物理迁移 `crisis_wakes` 表或大规模改名；
- Vector DB、复杂 Presence progression、关系图、Skill Evolution、自动 skill extraction；
- 通用 history/workflow/visualization DSL、Agent Director/Team coordinator、free A2A mind-to-mind；
- mass Agent society、LLM World Master/Judge、完整策略/战斗 simulator；
- cross-worldline Compare 的新语义；
- dashboard、Agent observability、pressure/presence meter 和其它非用户价值的内部可视化。

Deferred 不等于允许在其它阶段隐式实现；若未来需要，必须另立边界和验收。

## V5 invariants

1. **Worldline root**：Volume Worldline 才拥有 Lifetime、Profile、Gateway、global clock 和最终 cleanup。
2. **Host authority**：Agent 只能解释世界并 stage intent；所有 objective writes、delivery、operation、agreement 和 time advancement 由 Host deterministic validation/atomic commit 控制。
3. **Causal visibility**：Truth 不等于 Visibility，Visibility 不等于 Knowledge；消息未送达前不能进入主体可用知识。
4. **Persistent subject**：Lifetime 跨 Session、Crisis、controller、dormancy、process restart；Profile 可以跨 Crisis 但不能跨 Worldline。
5. **No artificial cognition**：bootstrap ready 不要求 LLM；controller switch、周期 tick 和无因 reflection 不是 wake 原因。
6. **One controller**：同一 Lifetime 同一时刻只有 Human 或 Hermes 一个 Controller；用户一次只能 inhabit 一条 Lifetime。
7. **One clock**：所有 Crisis、Field Event、Message、Operation 和 Ledger 排序服从 Volume world tick。
8. **Atomic moment**：Human/Agent 对同一 Logical Moment 从同一 frozen Perspective stage，commit 前不产生半个历史，retry exactly-once。
9. **Evidence-backed subjectivity**：Belief/expectation 的变化可追溯到合法 evidence；Human 未说出的理由和心理不被伪造。
10. **Real propagation**：跨 Crisis 连接只通过 Message、Document、Declaration、Institution、Position、Control、Agreement 或 observable Operation result 等真实 World object。
11. **Source-bounded history**：新增历史事实必须有 source/assertion；史料不支持的桥梁缩小或留空，不用 Demo 编造。
12. **Product boundary**：普通 UI 只展示 public world/follow 和当前 inhabited Life 的 private desk，不暴露 omniscient private state、Agent/Profile/Runtime jargon 或 dashboard。

## Migration safety

- schema migration 继续 additive、先 backup、保留未知表和旧字段，并保持 repeat-open idempotency。
- 旧 SEALED V4 Crisis 保留 legacy replay/compare，不强行转换成 V5 Worldline。
- 旧 ACTIVE V4 Crisis 不做无损热转换；按现有 legacy migration 安全封存，标明旧 product generation。
- 新 V5 只创建 `VOLUME` worldline；新代码不得把旧 `CRISIS_SETTLED → RUN_SEALED` 语义带入 V5。

## Phase boundary

后续阶段遵守 V5 原文顺序：先 characterization 和模块抽取，再 schema、Volume content、Persistent Profiles、Inhabitation、Global Runtime、Pending Logical Moment、Subject Continuity、Braided 甲申、Product Shell、Archive/Ending，最后执行 acceptance/docs。每阶段都必须有可复核的相关测试和语义明确 local commit，不能把全部 V5 压成一个 commit，也不能为了数量拆无意义 commit。
