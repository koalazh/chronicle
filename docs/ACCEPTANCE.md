# 当前验收记录

> 读者：开发者、验收人员和项目维护者。本文用于核对证据，不是产品上手指南；如果你只想体验，请从 [README](../README.md) 开始。

本文只记录当前工作树中可以复核的结果。多主体 Profile 的实现边界见 [多主体运行说明](MULTI_AGENT.md)。不同证据层各自回答不同问题：自动化检查不能替代浏览器体验，浏览器不能替代真实 Hermes 业务链，一次真实业务链也不能替代真人主观反馈。

## 结论

当前产品达到“可运行、可检查、可追溯”的工程验收状态：

- 默认 `jiashen` Volume 的来源、场景、危局和页面合同通过确定性检查；
- Volume、World、Follow、Inhabit、Life Desk、Leave、Archive 和 Ending 的产品链路可运行；
- Course、Attention、HOLD/REVISE、消息与 Agreement、Operation、结构边界和判断回看由同一 Host/Worldline 链承载；
- 隔离临时资源上的真实 Hermes Volume 已从浏览器 Human Course/Leave/re-entry 走到 Shanhai、Nanjing、Southern consolidation、Archive、Seal 和精确清理；
- 这条真实轨迹不是模型稳定性 benchmark，也不能代替真人问卷。真人产品反馈仍为 `UNCOLLECTED`。

## 证据矩阵

| 层级 | 当前结果 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 内容校验 | PASS | Source、Scenario、Volume 内容可解析，引用和路线约束成立 | 模型会如何行动 |
| 自动化回归 | PASS | Host 权威、权限、时钟、消息、原子提交、幂等、Archive 和失败路径稳定 | Provider 在所有环境下的行为 |
| 浏览器 | PASS | 四种视口的页面旅程、非空判断持久化、无横向溢出、无内部术语和空 warn/error 日志 | Hermes Profile、Session 或 Gateway 业务成立 |
| 真实 Hermes | PASS（单条脱敏轨迹） | 同一 Volume 中的主体、Session、Deliberation、Ledger 因果、消息、结算、Archive 和 cleanup 可关联 | Provider 稳定性、统计成功率或真人体验 |
| 真人反馈 | 未收集 | 尚无主观体验结论 | 不得由 coding agent 代答 |

## 可重复检查

在仓库根目录执行：

```bash
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts

set -o noglob
for file in $(git ls-files '*.js'); do
  node --check "$file" || exit 1
done

git diff --check
```

当前记录：`377` 项测试全部通过；Source validator 输出 `4 sources / 36 assertions / 36 events`；Scenario validator 输出 `3 Seats / 15 locations / 16 routes`；Volume validator 输出 `jiashen / 3 crises`；Ruff、compileall、tracked JavaScript syntax 和 diff check 通过。依赖的 deprecation warning 仍原样保留，不把 warning 写成“已消除”。

## 隔离真实业务记录

最近一次脱敏记录使用独立 SQLite、Hermes Home、loopback 产品端和 Gateway；没有覆盖项目默认数据库、全局 Hermes Home 或未知端口。业务链包含：

1. 浏览器 Human 写入 Course，离席，再次进入后仍能看到该判断；
2. 六个真实 Hermes Profile 均按各自 binding materialize，并以 fresh Session 在同一 Volume 中产生 Attention、HOLD/REVISE、消息、Agreement 和 Operation；
3. Wu 的判断经历 `BACKGROUND → REOPEN → HOLD`，Archive 可回看此前判断、重新判断和后来抵达的事实；
4. Shanhai、Nanjing 和 Southern consolidation 通过统一的世界时钟和结构边界自然完成；
5. Volume Seal 后状态为 `SEALED/ARCHIVED`，六条 binding 为 `REVOKED`，本卷 Profile 目录、Gateway owner 和任务端口均已精确清理。

原始 Provider response、密钥、token 和私有 prompt 没有进入仓库。详细阶段材料位于 [`archive/README.md`](archive/README.md)，不要把归档中的候选记录当作当前结论。

## 当前仍然明确不做的声明

- 不声称模型在不同 Provider、版本或提示下会稳定复现同一选择；
- 不声称一次轨迹等于大样本 benchmark；
- 不把自动化 PASS 改写成真人满意；
- 不把局部危局 settlement 改写成整卷 Archive；
- 不把历史材料、未送达消息、其他 Lifetime 的私有判断或未落笔思考展示给公共页面。
