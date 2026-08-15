# 当前验收记录

> 本文件只记录当前源码和本轮实际运行过的证据。确定性测试、浏览器检查、真实 Hermes 运行和真人接受度彼此不能替代。

## 当前结论

Chronicle 当前 Killer Demo 的活动产品边界已经收敛为：一个山海关世界、一个 `before-shanhaiguan` 危机、三个独立主体：`wu-sangui`、`li-zicheng`、`dorgon`。

当前实现可以支持以下本地产品链：

`Live World → 走近一段人生 → 留下判断 → 交还给世界 → 世界继续 → 重新接管 → 回看因果`

运行时继续由 Host/Volume Worldline 负责世界真相、权限、可见性、原子提交、恢复和事件因果；主体的 Experience 以结构化记录写入对应 Lifetime，并作为后续主体上下文的一部分。`EXPERIENCE_RECORDED` 是主体私有事件，不进入公共世界投影。

南方/Nanjing 资源仍可作为仓库中的历史资产存在，但已从活动 `jiashen` volume、解析器注册和产品页面移出；对应历史测试被明确标记为 skip，不再作为当前 V1 契约。

当前任务为 `COMPLETE`。Attempt 17 已独立返回 `PASS`，确认 v13 正常角色路径、v15 served terminal fault-path、当前前端修复和证据 accounting 均无 material gap。真人接受度按最新任务澄清记录为非阻塞项；v15 受控 fault provider 仍不外推为正常 Provider 稳定性。

## 证据矩阵

| 层级 | 当前结果 | 能证明什么 | 不能证明什么 |
| --- | --- | --- | --- |
| 确定性测试 | PASS（当前全量 `pytest -q`；[`static-current-v12.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/static-current-v12.md)） | 活动 pack、三主体、走廊投影、Experience 生成/持久化/因果引用、私有性、restart context、handoff、原子 moment、Archive、判断入口直接性和可选辅助超时边界、live wake retry/terminal-failure contract、v12 前端文案/轨迹归属/null actor/why-now 文本、嵌套 payload 文本和 sealed-continue 归档竞态等 | Provider 在所有环境下的稳定性；模型输出一致性 |
| 静态检查 | PASS（[`static-current-v12.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/static-current-v12.md)） | Python 编译、Ruff、前端 JavaScript 语法、volume 配置可加载、diff check | 浏览器实际布局、服务进程和 live Gateway |
| Browser（in-app） | v13 正常角色路径与 v15 terminal fault-path 已由执行者实跑；Attempt 17 独立 `PASS` | v13 receipt [`browser-live-current-v13-handback.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-current-v13-handback.md) 覆盖开始卷册→吴三桂→真实 handback→tick 5→Archive/回看；v15 receipt [`browser-live-terminal-fault-v15.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-terminal-fault-v15.md) 在真实 served Browser 中触发 `missing_logical_intent`，保留用户判断、阻止世界推进并给出唯一重试动作；v12 同一 served artifact 已在 390/639/1280 宽度完成无横向溢出检查；Attempt 17 独立复核无 material findings | 不证明 Provider 在所有未来请求中稳定或无长尾延迟；v15 是受控本地 Provider fault-path，不是正常模型质量结果；Browser shell 的 Statsig timeout 不属于 Chronicle 页面错误 |
| 真实 Hermes | v13 executor-run 完成；Attempt 17 独立 `PASS` 复核证据边界 | v13 fresh live run 的六个任务 Wake 全部 `COMPLETED`，最终 `SEALED/READY`、tick 5、协议违规为 0；新鲜服务的产品请求均为 200；SQLite 有 `LIFETIME_LEFT`；历史 causal-chain/restart/ablation receipts 仍分别保留，不能互相替代 | 单次 fresh run 不等于任意 Provider 的模型输出稳定；v15 controlled fault-path 不等于正常 Provider 质量结果 |
| 真实 Chronicle 进程 restart | PASS（状态恢复 receipt；2026-08-14） | `worldline-c56e225d01824692` 在 tick 5 由 PID `91319` 停止、PID `95961` 重启；同一 `runtime_epoch`、tick 5、Course/Experience 事件计数、Wu Profile Memory hash 和 Gateway owner 保持，重启后 `/health` 与 World GET 为 200 | 该 receipt 证明持久化状态恢复，不宣称重启后新 Provider Wake 成功；root14 的重启后首次 provider Wake 返回 503 并 fail-closed |
| Warm/cold Profile Memory ablation | PASS（真实 Hermes；2026-08-14） | receipt 中 `wu-sangui` 223 bytes Memory 与 `wu-sangui-cold` 0 bytes；相同只读 prompt、独立 fresh sessions；warm `memory_available=true` 并复述 implication，cold `false` 且不编造，两边 hash 不变 | 这是单对受控对照，不是模型 benchmark 或长期统计结论 |
| Independent Completion Challenge | Attempt 4：NEEDS_WORK；Attempt 5：NEEDS_WORK；Attempt 6：NEEDS_WORK；Attempt 7：历史 PASS（已被默认端口反例推翻）；Attempt 8：NEEDS_WORK；Attempt 9：历史 PASS（仅此前前端版本）；Attempt 10：NEEDS_WORK；Attempt 11：NEEDS_WORK；Attempt 12：NEEDS_WORK；Attempt 13：NEEDS_WORK；Attempt 14：NEEDS_WORK；Attempt 15：NEEDS_WORK；Attempt 16：NEEDS_WORK；Attempt 17：PASS | Attempt 17 独立确认 v13/v15 Browser 证据、当前源码/测试和 accounting 无 material findings；v15 仍明确为受控 fault-path，不外推正常 Provider 稳定性 | 不把真人接受度或未来 Provider 稳定性外推成更强结论 |
| 真人接受度 | `NON-BLOCKING / UNCOLLECTED` | 按最新任务澄清不作为本轮验收门槛 | 不由自动化结果冒充真人反馈 |

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

本轮实际执行的关键活动评估：

```bash
uv run pytest -q tests/test_killer_demo_convergence.py
```

### 本轮真实运行 receipts

- 当前 v13 handback Browser receipt：[`browser-live-current-v13-handback.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-current-v13-handback.md)，Worldline `worldline-05a84bb313b94c4b` 在新鲜隔离服务 `127.0.0.1:8711` 上从首页走到吴三桂判断、真实点击交还、世界推进、tick 5、Archive 和吴三桂判断回看；附有 `/leave` 逐请求记录、页面日志、服务访问日志和 SQLite `LIFETIME_LEFT`/sealed/Wake 状态回读。v12 receipt 仍保留 390/639/1280 同一 served artifact 的响应式证据。

- 当前 v15 terminal fault-path Browser receipt：[`browser-live-terminal-fault-v15.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-terminal-fault-v15.md)，Worldline `worldline-b8eb82fa688f47b1` 在 `dev=False` 的 task-owned Chronicle/Gateway 与本地 deterministic fault provider 上真实走过首页→吴三桂接管→判断→终端失败→重试；页面保留判断、明确停止世界并给出“重新检查当前卷册”，SQLite 记录 Dorgon/Li 的 `FAILED/missing_logical_intent`，协议违规为 0。该 receipt 是受控 fault-path 的执行者证据，不是正常 Provider 稳定性或独立 verdict。

- 默认 live Browser receipt：[`receipts/browser-live-attempt-8.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-attempt-8.md)，Worldline `worldline-86625b563b794ba1` 在默认 `uv run chronicle start` 下从新建卷册、吴三桂判断、交还世界走到 tick 5/Archive；三次产品推进与归档请求均为 200，最终 `SEALED/READY`，七个 wake 均为 `COMPLETED`。

- 修复后完整 live Browser receipt：[`receipts/browser-live-attempt-9.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/browser-live-attempt-9.md)，Worldline `worldline-58091a3cb55d4f7e` 覆盖首页、整卷开始、吴三桂接管/判断/交还、真实 agent wakes、tick 5、封存、吴三桂因果回看；所有产品请求为 200，七个 wake `COMPLETED`，`SEALED/READY`，协议违规为 0。

- 前端 v5/v7/v9/v12 receipts 仍作为历史对照保留；当前 v13 handback receipt 才是本轮 Browser 自验收输入，且不是 Completion Challenge verdict。

- 当前前端 v12 静态命令 receipt：[`static-current-v12.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/static-current-v12.md)，记录了角色归属、回看层级、null actor、空区块、嵌套 payload 文本、草稿保存、sealed-continue 竞态修复后的全量 pytest、Ruff、compileall、全部 web JavaScript `node --check`、volume validate 和 diff check。

- Browser fixture Worldline：`worldline-29d3b57405ad41b3`，当前最新源码 served by 隔离服务 `127.0.0.1:8711`；真实 Browser 从首页开始操作吴三桂，服务端收到 `POST /inhabit 200`、`POST /reconsider 200`、`POST /decision 200`、`POST /leave 200`、两次 `POST /continue 200`，随后打开 Archive 和 `archive?lifetime_id=wu-sangui`；页面从第 0 个时刻走到第 5 个时刻再到卷册边界。修复后的直接判断没有自动请求草稿，页面保持清晰的“这次判断”单一入口；默认视口 `innerWidth=1280`、`scrollWidth=1265`，页面 `error/warn=[]`，公共走廊显示为中文“现实 · 第 N 个时刻”。
- Browser fixture Worldline：`worldline-55e3a8ec3cd24775` 是同一修复后的早一轮 receipt，保留作为补充证据。
- 上一条 Browser fixture Worldline：`worldline-b62ca36d54844f6b`；它只覆盖到第 5 个时刻，作为早期 served-artifact receipt 保留，不替代本轮完整角色到 Archive/Replay 的证据。
- 首次隔离 live run：真实 Gateway/Profile 建立成功；后续 Wake 在 `wu-sangui` 处暴露 `live V6 Memory hash drifted`。根因是 DB 的无尾换行与 Profile mirror 的尾换行不一致；该失败先被回归测试固定，随后通过修复 `append_profile_memory` 重跑。
- 修复后的 live run：`worldline-9daf2abe266c4543` 产生真实 Hermes session/Wake，包含 `MESSAGE_DELIVERED`、`DECISION_HORIZON_REVISED`、`EXPERIENCE_RECORDED`，在 tick 5 封存，`protocol_violations=[]`。
- 人工接管/重启 live run：`worldline-17b467a02e3c401c` 在 tick 0 先 inhabit 吴三桂、提交“先守住山海关……”并 handback；停止隔离 Gateway 后以新 TestClient 恢复，同一 Worldline 继续至 tick 5，真实 Agent Wakes 有 fresh session。这个是隔离应用/Gateway 重启证据，不等于杀掉并重新启动独立 Chronicle 进程。
- 当前源码的 live Profile materialization：`worldline-d135b21864e647ae` 创建时实际目录为 `dorgon`、`li-zicheng`、`wu-sangui`；随后两个真实 `/continue` 均返回 200，tick 0 → 5，真实 Wakes 有 fresh session，`protocol_violations=[]`。
- 完整真实 Hermes causal-chain：[`receipts/live-chain-attempt-6.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/live-chain-attempt-6.md)；`worldline-c56e225d01824692` 在隔离 root `/private/tmp/chronicle-killer-demo-live13.TDWFtA` 上由真实 OAuth Gateway 与 canonical Profiles 运行；事件包含 `DECISION_HORIZON_ESTABLISHED`、`DECISION_DEPENDENCY_DUE`、`DECISION_HORIZON_REVISED`、`EXPERIENCE_RECORDED`，随后 tick 5 的 Wu `DELIBERATION_COMMITTED` 为 `HOLD` 且 `experience_refs=["experience-wu-sangui-3-50ed0f94ee7d"]`；五个非 checkpoint wakes 为 `COMPLETED`，三个 tick-0 checkpoint wakes 保持 `QUEUED`，`protocol_violations=[]`，rejected retries 原样记录。
- 真实 Chronicle 进程 kill/restart：[`receipts/restart-attempt-6.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/restart-attempt-6.md)；完成链 `worldline-c56e225d01824692` 在 tick 5 从 PID `91319` 停止、由 PID `95961` 恢复，Worldline 仍为 tick 5/READY，依赖、Experience、Course 事件计数和 Wu Profile Memory hash 不变；这不等同于重启后新 Wake 成功。
- 真实 warm/cold Profile ablation：[`receipts/ablation-attempt-6.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/ablation-attempt-6.md)；隔离 Hermes root `/private/tmp/chronicle-killer-demo-ablation.E5NrP8` 中 warm `wu-sangui` Memory 为 223 bytes、cold `wu-sangui-cold` 为 0 bytes；两个独立 fresh session 用相同只读 prompt，warm 返回 `memory_available=true` 并复述 implication，cold 返回 `false` 且不编造；前后 Memory hash 均不变。
- 本轮静态命令 receipt：[`receipts/static-attempt-8.md`](/Users/koala/.task-loop/20260814-143711-chronicle-killer-demo/receipts/static-attempt-8.md)，记录了当前 `pytest`、Ruff、compileall、全部 web JavaScript `node --check`、volume validate 和 diff check 的退出结果。

该文件覆盖：

- 活动 volume 只有一个山海关危机和三个主体；
- 公共世界只暴露北京 → 山海关 → 辽西走廊、三个人和不泄露内容的 transit；
- 判断被主动改写后生成结构化 Experience；
- Experience 写入 Lifetime，重启 Host 后仍可见；
- 后续 `DELIBERATION_COMMITTED` 可以引用 Experience，并通过 `EXPERIENCE_RECORDED` 建立因果父级；
- 三个主体的 Profile 名称彼此独立，主体 Experience 不进入公共世界。

## 产品和数据边界

- 公共页面显示现实走廊、人物位置/状态、正在路上的消息、近期公共后果；不显示主体私有知识、思考草稿、Profile/Session/Wake/Runtime 等内部词汇。
- 主体判断入口只要求用户写下“这次判断”或选择暂时不定；不自动拉取可选草稿，不让用户先决定是否采纳一份辅助文本。可选行动建议在后端有 2 秒上限，超时不阻塞用户自己的判断。
- Subject Desk 显示“我现在知道”“我此前打算”“我正在等”“哪些过去仍影响我”；Experience 只通过主体 Desk 和主体上下文返回。
- Experience 的最小来源是：承诺被现实迫使重新考虑，或主体自己的行动留下可见结果。记录保留最近六条，带来源事件和后续 implication。
- Host 写入数据库是权威持久化；live 模式下新增 Experience 还会追加到对应 Hermes Profile 的 `memories/MEMORY.md`。本轮真实 run 暴露并修复了 mirror hash 的换行边界；这不等于 Memory provider 在任意版本上都稳定。
- 旧南方/Nanjing crisis 目录没有被批量删除；正确性来自它们不再被活动 `volume.yaml` 注册，且 resolution registry 只注册山海关 resolver。

## 明确不声称

- 不声称 V8、第二个场景、Coordinator、聊天 UI、通用 Durable Agent 框架或完整认知架构已经实现。
- 不把静态检查、TestClient/fixture 测试写成浏览器 PASS；当前 Browser receipt 只覆盖上述隔离 `uv run chronicle start` 的真实 live 路径，独立挑战仍单列。
- 本轮 Browser receipt 只覆盖真实操作路径、可见文案/状态和页面日志；v13 已补上真实 handback，v15 已补上 served terminal fault-path receipt。当前不把 API/TestClient 正反例升级为 Browser 已验证，也不把 v15 受控 fault-path 写成正常 Provider 稳定性。真人接受度不作为本轮阻塞门槛。
- 不把部分 live Hermes receipt 写成完整 Killer Demo PASS。
- 不声称 Experience 等于模型自主反思；当前它是由已提交的现实后果和承诺修订确定性生成的最小结构化记忆。
- 不声称历史测试 skip 等于历史能力仍受当前契约保证；它们属于冻结的旧范围。
- 真人满意度仍未采集，但按最新任务澄清不阻塞本轮完成判断。
