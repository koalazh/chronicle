# Chronicle V6 最终修复与验收方案

这份方案用于把当前 `bc0ae4e` 的 V6 候选实现修复到 `Chronicle-V6.md` 所要求的可验证完成状态。它不把已有 `COMPLETE` 标签当作证据，也不建立 V7、平行 Runtime、通用评测平台或新的 Agent 编排层。

## 1. 当前基线与判定原则

当前实现已经保留了正确的主干：唯一 Current Course 位于 `Lifetime.plan[0]`，判断历史由 append-only Ledger 重建；Knowledge、Attention、Hermes cognition、Host commit、World effect 和 Archive 仍属于各自边界；六个 Lifetime 仍由独立 Hermes Profile/Session 承载。

最终完成必须同时满足以下原则：

1. 当前源码和真实行为优先于历史文档标签。
2. 每个材料性缺口先有失败复现，再有最小修复和回归。
3. fixture、确定性测试、浏览器、Strong-Agent、real Hermes 和真人问卷分别记录，不相互替代。
4. Agent 只提出选择；Host 继续拥有 schema、权限、时间、因果、原子性、幂等和世界效果。
5. Provider 失败、拒绝或不可用必须 fail closed；不能通过人工注入消息、手工结算或伪造摘要升级成 PASS。
6. 每个可独立解释、验证和回滚的语义修复形成一个本地 commit；不 push、不部署、不 squash。

## 2. 完成门与实施顺序

### R0 — 冻结合同、基线与反例

目标：确保修的是当前真实问题，而不是旧报告中的想象问题。

- 固化新的 Task Loop `TASK.md`、`HANDOFF.md` 和本方案。
- 保存 UI 非空判断丢失、reject 后同 Wake 可再次 proposal、Attention 来源不可达、Ablation/P9/live chain 证据不足的最小复现。
- 复跑当前完整测试、静态检查和内容 validators，记录起始 HEAD 与工作树状态。
- Readiness Challenge 只检查合同、权限、完成条件和方案覆盖，不替代实现验收。

验收：每个缺口都能指向当前源码或实际运行；没有把真人问卷、push 或全局 Hermes 资源纳入执行权限。

### R1 — Product Continuous Agency：先修用户入口

目标：用户在 Life Desk 写下的判断能够真实成为 Course。

- 在进入 busy/rerender 前捕获表单值，把不可变值传入 mutation；不再从已经被替换的 DOM 读取。
- 保持空输入明确表示等待，非空输入明确表示 REVISE；同一请求期间 mutation button 禁用。
- 清除产品页面中的 `Lifetime` 等内部执行术语，保留面向用户的“人生/人物/判断”语言。
- 增加 API/DOM 回归，并在 1440、1280、768、390 四个宽度实际操作非空提交、等待、double-submit、Leave 与 re-entry。

验收：浏览器提交前值非空；提交后 Ledger 出现该文字对应的 Course/Decision Horizon，绝不能出现 `intent.type=wait`；无 overflow、console warning/error 或内部术语。

建议 commit：`fix: preserve v6 human judgment through rerender`

### R2 — Deliberation：Host 强制 propose once

目标：消除同一 frozen moment 的 strategy-oracle 探测。

- 在现有 `crisis_wake_operations` 中记录一次 Agent Deliberation attempt；不新增表或第二套状态机。
- 第一次合法 proposal 仍形成一个 staged operation；第一次非法 proposal 形成一个可审计、无 World effect 的 rejected attempt。
- 同 Wake 的精确重送只返回同一结果；不同 proposal/idempotency key 一律拒绝，不能再次进入 World validation。
- rejected attempt 可让该 Wake 以无副作用的 rejection 收束，不能让 Pending Logical Moment 永久卡死，也不能改变 Course、Knowledge、World、Agreement 或 Operation。
- Hermes driver 看到 Host rejection 后立即停止；只有“从未形成 Host proposal”的协议缺失才允许有限格式修复，且不能把自然语言自动降级为 wait。

验收：非法 A 后合法 B 在同一 Wake 必须失败；非法 A 的 Ledger/operation 可审计且无 partial mutation；精确 retry 幂等；restart 后仍不能重试 B；accepted HOLD/REVISE 与原有原子性测试继续通过。

建议 commit：`fix: consume one v6 deliberation attempt per wake`

### R3 — Attention 与结构边界：让三类现实真正可达

目标：只保留计划允许的 Attention 来源，并让 Volume 能自然到达 Resolution/Settlement。

- A：继续使用 typed open-dependency match；消息、Offer/Agreement、deadline 的真实抵达必须带正确 event identity。
- B：只从确定性、可审计的自身承担后果产生，例如 failed/interrupted operation、agreement breach、authority/critical asset loss 或执行期 input drift；正常按计划完成仍只进入 Knowledge 并保持 BACKGROUND。
- C：只把 Scenario Pack 已声明、可见、source-supported 的结构性 pressure/checkpoint 作为 `structural_shock`；修正当前字段名不一致，不建立 Importance Scorer。
- Crisis checkpoint 为尚无 Current Course 的参与者打开一次初始判断边界，使六个主体都有机会形成自己的 Course；Human 接管已有 Wake 时保持同一 frozen reality。
- 把现有 `resolution/*` deterministic contracts 接入 Volume lifecycle：只在 contract gate READY 时应用结果和结算，不用 LLM Judge，也不允许 acceptance 通过任意 `settle_crisis(outcome=...)` 制造结果。
- Resolution effects、Agreement effects、可见 Knowledge、Attention 和下一个 Crisis envelope 继续通过同一个 Volume tick/Ledger/Host 事务边界。

验收：dependency、expected completion、unexpected own consequence、curated shock、initial checkpoint 和 resolver-ready settlement 均有 source-bound tests；正常 completion 不 Wake；pressure 不越过 visibility；Shanhai/Nanjing 从合法世界状态自动结算，非法/未就绪状态不能结算。

建议 commits：

- `fix: connect v6 attention to source-bound reality`
- `feat: resolve v6 crises at deterministic world gates`

### R4 — P6/P7/P8：证明持续性、稀疏 Attention 与有限 Agency

目标：把概念性 PASS 改成可计算、可反证的业务证据。

- P6 分别运行 Noise、confirming reality→HOLD、disconfirming reality→REVISE、fresh Session/restart/Human↔Hermes 四组；每组都核对同一个 Course identity/version 和 Horizon events。
- P7 从同一 Worldline Ledger 明确定义并统计：World events、按 visibility/seat 实际进入 Knowledge 的 actor-known events、REOPEN Attention boundaries、Deliberations；不能用 `TIME_ADVANCED` 或 `MESSAGE_DELIVERED` 数量冒充集合。
- P8 继续验证主体不能替他人承诺、Offer/Agreement 路由时间、Agreement/Institution prerequisites、private Course、causal parents、retry/restart；增加一次真实 mutation boundary 的负向拒绝。
- 生成最小脱敏 JSON receipt，只记录 IDs 的不可逆摘要、event type/count/tick/status/causal links，不保存 Secret、prompt、私有 Course 正文或模型原文。

验收：P6 四组逐项 PASS；P7 的实际 trace 满足 `World > actor-known > REOPEN ≈ Deliberations`，并能定位每个集合成员；P8 所有越权、提前、重复和跨主体路径 fail closed。

建议 commit：`test: prove v6 continuous bounded agency`

### R5 — Phase 9：四组 Harness Ablation 全部执行

目标：只基于实验决定保留或删除 scaffold。

四组实验使用同一模型、同一角色状态、独立 fresh Session 和明确的输入/判定：

1. **one-action**：比较 `0..1` 与允许多 action 的受控候选；验证多 action 是否破坏原子、权限或因果。生产合同在没有反证前保持 `0..1`。
2. **prompt complexity**：完整提示与最小必要提示各跑等量的 frozen perspectives；统计首次合法 proposal、缺工具调用、Host rejection 和 retry，不以一次成功删除边界提示。
3. **authored maneuvers**：在开发副本移除 `prepare_force`，重新跑 source validation 与 trajectory，确认是否失去通往 READY 的合法路径；不改正式 Pack 后再“证明”。
4. **fixed pressure**：同一初始状态分别保留/禁用 source-defined pressure，比较 Perfect Wait、机会关闭和能否达到 Resolution；该实验只决定 pressure 是否 load-bearing，不改写历史来源。

验收：四组都有输入、模型/Profile identity、样本边界、结果和明确结论；任何 Provider 未运行项不得标 COMPLETE；只有证据支持时才删除生产 scaffold。

建议 commit：`test: complete v6 harness ablations`

### R6 — P9：Strong-Agent Game，而不是 fixture 形状检查

目标：验证强模型依据 Life State 和现实行动，而不是机械复述历史或无限等待。

- **Perfect Wait**：给同一强模型明确“非必要则等待”的倾向，分别跑 Shanhai/Nanjing；时间、信息延迟、他人行动、制度 pressure 与机会关闭必须使无限等待不 dominant，并到达有限结果。
- **Canonicality Perturbation**：同模型、同 Lifetime、fresh Session，只有一个 actor-visible、load-bearing 且 Scenario 合法事实不同；策略必须随事实合理变化，不能在不兼容现实中机械选择真实历史路径。
- **Role-State Swap**：同一底层模型交换 Knowledge、authority、Course、assets，而非只改名字；输出必须跟交换后的合法 affordances/约束变化，且 Host 拒绝越权动作。
- **Strong Reasoner**：在同一不完全信息状态中确认至少存在两个合法、互不支配的 judgment；若出现唯一显然最优路径，回到 Knot geometry/pressure/commitment 设计审计，而不是改 prompt 要求“积极”。
- **Continuous trajectories**：Shanhai 与 Nanjing 都由多个独立主体经过真实 Hermes Deliberation、消息/Offer/Operation/pressure 和 deterministic resolver 连续运行，不能以静态 affordance 或手工 state mutation替代。

验收：五项计划要求和 Strong Reasoner 均记录明确 PASS/FAIL；paired runs 可核对同 model、role/state 差异和 fresh Session；模型失败不会被测试代码硬编码为成功。

建议 commit：`test: add real v6 strong-agent game proofs`

### R7 — Phase 12：同一个真实产品对象的完整 DoD

目标：在隔离环境中完成一条没有人工因果伪造的真实 Volume。

执行边界：新临时 SQLite、新 Hermes Home、任务独占 loopback Gateway/port、六个真实 Profiles；运行前后核对 owner、PID、Home、Profile identity、`/health`、`/v1/models`/当前 capabilities 和监听器，只清理该任务资源。

同一 Worldline 必须观察到：

1. 浏览器创建 live Volume、Human 进入吴三桂，并用非空中文判断建立 Course。
2. Human Leave；无关现实进入吴的 Knowledge 但为 BACKGROUND。
3. 吴的消息通过合法 Deliberation action 发出并按 route 抵达多尔衮；多尔衮因此 fresh Deliberation。
4. 李自成在自己的 checkpoint/Course/pressure 或可见后果中独立重新判断，而不是由测试直接 `dispatch_message`。
5. load-bearing reality 到达吴，产生 REOPEN 和 fresh Hermes HOLD/REVISE；Human re-entry 可以看见判断持续与变化原因。
6. Shanhai/Nanjing 使用相同 cognition-time/Attention/Host 模型，经合法 actions 和 deterministic resolution gates 自动结算；不得调用 acceptance-only `settle_crisis`。
7. 后续 envelope、Archive judgment history、boundary、Seal、bindings `REVOKED` 和精确 Profile/Gateway/临时目录 cleanup 完成。

验收：以上事件可由同一 Worldline 的 causal parents、Profile/Session records 和产品 API/浏览器状态关联；receipt 脱敏且机器可读；结束后任务端口无监听、临时 Profiles/Home 无残留。

建议 commit：`docs: record verified v6 end-to-end acceptance`

### R8 — 文档、全量回归与独立 Completion Challenge

目标：让交付说明与真实证据完全一致。

- 更新 `V6_IMPLEMENTATION.md`、`V6_MIGRATION.md`、`V6_ACCEPTANCE.md`、README、PRODUCT、ARCHITECTURE、FRONTEND、OPERATIONS 中受影响的状态和边界。
- 删除旧的过度声明，不删除真实历史记录；旧 Task Loop PASS 保持历史，只在新 Task Loop 中记录新的 Challenge。
- 运行完整 pytest、focused V6/bridge/live tests、Ruff、compileall、Source/Scenario/Volume validators、全部 tracked JS syntax、`git diff --check`、Secret scan、工作树和端口检查。
- 新鲜独立 Reviewer 执行 Behavioral Grounding + Adversarial Diff Inspection；返回 `NEEDS_WORK` 时按完整材料修复并重跑，最多三次 verdict。

验收：新的 Completion Challenge 返回精确 `PASS`，Task Loop `HANDOFF.md` 才可进入 `COMPLETE`；真人问卷继续诚实标记 `UNCOLLECTED`，不阻塞工程证据完成，也不被写成真人 PASS。

## 3. 证据分层

| 层 | 必须证明 | 不能替代 |
| --- | --- | --- |
| Source/Static | Pack、schema、权限、可达路径和无平行架构 | 运行行为 |
| Deterministic | Host、Ledger、Attention、resolution、retry/restart | Provider 行为 |
| Browser | 用户路径、可读性、输入持久化、响应式 | real Hermes cognition |
| Strong-Agent | paired decision、等待/扰动/状态交换、连续 trajectory | 真人产品感受 |
| Real Hermes | Profile/Session/tool/transport/业务 mutation/cleanup | 多次稳定性 benchmark |
| Human | 主观可玩性和历史主体感 | 任何自动化证据 |

## 4. 回滚与停止条件

- 每个 repair gate 只提交已通过定向与完整回归的独立变化；失败时回到最近一个语义 commit 分析，不清理用户工作或使用 destructive reset。
- 若 Provider、Gateway 或凭据不可用，保留确定性和浏览器成果，把 Strong-Agent/real Hermes 标为真实 blocker；不得用 fixture 填充。
- 若第三次 Completion Challenge 仍为 `NEEDS_WORK`，Task Loop 按协议进入 `BLOCKED`，不请求第四次，也不把部分完成写成 COMPLETE。
- 任何发现的新问题只有在直接影响 Chronicle-V6.md 的 intent、正确性、证据、安全、权限、可用性或交付时才进入本任务；邻接重构与可选优化不做。
