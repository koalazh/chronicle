# Chronicle V3 架构

本文是唯一的系统架构入口。它把 Run、主体状态、Hermes 和迁移放在同一条因果链里；产品旅程见 [产品说明](../PRODUCT.md)，页面约定见 [前端合同](FRONTEND.md)，历史边界见 [历史与视野](HISTORY.md)，现场操作见 [运维与验收](OPERATIONS.md)。

## 先看一条链

```text
Crisis Pack
    ↓ 创建
Run + Life State
    ↓ 找到下一个 trigger
Scheduler
    ↓ 冻结每个主体自己的 Perspective
Hermes Actor / Human Decision
    ↓ 通过同一组 World tools 提出请求
WorldService
    ↓ 校验并原子提交
Ledger + Snapshot + 下一时刻
```

Chronicle 的核心原则是：Host 负责现实，主体负责选择。没有一个中央模型替三位主体决定；Hermes 负责长期主体和 Agent loop，Chronicle 负责模拟世界和所有可验证效果。

## 四个词足够理解产品

| 词 | 含义 | 用户看到的说法 |
| --- | --- | --- |
| Crisis | 一段有来源、有地点、有停止边界的历史切片 | 这场危局 |
| Run | 从 checkpoint 开始的一次可推进经历 | 这一局 |
| Actor | 在 Run 中拥有私有状态并自己做选择的主体 | 李自成、吴三桂、多尔衮 |
| Perspective | 某个主体在某一刻合法能使用的信息 | 这个人的视野 |

`Run`、`Actor` 和 `Perspective` 是实现名；主产品只需要让用户理解“一场危局、一局经历、一个人的视野”。

## 状态分层

一个主体的状态不能和世界事实混在一起：

| 层 | 保存什么 | 谁能更新 |
| --- | --- | --- |
| Truth / Projection | 模拟日、位置、路线、消息、移动和世界效果 | Host 的确定性提交路径 |
| Knowledge | 该主体已经收到的断言、信件和观察 | 送达与观察规则 |
| Belief | 该主体对不确定事情的判断 | 主体通过 `update_plan` 提出 |
| Plan / Revisit | 该主体准备做什么、何时重新判断 | 主体通过 `update_plan`、`schedule_revisit` 提出 |

Knowledge 不是 Truth 的副本，Belief 不是史实定论，Plan/Revisit 也不是聊天记录。事件发生、消息发出、消息抵达分别记录；只有抵达后，消息才进入收件人的 Knowledge。

## Run 生命周期

### 创建

同一时间最多一局可玩的 ACTIVE Run。Host 从 Crisis Pack 读取 checkpoint、主体、走廊、路线、初始信息和在途消息，建立 Projection 与每个主体的 Life State，并原子写入创建/checkpoint 事件。fixture Run 随后直接授权 Agent binding 和 `ORIENT` Wake。

Watch 的 controller map 是三位 Agent；Takeover 是李自成 Agent、吴三桂 Human、多尔衮 Agent。live Run 先以 `BOOTSTRAPPING` 持久化同一局的主体 identity，再按 identity 幂等建立所需 Profile、当前局唯一的 root MCP allowlist 和私有 Gateway child，最后才在一个事务里授权 binding 和排入 `ORIENT` Wake。初始 `ORIENT` 必须通过 World MCP 留下 committed `update_plan`；否则 Run 保持同一 identity 并进入 `FAILED`，不会伪装成 memory-only 的合法 no-op。

### 推进

Scheduler 只寻找已经存在的下一件事：移动抵达、消息抵达、观察、Revisit 到期或 Reflection。没有 trigger 不创建 Wake，不使用墙钟 cron、heartbeat 或每日轮询。

`ORIENT` 仍必须留下初始 Plan，但不会因为计划包含等待而强制安排 Revisit。Plan 只在目标、方法或重新判断条件确有变化时写入 `PLAN_UPDATED`；相同内容的重述只留下不进入主产品的 `PLAN_REAFFIRMED` Ledger 记录。Reflection 不再由 Plan 改写自动触发，只在后续的重大世界后果需要长期理解时排入。

一个 logical moment 的顺序固定为：应用本时刻到期的确定性效果；冻结所有主体合法的 Perspective；不同主体并发运行、同一主体串行运行；每个 Wake 最多提出 8 个 World tool 请求；所有 Wake 返回后统一校验和提交；本时刻产生的消息、移动和观察排入未来时刻。

因此模型返回顺序不能改变世界语义；拒绝、等待、沉默和 no-op 都是合法结果；消息不能在同 tick 递归唤醒收件人。

### 封存

用户主动封存，或危局达到最大模拟日/需要进入大规模交战裁定时，Run 不再允许继续推进并应被封存。一次 seal 事务同时写入 `RUN_SEALED`、封存 Life State、撤销所有 Agent binding，并取消尚未开始的 Wake；之后只能读 Replay、Archive 和 History。

Profile、root MCP 条目和 Gateway child 是执行资源，不是历史的一部分。seal 之后的物理清理可重试：先停止可证明归属的 child，再移除本局 MCP/env 条目，最后删除带 marker 的 Profile。`CLEANUP_PENDING` 与空失败码表示已收束；有失败码时，下一次 `chronicle start` 或新开局前只重试这次清理。旧资源永远不会加入新局 allowlist，sealed Run 也不能被重入。

### 运行资源与重启

`runtime_phase` 不是新的产品概念，而是 ACTIVE Run 恢复资源时的最小持久化线索。它只使用 `BOOTSTRAPPING`、`READY`、`RECONCILING`、`FAILED`、`SEALING` 和 `CLEANUP_PENDING` 六个值；历史 status 仍是 `ACTIVE`/`SEALED`。

`chronicle start` 在启动页面服务时检查 active Run。它只会恢复同一 Run：已存在的 Profile 必须带有相同 Run/Actor/epoch marker，root MCP allowlist 和 Profile 工具配置也必须仍然完整；已存在 binding/Wake 必须与该 identity 完全一致。每个 Agent Wake 使用稳定的 `chronicle-<wake_id>` Session 标识；World 操作的持久化幂等键由 Host 根据 wake、工具和调用槽计算。重启遇到 `RUNNING`/`STAGED` Wake 时不会猜测外部调用是否完成，也不会直接重排；该 Wake 进入受控失败，用户只能封存这一局。

GatewayController 不是 daemon。它只是 `chronicle start` 管理的一个项目私有 child：owner record 不含密钥，并与 Hermes `gateway.pid`、PID 启动时间、私有 Home 和当前 root 配置指纹交叉核验。缺失、PID 复用、指纹不符或未知端口都 fail closed；Chronicle 不会停止、复用或覆盖未知进程。

## Perspective 与隐私

Host 为每个主体构造自己的 Perspective，包含当前模拟日、自己的位置、已送达 Knowledge、私有 Belief、Plan、Revisit、Resource、Authority 及动态 affordance manifest。manifest 只列出该主体可联系的 Actor、可用行动和 target、自己拥有的 asset、当前 Revisit、已知实体与可见世界约束；尚未实现的 Investigation、Offer 和 Agreement 在此阶段以空集合显式表示。

人物 Perspective 不包含世界全局投影、尚未送达的消息、其他主体的私有计划/Belief/Memory/Wake、checkpoint 之后的真实历史行动或战后结局。Takeover 活动期间，后端拒绝世界全局和其他主体 perspective；前端隐藏不构成权限控制。

## World tools

Hermes Agent 与 Human Decision Interpreter 共用同一组四种请求：

| 工具 | 主体表达什么 | Host 至少校验什么 |
| --- | --- | --- |
| `communicate(recipient, content, idempotency_key)` | 给另一主体发送一封信 | 收件人、内容、路线和抵达日 |
| `act(action, description, target, idempotency_key)` | `hold`、`prepare` 或 `move` | authority、目标资源/位置、路线、资源、边界和现实前提 |
| `update_plan(objective, steps, rationale, belief_updates, reconsider_when, idempotency_key)` | 更新目标、方法、重新判断条件和必要的 Belief | 内容完整性、信念格式、语义 no-op 和幂等键 |
| `schedule_revisit(after_days, reason, idempotency_key)` | 在未来模拟日重新判断 | 正数天数、原因、边界和幂等键 |

工具参数不接受 actor、run 或 wake 身份。Agent 身份来自 Profile 私有 token，Human 身份来自当前控制者。调用先落为 `PROPOSED` 或 `REJECTED`，Wake 成功时才与 Ledger、Projection、Life State 一起提交；重复幂等键返回第一次结果，超过 8 次被拒绝。

## Hermes 边界

| Hermes 负责 | Chronicle 负责 |
| --- | --- |
| Profile、模型请求、Agent loop、fresh Session | Run、模拟时间、停止边界、Perspective |
| Profile 原生 Memory 和会话上下文 | Knowledge、Belief、Plan、Revisit、Resource、Authority |
| 模型判断与工具调用 | 路线、消息送达、权限、世界效果和 Ledger |

Watch 在 live Run 建立后运行三个 Agent Profile；Takeover 运行李自成和多尔衮两个 Profile，吴三桂由 Human lifetime 承担。每个 Profile 的归属至少包含 `crisis_id`、`run_id`、`actor_id`、genesis hash、initial Memory snapshot 和 runtime epoch；World token 只在项目私有环境文件中，SQLite 只保存 token hash；封存时统一撤销 binding，并把执行资源移出后续 Run。

每次 Agent Wake 使用 fresh Session。普通 Wake 不得改变 durable Memory；只有 `REFLECTION` Wake 可以写入长期经验，也可以选择 `NO_CHANGE`。Plan、Belief、Revisit 和未送达消息属于 Chronicle Life State，不写进 Memory。Reflection 的 native Memory、Life State、Ledger 事件和 lineage version 必须作为同一个 SQLite moment 提交，失败时恢复 native 文件。

## Human Decision Interpreter

Takeover 的吴三桂没有 Hermes Actor Profile。Interpreter 只把用户文字解释成最多 8 个与 Agent 相同的 World tool 请求，再交给同一个 `WorldService` 校验和提交。它不决定行动是否成功，不替其他主体作决定，也不能从 private perspective 之外补充信息；live 解释失败不会回退成 regex 或 fixture。

## 迁移与旧数据

V2 的正式路径是 `Canon → Entry → Human Seat → Branch/Worldline → Debrief`；V3 改为 `Crisis Checkpoint → Run → 多主体推进 → Seal → Replay`。V2 的 Source Pack、Ledger、Snapshot、Perspective 边界、Profile 管理、Memory guard、旧表和旧 API 继续保留给迁移、History 和回归，但不再是首页入口。

schema v9 是 additive migration。对已有数据库，backup 后缀按源版本选择：v1→`.pre-v2.*`、v2→`.pre-v3.*`、v3→`.pre-v4.*`、v4/v5/v6→`.pre-v7.*`、v7→`.pre-v8.*`、v8→`.pre-v9.*`。v9 新增 Volume/Crisis 内容与 Resolution pin、`crisis_phase`、`outcome_json`、`settlement_reason` 和 `revisits_json`；旧 `commitments_json` 保留为 legacy replay field。迁移时仍会把旧 active `BRANCH` 写为 `LEGACY_V2_SEALED`；active V3 `CRISIS` 则写入 `LEGACY_V3_SEALED` 并封存，不把旧 9 日/Commitment 语义热迁移成 V4。旧 live Crisis 会标为 `CLEANUP_PENDING`，由既有受限清理路径处理；ACTIVE Canon 或已经封存的旧行不会被重复包装。V2 细节见 [V2 归档](archive/v2/V2_MIGRATION.md)。

## 不要把证据混在一起

确定性测试证明本地协议和失败路径，Doctor 证明 Gateway/Profile/MCP 前置能力，浏览器证明页面状态，live business Run 才证明真实 Profile、fresh Session、World tools、持久状态、后续 Wake、消息送达和封存能在同一局中关联。完整记录见 [验收记录](ACCEPTANCE.md)。
