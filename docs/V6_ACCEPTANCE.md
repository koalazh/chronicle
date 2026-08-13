# Chronicle V6 Acceptance Record

> 状态：**COMPLETE — V5 baseline、V6 deterministic/product/browser gates 与隔离 real Hermes Volume 链均已执行；真人产品问卷仍保持未完成边界**
>
> 本文只记录实际执行、可复核且不含 Secret 的证据。fixture、自动化、浏览器、Doctor、Hermes readiness 与 real Hermes business chain 互不替代。

## V5 boundary retained

V5 P0–P4 在 `docs/V5_ACCEPTANCE.md` 所列证据层为 PASS。V5 P5 仍为 `CANDIDATE`：缺少真人试玩逐题回答与正式 Completion Challenge。V6 不伪造回答，也不把 P5 改成 PASS。

## Phase 0 baseline

| Check | Status | Evidence |
| --- | --- | --- |
| `uv sync` | PASS | 2026-08-13，exit 0，lock-resolved environment |
| Source / Scenario / Crisis validators | PASS | `4 sources / 36 assertions / 36 events`; `3 Seats / 15 locations / 16 routes`; `jiashen / 3 crisises` |
| `pytest` / Ruff / compileall | PASS | `uv run pytest -q` exit 0；318 tests collected；Ruff 与 compileall exit 0 |
| web syntax / diff check | PASS | `web/app.js`、`web/router.js`、`web/state.js` syntax 与初始 `git diff --check` 均 exit 0 |
| baseline test count / warnings / schema / P0–P5 | PASS | schema `10`；pytest 4 条既有 warning；V5 P0–P4 scoped PASS，P5 CANDIDATE |

## Phase 1 characterization

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| Event → Knowledge → Wake | PASS | 6 项 `tests/test_v6_characterization.py` 覆盖 message、operation completion 与 investigation observation 的现有 V5 链路 |
| Current Plan | PASS | 已固定 `plan[0]` 与 prose `reconsider_when` 的现状，作为 Phase 2 migration 的回归边界 |
| Live harness write boundary | PASS | 通过 Volume MCP staging 测试同一 Wake 的第二个不同写入被拒绝；这不是 Provider 调用证据 |
| `/continue` step boundary | PASS | fixture API 测试每 request 仅新增一个 `TIME_ADVANCED` |
| Full deterministic regression | PASS | `uv run pytest -q` exit 0，324 tests collected；Ruff、compileall exit 0 |

Phase 1 不主张 Continuous Agency、Attention、bounded agency 或 real Hermes 成功；P6–P9 仍是 `NOT_RUN`。

## Phase 2 Decision Horizon

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| One persisted Current Course | PASS | 新 Course 只写入 `Lifetime.plan[0]`；未增加 Horizon 表或 parallel Runtime |
| Course ledger | PASS | `PLAN_UPDATED` 同 Moment 追加 `DECISION_HORIZON_ESTABLISHED` 或 `DECISION_HORIZON_REVISED`，可由 append-only events 重建变化 |
| Typed dependencies | PASS | data-only allow-list；拒绝 arbitrary predicate / unsupported fields；未使用 LLM relevance |
| Continuity | PASS | tick、SQLite restart、HUMAN↔AGENT controller switch 与 fresh-session prompt 均保留相同 Course |
| V5 compatibility / regression | PASS | legacy `plan_json` read-only 投影；`tests/test_v6_decision_horizon.py` 5 passed；完整 pytest exit 0（329 tests collected）、Ruff / compileall exit 0 |

这是 deterministic fixture / mocked fresh-session payload 证据，尚未证明 Attention、continuous product flow 或 real Hermes business chain。

## Phase 3 Knowledge / Attention separation

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| Deterministic policy | PASS | `subject_attention.evaluate_attention` 是 pure logic，输出 decision / reason / trigger IDs / matched dependency IDs；没有 DB、LLM 或 World write |
| Irrelevant known fact | PASS | 无关来信进入 Wu Knowledge，追加 `ATTENTION_EVALUATED(BACKGROUND)`，不创建 Wake |
| Typed dependency match | PASS | `MESSAGE_FROM(dorgon)` 与真正送达的 Dorgon message 产生一条 `REOPEN` Wake，且保留 matched dependency ID |
| Expected own completion | PASS | `prepare_force` completion 进入 Knowledge，但没有 Course dependency 时是 `BACKGROUND`，不重复叫回主体 |
| Host-owned deadline | PASS | Course `DEADLINE` 参与 next-tick、写 `DECISION_DEPENDENCY_DUE`、进入 Knowledge 后才 `REOPEN`；不依赖 wall-clock polling |
| Regression | PASS | `tests/test_v6_attention.py` 5 passed；完整 pytest exit 0（334 tests collected）、Ruff / compileall 与 Source / Scenario / Crisis validators exit 0 |

Phase 3 尚未把 Offer / Agreement 的现有 V5 `tick+1` scaffold 当作真实 remote transport；该边界留给 Phase 8。上述不是 continuous `/continue`、browser 或 real Hermes business evidence。

## Phase 4 Reality-first Context

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| Frozen sections | PASS | `why_now`、`since_last_deliberation`、`binding_reality`、`previous_course`、`relevant_experience`、`affordances` 已由现有 `LifetimeContextBuilder` 生成 |
| Reality before memory | PASS | Course 等待 Dorgon 时，Li 的公开东进消息仍进入 `since_last_deliberation`；不会被 token relevance 或 Course 过滤 |
| Last deliberated boundary | PASS | 使用 Course `last_deliberated_tick`，保留无 Wake 的 Background Knowledge |
| Privacy / affordance scope | PASS | Nanjing context 只暴露 Ma 可用的 operation / investigation / offer terms，未泄漏其他主体私有能力 |
| Regression | PASS | Phase 4 定向 2 passed；Ruff、compileall、diff check 已通过；完整 pytest 与三项 validators 在提交前复跑 |

Phase 4 仍只是冻结 context 编译证据；尚未证明 HOLD / REVISE、continuous `/continue`、P6–P9、browser 或 real Hermes business chain。

## Phase 5 Deliberation Protocol

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| HOLD as cognition | PASS | `commit_deliberation` emits `DELIBERATION_COMMITTED` + `DECISION_HORIZON_HELD` with zero World action and advances the last-deliberated boundary |
| Agent REVISE evidence | PASS | missing `evidence_event_ids` is rejected before staging; actor-visible delivery can revise Course and commit one message |
| 0..1 agency | PASS | proposal shape rejects two world actions; existing Host/pack validators reject invalid action before any staged operation |
| Atomicity / causal chain | PASS | Course, belief, one action, `MOMENT_COMMITTED` are committed in one DB moment; action parent is `DELIBERATION_COMMITTED` |
| Restart / idempotency | PASS | staged proposal survives new `ChronicleHost`, commits once, and repeated commit is idempotent |
| Regression | PASS | Phase 5 focused tests 5 passed; full pytest, Ruff, compileall, content validators and web syntax are rerun at phase close |

Phase 5 deterministic evidence does not prove Provider behavior, continuous `/continue`, P6–P9, browser, human acceptance or isolated real Hermes business evidence.

## Phase 6 Product Continuous Agency

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| bounded `/continue` | PASS | `tests/test_v6_continuous_agency.py` 验证一次 request 可跨多个 Global Tick，遇到 Human Attention 返回；fixture 仍保留每个 `advance_one` 的 atomic boundary |
| safety cap | PASS | product router 设定 12 ticks / 24 Agent deliberations / 30 秒 wall time；达到 cap 返回 `continue_status=safety_cap`，不抛业务错误、不启后台 daemon |
| voluntary reconsideration | PASS | 同一当前 tick 建立 Human-only boundary；定向测试确认 current tick 不变，且没有新增 `TIME_ADVANCED` |
| Life Desk semantics | PASS | `current_course`、`since_last_deliberation`、`why_now`、`binding_reality`、`reconsideration` 与旧字段并存；frontend copy / syntax checks 通过 |
| Regression | PASS | Phase 6 定向 product API、desk projection、frontend copy tests 通过；完整回归、validators、browser 与 real Hermes 在后续阶段复跑 |

上述 PASS 只覆盖 deterministic fixture / product surface；尚未证明 Provider 行为、P6/P7/P8/P9 完整 trajectory、browser 多视口或 live Hermes business chain。

## Phase 7 Agency Conservation

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| Subject / Institution / Claimant separation | PASS | Pack contract test confirms each Nanjing operation actor set, owned assets, claimant entities and no claimant Lifetime/Profile |
| cross-subject refusal | PASS | Ma attempting `formalize_fu_regency` is rejected at staging with `operation_authority_denied`; no institution state mutation |
| effect ownership / causal chain | PASS | `make_fu_backing_visible` completion and entity effect retain `seat_id=ma-shiying`, with effect parent equal to `OPERATION_COMPLETED` |
| source-first scope | PASS | No generic agency layer, extra Agent, or unsupported mechanism added; existing Pack descriptions remain the authority |

Phase 7 evidence is deterministic fixture / Pack evidence. It does not prove real Hermes trajectories or replace the Phase 8 content audit.

## Phase 8 Content / World Correctness

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| remote Offer transport | PASS | `tests/test_v6_content_world.py` verifies Wu → Dorgon proposal uses the Shanhai–Liaoxi route, arrives at tick 3, and creates no pre-arrival Agreement |
| response / Agreement causality | PASS | Dorgon acceptance is dispatched at tick 3, reaches Wu at tick 5, then emits `OFFER_ACCEPTED` / `OFFER_CHANGED` / `AGREEMENT_CREATED` with `effective_tick=5` |
| structured commitment visibility | PASS | `visible_to` hides an in-transit Offer; delivery admits a structured Offer fact and Attention boundary; ordinary message transport remains unchanged |
| Shanhai fixed operation / pressure | PASS | Pack test confirms `prepare_force` is a source-defined 2-day fixed operation; pressure remains tick 5 `EXOGENOUS`, `scenario_assumption`, assertion `c015` |
| Nanjing source bounds | PASS | Phase 7 agency tests retain claimant/institution/backing separation; no unsupported Lifetime, consensus or resolver mechanism added |
| Regression | PASS | Phase 8 focused tests, full `uv run pytest -q`, Ruff and compileall pass; evidence is deterministic fixture/source only |

Phase 8 does not claim browser, Hermes Provider or real Hermes business-chain completion.

## Phase 9 Harness Ablation

| Experiment | Status | Evidence / boundary |
| --- | --- | --- |
| one-action | PASS | Promptless direct `stage_deliberation` with two blind-staged actions is rejected before any operation; retain `0..1` |
| authored maneuver | PASS | Removing `prepare_force` from a validated development Pack leaves `enter-shanhai-pass` without a source-defined path to `READY`; retain the maneuver |
| verbose prompt | BOUNDED | Host/schema rejection is prompt-independent; no real Provider sample exists for a shortened prompt, so current protocol hints remain |
| fixed pressure | BOUNDED | Source/Pack effect is verified; no strong-agent trajectory comparison with pressure disabled was run |
| Regression | PASS | `tests/test_v6_harness_ablation.py` 2 passed; full deterministic suite, Ruff and compileall pass |

Phase 9 proves only the bounded scaffold decisions above. The two `BOUNDED` rows require isolated real Hermes business evidence before any deletion.

## Phase 10 V6 Game Tests

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| Perfect Wait | PASS | Silent fixture driver reaches finite Shanhai and Nanjing outcomes/limits; no benchmark claim |
| canonicality perturbation | PASS | Actor-visible Nanjing court/recognition state perturbation changes Han affordances |
| role-state swap | PASS | Pure Attention result is unchanged when only seat labels change under identical Course/Knowledge/dependency inputs |
| Shanhai / Nanjing trajectories | PARTIAL | Existing Pack/causal loop tests pass; strong-agent paired trajectories remain for isolated real Hermes |
| Regression | PASS | `tests/test_v6_game_proofs.py` 4 passed; full deterministic suite, Ruff and compileall pass |

Phase 10 deterministic PASS does not claim strong-model Canonical History, live Role-State Swap or human product acceptance.

## Phase 11 Archive / UX

| Check | Status | Evidence / boundary |
| --- | --- | --- |
| append-only judgment history | PASS | `tests/test_v6_archive_history.py` verifies `judgment_history` is rebuilt from the selected Lifetime's Horizon events and does not expose ledger field names |
| Archive product copy | PASS | Public replay, Lifetime replay and judgment replay are separated; selected replay remains opt-in and the page text contains no Profile/Session/Memory/Wake/Runtime or thinking-animation jargon |
| responsive browser surface | PASS | Isolated fixture server `127.0.0.1:18880`, sealed `worldline-2d4eaec1219045d0`, Archive → 吴三桂 judgment replay checked at 1440/1280/768/390; all four had `scrollWidth == innerWidth` and no error/warn logs |
| deterministic regression | PASS | `uv run pytest -q`: 357 passed; Ruff, compileall, JS syntax and diff check pass |

Phase 11 evidence is deterministic fixture/API plus browser product evidence. It does not prove the Phase 12 real Hermes business chain or replace human product answers.

## Phase 12 isolated real Hermes Volume acceptance

2026-08-13 在全新临时资源中执行了一条完整 Volume 链：

- 资源：临时 SQLite、临时 Hermes Home、Gateway `127.0.0.1:18882`；没有使用项目默认数据库、全局 Hermes Home 或未知监听器；脚本结束后精确临时目录、Profiles、Gateway owner 与该端口均无残留。
- `worldline-558ea78dc4154343` 创建成功，六个 Lifetime Profile 均实际 materialize；`/api/worldlines`、`inhabit`、`leave`、`continue`、`decision`、`archive`、`seal` 均走真实 Volume product path。
- Human 吴三桂先建立“暂不作最终归属，继续维持关口可控，等清方明确回复”的 Course；离席后，李自成旁支消息在 tick 2 到达并被吴纳入 `BACKGROUND`，没有为该无关事实创建吴的 cognition Wake；多尔衮消息在 tick 4 到达并产生吴的 `REOPEN`。
- 真实主体事件摘要：`ATTENTION_EVALUATED=12`、`DELIBERATION_COMMITTED=7`、`MESSAGE_DELIVERED=7`、`MESSAGE_DISPATCHED=7`、`TIME_ADVANCED=10`、`MOMENT_COMMITTED=5`；Deliberation seats 为多尔衮、吴三桂、史可法、马士英、韩赞周，说明至少两个 Crisis 中的独立主体真实提交了判断。
- `attention_by_seat` 中吴三桂为 `REOPEN → BACKGROUND → REOPEN → BACKGROUND`；`wu_background_without_wake=true`、`wu_reopen=true`、`wu_v6_deliberation=true`、`dorgon_independent=true`。每个实际唤醒主体都有真实 Hermes session 记录；这证明的是一次隔离业务链，不是所有模型输出的稳定性 benchmark。
- 同一 Volume 中山海关与南京 Crisis 都被 Host 结算；结构边界 `structural_boundary` ready 后 `seal=200`，Archive selected Wu judgment history 为 3 条，最终 `status=SEALED`、bindings 为 `REVOKED`、Profile 目录已清理。

这条 live 证据覆盖了 Volume 的真实 transport、Knowledge/Attention、独立主体 Deliberation、Human re-entry、Archive、Seal 与 cleanup。它不伪造真人对以下问题的回答，也不把单次 Provider 运行升级为模型质量或重复运行率保证。

## V6 Proof Gates

| Gate | Required claim | Status | Evidence |
| --- | --- | --- | --- |
| P6 Continuous Agency | Course survives noise, confirming/disconfirming reality, session/restart/controller changes | PASS | Deterministic restart/controller tests plus isolated Volume trace: Wu background fact did not reopen cognition, later Dorgon reality did; Human Leave/Re-enter and live Deliberation/Archive chain completed |
| P7 Attention | World events > actor-known events > attention boundaries approximately equal deliberations | PASS | Live trace recorded `TIME_ADVANCED=10`, `MESSAGE_DELIVERED=7`, `ATTENTION_EVALUATED=12`, `DELIBERATION_COMMITTED=7`; explicit Wu `BACKGROUND` without Wake and later `REOPEN`; no fixed benchmark claim |
| P8 Bounded Agency | no cross-subject commitment, lawful Agreement/Institution, transport/privacy/retry/restart safety | PASS | Deterministic ownership, causal-parent, remote Offer/Agreement, privacy and idempotency tests pass; live Volume preserves independent seats, route-delivered messages, revoked bindings and exact cleanup |
| P9 Strong-Agent Game | Perfect Wait, canonicality perturbation, role-state swap, Shanhai/Nanjing trajectories | PASS | Phase 10 deterministic probes PASS plus one isolated real Volume containing Shanhai and Nanjing Crisis trajectories with 7 real Deliberations; not a benchmark or paired-model score |

## Required evidence layers

- deterministic tests and static checks;
- Shanhai and Nanjing trajectory evidence;
- isolated real Hermes Volume with fresh sessions, background Knowledge, Attention, cleanup and no secrets;
- browser checks at 1440, 1280, 768 and 390 without horizontal overflow or internal jargon;
- source/diff review and final independent Completion Challenge.

## 真人产品验收 checklist

Coding agent 不能替真人回答。V6 产品验收前提供给试玩者：

1. 为什么这一次系统又停下来问你？
2. 没有问你的那几天，你觉得发生了什么？
3. 你觉得之前作出的决定有没有一直“在起作用”？
4. 重新进入同一个人以后，你觉得还是同一段人生吗？
5. 如果重新开始一条 Worldline，你最想改变的是哪个“判断”？

尚未收集答案；这不是 PASS。

## Final repair acceptance — r11 (2026-08-13)

本节是对本文较早 `worldline-558ea78dc4154343` 记录的最新补充；较早记录保留为历史证据，不覆盖本次结果。r11 使用独占临时 SQLite、Hermes Home、产品端口 `127.0.0.1:18786` 和 Gateway `127.0.0.1:18886`，真实 Worldline 为 `worldline-f44420f2821e42b3`。

### Real business chain

- Human 在真实产品页面进入吴三桂，提交非空中文 Course，Leave 后再次进入；Course、判断历史和 `BACKGROUND/REOPEN/HOLD` 语义持续存在。
- 六个真实 Hermes Lifetime Profile 完成 fresh-session wake。脱敏 Ledger 摘要：`DELIBERATION_COMMITTED=25`、`ATTENTION_EVALUATED=32`、`DECISION_HORIZON_HELD=6`、`DECISION_HORIZON_REVISED=13`、`MESSAGE_DISPATCHED=8`、`MESSAGE_DELIVERED=8`、`OPERATION_STARTED=7`、`OPERATION_COMPLETED=7`、`OFFER_PROPOSED=1`、`OFFER_ACCEPTED=1`、`AGREEMENT_CREATED=1`、`MOMENT_COMMITTED=13`。
- 山海关 `WINDOW_EXPIRED_DEFERRED` 在 tick 5 结算；南京真实主体通过 `convene_recognition_assembly`、潞王入场、公开支持 Offer/Agreement 和 `formalize_lu_regency` 在 tick 14 结算为 `LU_RECOGNIZED`；南方随后经真实产品 Human Han 的两项操作与统一 local/global clock 在 tick 18 结算为 `JIANGBEI_COORDINATION`。
- Seal 回执为 `VOLUME_SEALED`，boundary code 为 `structural_boundary`，Worldline 为 `SEALED/ARCHIVED`；六条 bindings 为 `REVOKED`。Profile 目录为空，Gateway owner 与 18786/18886 监听均不存在。完整临时目录已移动到 `/Users/koala/.Trash/chronicle-v6-live.r11-complete-20260813`，未进入 Git。

### Browser read-back

在产品端口重启后，浏览器实际打开 `/archive`，看到“已封存”和时刻 `18`；打开公共回看并选择吴三桂，页面显示其判断从“先守住山海关，等关外回信再决定出兵”到后续维持的回看。页面文本没有 Profile、Session、Memory、Wake、Runtime 等内部术语；Phase 11 已有 1440/1280/768/390 no-overflow、空 warn/error 日志证据，r11 补充了同一 real Volume 的 Archive read-back。

### Final proof-gate matrix

| Gate | Final status | Ground |
| --- | --- | --- |
| P6 Continuous Agency | PASS | deterministic restart/controller tests，加上 r11 的 Human Course、Leave/re-entry、Wu `BACKGROUND → REOPEN → HOLD` 与 fresh Session |
| P7 Attention | PASS | r11 同一 Ledger 的 World/Knowledge/Attention/Deliberation trace；Wu 的无关事实没有 Wake，结构压力才打开 Wake |
| P8 Bounded Agency | PASS | deterministic ownership/causal/transport/privacy/retry/restart tests，加上 real Offer/Agreement、独立主体与 revoked cleanup |
| P9 Strong-Agent Game | PASS（分层证据） | Perfect Wait、Canonicality、Role-State deterministic probes；r11 同一真实 Volume 的 Shanhai/Nanjing continuous trajectory；不宣称 paired-model benchmark |

Phase 9 的四项 ablation 当前均由 `tests/test_v6_harness_ablation.py` 执行并通过：one-action、authored maneuver、prompt-complexity Host boundary、fixed-pressure Pack/Host boundary。后两项的结论是保留协议提示与来源 pressure，不把 Host/Pack 结果写成 Provider 策略质量实验。

最终工程状态仍不包含 V5 P5 或 V6 真人产品问卷的答案；这两项继续为 `CANDIDATE/UNCOLLECTED`，没有被 coding agent 代答。
