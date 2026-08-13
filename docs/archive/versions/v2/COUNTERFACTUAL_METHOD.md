# V2 反事实方法归档

> 历史归档。当前入口见 [`../../../../README.md`](../../../../README.md)，本文只用于追溯早期方法。

> 这是历史归档，不是当前产品入口。当前系统边界见 [架构](../../../ARCHITECTURE.md)。

## 方法目标

旧 Worldline 不是“预测历史如果改变会怎样”，而是在一个有来源的 Entry 上，展示有限、可追溯、可复盘的短期差异。

## V2 规则

- 先把 Canon 推进到唯一 Entry，再创建带 `kind`、`controller`、`status` 和 `entry_id` 的 Worldline；
- Live 期间 Seat 只能读取已经抵达的信息，Host 不把分支全局投影注入 Seat；
- 用户输入经过 Entry-local intent compiler 和 Host 权限校验；不明确、未支持或不可执行的输入分别返回 `AMBIGUOUS`、`UNSUPPORTED` 或 `IMPOSSIBLE`；
- 高影响动作先成为待确认意图，确认后才写入 Ledger；消息仍经过 transit 和 delivery；
- 推进由下一条 Canon event、观察 delivery、到期消息或 Entry 内调度点驱动，不把“一次输入”当作“一天”；
- 到达 14 日 horizon 或用户退出后，Worldline `SEALED`，Debrief 只读取已保存的 context、projection 和 causal descendants。

## V1 兼容规则

V1 Branch 只能从 `fork.yaml` 指定的 Canon event 创建；Host 必须到达 fork tick，同一 fork 不能重复创建。Branch 初始状态复制 fork tick 的 Canon 摘要并标注 `provenance=branch_derived`。

V1 的有限动作包括 `WAIT`、传信、发命令和准备移动。Host 根据 Source Pack 路线计算 transit、location、order 和 day offset；没有定义路线的移动/传信会被拒绝。

## 为什么停止

超过十四天后，Source Pack 不再支撑战役进展、联盟、政权和个人选择。继续生成会把模型流畅度误报成历史或反事实证据，所以 Boundary 页面必须同时说明当前状态、已提交动作和停止理由。

## 结果标签

Canon 仍标为 `historical`；Branch 的 action、transit、状态差异和 Life Record 关联标为 `branch_derived`。Branch 不修改 Canon tick，也不修改历史 Source Pack。
