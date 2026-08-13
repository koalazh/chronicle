# 前端合同

> 读者：前端开发者。本文是实现合同，不是用户指南；其中的接口名和内部状态名只用于代码、隐私和验收。

本文描述当前页面应该让用户看到什么，以及前端和 Product API 的接缝。实现以 `web/index.html`、`web/app.js`、`web/api.js`、`web/router.js`、`web/state.js` 和 `web/styles.css` 为准。Profile、Wake、Session、Memory、Runtime 等词可以出现在工程诊断中，但不能成为普通用户界面的心智模型。

## 页面信息架构

```text
Volume Home
  ├─ World
  │    ├─ Follow a Lifetime
  │    └─ Inhabit → Life Desk → Leave
  ├─ Volume Ending
  └─ Archive → 公共回看 → 人生回看 → 判断回看
```

当前页面是 `volume`、`world`、`follow/{lifetime_id}`、`desk`、`archive` 和 `ending`。旧导航和旧页面不再注册，不是新增页面的设计来源。

## 页面合同

### Volume Home

首页首先讲清楚“甲申”这一卷册和阅读方式：先看世界，再选择一段人生。开始按钮只创建一个 Volume Worldline；已有活动卷册时，入口改为继续当前卷册。首页不展示 Profile、Agent、Session、数据库 ID 或技术 readiness。

### World

World 展示当前卷册时刻、仍在收紧的公共 knot、公开位置、可接近的人生和公开理由，以及是否已有一段正在 inhabited 的人生。

它不展示全局 Ledger、其他 Lifetime 的私有 Plan/Belief、未送达消息、模型输出或内部工具调用。局部 settlement 可以显示为已经留下 Meaning，但不能画成 Volume 已经结束。

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

打开已封存卷册后分成两层：

1. 公共回看：只显示 public-safe 的事件文本和世界轨迹；
2. 人生回看：用户主动选择一段人生后，显示该 Lifetime 的回看和 `later_known` 事实。

选定 Lifetime 后增加 `judgment_history`：它从 append-only decision-horizon 事件投影此前的打算、这次决定、重新判断的公开原因、后来才知道的事实和公开后果。它不显示未落笔的思考，也不显示内部 Ledger、Wake、Profile、Session 或 Memory 字段。

默认不加载任何 Lifetime private replay。封存页面不显示 raw event payload、token、Session ID 或其他 Lifetime 的私有内容。

## 前后端接缝

| 用户动作 | API | 前端使用的投影 |
| --- | --- | --- |
| 打开首页 | `GET /api/worldlines/active` | Volume metadata、active world |
| 开始卷册 | `POST /api/worldlines` with `live` | worldline、world、lifetimes |
| 查看世界 | `GET /api/worldlines/{id}/world` | public world |
| 查看人生入口 | `GET /api/worldlines/{id}/follow/{lifetime_id}` | selected follow |
| 进入人生 | `POST /api/worldlines/{id}/inhabit` | world with inhabited lifetime |
| 打开书案 | `GET /api/worldlines/{id}/desk` | private current Life Desk |
| 继续/决定 | `POST .../continue`, `POST .../decision` | world、pending moment、desk |
| 离席 | `POST /api/worldlines/{id}/leave` | public world |
| 公共回看 | `GET /api/worldlines/{id}/archive` | public replay |
| 选定一段人生回看 | `GET .../archive?lifetime_id=...` | selected replay 与 judgment history |
| Volume Ending | `POST /api/worldlines/{id}/seal` | boundary/ending result |

前端只加载产品投影和提交用户 intent，不复制时间调度、权限、路由、消息抵达、seal boundary 或隐私规则。后端错误必须翻译成下一步可执行的中文，不显示 traceback、HTTP status code、数据库表名或原始模型配置。

## 视觉与文案

Chronicle 是可交互的历史文书，不是策略游戏 HUD、地图编辑器、聊天窗口或控制台。纸色承载阅读，墨色建立层级，朱红标记未决/边界，蓝灰表示在途或尚未确认。

文案应以用户能感知的事实表达：

- “正在收紧”“已经留下结果”“消息仍在途中”；
- “你接过了这段人生的下一步”；
- “你已经离开书案，世界继续向前”；
- “这一卷已经成为过去”。

不使用 “Agent is thinking”、Profile switch、Memory sync、Session reconnect、Worldline ID、Wake queue、runtime phase 等内部状态制造戏剧性。

## 隐私和状态

- Follow 不得泄漏未进入该 Lifetime 的 private context；
- Life Desk 只由当前 inhabited Lifetime 派生；
- Archive public replay 过滤私有事件，只返回安全文本；
- selected replay 必须明确选择一个 Lifetime，不能请求空泛的“全局回看”；
- busy 状态覆盖开始、继续、进入、离席、决定和 Archive action；
- 空输入明确表示等待，不被当作没有提交；
- 失败保留用户可理解的状态，不清空已捕获文字或展示密钥。

## 响应式验收

每次页面大改都检查 1440、1280、768 和 390 宽度：

- 没有 horizontal overflow；
- World 桌面横向信息、手机单列；
- Follow 可读，且不显示 private leak；
- Inhabit 只允许当前 Life；
- Leave 显式且不会误封存；
- textarea 在 rerender 和提交前保留输入；
- busy mutation 不能 double-submit；
- Archive/Ending 在手机仍可读，公共回看、人生回看、判断回看层次不混淆；
- 不出现 Agent/Profile/Session/Memory 技术术语、crisis dashboard、meter 或 AI thinking animation。

最近一次浏览器检查覆盖首页、World、Follow、Inhabit、Desk、Continue、Decision、Leave、Archive 和判断回看；四种 viewport 均无横向溢出，内部术语扫描和 error/warn logs 为空。真实 Hermes 业务链另用隔离 Volume 验证，不把 live 运行偷换成浏览器 fixture。结果见 [当前验收](ACCEPTANCE.md)。
