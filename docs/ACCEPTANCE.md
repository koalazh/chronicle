# 当前验收记录

> 读者：开发者、验收人员和项目维护者。本文只记录当前源码和本轮实际运行过的证据，不是产品上手指南。

不同证据层各自回答不同问题：确定性测试不能替代浏览器体验，浏览器不能替代真实 Hermes 业务链，真实业务链也不能替代真人主观反馈。

## 结论

Product Convergence 的 12 个 Slice 已按计划完成本地实现与记录，最近的实现提交为 `9d8a1ca`；本文件对应 Slice 12。当前证据可以支持：

- Product Projection、World、Follow、Inhabit、Life Desk、Leave、Continue、Archive 的当前产品合同由同一 Host/Volume Worldline 链承载；
- Human Course、Attention、HOLD、Human Judgment、消息、调查、行动、结构边界和判断回看有确定性语义测试；
- 当前源码经过一次浏览器 fixture 旅程检查，覆盖 World → Follow → Inhabit → Judgment Desk、离席回到 World、Past 读取和移动视口；
- 一条全新的隔离 live Volume 真实运行过六个 Persistent Profile、Human-held Lifetime、真实 Hermes Deliberation、消息、调查、Operation、Field Event、delayed Knowledge、HOLD、Host 验证后的 Human Judgment、自动封存和精确 cleanup；另一条 fresh live Volume 的真实 Hermes Wake 在 `OPEN_DEPENDENCY_MATCH → REOPEN` 后提交了 autonomous `REVISE` 并自动封存；另有一条 fresh live Product receipt 运行过 Human `REVISE`、史可法 delayed Knowledge 和自动封存；后一条使用 Host-controlled agent waits，不计作 Hermes 自主选择；
- V7 的完整两条 endogenous-history 分叉由确定性测试证明；本轮 live 轨迹只证明其中真实 Field/Entity 变化，不把单条 live 轨迹改写成 V7 大样本或双分支证明；
- 真人反馈仍为 `UNCOLLECTED`。

真实 Hermes 的 Draft/Execution Assist provider trajectory 不作为模型稳定性 benchmark。另有一条补充 fresh live Volume 因 provider 返回无效结构化工具调用而失败；它没有被计入 PASS，具体边界见下文。

## 证据矩阵

| 层级 | 结果 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 确定性测试 | PASS | 当前 Host 权威、权限、时钟、消息、原子提交、幂等、Archive、Drafting Aid、Execution Assist 失败保存 Human Judgment、handback、REVISE 和 V7 分叉语义 | Provider 在所有环境下的稳定性 |
| 浏览器 | PASS（本轮范围） | 当前源码可完成 World → Follow → Inhabit → Judgment Desk；Human-held 时不展示 World 入口；Leave 后回到 World；Past 页面不暴露 Archive/Runtime 内部术语；390px 视口无横向溢出，console 无 error/warning | Hermes Profile、Session 或 live Gateway 业务成立 |
| 真实 Hermes 主轨迹 | PASS（有边界） | 隔离 Volume `worldline-1208b91809d448e6` 的 11 个 Wake 全部 `COMPLETED`，其中 9 个有 fresh Hermes Session；真实 Deliberation/Attention、HOLD、Field Event、消息、调查、Operation、delayed Knowledge、Host settlement、产品 `/continue` 自动 Seal 和 cleanup 成立 | Provider 的可重复选择、完整 live REVISE 或大样本稳定性 |
| 真实 Hermes autonomous REVISE | PASS（窄 receipt） | 全新 live Volume `worldline-c2a270e75800463c` 中真实 Hermes fresh Session 在 `OPEN_DEPENDENCY_MATCH → REOPEN` 后提交 `commit_deliberation`，proposal outcome 为 `REVISE`；8 个 Wake `COMPLETED`，产品 `/continue` 自动 Seal，raw DB `SEALED/READY` | 不是模型稳定性 benchmark；其他 Wakes 使用 Host-controlled wait，不扩张为全卷自主性声明 |
| 真实 Hermes 补充轨迹 | NOT PASS，已排除 | 新 Volume `worldline-91c7caa580ca49dc` 暴露了真实 provider/tool 失败：5 个 Agent Wake 为 `live_wake_failed`；专属 Gateway 已按 owner 精确停止 | 不能把这条失败轨迹写成 real Hermes PASS |
| live Product receipt | PASS（Host-controlled） | 新 Volume `worldline-0d8a466215d74cca` 的 Human `REVISE`、史可法 delayed Knowledge、Field、自动 Seal 和 Archive receipts 可复核 | 不证明 Hermes 自主产生了 `REVISE`，也不替代主轨迹的真实 Hermes Deliberation |
| 真人反馈 | `UNCOLLECTED` | 尚无主观体验结论 | 不得由 coding agent 代答 |

## 可重复的确定性检查

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

Slice 11 完成后的全量 `uv run pytest -q` 已通过；新增 Product Convergence acceptance tests 与 Archive/frontend 负面断言均通过。依赖层的 Starlette/httpx 和 pydantic warning 仍原样保留，不把 warning 写成“已消除”。

确定性 acceptance 覆盖的关键边界包括：

- 读取已存 snapshot 不重放 Runtime，也不把 Applied Field/Silence 伪造为事实；
- Drafting Aid 是只读、无 Profile/Memory/World tool 的窄 assist；
- Execution Assist provider 超时后 Human Judgment 仍写入；
- late action conflict 不回滚 Course；
- handback 复用同一个 Wake，不产生新的 Wake；
- 完成判断后离席不会凭空新增 Wake；
- Archive 只给 History、Lives、Past 与 durable reality，不恢复 Event Viewer、Wake、Moment 或 Runtime ledger；
- V7 Endogenous History 的两条 deterministic Worldline 真实分叉、形成不同 topology/Knowledge/现实并分别 Seal。

## 浏览器检查记录

本轮针对当前源码做了局部 fixture 浏览器检查：

1. World 中可以看到南都定策，走近史可法并进入 Judgment Desk；
2. Human-held 时 World 入口被禁止，离席后可以回到 World；
3. Past/Archive 读取不显示内部 Archive、Runtime、Event、Wake、Moment 等术语；
4. 390px 移动视口没有横向溢出，渲染后的内部术语扫描为空；
5. 浏览器 console 没有 error 或 warning。

这是浏览器层的当前实现检查，不等价于真实 Hermes 或真人接受度。

## 本轮隔离真实 Hermes 主轨迹

2026-08-14 在独立临时 SQLite、Hermes Home、loopback Gateway `127.0.0.1:51783` 上创建了全新的 live Volume `worldline-1208b91809d448e6`。运行时使用 Hermes `v0.20.0`；没有覆盖项目默认数据库、默认 Hermes Home 或默认 Gateway。

实际结果摘要：

1. 六个 Volume Profile 均 materialize，Gateway owner 与 runtime epoch 对齐；Profile API probe 为 6/6 `200`，multiplex 可用，跨 Profile 请求返回 `401`；
2. 产品路径进入史可法，形成 Human-held Lifetime；`Drafting Aid` 返回 `200 / available=false`，没有调用 Persistent Profile。确定性测试进一步证明 Drafting Aid 失败或不可用时不影响 Human Judgment；
3. 首次 Human `CHANGE` 返回 `200`，之后仍由 Host 验证 proposal；真实轨迹出现 `DECISION_HORIZON_ESTABLISHED`、`DECISION_HORIZON_HELD`、`DELIBERATION_COMMITTED`、`ATTENTION_EVALUATED` 等事件；
4. 其他 Lifetimes 通过真实 Hermes Session 完成普通 Deliberation。最终 11 个 Wake 均为 `COMPLETED`，Wake operation 统计为 `commit_deliberation=8`、`logical_intent=1`、`investigate=1`、`operate=1`；
5. 真实轨迹包含 `FIELD_EVENT_APPLIED`、`CRISIS_RESOLVED`、`ENTITY_STATE_CHANGED`、`INVESTIGATION_COMPLETED`、`OPERATION_COMPLETED` 和消息 dispatch/delivery。Archive 对吴三桂和多尔衮各返回 1 条 `later_known`，证明 delayed Knowledge；本轨迹的 shared durable `final_reality` 为空，因此不声称有 shared final reality；
6. 通过 Host 的受控 settlement/suppression 将尚未落地的局势收束后，产品 `POST /api/worldlines/{id}/continue` 返回 `200 / volume_sealed`，不是直接调用 Seal API。最终 raw DB 为 `SEALED/READY`、tick 9，3 个 Crisis 为 2 个 `SETTLED` 加 1 个 `SUPPRESSED`，6 个 binding 为 `REVOKED`，6 个 Lifetime 为 `SEALED`；
7. Seal 后精确 cleanup 成立：任务 Gateway 端口无 listener、owner 文件消失、主轨迹的 Chronicle Profile 目录被清理；Archive 返回 `available=true`、`ending.code=structural_boundary`，并可列入 sealed Volume。

另外一条 fresh live Hermes autonomous `REVISE` receipt 为 `worldline-c2a270e75800463c`：Host 先建立带 `MESSAGE_FROM` dependency 的合法 Course，消息命中后真实 Attention 返回 `OPEN_DEPENDENCY_MATCH / REOPEN`；随后唯一的真实 Hermes Wake 使用 fresh Session，产生一个 `commit_deliberation`，proposal outcome 为 `REVISE`。该 Volume 最终 8 个 Wake 全部 `COMPLETED`，`DECISION_HORIZON_REVISED=1`，产品 `/continue` 返回 `200 / volume_sealed`，raw DB 为 `SEALED/READY`。为保持证据边界，这条窄 receipt 的其他 Wakes 使用 Host-controlled wait，不把它写成全卷模型自主性。

其中 Host settlement/suppression 是把真实 live cognition 接到结构边界的受控验收动作，不计作模型自主选择。Draft/Execution Assist provider 轨迹也不计作 benchmark。

### 补充失败轨迹

为检查 Human `REVISE` 的 live 边界，另建了 fresh Volume `worldline-91c7caa580ca49dc`。首次 Human proposal 已留在 pending moment 中，但 provider 随后对 5 个 Agent Wake 返回 `live_wake_failed`；Gateway 日志显示无效的结构化 tool 参数和失效 Wake identity。该 Volume 没有被写入主验收 PASS，专属 Gateway 已用准确的 `worldline_id + runtime_epoch` 停止；其隔离 DB 作为失败证据保留。

因此当前声明是：`HOLD` 有主轨迹的真实 Hermes 证据，`REVISE` 也有 fresh live Hermes autonomous receipt；另有 Host-controlled Product receipt 证明 Human reconsideration 与史可法 delayed Knowledge。失败补跑仍不计入 PASS。

## 三条端到端体验的 receipts

### A. Single-Life Whole Volume

`worldline-0d8a466215d74cca` 是一条只进入史可法的 live Product receipt：

- Product `/inhabit` 返回 `200`，同一 Lifetime 完成第一次判断；
- Product `/reconsider` 返回 `200`，随后产生 1 条 `DECISION_HORIZON_REVISED`，Archive 的 `judgment_history=2`；
- Host-controlled 北方消息在 tick 0 dispatch、tick 1 delivery，史可法 Archive 的 `later_known=1`；
- Field tick 9 应用，Product `/continue` 返回 `200 / volume_sealed`，Archive `ending.code=structural_boundary`；
- 这条 receipt 的 agent checkpoint 使用 Host `wait` 以避免把 provider 轨迹冒充为模型选择。主 real Hermes 轨迹 `worldline-1208b91809d448e6` 另行证明其他 Lifetimes 的真实 Hermes Deliberation、消息、调查、Operation 和 HOLD。

对应的自动化边界由 `tests/test_product_convergence_acceptance.py`、`tests/test_phase11_archive_ending.py` 和 `tests/test_product_convergence_slice9.py` 覆盖；本轮这些文件共 14 项通过。

### B. Human → Agent handback

`tests/test_handoff_requeues_the_same_wake_without_creating_another_one` 实际断言 Leave 前后的 Wake id 集合完全相同，Human Wake 回到 `QUEUED`；`tests/test_completed_judgment_then_leave_does_not_create_a_new_wake` 断言完成判断后离席不新增 Wake。主 real Hermes Volume 还实际记录了 `LIFETIME_INHABITED` 与 `LIFETIME_LEFT`，最终全部 Wake `COMPLETED`。

### C. V7 Divergence as Product

确定性 receipt：

```bash
uv run pytest -q tests/test_v7_endogenous_history.py -k 'complete_deterministic_worldlines_a_and_b_diverge_and_seal'
```

本轮结果为 `1 passed`。该测试真实比较两条独立 Worldline 的 North record、Nanjing/Southern topology、Knowledge、shared World consequence 和最终 Seal，不把 Branch A/B 术语放进公共产品投影。主 real Hermes Volume 还观察到 `FIELD_EVENT_APPLIED → CRISIS_RESOLVED → ENTITY_STATE_CHANGED → CRISIS_SETTLED/CRISIS_SUPPRESSED` 的单条因果链；这证明 live endogenous history 的落地事件，但不替代上述双分支 proof。

## Complexity Budget 与 Kill Criteria

本轮收敛没有新增 DB table、schema bump、persistent Agent、Product truth store、History runtime、scheduler、Wake type 或 frontend framework。Runtime materialize 的六个 Profile 属于 live Volume 的既有运行资源，不是新增产品架构。

已用测试和当前源码检查确认：Drafting Aid 不持久化、不调用 World tool、不自动 commit；Execution Assist 不写 World、不产生第二次 Judgment，失败不丢 Human Judgment；Product Projection 只读；Archive 不恢复 ledger；前端不复制 presence/attention/runtime 规则。若后续实现朝这些 Kill Criteria 方向变化，应停止并重新审查，而不是继续堆功能。

## 明确不做的声明

- 不声称模型会在不同 Provider、版本或提示下稳定复现同一选择；
- 不声称一次真实轨迹等于 benchmark；
- 不把自动化 PASS、浏览器 PASS 或 real Hermes 轨迹改写成真人满意；
- 不把局部 Crisis settlement 改写成整卷 Archive；
- 不把 deterministic V7 双分支改写成当前单条 live 轨迹已经完成双分支证明；
- 不把 `Human feedback: UNCOLLECTED` 伪造为用户反馈；
- 不把旧的 V7/real Hermes 记录复用为本轮 Product Convergence 的当前 PASS。
