# Chronicle V6 Acceptance Record

> 状态：**IN_PROGRESS — V5 baseline 已冻结；尚未执行 V6 P6–P9 proof**
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

## V6 Proof Gates

| Gate | Required claim | Status | Evidence |
| --- | --- | --- | --- |
| P6 Continuous Agency | Course survives noise, confirming/disconfirming reality, session/restart/controller changes | NOT_RUN | |
| P7 Attention | World events > actor-known events > attention boundaries approximately equal deliberations | NOT_RUN | |
| P8 Bounded Agency | no cross-subject commitment, lawful Agreement/Institution, transport/privacy/retry/restart safety | NOT_RUN | |
| P9 Strong-Agent Game | Perfect Wait, canonicality perturbation, role-state swap, Shanhai/Nanjing trajectories | NOT_RUN | |

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
