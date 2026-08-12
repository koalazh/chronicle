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
