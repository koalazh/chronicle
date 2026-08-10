# Chronicle V4 Migration Boundary

## KEEP

- `WorldService` 作为 Agent/Human 共用的确定性世界写入边界，继续把身份绑定在 Profile token、Run、Actor 与 Wake 上，而不是放进工具参数（`chronicle/world.py`）。
- append-only `worldline_events`、Snapshot/Projection、Snapshot history、原子 moment 提交和因果 parent 链（`chronicle/db.py`）。V4 世界对象继续由 Ledger 构成，不预建每个 noun 的 CRUD 表。
- Truth / Knowledge / Belief / private Plan 的分层、Perspective lock、私有 Knowledge 仅在真实送达后写入，以及 Takeover 的后端权限控制（`chronicle/crisis_runtime.py`、`chronicle/app.py`）。
- 同 logical moment 冻结 Perspective、不同 Actor 并发、所有返回后统一提交的 scheduler 语义（`CrisisRunEngine._run_wake_moment`）。
- Run-scoped Hermes Profile materialization、ownership marker、World MCP identity、fresh Session、ordinary Wake Memory guard、Reflection rollback、runtime epoch、private Gateway child、restart reconciliation、fail-closed cleanup（`chronicle/hermes.py`、`chronicle/live_runtime.py`、`chronicle/gateway.py`）。
- live / fixture 明确分离；fixture 只能替代模型输出，不能替代 Host、Ledger、权限或 Hermes 业务验收。
- 现有 HTTP/SQLite/vanilla-web 基础、Setup/provider validation、`/api/dev/*` 诊断与中文 paper/ink/vermilion 视觉语言。
- V2 与已封存 V3 的归档、Replay 和 migration backup；不得删除或把旧语义伪装成 V4。

## GENERALIZE

- `CrisisPack` 从单个 `config.crisis_path` 变为 Volume → Crisis registry；继续保留 YAML、sources/assertions/provenance 校验，但由 Crisis 自己声明内容、surface 与 resolver contract（`chronicle/crisis.py`、`chronicle/config.py`）。
- `CrisisActorDefinition`、life state、Profile spec、controller map、Perspective 与 Replay 从三位固定历史人物变为 2–5 位 unique Decision Actors；Actor ID 不再承担 UI 或控制权语义。
- `RunMode.TAKEOVER` 接收 `human_actor_id`，只以 Crisis 的 `playable_actor_ids` 和持久化 controller map 判断 Human/Agent；Human 不 materialize Profile，其余 Agent 全部 materialize。
- 当前 locations/routes/messages/movements Projection 和 `WorldService.route_days` 保留为可复用的空间能力；Crisis-defined Entity、Asset、Operation、Investigation、Offer、Agreement、Pressure、Resolution 与 Settlement 进入同一 Projection。
- Profile metadata、run creation、content loading、doctor/readiness 与 live reconciliation 使用 `volume_id`、`crisis_id`、Actor ID 和 pinned content/resolver metadata，而不假定山海关。
- 现有 `/api/runs`、perspective、world、archive、history 与 replay 基础改为 Volume/Crisis-aware product API；`advance_one` 保留在 dev/internal 路径。
- vanilla frontend 改为 `api` / `state` / `router`、pages、surfaces、components 的模块边界。当前 1,097 行 `web/app.js` 的异步 input-preservation/reconciliation 逻辑应保留并迁移，不以框架重写取代它。

## REPLACE

- `commitments_json` 的 V3 正式写入与 `schedule_followup` 改为 V4 `revisits_json` / `schedule_revisit`；旧 `commitments_json` 只作为 legacy replay field。Revisit 只支持 time-based `PENDING` / `DUE` / `FULFILLED` / `CANCELLED`。
- 每次 `update_plan` 都产生 `PLAN_UPDATED`，以及 objective 变化立即排 Reflection 的策略，改为 semantic no-op / `PLAN_REAFFIRMED` 和 material-consequence reflection triggers。
- `act(hold|prepare|move)` 的弱世界效果改为 Crisis-defined `operate` lifecycle；movement 成为一种可配置 Operation effect，而不是 V4 的唯一长期行动。
- 仅依赖 message/movement/commitment 的 next-tick scheduler 改为可处理 Investigation、Offer/Agreement、Operation、Pressure、Resolution 和 Settlement 的 event-driven scheduler；产品 `continue` 改为 `advance_to_attention`。
- `SimulationBoundary` 作为产品 Ending 与 7–10 日 hard horizon，改为内部 Safety Horizon + `crisis_phase`：`OPEN`、`RESOLUTION_PENDING`、`AFTERMATH`、`SETTLED`。Safety Horizon 产生 settled `DEFERRED` outcome，不是错误。
- V3 单层 `run_summary`、`world_view`、`product_perspective`、Replay 文案和 Archive 条目改为 Outcome / causal attribution / hidden-world reveal / historical compatibility / same-crisis compare 投影。
- 当前 `CrisisRunEngine` 的山海关专用 Human decision path 和 Model Decision Interpreter prompt 改为 dynamic affordance manifest 与六个 V4 MCP tools。

## DELETE

- `expected_actors = {"li-zicheng", "wu-sangui", "dorgon"}`、required works 被当作所有 Crisis 的 validator、固定三位 Actor 的 controller/profile/replay assumptions（`chronicle/crisis.py`）。山海关的史料要求保留在该 Pack 的内容校验。
- `actor.id == "wu-sangui"`、`human_actors == ["wu-sangui"]`、`wu-sangui`-only Human wake/decision/commitment code，以及 Human only receives the Wu desk（`chronicle/crisis_runtime.py`、`chronicle/decision.py`、`chronicle/app.py`）。
- Global `Corridor` 作为全局产品心智、`actorNames` hardcode、山海关标题、固定四个 Watch lenses、首页“成为吴三桂”、`第 X / 最大 Y 日`、以及在用户界面展示 simulation boundary（`web/app.js`、`web/index.html`、`docs/FRONTEND.md`）。
- “需要裁定大规模冲突即停止”作为世界终止条件，以及把真实历史中 Decision Actor 后续行动写成自动 pressure 的任何路径。
- V3 tool rejection 混合显示/统计、forced followup wording、Plan churn 和将 next runtime moment 等同于 next human moment 的产品假设。

## NEW

- `VolumeDefinition` 与 Crisis registry：一个 `jiashen` Volume，两个独立 content-pinned Crisis；Run pin `volume_id`、`crisis_id`、`crisis_version`、`crisis_hash`、resolution contract id/version 和 `resolution_seed`。
- schema v9 additive migration：`crisis_phase`、`outcome_json`、`settlement_reason`、content/resolver pinning 和 `revisits_json`；migration 将 active V3 Crisis Run 以 `LEGACY_V3` seal，sealed V3/V2 继续走 legacy replay。
- Actor / `CrisisEntity` 分层、qualitative Asset state、generic surface projection；只实现 `SPATIAL` 和 `POLITICAL` renderer，不建 entity-component framework 或 visualization DSL。
- 世界 primitives：delayed Investigation → Observation (source/reliability/provenance)、Offer → Agreement (affordance-changing and breach-visible)、Operation lifecycle、EXOGENOUS/CONDITIONAL Pressure。
- Dynamic affordance manifest、technical rejection recovery、domain-language World refusal、reduced churn telemetry 和 player-/watch-specific attention policy。
- Explicit deterministic, seeded-only-if-ambiguous resolver implementations for `shanhaiguan-v1` and `nanjing-succession-v1`; Resolution writes world events/state/knowledge, then Aftermath and automatic Settlement.
- `outcome_json` with settlement, stakes, positions, assets, agreements, operations, compatibility and material causal roots; deterministic historical compatibility and compressed causal attribution.
- Shanhaiguan V4 pack/resolver plus a separately researched Nanjing succession pack/resolver, with role-charter/source audit and disputed/scenario/modeled labels.
- V4 Chinese product IA: Volume Home, Crisis Cover, Watch, generic Takeover Desk, Settlement, Replay, Compare, Archive, History and Setup; Resolution/Aftermath transitions must remain a living historical document rather than a battle or dashboard screen.
- Focused generic-pack/controller/primitive/resolver/attention/aftermath/legacy tests, two live Hermes acceptance chains, and browser evidence kept distinct from fixture and readiness evidence.
