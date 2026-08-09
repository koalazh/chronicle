# Chronicle V2：从 V1 Branch 到 Worldline

> 状态：当前产品与运行时契约（2026-08-08）

Chronicle V2 把 V1 的“Branch 页面”收敛为一条可恢复、可封存、可追溯的经历：

    Observe → Enter → Live → Debrief

用户先观察 Canon，再从唯一 Entry 进入一个 Worldline；进入后只通过自己的
SeatContextView 看到已经抵达的信息，提交自然语言意图，最后显式退出并封存。

## 当前 V2 范围

- Source Pack 仍是甲申场景，唯一 Entry 是 e019 / jiangnan-prince-command。
- 当前可玩的 Seat 是 A；Seat B、C 由确定性 fixture 或可选的 Hermes lazy Profile 驱动。
- Worldline 最多推进 14 天，达到边界后自动封存为 BOUNDARY。
- 运行时只支持 Entry 声明的有限动作；不支持自由世界模拟、战役推演或通用 Agent 编排。
- 同时只能有一个由 Human 控制的 ACTIVE Branch Worldline。

## V1 → V2

| V1 概念 | V2 对应 | 说明 |
| --- | --- | --- |
| Branch | Worldline(kind=BRANCH) | Branch 是一条带控制者、事件账本和生命周期的经历。 |
| BranchRecord | worldline_events | 旧记录会作为 LEGACY_IMPORT 事件封存导入，不覆盖旧表。 |
| state_json | worldline_snapshots + projection | Snapshot 是可读投影；append-only ledger 才是权威。 |
| step | advance | 推进由下一条可交付观察、Canon 事件或已到期消息驱动。 |
| Life Record | worldline_lifetimes | 每个 Seat 有独立 branch lifetime；Agent Profile 按需创建，当前 Seat Lifetime 另带可重建的经历条目与统计。 |
| Branch 双栏 | Seat 页面 + Debrief | Live 期间不向 Seat 暴露分支全局状态。 |

V2 迁移是 additive 的。首次初始化旧数据库时会：

1. 读取旧 schema version；
2. 在同一目录生成带 UTC 微秒时间戳的 *.pre-v2.*.db SQLite backup；
3. 创建 V2 表和唯一 active-human 约束；
4. 把已有 V1 Branch 作为 SEALED 的 legacy-<branch_id> Worldline 导入；
5. 保留旧表与旧 API，供回归和人工取证使用。

迁移不会删除数据库、重置 Hermes Home 或覆盖旧 Branch 记录。

## SeatContextView 是边界

Seat 与 Agent 都从同一个 SeatContextView 构造输入，包含：

- 当前 tick 与自己的已知世界；
- 已送达的消息与观察；
- 自己携带的经历；
- authority、已知不确定性、可见实体和 assertion ID。

它不包含 Branch 全局投影、未来事件、其他 Seat 未送达的信息或展示层结局。
因此“读了数据库里的全局状态”不是 Seat 的合法路径；这条边界由 runtime
和测试共同维护。

Human Worldline ACTIVE 时，Archivist 的 Canon、Source、Who Knows、全局 Lifetime
和旧 Branch 写接口返回 423 Locked。V2 Branch Lifetime 列表只返回位置名册；
其他 Seat 的知识、信念与记忆不会穿过 Human Seat 边界。浏览器刷新通过
GET /api/worldlines/active 恢复同一 Seat lens；只有显式封存后才回到 Archivist。当前 Seat 的 Lifetime 详情只从
`/api/worldlines/{id}/lifetimes/{seat}` 读取，旧 `/api/lifetimes/{seat}` 不属于 V2 主 UI。

## HTTP 入口

| 用途 | API |
| --- | --- |
| Entry / Canon | GET /api/entries、POST /api/canon/advance-next |
| 进入 / 恢复 | POST /api/worldlines、GET /api/worldlines/active |
| Seat context | GET /api/worldlines/{id}/context |
| Branch Lifetime 名册 | GET /api/worldlines/{id}/lifetimes |
| 当前 Seat Lifetime | GET /api/worldlines/{id}/lifetimes/{seat}（包含 branch records/stats） |
| 可见分支记录 | GET /api/worldlines/{id}/ledger |
| 自然语言输入 | POST /api/worldlines/{id}/input |
| 高影响确认 | POST /api/worldlines/{id}/confirm |
| 取消待确认动作 | POST /api/worldlines/{id}/cancel |
| 事件驱动推进 | POST /api/worldlines/{id}/advance |
| 退出 / 复盘 | POST /api/worldlines/{id}/seal、GET /api/worldlines/{id}/debrief |

input 的结果只允许 ACCEPTED、IMPOSSIBLE、UNSUPPORTED、AMBIGUOUS。
高影响动作先返回 confirmation，再由用户明确确认。

一次输入的 context、原文、判断/动作结果和 pending confirmation 使用同一事务提交；
编译或 Host 校验失败不会留下半条输入。确认与取消也使用当前 tick 和 pending
内容做条件提交，重复请求返回可识别的幂等结果。

每个动作还必须落在 Entry 声明的 causal envelope 中；Ledger 的动作事件会保留
对应边界类别。复合输入不会静默丢掉后半段，而是写入 clarification 事件，要求
用户拆成单项动作。普通观察可以先进入 Branch Lifetime 的 knowledge，但只有
Entry wake policy 声明的频道或消息抵达才会触发 Agent Wake。推进也会处理此前尚未写入 Ledger、但仍在当前 Entry 范围内的观察 delivery；同一观察不会重复投递。

所有移动类动作（准备移动、移动主体、调动既有兵力）都必须从当前投影位置沿
Entry 路线表中的直接路线到达目标；地点存在但没有路线也会被拒绝。动作提交只
记录 Host 已接受的效果，不会因提交意图自动推进时间。

## Hermes 边界

Agent lifetime 不在进入时批量创建。只有分支专属观察真正抵达 Agent Seat 时，
runtime 才创建动态、稳定命名的 branch Profile，并用 Entry 进入时的 memory
snapshot 作为起点。每次 wake 都使用新 session，不复用旧聊天 transcript。

fixture 模式是可重复的确定性替身；live Hermes 不可用时不会静默降级为 live
成功。当前 Jiashen fixture 中，C 收到 A 的消息后会基于自身视角回传一条受路线
约束的消息；这只是可复现的最小因果反馈，不代表通用 Agent 规划。doctor、gateway probe 和真实业务 wake 必须分别记录，健康探针不等于
真实业务调用。

## Debrief

封存后复盘只读取已经保存的材料：

- **What You Saw**：该 Seat 当时收到的 context；
- **What Was True**：该 Worldline 的 Host projection；
- **What You Changed**：有 causal parent 的分支事件；
- **Where It Stopped**：显式退出、horizon 或失败边界。

Debrief 不给分、不让 LLM 生成事后总结，也不把未送达的信息伪装成当时所见。

## 验证边界

本地 pytest、Source Pack/scenario 校验和浏览器旅程证明确定性 fixture、API
锁、恢复、封存、迁移与页面状态。它们不能证明现场 Hermes provider、真实
模型响应或外部服务已可用；这些证据要以当前 chronicle doctor 和真实业务
wake 的结果单独报告。
