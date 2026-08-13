# 当前验收记录

> 读者：开发者、验收人员和项目维护者。本文用于核对证据，不是产品上手指南；如果你只想体验，请从 [README](../README.md) 开始。

本文只记录当前工作树中可以复核的结果。多主体 Profile 的实现边界见 [多主体运行说明](MULTI_AGENT.md)。不同证据层各自回答不同问题：自动化检查不能替代浏览器体验，浏览器不能替代真实 Hermes 业务链，一次真实业务链也不能替代真人主观反馈。

## 结论

当前产品达到“可运行、可检查、可追溯”的工程验收状态；V7 的确定性实现、当前源码浏览器旅程和隔离 real Hermes Volume 均已在本轮复跑：

- 默认 `jiashen` Volume 的来源、危局和页面合同通过确定性检查；
- Volume、World、Follow、Inhabit、Life Desk、Leave、Archive 和 Ending 的产品链路可运行；
- Course、Attention、HOLD/REVISE、消息与 Agreement、Operation、结构边界和判断回看由同一 Host/Worldline 链承载；
- V7 的 Endogenous History、shared Nanjing consequence、Southern endogenous topology 和 branch-neutral boundary 由确定性 proof 覆盖；两条完整 Worldline A/B 都由真实 World action 分叉、各自形成结果并 Seal；
- Outcome Deletion 和 Canon Deletion 均通过；后者移除所有 `REFERENCE_ONLY` anchors 后仍由实际 Nanjing/Southern action 形成 World consequence、Knot topology 和 Seal；
- 当前源码已通过浏览器产品旅程和 1440/1280/768/390 四种视口检查；
- 当前源码已通过一条隔离 real Hermes Volume 业务链，覆盖六个 Profile、fresh Session、Deliberation、消息、Operation、Nanjing Resolution、Southern suppression、结构边界、Seal 和 cleanup；
- 这条真实轨迹不是模型稳定性 benchmark，也不能代替真人问卷。真人产品反馈仍为 `UNCOLLECTED`。

## 证据矩阵

| 层级 | 当前结果 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 内容校验 | PASS | 当前 Volume、Crisis Pack、引用和路线约束可解析 | 模型会如何行动 |
| 自动化回归 | PASS | Host 权威、权限、时钟、消息、原子提交、幂等、Archive 和失败路径稳定 | Provider 在所有环境下的行为 |
| 浏览器 | PASS | 当前源码完成 World → Follow → Inhabit → 非空 Course → Leave → Continue；未封存与已封存 Archive/Ending 均可读；四种视口无横向溢出、内部术语扫描为空、dev logs 为空 | Hermes Profile、Session 或 live Gateway 业务成立 |
| 真实 Hermes | PASS | 隔离 Volume `worldline-aed48407cea14c1c` 在产品/Host 链中 materialize 6 个 Profile，完成 17 个 fresh Session、真实 Deliberation/Attention、消息、Operation、Agreement/Offer、Nanjing Resolution、Southern suppression、Seal 和精确 cleanup | Provider 在不同环境、提示或版本下的稳定性；真人产品反馈 |
| 真人反馈 | 未收集 | 尚无主观体验结论 | 不得由 coding agent 代答 |

## 可重复检查

在仓库根目录执行：

```bash
uv run chronicle volume validate
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts

set -o noglob
for file in $(find web -type f -name '*.js'); do
  node --check "$file" || exit 1
done

git diff --check
```

当前记录：`215` 项测试全部通过，其中 `48` 项来自 V7 proof 文件；Volume validator 输出 `Volume valid: jiashen, 3 crises`；Ruff、compileall、当前前端 JavaScript syntax 和 diff check 通过。依赖的 deprecation warning 仍原样保留，不把 warning 写成“已消除”。

## V7 确定性 Worldline 与高阶 Proof

以下检查在当前源码上执行：

```bash
uv run pytest -q tests/test_v7_endogenous_history.py
```

其中 `test_v7_complete_deterministic_worldlines_a_and_b_diverge_and_seal` 实际运行两条独立 Worldline：

- A：李自成兵力真实移动到永平并生成动态公开记录；随后福王在南京真实完成承认，南方由 shared `FU_RECOGNIZED` 激活；史可法起草文书、马士英独立回应，Southern 以 `JIANGBEI_COORDINATION` 真实结算并 Seal。
- B：多尔衮真实进入山海关形成另一条 North record；随后潞王在南京真实完成承认，Southern 因 shared `LU_RECOGNIZED` 保持 `SUPPRESSED`，Volume 仍正常 Seal。

测试比较两条轨迹的 Ledger、South Knowledge、shared current World、Knot topology 和 Archive，并验证 A 的真实 Southern resolution 与 B 没有该 resolution。

高阶 Proof 还分别删除所有 Crisis outcome metadata，以及删除所有 `REFERENCE_ONLY` anchors。Canon Deletion 路径不调用手工 `settle_crisis`/抑制来结束主体 Knot，而是通过真实 FU、文书起草和马士英协调 action 形成 Nanjing/Southern World consequence，再 drain 到 structural boundary 并 Seal。

## 本轮隔离真实业务记录

2026-08-13 在独立临时 SQLite、Hermes Home、loopback 产品端 `127.0.0.1:18714` 和本卷 Gateway `127.0.0.1:18883` 上完成 real Hermes Volume。没有覆盖项目默认数据库、全局 Hermes Home 或未知端口；最终保留 SQLite 作为脱敏审计证据，不保留 Provider response、密钥或 token。

同一 Volume `worldline-aed48407cea14c1c` 的可复核摘要：

1. 产品 Human 路径写入 Course，离席，再次进入后仍能看到该判断；
2. 六个真实 Hermes Profile 均按各自 binding materialize；23 个 Wake 完成，其中 17 个带 fresh Hermes Session，产生真实 Deliberation/Attention、`HOLD`/`REVISE`、消息、Offer/Agreement 和 Operation；
3. 同一 Volume 中北方公开 Field Event 在 tick 9 落地；Nanjing 两位候选均进入程序空间，Host/Resolver 在 tick 12 产生 `DUAL_ENTRY_WITHOUT_RECOGNITION` 并 `CRISIS_SETTLED`；
4. shared `nanjing-political-center` 的非 FU 结果使 Southern 按真实前置条件 `CRISIS_SUPPRESSED`，没有静态激活；
5. tick 21 的 `jiashen-structural-closure-v2` 为 `structural_boundary`，之后 Volume 为 `SEALED/ARCHIVED`，六条 binding 为 `REVOKED`，本卷 Profile 目录、Gateway owner、PID marker 和任务端口均已精确清理。

其中 Nanjing 的两个公开世界行动和最终 tick 21 的 HOLD 是受控 Host 选择，用来把真实 Provider 产生的 live cognition 与确定性世界兑现连接起来；它们不被计作模型自主选择。第一次受控 live 尝试还记录到 Provider 缺少 `evidence_event_ids` 的 REVISE 被 Host fail-closed 拒绝，随后精确清理；该失败不被计入 PASS 轨迹。

原始 Provider response、密钥、token 和私有 prompt 没有进入仓库。详细阶段材料位于 [`archive/README.md`](archive/README.md)，不要把归档中的候选记录当作当前结论。

## 当前仍然明确不做的声明

- 不声称模型在不同 Provider、版本或提示下会稳定复现同一选择；
- 不声称一次轨迹等于大样本 benchmark；
- 不把自动化 PASS 改写成真人满意；
- 不把局部危局 settlement 改写成整卷 Archive；
- 不把历史材料、未送达消息、其他 Lifetime 的私有判断或未落笔思考展示给公共页面。
