# 当前架构

> 读者：开发者。本文解释系统内部如何保持世界、权限和因果的一致性；普通用户无需阅读，也不应把其中的代码名称当成产品词汇。

本文描述当前实现的唯一运行边界。多主体 Profile 的身份、协作传输和 Hermes 边界见 [多主体运行说明](MULTI_AGENT.md)。产品旅程见 [产品说明](../PRODUCT.md)，页面合同见 [前端](FRONTEND.md)，启动和验收见 [运维](OPERATIONS.md) 与 [当前验收](ACCEPTANCE.md)。历史迁移和阶段记录只在 [归档](archive/README.md) 中保留。

## 一条因果链

```text
VolumePack
  ├─ shared Shanhaiguan World / Global World Tick
  ├─ three persistent Lifetimes
  └─ one active Crisis envelope
          ↓
Volume Worldline
          ↓
Host / VolumeRuntime
          ↓
frozen Perspective + Pending Logical Moment
          ↓
Human or Hermes intent staging
          ↓
Host validation + atomic commit
          ↓
append-only Ledger + Snapshot/Projection
          ↓
Product Projection (read-only view compiler)
          ↓
World / Life / Past
```

Host 拥有现实：时间、来源、位置、路线、消息抵达、权限、资源、状态效果、幂等和最终提交。Lifetime 拥有主体性：解释可见上下文、等待、通信、更新计划、安排有限的下一步和选择长期经验。没有一个中央模型替所有 Lifetime 决定世界结局。

## 产品层边界（本轮冻结）

产品层只建立三个用户心智空间：

| 空间 | 只回答什么 | 主要来源 |
| --- | --- | --- |
| 世界 | 现在仍没有定下来的问题、已经成为现实的公开结果、谁在其中 | authored Pack + current Snapshot + public-safe Ledger consequence |
| 这一生 | 当前人物当时知道什么、已有判断是否仍生效、何时真正需要重新判断 | frozen bounded perspective + current Lifetime state |
| 过去 | 这一卷最后成为什么、谁让哪些事情成为现实、某段人生如何判断 | sealed Snapshot + Ledger + Pack 的 deterministic projection |

`chronicle/product_projection.py` 是只读 view compiler：它可以读取 Pack、Snapshot、Ledger 和窄的 Runtime read-only invariant，但不能写 DB、推进 World、创建 Wake、调用 Agent、预测结果或持久化 Product truth。无法可靠表达的事实必须少展示，不由 LLM 补写。

`chronicle/product_api.py` 保留路由、编排、Runtime 调用、Assist 调用和错误分类；`chronicle/product_assist.py`（若启用）只提供两个 stateless、bounded、non-authoritative 能力：参考草稿和 0..1 个行动候选。主产品前端不自动请求参考草稿；人工判断的可选行动候选有 2 秒上限，超时直接保存用户判断。Assist 不拥有 Profile、Session、Memory、MCP、World token、Ledger event 或确认权。

产品不新增 V8、平行 Runtime、History model、Product Projection persistence、Agent dashboard、Human tool picker、Dynamic Knot、new Wake、new Attention、compatibility/replay runtime 或大型前端框架。前端不能复制 Runtime authority、presence、attention、message、boundary 或隐私规则。

## 核心对象

| 对象 | 唯一职责 | 持久边界 |
| --- | --- | --- |
| `VolumePack` | 来源、Lifetime、共享 World、Field Event、危局引用和 boundary 条件 | `scenarios/jiashen` |
| `Volume Worldline` | 一次完整卷册经历的生命周期根 | `worldlines.kind = VOLUME` |
| `Lifetime` | 跨危局、Session、controller 和离席持续的主体身份与 Life State | `worldline_id + lifetime_id` |
| `Crisis Instance` | 局部因果 knot 的 activation、phase、参与者和 settlement | 属于 Volume Worldline |
| `Profile` | Lifetime 的执行资源和认知 home | 同一卷册内复用；不同卷册不共享 |
| `Global World Tick` | 所有危局、消息、Operation、Field Event 和 Ledger 的唯一时间排序 | Volume Worldline |
| `Logical Moment` | 同一 tick 的冻结上下文、主体 intent 和原子 commit 单元 | Pending projection + Ledger |
| `Archive` | 封存后的公共回看和选定 Lifetime 回看 | 只读；不重跑过去 |

数据库当前只创建和使用当前 Volume 所需的表。既有 schema `10` 数据库只做一次窄的物理形状补齐（例如 Lifetime genesis 列名），不恢复旧迁移链、不读取旧 Branch/Run 数据，也不提供旧 API 兼容层。未知或旧 schema 会在写入前拒绝打开，不能通过直接改状态字段制造验收结果。

## 状态分层与隐私

```text
Truth / Projection
        ↓ visibility rules
Knowledge of one Lifetime
        ↓ interpretation
Belief / expectation
        ↓ deliberate planning
Plan / obligation / revisit
        ↓ explicit retention
Memory
```

- Truth 是 Host 已提交的世界事实；Projection 是当前 tick 的可读派生状态。
- Visibility 决定某事实是否进入某个主体的合法上下文。
- Knowledge 只包含已经抵达或被合法观察到的事实；发出消息不等于收件人知道。
- Belief 和 Plan 是主体状态，不能被公共 World 当成事实。
- Memory 不是全量人生 dump，只保存明确值得长期保留的主体经验。

产品读取遵守四道后端边界：公共 World 只读 public projection；Life threshold 只读选定 Lifetime 的可见入口；这一生只读当前 Human Lifetime 的 private context；Past 只读 sealed deterministic projection。Host 不依赖前端隐藏来做权限控制。

## Volume 生命周期

### 创建

`VolumeRuntime.create()` 在一个新 Volume Worldline 中建立 Volume genesis、所有 Lifetime genesis、初始 Projection、共享 World、历史 Field Event、危局来源引用、Profile binding metadata 和从 tick `0` 开始的 Ledger/Snapshot。

当前活动 pack 只注册 `before-shanhaiguan`，包含李自成、吴三桂、多尔衮三个主体。旧南方/Nanjing Crisis 目录仍作为历史内容资产保留，但不再进入活动 Volume、Envelope reconcile 或产品投影；前置条件消失时仍由现有机制写入 `SUPPRESSED`，不伪造可玩的危局。

### Restart reconcile

真实进程启动时，Host fail closed 地核对唯一 active Volume owner、每条 Lifetime/Profile、genesis marker、binding、private token、Volume MCP allowlist，以及未完成 Pending Logical Moment 中的 Wake/operation 归属。缺失、漂移、重复或不可恢复状态会把 active Volume 标成 `FAILED`；已封存卷册的 `CLEANUP_PENDING` 只重试属于它的 Gateway/Profile cleanup。

### 局部结算与整卷边界

危局 `SETTLED` 或 `SUPPRESSED` 只写入 Instance outcome、world effects 和 `CRISIS_SETTLED` Meaning，不撤销 Lifetime binding，也不清理 Profile。其他危局或 shared Field Event 仍可让同一卷册继续向前。

`VolumeBoundaryPolicy` 只有在以下条件同时满足时才返回 ready：

- 没有 Pending Logical Moment、queued/staged wake 或到期 wake；
- 没有在途消息和待应用 historical field；
- 没有后续 `next_tick`；
- 每个 Crisis Instance 都是 `SETTLED` 或 `SUPPRESSED`；
- 所有待应用 historical field 已完成；不要求某个固定 Field Event 产生消息。

安全 horizon 只能说明“尚未收束”的 fallback，不能把未满足条件的卷册伪装成 Ending。Seal event 记录 boundary policy、证据事件和 reason，之后才允许 Archive。

### Seal 与清理

```text
VOLUME_SEALED
→ worldline status = SEALED / phase = ARCHIVED
→ Lifetime/Profile bindings revoked
→ queued wakes cancelled
→ owned Profiles and World MCP entries cleaned
```

物理清理是 seal 之后的可重试动作，不是历史的一部分。清理只能删除 marker 明确属于该 Worldline 的 Profile 和 server，不能接管未知进程、删除别的卷册资源或覆盖用户 Hermes Home。重复 seal 只重试本卷册的清理并返回幂等结果。

## Global Clock 与 Logical Moment

一个 Volume Worldline 只有一个 authoritative world tick。危局的 `local_tick` 是从 activation tick 派生的显示值，不能改变 Ledger 排序。

当前历史 Field 仍沿用 `FIELD_EVENT_APPLIED → MESSAGE_DISPATCHED → MESSAGE_DELIVERED` 的既有链路。North 的 bounded `position_report` 只在 observation tick 读取当前 Projection：genesis 位置不报告、在途 Movement 不泄露，且每个公开位置必须由已提交的 Movement completion 支撑；没有可报告事实时 Field 仍会应用但保持静默。动态消息是 `VOLUME_DERIVED`，并携带 Field 应用事件与实际 Movement completion 的 causal parents。

推进步骤固定为：

1. 应用该 tick 到期的 deterministic effects、消息和历史 Field Event；
2. 把所有需要主体处理的 wake 冻结为一个 Pending Logical Moment；
3. 为每个 Lifetime 构造当时合法的 Perspective；
4. Human 与 Hermes 各自 stage intent，commit 前互不可见；
5. Host 统一校验、按稳定顺序提交并写入 causal parents；
6. 排入未来 tick 的消息、wake、Operation、revisit 或其他效果。

Human/Hermes 执行顺序、网络 wall time 和模型响应快慢都不能改写同一 moment 的世界语义。相同 idempotency key 重试必须返回既有结果，而不是产生第二个世界效果。

## Runtime 与 Hermes 边界

### Fixture

`runtime_mode = fixture` 只在 `CHRONICLE_DEV=true` 或自动化中开放。它为主体 wake 生成确定性结果，用来验证 Host、消息、时钟、隐私、Pending Moment 和 Archive；它不是模型认知证明。

### Live

`runtime_mode = live` 通过 `materialize_lifetime_profiles()` 按 `worldline_id + lifetime_id` 安装或校验 Profile、marker、Profile env、Volume-specific MCP configuration 和 durable binding metadata。真实 Wake 使用同一 Lifetime 的 fresh Session，读取 bounded frozen Perspective，经 Profile 专属 World MCP 的 `logical_intent` staging 提交受限意图，再由 Host 完成 Pending Logical Moment 的 atomic commit。

普通 Wake 的 Hermes Memory 发生变化会 rollback 并阻断；没有结构化意图也不会静默降级成等待。Gateway health、一次 chat 或 `doctor` 只能证明前置能力，不能单独证明跨主体连续性或完整卷册因果。

## API ownership

正式产品路由集中在 `chronicle/product_api.py`：

| 层 | 入口 | 返回边界 |
| --- | --- | --- |
| Volume | `/api/worldlines`, `/active` | Volume metadata、public world、Lifetime list |
| Public World | `/{id}/world` | knots、public positions、公开状态和公共 attention |
| Follow | `/{id}/follow/{lifetime_id}` | selected Lifetime 的可见入口，不含其他私态 |
| Life Desk | `/{id}/desk` | 当前 inhabited Lifetime 的 private context |
| Mutation | `inhabit`, `leave`, `continue`, `decision` | Host-validated state transition |
| Archive | `/{id}/archive[?lifetime_id=...]` | public replay；可选一个 selected Lifetime replay |
| Ending | `/{id}/seal` | 仅 boundary ready 时写入 `VOLUME_SEALED` |

旧 API 和旧 replay 已不再注册；旧路径返回 404。新功能必须沿当前 Volume API、Host、Ledger 和 projection 边界实现。

## 明确不引入

当前架构不引入 generic history/workflow DSL、第二套运行时、Agent Director、free A2A mind-to-mind、关系分/信任表、Theory-of-Mind graph、skill extraction、跨 Lifetime/Worldline Profile 共享、daily forced tick、Agent dashboard、LLM World Master/Judge 或完整战斗模拟器。

## 可复核的当前边界

本轮确定性检查覆盖三主体 Volume、fresh-context restart、Attention/Deliberation、Experience/Reflection、Human handback、Archive 和边界清理；真实 Hermes、浏览器和真人接受度没有在本轮升级为 PASS。详细结果和限制见 [当前验收](ACCEPTANCE.md)。
