# Chronicle V6 Migration Boundary

本文档区分永久 World invariant 与 V5 Harness scaffold。它只记录 V6 迁移边界与实验结论，不建立 Harness Registry 或新的 framework。

## 原则

V6 改的是现有 Volume Runtime 的认知时间语义，不重造 V5。Agent 可以形成和修订判断；Host 继续拥有时间、可见性、Knowledge admission、权限、World effects、原子 commit 与 Resolution。

| V5 约束 | 为什么存在 | 永久 invariant? | V6 怎么处理 |
| --- | --- | ---: | --- |
| frozen Perspective | epistemic correctness / same-moment blindness | Yes | 保留；V6 Context 在冻结前按 Reality-first 组织 |
| atomic Logical Moment | causal correctness / exactly-once | Yes | 保留，协议演进为 one staged deliberation commit |
| exact wake identity | execution correctness | Yes | 保留；改变的是为什么创建 Wake |
| Host validates effects | Agency / safety | Yes | 保留并专项审计 causal ownership |
| message travel | causal / temporal correctness | Yes | 保留，Offer/Agreement 必须服从同一 World transport |
| Profile = cognitive home; Session = temporary cognition | continuous identity | Yes | 保留 fresh Session，不用聊天历史替代 Course |
| one action per Wake | V5 model/harness scaffold | No | Phase 5 先验证 0..1 new World action；Phase 9 才做受控 ablation |
| generic result → Wake | V5 interaction model | No | 拆为 Knowledge admission → deterministic Attention（BACKGROUND / REOPEN） |
| verbose protocol prompt | model scaffold | No | 先把硬规则移到 Host/schema/MCP，后期在不削弱安全性的前提下实验 |
| fixed Shanhai pressure | content pacing | Unknown | Source-first ablation；只有真实结构必要时保留 |

## Phase 1 observed baseline

- 当前 V5 将 message、operation completion、investigation observation 直接从 Knowledge admission 连到 Wake；Phase 3 必须在不丢失 Knowledge 的前提下切开这个耦合。
- 当前 `plan[0]` 是唯一对 Lifetime Context 可见的 Current Plan，且 `reconsider_when` 是 prose；Phase 2 在该字段原位升级，不建 parallel Horizon store。
- 当前 Volume MCP 把“一 Wake 一个世界写入”作为 harness 约束；Phase 5 先把 commit schema 固化为 `0..1` action，Phase 9 才依据实验决定是否消减具体 prompt / tool scaffolding。
- 当前 `/continue` 一次 request 只做一次 Global advance；Phase 6 可在不改变 Host-owned single advance 原子边界的前提下循环至有意义的人类 Attention。

## Phase 2 data migration

V6 不增加物理 Horizon table，也不递增 SQLite schema version；`worldline_lifetimes.plan_json` 已能承载一个 JSON Course。新写入始终替换为单元素列表 `[course]`，因此旧 Course 历史只留在 append-only Ledger，不能被 mutable list 覆盖。

| Existing V5 data | V6 read behaviour | V6 write behaviour |
| --- | --- | --- |
| `plan == []` | no Current Course | 首次 `update_plan` 建立 `[course]` 与 `DECISION_HORIZON_ESTABLISHED` |
| `plan[0]` only has V5 fields | 只读投影 `course=objective`、`IN_FORCE`、empty typed dependencies；不回写 | 下次合法 Course 写入替换为完整 V6 shape，并追加 `DECISION_HORIZON_REVISED` |
| V5 `reconsider_when` prose | 继续对旧 consumer 可见，但不作为 machine predicate | 新 machine-visible condition 只写 `open_dependencies` allow-list |

`open_dependencies` 只允许实际 Volume 已有的消息、调查、操作、offer/agreement、实体变化与 deadline 事实 ID/tick；没有 free-form predicate、nested DSL、LLM relevance 或自动行动。依赖只会在 Phase 3 作为重新思考资格，绝不直接提交世界动作。

## Phase 3 attention boundary

`knowledge_json` 仍是事实 admission 的唯一持久位置；Attention 没有新表，也不写 Course。每个有新事实的 Lifetime 在同一 global tick 只有一次 `ATTENTION_EVALUATED` Ledger record：

| Admission | No matching Course condition | Matching condition |
| --- | --- | --- |
| delivered message | `BACKGROUND`，事实留在 Knowledge | `MESSAGE_FROM` → `REOPEN` |
| operation completion | 预期结果 `BACKGROUND`，事实留在 Knowledge | `OPERATION_OUTCOME` / observed entity change → `REOPEN` |
| investigation observation | `BACKGROUND`，事实留在 Knowledge | `OBSERVATION_FOR` → `REOPEN` |
| Course deadline | 无此分支 | Host 记录 `DECISION_DEPENDENCY_DUE`，admit 后 `REOPEN` |

首次进入 Knowledge 而尚无 Course 的 Lifetime 以 `NO_CURRENT_COURSE` 重开，以建立第一个判断。`REOPEN` 仅授权新的 Deliberation；它不自动发送消息、接受 Offer、执行操作或替任何 Subject 作选择。Offer / Agreement notification 要等 Phase 8 接入真实 transport 后再进入这张表。

## Phase 4 reality-first context

Context 仍由原有 `LifetimeContextBuilder` 在冻结时构造，没有新表或平行 Perspective runtime。V6 section 顺序为：

```text
why_now
since_last_deliberation
binding_reality
previous_course
relevant_experience
affordances
```

`since_last_deliberation` 使用 Course 的 typed `last_deliberated_tick`，不是 last Wake；因此没有 Wake 的 Background Knowledge 也不会消失。`binding_reality` 和 `affordances` 先于 token relevance / private memory 计算，当前 Course 不得过滤与之相反的 actor-known fact。所有 operation、investigation、offer term 都继续由现有 pack 的主体可见性与能力函数提供，其他 Lifetime 的私有 Knowledge 不进入这些 sections。

## Phase 5 deliberation boundary

`commit_deliberation` 是开发层 staging contract，不是新的用户领域对象。它必须绑定当前 Volume、Lifetime、Pending Logical Moment 与 exact Wake：

| Proposal | Host result |
| --- | --- |
| `HOLD` + 0 action | Course remains in force; append `DELIBERATION_COMMITTED` and `DECISION_HORIZON_HELD`; advance last-deliberated boundary |
| `REVISE` + 0 action | replace the single Course; Agent must cite actor-visible evidence; append revised horizon Ledger events |
| either + 1 action | validate existing capability and commit the one action with the Deliberation event as causal parent |
| malformed / unauthorized / 2 actions / invalid effect | reject before staging, with no partial World or Course write |

`belief_updates` remain evidence-backed and private. Existing V5 logical intent and direct World-tool paths remain readable for compatibility, but the V6 live prompt advertises one complete `commit_deliberation`; a model cannot obtain an action by probing multiple rejected proposals in one frozen moment. Restart finds the same one staged `commit_deliberation` operation and retries it idempotently.

## Phase 6 continuous product boundary

`/continue` 只循环已有的 `advance_one`，不把时间推进交给前端、不创建后台 daemon，也不让 Agent 绕过 Pending Logical Moment。每个 request 先处理已有 Human Attention，再处理同 tick Agent Wakes；随后按 Volume boundary、tick / Agent / wall-clock cap、Global Tick、due Wake 与 meaningful knot boundary 的顺序停止或继续。cap 返回当前合法状态，下一次 request 继续。

`/decision` 的自然语言输入是 Human-owned `REVISE`；已有 Course 的空白输入是 `HOLD`。没有 Human Attention 时，Host 在当前 tick 只为当前 inhabited Lifetime 建立一次 voluntary boundary；它不产生 `TIME_ADVANCED`，不调用 Hermes，也不改变其他 Subject 的待处理 Wake。V5 `wait`、`update_plan`、`message` intent 仍保留兼容路径。

Life Desk 的新增投影来自同一个 actor-scoped `LifetimeContextBuilder`，不新建页面或平行状态：此前 Course、deliberation 后的 Knowledge、reopen 的真实事实、binding reality 和 uncertainty。内部 `reason_code`、Wake、Profile、Hermes、MCP 等字段不进入产品投影。

## 数据迁移策略

- 优先将已有 `plan[0]` 升级为唯一 Current Course，而不是新建 Horizon 表。
- 历史 Course 通过 append-only Ledger 的 `DECISION_HORIZON_*` 事件重建；不存 chain-of-thought、候选方案或隐藏评分。
- migration 保持 additive、backup-first、repeat-open idempotency，保留旧 V3/V4 compatibility 和未知物理表。
- 现有 `knowledge_json` 必须继续接收合法已知事实；Attention 只决定是否创建 cognition boundary，不能丢弃 Knowledge。

## 尚未验证的迁移结论

- typed dependency 的实际最小类型集合；
- remote Offer/Agreement 的精确 transport 实现；
- 山海关 fixed pressure / authored maneuver / one-action / prompt 复杂度是否可删除或必须保留；
- 南京 aggregate backing、候选进入与 fragmented resolver 的最小真实建模。
