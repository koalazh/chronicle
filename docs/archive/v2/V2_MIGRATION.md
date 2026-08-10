# V2 迁移归档：Branch 到 Worldline

> 这是历史归档，不是 V3 产品入口。当前系统边界见 [V3 架构](../../ARCHITECTURE.md)，现场操作见 [运维与验收](../../OPERATIONS.md)。

## V2 当时解决的问题

V2 把 V1 的 Branch 页面收敛成一条可恢复、可封存、可追溯的经历：

```text
Observe → Enter → Live → Debrief
```

用户先观察 Canon，再从唯一 Entry 进入一个 Worldline；Live 期间只通过自己的 `SeatContextView` 读取已经抵达的信息，最后显式退出并封存。

## 旧数据与迁移

V2 使用 `worldlines`、`worldline_events`、`worldline_snapshots` 和 lifetime 表保存经历。V3 的 schema v7 迁移是 additive：对已有数据库按源 schema 生成 `.pre-v2.*`、`.pre-v3.*`、`.pre-v4.*` 或 `.pre-v7.*` backup，保留旧表、未知表和旧 API，再增加 V3 Run、Wake、operation、Life State 和 binding revocation 结构。

只有仍为 ACTIVE 且 `kind='BRANCH'` 的旧 Worldline 才会写入 `LEGACY_V2_SEALED`；迁移不删除旧数据库、不重置 Hermes Home，也不把旧 Branch 猜测性转换成 V3 Crisis Run。迁移验收必须在副本上进行。

## V2 的信息边界

`SeatContextView` 包含当前 tick、自己的已知世界、送达消息/观察、自己的经历、authority 和可见实体。它不包含 Branch 全局投影、未来事件、其他 Seat 未送达的信息或展示层结局。

Human Worldline ACTIVE 时，Archivist 的全局读写接口被锁定；只有显式封存后才回到 Archivist。这条边界是 V3 ActorPerspective 后端锁的历史前身。

## V2 的输入与推进

旧输入结果是 `ACCEPTED`、`IMPOSSIBLE`、`UNSUPPORTED` 或 `AMBIGUOUS`。高影响动作先生成 confirmation，再由用户确认；一次输入的 context、原文、结果和 pending confirmation 在同一事务中提交。

移动和传信必须沿 Entry 路线表校验；提交意图不会自动把时间推进一天。推进由下一条可交付观察、Canon 事件或到期消息驱动。

## V2 Hermes 边界与 Debrief

旧路径采用 lazy branch Profile：分支专属观察抵达 Agent Seat 后才创建稳定命名的 Profile，每次 Wake 使用新 Session。fixture 是确定性替身，live Hermes 不可用时不会静默写成成功；这些规则仍服务于 legacy 数据读取和回归，不是 V3 的主体创建方式。

封存后 Debrief 只读取保存的材料：**What You Saw** 是该 Seat 当时收到的 context，**What Was True** 是 Worldline 的 Host projection，**What You Changed** 是有 causal parent 的分支事件，**Where It Stopped** 是用户退出、horizon 或失败边界。Debrief 不给分、不生成事后 LLM 总结，也不把未送达信息伪装成当时所见。
