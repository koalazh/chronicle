# Counterfactual Method：有限、可停止的 Branch

Branch 的目的不是预测“如果历史改变会怎样”，而是展示一个受约束的决定节点如何产生可追溯的短期差异。

## V1 规则

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
