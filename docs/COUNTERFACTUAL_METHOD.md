# Counterfactual Method：有限、可停止的 Worldline

Worldline 的目的不是预测“如果历史改变会怎样”，而是展示一个受约束的 Entry 如何产生可追溯、可复盘的短期差异。

## V2 规则

- 先推进 Canon 到唯一 Entry，再创建一个带 kind、controller、status 和 entry_id 的 Worldline。
- Live 期间 Seat 只能从 SeatContextView 接收已抵达的信息；Host 不把分支全局投影注入 Seat。
- 每个用户输入先经过 Entry-local intent compiler 和 Host 权限校验；不明确的输入返回 AMBIGUOUS，不支持的输入返回 UNSUPPORTED，不可执行的输入返回 IMPOSSIBLE。
- 高影响动作先冻结为待确认意图；确认后才追加 ledger event。所有效果都带 causal parent，消息继续经过 transit 和 delivery。
- 推进由下一条 Canon event、已到期观察 delivery、到期消息或 Entry 内部调度点驱动，而不是“一次输入等于一天”。
- 到达十四天 horizon 或用户显式退出后，Worldline 进入 SEALED；Debrief 只读取已保存的 context、projection 和 causal descendants。

V1 的 Branch 表和 API 仍作为 legacy compatibility 保留，不是 V2 的用户心智或新的事实来源。

## V1 兼容规则

- 只能从 `fork.yaml` 指定的 Canon event 创建 Branch。
- Host 当前 Canon tick 必须已经到达该 event 的 fork tick；同一 fork 不能重复创建。
- 当前唯一 fork 是南迁讨论中的“太子抚军江南”提议。
- Branch 初始状态复制 Host 在 fork tick 的 Canon 摘要，并标记 `provenance=branch_derived`。
- 每次 action 只能来自一个 Seat 的 authority；`WAIT`、传信、发命令和准备移动是 V1 的有限动作。
- Host 按 Source Pack 路线计算 transit delivery、location、order 和 day offset；没有定义路线的移动或传信会被拒绝，不调用 World Master LLM。
- 最大十四个 simulated days。到边界后状态为 `boundary`，不再继续补写事件。

## 为什么停止

超过十四天后，需要未经 Source Pack 支撑的战役进展、联盟、政权和个人选择。继续生成会把模型流畅度误报成历史或反事实证据。Boundary 页面因此同时显示当前状态、已提交 action 和停止理由。

## 结果标签

Canon 仍然是 `historical`；Branch 的 action、transit、状态差异和 Life Record 关联均为 `branch_derived`。Branch 不修改 Canon tick，也不修改历史 Source Pack。
