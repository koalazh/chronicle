# Chronicle V5 Acceptance Record

> 记录日期：2026-08-12
> 分支：`dev_v5`
> 状态：**NOT COMPLETE — P0–P5 与完整 live V5 业务链尚未通过**

本文是 V5 的唯一当前验收记录。它只记录已经执行、可以复核、没有泄漏 Secret 的证据；`PASS` 只对对应证据层有效，不向上推导为整卷产品完成。

## 1. 目标链路

V5 Definition of Done 要求同一条 Volume Worldline 真实完成：

```text
Volume
→ multiple persistent Lifetimes
→ Human inhabits one Life
→ other Lifetimes continue
→ Leave
→ same Lifetime continues under Hermes
→ past evidence changes later action
→ independent Subjects form different expectations/actions
→ Crisis results propagate through real World objects
→ another Life can be entered later
→ Volume boundary
→ Archive / Volume Ending
→ only then revoke and clean owned runtime resources
```

当前实现已经固定了这条链的 deterministic Host/API/Archive 结构，但还没有用真实 V5 Hermes cognition 完整走通它。

## 2. Phase 证据

Phase 0–11 均已在 `dev_v5` 分别提交；Phase 12 的入口文档已由 `f52ddf9` 提交，随后以 `b287ee6` 接通最小 live Hermes Wake bridge；完整 proof gates 仍未完成：

| 阶段 | commit | 结果边界 |
| --- | --- | --- |
| 0 | `0f085bd` | baseline / migration boundary |
| 1 | `cc88750` | VolumePack / Lifetime source structure |
| 2 | `22ad7ff` | additive schema / Volume records |
| 3 | `b78dab1` | persistent Lifetime/Profile seam |
| 4 | `8f58cd3` | Inhabit/Leave controller boundary |
| 5 | `7a81ac5` | global Volume clock |
| 6 | `cfa5b35` | pending Logical Moment |
| 7 | `3a3f59e` | bounded subject continuity |
| 8 | `89c0625` | braiding / propagation structure |
| 9 | `ba6c530` | Volume Product API boundary |
| 10 | `3b3365d` | V5 product shell |
| 11 | `1ed13d5` | Archive / Volume Ending |
| 12 | `f52ddf9` + `b287ee6` | V5 source-of-truth docs、隔离 live evidence、Hermes `logical_intent` Wake bridge；P0–P5/浏览器 proof 仍未完成 |

Phase 0–11 的 commit scope、测试和边界记录同步在 task-loop `TASK.md`/`HANDOFF.md` 中；它们不替代本文件的 live proof。

## 3. 已通过的检查

### 3.1 Source / Scenario / Volume

以下命令在当前 checkout 退出码为 0：

```bash
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
```

当前摘要：

- Source Pack：`4 sources / 36 assertions / 36 events`；
- Scenario Pack：`36 canon events / fork=jiangnan-prince-command`；
- `jiashen` Volume：3 个 Crisis references；默认 Volume 有 6 条 Lifetime。

### 3.2 Automated / static

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests
node --check web/app.js
node --check web/router.js
node --check web/state.js
git diff --check
```

结果：全部通过；pytest 仅保留既有 Starlette/httpx、Pydantic 和 FastAPI deprecation warnings。测试覆盖的层级包括：

- Volume genesis、shared clock、Crisis Instance settlement；
- Inhabit/Leave 同一 Lifetime 的 controller 边界；
- Human/Agent Pending Logical Moment、intent staging、atomic commit 和 idempotency；
- message dispatch/delivery、later-known/unknown-at-time replay；
- public World/Follow/Desk 隐私过滤；
- boundary rejection、`n013` evidence、`VOLUME_SEALED`、binding revoke、queued wake cancel；
- fixture live-materialization/cleanup seam，确认 cleanup 只在 DB 已经 `SEALED` 后调用；
- Archive public replay 与 selected Lifetime replay privacy。

这些结果证明 deterministic contract，不证明真实模型产生了正确的主体行动。

## 4. 浏览器证据

### 已有证据：Phase 10 shell flow

在独立临时 SQLite 和本地 server 上验证过：

```text
homepage → World（3 个 knots）→ Follow Wu → Inhabit Desk
→ Continue pending → Decision/wait → Leave
```

当次 console errors 为 `[]`，页面保持纸本文书视觉。该证据只覆盖 Phase 10 flow 和当时的 viewport；它不覆盖 Phase 11 新增 Archive/Ending，也不覆盖四种响应式宽度。

### 尚未通过：Phase 11 / responsive

以下仍是 `NOT PROVEN`：

- Archive list → Public Replay → selected Lifetime Replay 的真实浏览器交互；
- Volume Ending 的 sealed/unsealed 两态浏览器交互；
- 1440、1280、768、390 四种 viewport 的 no-overflow；
- 新页面的 keyboard/accessibility/busy mutation 检查；
- 新页面在真实 live API 下的状态表现。

截图、静态 HTML 和 JS syntax 都不能替代这些证据。

## 5. Hermes live evidence

### 已验证的基础链路

2026-08-12 在独立临时 SQLite、独立 Hermes Home、独立 loopback port `18642` 上执行真实 live preflight：

| 检查 | 结果 |
| --- | --- |
| Hermes CLI | v0.20.0 |
| `VolumeRuntime.create(runtime_mode="live")` | materialized 6 个 Lifetime Profiles |
| Gateway health | PASS |
| 6 Profile routes | 全部 `200` |
| Profile toolsets | 全部 `memory` |
| valid Profile key | `200` |
| cross-profile key | `401` |
| fresh Session | PASS |
| real Hermes chat | PASS；只保留响应 hash，不保留正文 |
| V5 real Wake | PASS；真实 Profile 通过 `logical_intent` staging，一个 `INTENT_COMMITTED` 与一个 `MOMENT_COMMITTED` 写入同一 Pending Logical Moment |
| product `continue` | PASS；同类隔离 API harness 返回 `200`、推进到 tick 1、attention=`DECISION`、无遗留 pending moment |
| Gateway teardown | PASS；owner/PID 起始标识复核后 clean stop，未留下监听端口 |

这证明 Hermes 基础运行资源和一条真实 V5 Agent Wake 在隔离目录可工作，并实际经过 V5 MCP staging 与原子 Logical Moment commit。它仍没有证明 Human↔Hermes continuity、跨 Subject 行为差异、Learning、完整 message/settlement braid 或 Volume Ending。

### 隔离边界

以上 harness 使用独立临时 SQLite、Hermes Home 和 loopback 端口（真实 Wake 使用 `18647`，product API 使用 `18648`），没有触碰项目现有 Hermes Home、数据库或其他监听服务；临时目录在 harness 退出后清理。

## 6. P0–P5 Proof Gates

| Gate | 当前状态 | 证据与缺口 |
| --- | --- | --- |
| P0 Subject Proof | **NOT PROVEN** | 尚无同一 Lifetime 的完整真实 `Hermes → Human → Hermes → Human`；单 Wake 已证明 same Profile 可创建 fresh Session 并提交意图，但尚未证明 handoff 后 obligations/plans/revisits 与新 evidence 的连续行为。 |
| P1 Multi-Subject Proof | **NOT PROVEN** | 尚无两个真实 Profiles 对同一第三方持有不同 evidence/expectation 并实际做出不同 action 的同一 Run 证据。 |
| P2 Temporal Proof | **PARTIAL / NOT COMPLETE** | 单 Wake live 与 deterministic message transit/delivery 已有证据；尚无真实 `A sends → B decides before arrival → arrival → B reconsiders`，也尚无 Human/Agent 同 slice 的 live order-independence proof。 |
| P3 Learning Causality | **NOT PROVEN** | 尚无 evidence-backed expectation → later retrieval → materially different action 的 live paired memory-ablation test。 |
| P4 Game Proof | **NOT RUN** | 尚无一个 Knot 的 10–20 条 live Hermes trajectory，也没有 Investigation/Wait/Agreement/tension 观察记录。 |
| P5 30-minute Product Proof | **NOT RUN** | 尚无真实用户试玩和独立 evaluator 对“他们在我离开后仍有下一步”的记录。 |

## 7. Live V5 acceptance checklist

计划要求同一真实 V5 中记录以下项目；当前均未形成完整可关联链：

- 4+ persistent Profiles（单次 live V5 harness 已 materialize 6 个，并使用其中一个完成真实 Wake；跨多次缺席的连续性仍未完整记录）；
- 初次 Human Life 的 dormant Profile；
- 0 mandatory ORIENT（已通过单次 live V5 创建与 Wake 证据）；
- 至少一条真实 `logical_intent` staging → `INTENT_COMMITTED` → `MOMENT_COMMITTED`（已通过单次 live V5 证据）；
- Human→Hermes handoff、same Profile、fresh Session；
- delayed message、crossing action、off-screen Agent↔Agent causal chain；
- evidence-backed past affecting future；
- Crisis settlement 后 Profiles 仍存活；
- second Crisis / later Knot continuation；
- later cross-crisis knowledge arrival；
- final Volume seal；
- seal 之后才 revoke/clean owned Profiles。

当前不能用 preflight、fixture 或旧 V4 live runtime 填充这些空项。

## 8. 当前 blockers 与下一步

1. 在同一临时 live Run 上完成 P0–P4 的 instrumented proof，并把 evidence IDs、ticks、session/profile 状态和清理结果写入脱敏记录。
2. 完成 P5 真实试玩和独立 evaluator 记录；不能用开发者主观感受替代。
3. 对 Phase 11 Archive/Ending 补做 1440/1280/768/390 浏览器检查，记录 console、overflow、privacy、busy mutation 和 keyboard 状态。

在以上 blocker 关闭前，不能把本文件状态改成 `COMPLETE`，也不能把 README、产品发布说明或 commit message 写成“V5 已完成”。
