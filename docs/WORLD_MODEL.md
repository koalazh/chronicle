# World Model：Host 拥有事实与变化

Chronicle Host 是一个小型、确定性的世界内核，而不是 World Master LLM。

## Canon 状态

Canon tick 只能向前移动。每个事件按 tick 应用 `world_effects`，形成地点控制、路线压力、首都状态、指挥状态、兵力姿态和信息状态。相同 Source Pack、相同 tick 和相同 DB 初态应得到相同状态。

## Knowledge 状态

观察属于 Seat，并有独立的 `delivery_tick`。`observations_for(seat, tick)` 只返回已到达的观察；`who_knows` 从同一规则派生，不接受 Agent 自报“我已经知道”。

## Life Record 与 Memory

- Life Record 是 append-only，记录 wake 类型、tick、观察 ID、belief 前后值、意图、runtime epoch 和 memory hash。
- 普通 observation wake 不能修改 durable memory。
- live Reflection 通过 Hermes 内置 `memory` tool 写入 profile 的 `MEMORY.md`；Chronicle 只记录前一版本 hash、native hash 和来源 Life Record。
- fixture mode 使用 SQLite memory mirror 复现同一条 gate，便于无外部依赖的测试。
- Belief 可以随 wake 更新，但它不等同于历史事实。

数据库触发器禁止更新或删除 Life Record。SQLite 适合 V1 的本地单用户运行；若未来需要并发多用户，应先定义租户、锁和迁移策略，不应默默替换存储。

## Action 边界

Agent 只返回结构化 `ActorWakeResponse`。Branch action 由 Host 按 Seat authority、目标、payload 和当前 Branch 状态校验后才会应用。消息会进入 Host 管理的 transit queue，不能在提交时瞬移到收件人。
