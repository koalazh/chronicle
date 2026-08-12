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

## Phase 7 ownership audit boundary

Agency audit 的分类结果保持在现有 Pack / Host contract 内：`SUBJECT` 只能通过自己的 authority 与 owned/delegated target 发起 action；`AGREEMENT` 由双方可见的结构化承诺建立并以其事件作为后续 action 的前置；`INSTITUTION` 只在来源支持的 procedure operation 中变化；`DETERMINISTIC_WORLD` / `RESOLUTION` 继续由 Host / resolver 改写。南京候选仍是 Claimant entity，不因 entry operation 变成可被 Host 代演的 Persistent Lifetime；山海关的 movement / pass 仍由 actor authority、route 和 agreement 约束。

Phase 7 没有发现需要补一层 generic agency system 的真实缺口。越权尝试必须在 staging 前拒绝，合法 operation 的 state effect 必须保留 actor seat 与 causal parent；这些边界由 `tests/test_v6_agency_conservation.py` 固定。

## Phase 8 content / world correctness boundary

Offer 与 Agreement 不再沿用 V5 的同 tick / `tick+1` wake scaffold。发送方提交后只产生一条带 `offer_id`、`offer_action` 和真实 `arrival_tick` 的 `volume_offer` Message；提案从当前位置到收件人当前位置沿 Pack route graph 计算 travel days，响应也必须沿反向路线返回。消息抵达前，收件人看不到 Offer、不能回应，原 Offer 也不能创建 Agreement；接受、拒绝、withdraw 或 counter 只在回应 Message 抵达时改变状态。只有结构化 `OFFER_CHANGED` 才进入 Attention，普通背景 Message 仍走原有 Knowledge → Attention policy。

Agreement 的 `effective_tick` 是回应抵达的 global tick，而非提交 tick；Offer / counter lineage、`MESSAGE_DISPATCHED` → `MESSAGE_DELIVERED` → `OFFER_*` → `AGREEMENT_CREATED` 保留可复核 causal chain。过期或无 route 是 World refusal，不被包装成模型失败。

来源审计结果：山海关 `prepare_force` 仍按 Pack 的 2 日固定完成，不添加未经来源支持的“平衡代价”；`eastern-transit-window-narrows` 仍是 tick 5 的外生 scenario pressure（`c015`）。南京候选、backing 与 fragmented resolver 不因本阶段的 transport 修复扩大为 Lifetime、全体同意或额外机构。

定向证据位于 `tests/test_v6_content_world.py`，并与 `tests/test_v6_agency_conservation.py`、既有 Volume offer/Attention 测试一起复跑。它证明 deterministic source/fixture boundary，不证明 provider、browser 或 real Hermes。

## Phase 9 harness ablation boundary

| Experiment | Result | Decision |
| --- | --- | --- |
| `0..1` action vs multiple blind-staged actions | Host/schema 在无 prompt 帮助的直接调用中拒绝第二个 action，且没有 staged operation | 保留 `0..1`；它是 atomic cognitive boundary，未观察到可授权放宽的 coherence / spam 证据 |
| verbose prompt reduction | promptless malformed two-action proposal 仍 fail-closed；真实 Provider 的成功率、重试率、协议错误分布尚未采样 | 保留现有低级协议提示，直到有隔离 real Hermes ablation；不把 fixture 拒绝当成模型行为 PASS |
| authored maneuvers | 去掉 `prepare_force` 后需删除冲突引用才能让 Pack 通过，且 `enter-shanhai-pass` 仍无可达 `READY` 生产路径 | 保留 source-defined maneuver；不把它重写成通用平衡代价 |
| fixed pressure | tick 5 pressure 的来源与确定性 effect 已验证；没有 strong-agent / Provider trajectory 实验 | 保留 `eastern-transit-window-narrows`，不宣称禁用后自然策略结果 |

Phase 9 的“未运行”是证据边界，不是静默跳过：Prompt 与 autonomous fixed-pressure ablation 需要隔离 real Hermes Provider，留待 Phase 12；在此之前不能据此删掉 protocol 或 content scaffold。永久 invariants（frozen Perspective、private Knowledge、Host authority、atomicity、idempotency、causal chain、message latency、restart safety、cleanup）不参与消融。

## Phase 10 game-proof boundary

`tests/test_v6_game_proofs.py` 将 game proof 限定为四个可重跑的小测试：Perfect Wait 的有限推进、南京状态扰动导致 affordance 变化、相同状态交换 seat label 后 Attention 结果不变，以及 fixture boundary 的明确声明。Continuous Agency / Attention / Agency Conservation / Shanhai / Nanjing 则引用对应 Phase 测试，不另造 benchmark 或评分平台。

这些测试证明 Host/Pack/policy 的结构性边界；它们不替代 stronger Agent 的 Canonical History paired run、Role-State live swap 或真人选择结果。后者必须在隔离 real Hermes acceptance 中单独记录。

## Phase 11 Archive projection boundary

`judgment_history` 是 Archive 的只读派生投影，不增加表、不回写 `plan_json`，也不把可变的 `Lifetime.plan[0]` 当作历史。它按 Lifetime seat 过滤 append-only Horizon events，并用 public-safe event copy 组织为“此前 / 这次决定 / 后来知道 / 之后发生”；事件 ID 只作为稳定的 API 标识，不进入页面文案。

selected Lifetime replay 仍必须由用户显式选择；公共回看不会加载其他 Lifetime 的 Course、Belief、Knowledge 或判断史。没有 Horizon event 的 Lifetime 返回空历史，而不是从当前 Course 猜测过去。浏览器布局检查只证明 fixture/API 的产品边界，不证明 live Hermes 状态。

## 数据迁移策略

- 优先将已有 `plan[0]` 升级为唯一 Current Course，而不是新建 Horizon 表。
- 历史 Course 通过 append-only Ledger 的 `DECISION_HORIZON_*` 事件重建；不存 chain-of-thought、候选方案或隐藏评分。
- migration 保持 additive、backup-first、repeat-open idempotency，保留旧 V3/V4 compatibility 和未知物理表。
- 现有 `knowledge_json` 必须继续接收合法已知事实；Attention 只决定是否创建 cognition boundary，不能丢弃 Knowledge。

## 尚未验证的迁移结论

- typed dependency 的实际最小类型集合；
- 山海关 authored maneuver / one-action / prompt 复杂度是否可删除或必须保留；
- 南京 aggregate backing、候选进入与 fragmented resolver 的最小真实建模。

## Phase 12 live migration boundary (2026-08-13)

V6 迁移语义在一条隔离 real Hermes Volume 上完成复核：六个 Lifetime 的既有 Profile/binding 仍由 Volume Runtime 持有；Course、Knowledge、Attention、Deliberation、Human controller handoff、Archive 与 Seal 没有新增平行表或 Runtime。`worldline-558ea78dc4154343` 的消息抵达、背景事实、相关现实重开与 7 次真实 Deliberation 均落在同一 global clock 与 append-only Ledger 中。

本次只使用临时 SQLite、Hermes Home 和 loopback Gateway；封存后 bindings 为 `REVOKED`，所属 Profiles、MCP entries、Gateway owner 与 `18882` 监听均清理。该记录证明当前迁移在真实 Volume 链上可运行；Provider 的跨运行稳定性和真人产品回答仍不是迁移结论。
