# World Model：Ledger、Projection 与 Seat 边界

Chronicle Host 是一个小型、确定性的世界内核，而不是 World Master LLM。

## V2 Worldline

V2 把一次经历拆成四个持久对象：Scenario/Entry 定义范围，Worldline 定义一次
进入，worldline_events 是 append-only ledger，worldline_snapshot_history 是按
tick 与 ledger cursor 追加保存的可读 projection。Projection 可以重建；ledger 的 sequence、causal parent
和 provenance 才是审计事实。

Worldline 有 CANON 与 BRANCH 两种 kind，以及 ACTIVE/SEALED 生命周期。Human
Branch 是单用户锁：存在 active human worldline 时，Archivist 的 Canon、来源、
Who Knows、Lifetime 和旧 Branch 写路径都暂停，避免一边修改 Canon 一边观察
自己的分支。

SeatContextView 是 Seat 与 Agent 共用的唯一输入边界。它只包含该 Seat 已收到的
消息和观察、自己的 belief/memory snapshot、authority、已知不确定性与允许动作；
Branch projection 的未送达事实不在这个对象中。

## Canon 状态

Canon tick 只能向前移动。每个事件按 tick 应用 `world_effects`，形成地点控制、路线压力、首都状态、指挥状态、兵力姿态、信息状态、季节、朝议、军需、指挥冲突、判断压力和模拟边界；原始 effect 类型同时保存在 `world.effects` 中，不能被静默丢弃。相同 Source Pack、相同 tick 和相同 DB 初态应得到相同状态。

## Knowledge 状态

观察属于 Seat，并有独立的 `delivery_tick`。`observations_for(seat, tick)` 只返回已到达的观察；`who_knows` 从同一规则派生，不接受 Agent 自报“我已经知道”。

## Life Record 与 Memory

- Life Record 是 append-only，记录 wake 类型、tick、观察 ID、belief 前后值、意图、runtime epoch 和 memory hash。
- 普通 observation wake 不能修改 durable memory。
- live Reflection 通过 Hermes 内置 `memory` tool 写入 profile 的 `MEMORY.md`；Chronicle 记录前一版本 hash、native hash、内容 diff 和来源 Life Record。
- 普通 Wake 发现 native Memory 变化时会 rollback，并追加 `protocol_violations` 记录；rollback 失败会阻止本次 Wake 完成。
- fixture mode 使用 SQLite memory mirror 复现同一条 gate，便于无外部依赖的测试。
- Belief 可以随 wake 更新，但它不等同于历史事实。

数据库触发器禁止更新或删除 Life Record。SQLite 适合 V1 的本地单用户运行；若未来需要并发多用户，应先定义租户、锁和迁移策略，不应默默替换存储。

## Action 边界

Agent 只返回结构化 `ActorWakeResponse`。Branch 只能在 Canon 到达 fork tick 后创建，同一 fork 只能创建一次。Branch action 由 Host 按 Seat authority、已定义路线、收件人、目标、payload 和当前 Branch 状态校验后才会应用。消息会按路线 travel days 进入 Host 管理的 transit queue，不能在提交时瞬移到收件人。
