# Chronicle V5 前端合同

本文描述 V5 正式页面应该让用户看到什么，以及前端和 Product API 的接缝。实现以 `web/index.html`、`web/app.js`、`web/router.js`、`web/state.js`、`web/styles.css` 和 `web/components/` 为准。内部 Profile、Wake、Session、Memory、Runtime 等词可以出现在工程文档和诊断中，但不能成为普通用户界面的心智模型。

## 页面信息架构

```text
Volume Home
  ├─ World
  │    ├─ Follow a Lifetime
  │    └─ Inhabit → Life Desk → Leave
  ├─ Volume Ending
  └─ Archive → Public Replay → selected Lifetime Replay
```

当前正式 hash pages 是 `volume`、`world`、`follow/{lifetime_id}`、`desk`、`archive` 和 `ending`。旧 Watch、Takeover、Settlement、Compare 页面不属于 V5 正式导航；旧代码只能作为 legacy compatibility 使用。

## 页面合同

### Volume Home

首页首先讲清楚“甲申”这一卷册和阅读方式：先看世界，再选择一段人生。开始按钮只创建一个 Volume Worldline；已有活动卷册时，入口改为继续当前卷册。首页不展示 Profile、Agent、Session、数据库 ID 或技术 readiness。

### World

World 页面展示：

- 当前卷册时刻和仍在收紧的 public knots；
- 每个 knot 的标题、阶段、公共 Surface；
- 可接近的人生、位置和公开的可接近理由；
- 当前卷册是否已有一段正在 inhabited 的人生。

它不展示全局 Ledger、其他 Lifetime 的私有 Plan/Belief、未送达消息、模型输出或内部工具调用。Crisis 的局部 settlement 可显示为已经留下 Meaning，但不能把它画成 Volume 已经结束。

### Follow

Follow 是接近一段人生前的公共观察页。它回答“这段人生现在在哪里、哪些事情已经抵达、什么仍然只是一种不确定性”。它不能通过接口参数任意读取别的 Lifetime private context；选择的人生必须由后端在当前 Worldline 中解析。

### Inhabit / Life Desk

进入按钮明确表达“接过这段人生”。进入后 Life Desk 只显示当前 inhabited Lifetime 的：

- `arrivals`：已经收到的抵达；
- `known`：当前可用的相关证据；
- `uncertainty`：仍未确认的判断；
- `current_plan` 和 `active_obligations`；
- `position` 与 `role`。

决定区只有一个有限 intent 入口：写下准备承担的下一步，或者点击等待。提交前先读取 textarea 内容，再进入 `busy` 状态；重绘不能把非空输入变成沉默。提交中所有 mutation button disabled，不能在同一请求尚未结束时 double-submit。

Leave 是显式动作，文案说明“把这段人生交还给世界”。它不会伪装成结束卷册，也不会制造一个“主体离线”的技术面板。

### Volume Ending / Archive

未到 boundary 时，Ending 页只能说明“这一卷仍未走到边界”，不能提供伪造的结束按钮。封存卷册页只列 `SEALED` 的 VOLUME Worldline。

打开一个已封存卷册后，页面分成两层：

1. `Public Replay`：只显示 public-safe 的事件文本和世界轨迹；
2. `Lifetime Replay`：用户主动选择一段人生后，显示该 Lifetime 的回看和 `later_known` 事实。

默认不加载任何 Lifetime private replay。封存页面不显示 raw event payload、Profile 名、token、Session ID 或其他 Lifetime 的私有内容。

## 前后端接缝

| 用户动作 | V5 API | 前端使用的投影 |
| --- | --- | --- |
| 打开首页 | `GET /api/volume`, `GET /api/worldlines/active` | Volume metadata、active world |
| 开始卷册 | `POST /api/worldlines` with `live` | `worldline`, `world`, `lifetimes` |
| 查看世界 | `GET /api/worldlines/{id}/world` | public world |
| 查看人生入口 | `GET /api/worldlines/{id}/follow/{lifetime_id}` | selected follow |
| 进入人生 | `POST /api/worldlines/{id}/inhabit` | world with inhabited lifetime |
| 打开书案 | `GET /api/worldlines/{id}/desk` | private current Life desk |
| 继续/决定 | `POST .../continue`, `POST .../decision` | world, pending moment, desk |
| 离席 | `POST /api/worldlines/{id}/leave` | public world |
| 封存卷册列表 | `GET /api/worldlines` | sealed archive rows |
| 公共回看 | `GET /api/worldlines/{id}/archive` | public replay |
| 选定一段人生回看 | `GET .../archive?lifetime_id=...` | selected Lifetime replay only |
| Volume Ending | `POST /api/worldlines/{id}/seal` | boundary/ending result |

前端只加载产品投影和提交用户 intent，不复制时间调度、权限、路由、消息抵达、seal boundary 或 privacy 规则。后端错误必须翻译成下一步可执行的中文，不显示 traceback、HTTP status code、数据库表名或原始模型配置。

## 视觉与文案

Chronicle 是可交互的历史文书，不是策略游戏 HUD、地图编辑器、聊天窗口或 Agent 控制台。当前视觉 token 是 `--paper`、`--ink`、`--red` 和 `--blue`：纸色承载阅读，墨色建立层级，朱红标记未决/边界，蓝灰表示在途或尚未确认。

文案应始终以用户能感知的事实表达：

- “正在收紧”“已经留下结果”“消息仍在途中”；
- “你接过了这段人生的下一步”；
- “你已经离开书案，世界继续向前”；
- “这一卷已经成为过去”。

不使用 “Agent is thinking”、Profile switch、Memory sync、Session reconnect、Worldline ID、Wake queue、runtime phase 等内部状态来制造戏剧性。

## 隐私和状态

- Follow 不得泄漏未进入该 Lifetime 的私有 context；
- Life Desk 只由当前 inhabited Lifetime 派生；
- Archive public replay 过滤私有事件，只返回安全文本；
- selected Lifetime replay 不接受空泛的“全局回看”，只能明确选择一个 Lifetime；
- busy 状态覆盖开始、继续、进入、离席、决定和 Archive action；
- 空输入明确表示等待，不被当作没有提交；
- 失败保留用户可理解的状态，不清空已捕获文字或展示密钥。

## 响应式验收

每次 V5 页面大改必须检查 1440、1280、768 和 390 宽度：

- 没有 horizontal overflow；
- World 桌面横向信息、手机单列；
- Follow 可读，且不显示 private leak；
- Inhabit 只允许当前 Life；
- Leave 显式且不会误封存；
- textarea 在 rerender 和提交前保留输入；
- busy mutation 不能 double-submit；
- Archive/Ending 在手机仍可读，public/lifetime replay 层次不混淆；
- 不出现 Agent/Profile/Session/Memory 技术术语、crisis dashboard、meter 或 AI thinking animation。

本仓库已有 Phase 10 的隔离浏览器流程证据，覆盖首页、World、Follow、Inhabit、Desk、Continue、Decision、Leave；Phase 11 新增的 Archive/Ending 和四种 viewport 尚未在本轮形成浏览器证据，见 [V5_ACCEPTANCE.md](V5_ACCEPTANCE.md)。
