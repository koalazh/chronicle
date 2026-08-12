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
