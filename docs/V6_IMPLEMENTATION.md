# Chronicle V6 实施记录

## 开始信息

- start_commit: `13dcbe28ac781828f5553de918897ddd7f4e6e9e`
- branch: `dev_v6`
- date: 2026-08-13
- worktree: `/Users/koala/work/product/chronicle-v6`

## V5 baseline

当前 schema version 为 `10`。V5 的 Volume Worldline、Global World Tick、Persistent Lifetime、frozen Perspective、Pending Logical Moment、Profile/Session 边界、Ledger、Archive 与 cleanup 均是 V6 的既有基础。

2026-08-13 在干净 `dev_v6` worktree 上实际执行：

- `uv sync`：exit 0；
- `uv run chronicle source validate`：`4 sources / 36 assertions / 36 events`；
- `uv run chronicle scenario validate`：`3 Seats / 15 locations / 16 routes / fork=jiangnan-prince-command`；
- `uv run chronicle crisis validate`：`jiashen / 3 crisises`；
- `uv run pytest -q`：exit 0；`pytest --collect-only -q` 统计为 318 tests；
- `uv run ruff check .`、`uv run python -m compileall -q chronicle tests`、`node --check web/app.js`、`node --check web/router.js`、`node --check web/state.js`：均 exit 0；
- 初始源码树的 `git diff --check`：exit 0。

完整 pytest 保留 4 条既有依赖/框架 warning：Starlette TestClient/httpx deprecation、Pydantic settings incomplete field definition，以及 FastAPI `on_event` deprecation 两条；本阶段不修改它们。

根据 `docs/V5_ACCEPTANCE.md`，P0–P4 仅在各自所列证据层为 PASS；P5 是 `CANDIDATE`，仍缺真人试玩逐题回答与正式 Completion Challenge。V6 不改写这个事实。

## Phase 1 Characterization + seam

本阶段只新增 `tests/test_v6_characterization.py`，没有改变生产运行时语义。它固定当时 V5 的实际边界：

- `MESSAGE_DELIVERED` 会写入 recipient Knowledge，并立即产生 `OBSERVATION` Wake；
- `OPERATION_COMPLETED` 与 `OBSERVATION_OBTAINED` 分别会写入 Knowledge，并产生相应结果 Wake；
- `Lifetime.plan` 当前仅投影 `plan[0]` 为 Current Plan，`reconsider_when` 仍是 prose；
- Volume MCP 在同一 Wake 内拒绝第二个不同 idempotency key 的世界写入；
- 现有 `/continue` 每个 request 只调用一次 Global advance（一个 `TIME_ADVANCED`）。

2026-08-13 实际执行：`uv run pytest -q tests/test_v6_characterization.py` 为 6 passed；完整 `uv run pytest -q` exit 0（324 tests collected）；`uv run ruff check .` 与 `uv run python -m compileall -q chronicle tests` 均 exit 0。上述是 fixture / deterministic 证据，不构成 P6–P9 或 live Hermes 证明。

## Phase 2 Decision Horizon

`Lifetime.plan[0]` 现为唯一持久化的 Current Course；未新增 Horizon 表或平行 Runtime，数据库 schema version 仍为 `10`。新写入在保留 V5 `objective`、`steps`、`rationale` 与 `reconsider_when` 读取字段的同时，加入：

- `course_schema_version`、`course`、`status=IN_FORCE`；
- `established_tick` / `established_event_id`；
- 只接受 data-only typed `open_dependencies`（`DEADLINE`、`MESSAGE_FROM`、`OBSERVATION_FOR`、`OPERATION_OUTCOME`、`OFFER_CHANGE`、`AGREEMENT_CHANGE`、`ENTITY_OBSERVED_CHANGE`），拒绝 predicate / 任意代码字段；
- `explicit_rationale`、actor-known `evidence_event_ids`、`last_deliberated_tick` / `last_deliberated_event_id`。

每次首次建立或替换 Course 都仍在同一个 atomic Pending Logical Moment 内写入 `PLAN_UPDATED`，并追加 `DECISION_HORIZON_ESTABLISHED` 或 `DECISION_HORIZON_REVISED`。旧 V5 `plan_json` 不在 read 时被改写，而是在 Context 中投影为可读的 Course。`tests/test_v6_decision_horizon.py` 覆盖单 Course、typed dependency reject、tick / restart / HUMAN↔AGENT controller switch / fresh-session prompt continuity、revision 与 legacy read；定向 5 passed、完整 pytest exit 0（329 tests collected）、Ruff / compileall exit 0。

## Phase 3 Knowledge / Attention separation

新增 `chronicle/subject_attention.py`。`evaluate_attention(lifetime, new_known_events, projection)` 是不读 DB、不调用 LLM、不提交 World action 的 pure deterministic policy，并总是返回 `decision`、`reason_code`、`trigger_event_ids` 与 `matched_dependency_ids`。

- message delivery、operation completion 与 investigation observation 现在先写入 Knowledge，再在同一 tick 归并评估 Attention；`BACKGROUND` 只写 append-only `ATTENTION_EVALUATED` Ledger event，不创建 Wake；
- `MESSAGE_FROM`、`OBSERVATION_FOR`、`OPERATION_OUTCOME`、`ENTITY_OBSERVED_CHANGE` 和 Host-owned `DEADLINE` 可匹配已存在 typed dependency；其中 deadline 由 `DECISION_DEPENDENCY_DUE` 记录并进入 Knowledge，不是 wall-clock polling；
- 无 Current Course 的初始事实仍 `REOPEN`，以便建立首个判断；对已有 Course，预期操作完成和无关消息只作为 Background；
- `REOPEN` 保留 exact Wake identity 与原有来源 wake type，但 Wake 的 causal trigger 变为私有的 `ATTENTION_EVALUATED` event，包含实际进入 Knowledge 的事实 ID，而不是把任意 result 直接升级为 cognition。

Offer / Agreement 的事实 transport 仍是 Phase 8 的专门改动；本阶段未把现有 `tick+1` offer scaffold 伪装成 transport semantics。`tests/test_v6_attention.py` 覆盖无关已知消息、typed sender match、预期操作完成、deadline 与 pure policy；完整 pytest exit 0（334 tests collected），Ruff、compileall 和三项 content validator 均 exit 0。

## V6 thesis

V5 让同一人跨离席、Session 与重启继续存在；V6 让该人已形成的判断跨时间继续有效。一个 Lifetime 的 Current Course 只有在 actor-known 的现实真正改变其基础时，才经 deterministic Attention 打开新的 Deliberation；信息进入 Knowledge 本身不等于重新计算。

## Non-goals

- 不重写 Volume Runtime、World、Hermes Profile/Session 或前端框架。
- 不增加平行 V6 Runtime、generic workflow/DSL、Attention Agent、Planner/World Master、Memory V2、评分/关系系统或在线自演化。
- 不用 fixture、health、静态页面或 Agent 自述替代 real Hermes / 真人验收事实。

## Phase status

| Phase | 状态 | 说明 |
| --- | --- | --- |
| 0 Baseline | COMPLETE | V6 文档、实际 V5 baseline 与 staged scope review 已完成；本 commit 只包含此 Phase |
| 1 Characterization + seam | COMPLETE | V5 wake、Current Plan、MCP 单写入与 `/continue` 单推进已由 6 项特征测试固定；未作生产语义变更 |
| 2 Decision Horizon | COMPLETE | `plan[0]` 原位升级为唯一 Course、typed dependencies、established/last-deliberated Ledger 边界与 V5 read compatibility 已验证 |
| 3 Knowledge / Attention | COMPLETE | Knowledge admission 与 deterministic BACKGROUND/REOPEN 已分离；无关消息与预期操作不再直接创建 Wake |
| 4 Context Compiler | NOT_STARTED | |
| 5 Deliberation Protocol | NOT_STARTED | |
| 6 Product Continuous Agency | NOT_STARTED | |
| 7 Agency Conservation | NOT_STARTED | |
| 8 Content / World Correctness | NOT_STARTED | |
| 9 Harness Ablation | NOT_STARTED | |
| 10 V6 Game Tests | NOT_STARTED | |
| 11 Archive / UX | NOT_STARTED | |
| 12 Real Hermes live acceptance | NOT_STARTED | |

## Open questions

- V6 typed dependency 最小集合将以现有甲申两类 Crisis 的实际事件/操作为准；不因预设清单而引入未使用类型。
- Phase 8 的 remote Offer/Agreement、fixed pressure 与南京 ownership 只在 source-first characterization/实验支持时改变。
- Phase 12 依赖可用 Provider/Hermes 环境；在运行前必须重新核对并隔离资源。

## Experiments

- 尚未执行 V6 ablation；Phase 0 只记录 baseline。

## Accepted decisions

- 复用 `Lifetime.plan[0]` 作为 V6 Current Course 的优先落点，先升级 schema，不新建 Horizon table。
- 保留 exact wake identity、frozen Perspective、Host authority、atomicity、idempotency、message latency 和 restart safety。
- 原工作树的 `tmp/` 不属于本任务；实现仅在干净 `dev_v6` worktree 进行。

## Rejected decisions

- 建立 `V6Runtime`、`ContinuousAgencyEngine`、`NewWorldRuntime`、`NewAgentRuntime` 或 `V6Worldline`。
- 用 LLM 判断 attention、世界效果或其他 Subject 的选择。
- 把 V5 P5 的缺失真人验收伪造为 PASS。
