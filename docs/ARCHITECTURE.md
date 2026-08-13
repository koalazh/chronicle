# Chronicle V5 架构

本文是当前 V5/V6 的架构入口。产品旅程见 [PRODUCT.md](../PRODUCT.md)，页面合同见 [FRONTEND.md](FRONTEND.md)，运行与验收见 [OPERATIONS.md](OPERATIONS.md) 和 [V6_ACCEPTANCE.md](V6_ACCEPTANCE.md)。旧 V3/V4 文档、旧 `/api/runs` 和 legacy router 只描述兼容边界，不再作为新 V5/V6 的设计来源。

## 一条因果链

```text
VolumePack
  ├─ shared World / Global World Tick
  ├─ persistent Lifetimes
  └─ Crisis envelopes
          ↓
Volume Worldline
          ↓
deterministic Host / VolumeRuntime
          ↓
frozen Perspective + Pending Logical Moment
          ↓
Human or Hermes intent staging
          ↓
Host validation + atomic commit
          ↓
append-only Ledger + Snapshot/Projection
          ↓
public World / private Life Desk / Archive
```

Host 拥有现实：时间、来源、位置、路线、消息抵达、权限、资源、状态效果、幂等和最终提交。Lifetime 拥有主体性：解释可见上下文、等待、通信、更新计划、安排有限的下一步和选择长期经验。没有一个中央模型替所有 Lifetime 决定世界结局。

## V5 核心对象

| 对象 | 唯一职责 | 持久边界 |
| --- | --- | --- |
| `VolumePack` | Volume 的来源、Lifetime、共享 World、Field Event、Crisis 引用和 boundary 条件 | `scenarios/jiashen` |
| `Volume Worldline` | 一次完整卷册经历的生命周期根 | `worldlines.kind = VOLUME` |
| `Lifetime` | 跨 Crisis、Session、controller 和离席持续的主体身份与 Life State | `worldline_id + lifetime_id` |
| `Crisis Instance` | 一个局部 causal knot 的 activation、phase、参与者和 settlement | 属于 Volume Worldline |
| `Profile` | Lifetime 的执行资源和认知 home | 同一 Volume 内复用；不同 Worldline 永不共享 |
| `Global World Tick` | 所有 Crisis、消息、Operation、Field Event 和 Ledger 的唯一时间排序 | Volume Worldline |
| `Logical Moment` | 同一 tick 的冻结上下文、主体 intents 和原子 commit 单元 | Pending projection + Ledger |
| `Archive` | 封存后的公共 replay 和选定 Lifetime replay | 只读；不重跑过去 |

V5 当前数据库保留迁移后的旧物理表和兼容字段，当前 schema version 是 `10`；物理表名不等于产品概念。增量迁移、未知表保留和旧数据安全边界见 [V5_MIGRATION.md](V5_MIGRATION.md)。

## 状态分层

```text
Truth / Projection
        ↓ visibility rules
Knowledge of one Lifetime
        ↓ interpretation
Belief / expectation
        ↓ deliberate planning
Plan / obligation / revisit
        ↓ optional long-term reflection
Memory
```

- Truth 是 Host 已提交的世界事实；Projection 是当前 tick 的可读派生状态。
- Visibility 决定某事实是否进入某个主体的合法上下文。
- Knowledge 只包含已经抵达或被合法观察到的事实；发出消息不等于收件人知道。
- Belief 和 Plan 是主体状态，不能被公共 World 当成事实。
- Memory 不是全量人生 dump；它只保存明确值得长期保留的主体经验。

产品读取时遵守三条边界：公共 `/world` 只读 public projection；`/follow` 只读选定 Lifetime 的可见入口；`/desk` 只读当前 Human Lifetime 的 private context。Host 不依赖前端隐藏来做权限控制。

## Volume 生命周期

### 创建

`VolumeRuntime.create()` 在一个新 `VOLUME` Worldline 中建立：

1. Volume genesis、所有 Lifetime genesis 和初始 Projection；
2. shared World、historical Field Event 和 Crisis Instance 的来源引用；
3. Profile binding 的持久 metadata；
4. 世界 tick 从 `0` 开始的 append-only Ledger/Snapshot。

创建先把 VolumePack 中的 Crisis references 注册为带 Envelope 元数据的 `DORMANT` Instance；Host 再按 `earliest_activation_tick`、结构性 activation preconditions、participants 和 local horizon 做确定性 reconcile。当前 `before-shanhaiguan` 与 `nanjing-succession` 在初始 tick eligible，`southern-consolidation` 必须等南都定策 `SETTLED` 后才激活；若前置结构性条件消失，则写入 `SUPPRESSED`，不伪造可玩的 Crisis。Crisis 激活只建立局部实例和触发条件，不创建新的 World、Profile 或时钟。

### Restart reconcile

live V5 进程启动时，Host 不猜测或修复身份，而是 fail closed 地核对唯一 active Volume owner、每条 Lifetime/Profile、genesis marker、agent binding、private token、Volume MCP allowlist，以及未完成 Pending Logical Moment 中的 Wake/operation 归属。任何缺失、漂移、重复或不可恢复状态都会把 active Volume 标成 `FAILED`；sealed Volume 的 `CLEANUP_PENDING` 只重试属于它的 Gateway/Profile cleanup。

### Crisis settlement

Crisis 的 `SETTLED` 或 `SUPPRESSED` 只写入 Instance outcome、world effects 和 `CRISIS_SETTLED` Meaning。它不会写 `VOLUME_SEALED`，不会撤销 Lifetime binding，也不会清理 Profile。其他 Crisis 或 shared Field Event 仍可让同一卷册继续向前。

### Volume boundary

`VolumeBoundaryPolicy` 只在结构性条件满足时返回 ready。当前规则同时要求：

- 没有 Pending Logical Moment、queued/staged wake 或到期 wake；
- 没有在途消息和待应用 historical field；
- 没有后续 `next_tick`；
- 每个 Crisis Instance 都是 `SETTLED` 或 `SUPPRESSED`；
- required historical field 已实际应用。

安全 horizon 可以说明“尚未收束”的 fallback，却不能把未满足条件的卷册伪装成产品 Ending。Seal event 会记录 boundary policy、evidence event/assertion IDs 和 reason，之后才允许 Archive。

### V6 judgment history

Archive 的 selected Lifetime replay 通过 `chronicle/product_api.py` 从 append-only `DECISION_HORIZON_*` Ledger events 派生判断史。它只保留此前 Course、已提交的 HOLD/REVISE 结果、公开可解释的重新判断原因、后来进入 Knowledge 的事实和可见后果；不新增可变历史表，不暴露 chain-of-thought，也不让当前 `plan[0]` 覆盖过去。

### Seal 与清理

Volume seal 的原子边界是：

```text
VOLUME_SEALED
→ worldline status = SEALED / phase = ARCHIVED
→ Lifetime/Profile bindings revoked
→ queued wakes cancelled
→ live-owned Profiles and World MCP entries cleaned
```

物理清理是 seal 之后的可重试动作，不是历史的一部分。清理只能删除 marker 明确属于该 Worldline 的 Profile 和 server；不能接管未知进程、删除别的 Worldline 资源或覆盖用户的 Hermes Home。已经 sealed 的请求再次执行只重试清理并返回 idempotent 结果。

## Global Clock 与 Logical Moment

一个 Volume Worldline 只有一个 authoritative world tick。Crisis 的 `local_tick` 是从 activation tick 派生的显示值，不能改变 Ledger 的排序。

推进步骤固定为：

1. 应用该 tick 到期的 deterministic effects、消息和历史 Field Event；
2. 把所有需要主体处理的 wake 冻结为一个 Pending Logical Moment；
3. 为每个 Lifetime 构造当时合法的 Perspective；
4. Human 与 Agent 各自 stage intent，commit 前互不可见；
5. Host 统一校验、按稳定顺序提交并写入 causal parents；
6. 排入未来 tick 的消息、wake、Operation、revisit 或其他效果。

Human/Agent 执行顺序、网络 wall time 和模型响应快慢都不能改写同一 moment 的世界语义。相同 idempotency key 重试必须返回既有结果，而不是产生第二个世界效果。

## Runtime 与 Hermes 边界

### Fixture

`runtime_mode = fixture` 只在 `CHRONICLE_DEV=true` 或自动化中开放。当前产品 router 的 `resolve_agent_wakes()` 为 Agent wake 生成确定性 `wait`，用于验证 Host、消息、时钟、隐私、Pending Moment 和 Archive；它不是 Hermes 认知证明。

### Live（当前已实现的部分）

`runtime_mode = live` 会调用 `materialize_lifetime_profiles()`，按 `worldline_id + lifetime_id` 安装或校验 6 个 Lifetime Profile，写入 marker、Profile env、Volume-specific MCP configuration 和 durable binding metadata。真实 live preflight 已在隔离临时 Home 中验证 Profile routing、`memory`-only toolset、key isolation、fresh Session 和一次 chat。

### Live（当前已接通的最小链路）

V5 product router 的 live Agent Wake 现在由 `HermesVolumeActorDriver` 执行：从同一 Lifetime Profile 创建 fresh Session，读取 bounded frozen Perspective，经 Profile 专属 World MCP 的 `logical_intent` staging 提交一个 `wait`、`message` 或 `update_plan`，并继续由 V5 Host 完成 Pending Logical Moment 的 atomic commit。普通 Wake 的 Hermes Memory 发生变化会 rollback 并阻断；没有结构化意图也不会静默改成 `wait`。隔离 live harness 已通过一条真实 Wake 和 product `continue` 验证这条最小链路。

这段 V5 最小链路本身仍不等于旧 V5 P0–P5 全部验收；V4 的旧 `CrisisRunEngine`/`LiveRuntimeManager` 仍保留其兼容路径，不能代替 V5 proof gates。V6 Phase 12 已在另一条隔离 Volume 链上补充 Human↔Hermes handoff、Multi-Subject Attention/Deliberation、Shanhai/Nanjing trajectory、Archive 与 cleanup 证据；V5 P5 真人产品验收仍保持原边界。具体状态见 [V5_ACCEPTANCE.md](V5_ACCEPTANCE.md) 与 [V6_ACCEPTANCE.md](V6_ACCEPTANCE.md)。

这一区分很重要：Profile materialization、Gateway health、一次 chat 和 Doctor 都不能单独证明 P0 Subject continuity、P1 Multi-Subject、P2 Temporal、P3 Learning、P4 Game 或 P5 30-minute product proof。

## API ownership

正式 V5 路由集中在 `chronicle/product_api.py`：

| 层 | 入口 | 返回边界 |
| --- | --- | --- |
| Volume | `/api/worldlines`, `/active` | Volume metadata、public world、Lifetime list |
| Public World | `/{id}/world` | knots、public positions、公开状态和公共 attention |
| Follow | `/{id}/follow/{lifetime_id}` | selected Lifetime 的可见入口，不含其他私态 |
| Life Desk | `/{id}/desk` | 当前 inhabited Lifetime 的 private context |
| Mutation | `inhabit`, `leave`, `continue`, `decision` | Host-validated state transition |
| Archive | `/{id}/archive[?lifetime_id=...]` | public replay；可选一个 selected Lifetime replay |
| Ending | `/{id}/seal` | 仅 boundary ready 时写入 `VOLUME_SEALED` |

`entry_id` 传入 `/api/worldlines` 时才进入 V4 compatibility branch。`/api/runs`、旧 Compare 和旧 replay 继续用于 legacy 数据，但新 V5 UI 不依赖它们。

## V5 不做的架构扩张

当前架构不引入 generic history DSL、universal visualization DSL、Agent Director、Agent Team coordinator、free A2A mind-to-mind、relationship score/trust meter、Theory-of-Mind graph、skill extraction、cross-Lifetime skill sharing、cross-Worldline Profile sharing、daily forced tick、Agent observability dashboard、LLM World Master/Judge 或完整战斗模拟器。

## V6 final live trace

r11 的 `worldline-f44420f2821e42b3` 证明同一 `VOLUME` 根下的六个 Lifetime Profile、fresh Session、frozen Perspective、Attention、Deliberation、Operation、Offer/Agreement、Resolution、Archive 和 Seal 仍由上述同一 Host/Global Clock 链连接；未增加平行运行时。Seal 后 bindings `REVOKED`，Profile/MCP/Gateway cleanup 只针对该 Worldline。
