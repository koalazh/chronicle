# V4 前端可维护性 Spike

> 状态：已审计，采用渐进式 vanilla ES module 拆分；不是 React/Vite 重写的授权。

## 观察到的边界

当前 `web/app.js` 为 1,147 行单模块，同时承担：

- 全局状态、HTTP timeout/error translation、hash 路由与页面数据加载；
- 首页、Watch、Takeover Desk、Replay、Archive、History、Setup、Dev 的 HTML 生成；
- 两种 Crisis Surface 的 renderer；
- 输入保留、单次决定锁、异步结果核对与 runtime recovery；
- 全局 delegated event handlers。

这不是单纯的文件长度问题。页面每次 `render()` 都替换 `#app`；因此 `draftDecision`、`activity`、`operationSeq`、`viewSeq` 和 decision reconciliation 共同保护了“忙碌时不丢失已捕获输入、未知请求不重复提交”的现有产品语义。V4 不能把它们作为样板代码重写或丢弃。

同时，后端已经提供 `GET /api/volume`、`GET /api/crises`、`GET /api/crises/{id}`、generic actor list 和两种 `surface.kind`，而首次加载仍只读取 `/api/crisis`，首页、Archive、run header 与默认 Takeover 仍带有单山海关 / 固定角色 / 最大日数的 V3 文案。这是 Volume IA 的实际接缝，而不是新建前端领域模型的理由。

## 选择

保留 vanilla DOM + 原生 ES modules：`index.html` 已经使用 `type="module"`，FastAPI 将整个 `web/` 目录作为 `/assets` 静态资源提供，不需要引入 build chain、Node dependencies 或 React state migration。当前没有证据表明框架会降低 input/race 风险；相反，先迁移上述异步控制语义会扩大风险面。

拆分采用可回滚的职责边界：

```text
web/
  api.js          请求、timeout、产品错误翻译
  state.js        唯一的页面状态
  router.js       hash 解析与跳转
  components/     无世界规则的可复用文书片段
  surfaces/       SPATIAL / POLITICAL 纯投影 renderer
  pages/          Volume、Crisis Cover、Desk，后续逐页迁移
  app.js          暂时保留生命周期、加载、mutation lock 与事件委托
```

模块不能读取或改写 Scheduler、权限或 Resolver；它们只接收已投影的 API 数据。`app.js` 仍是生命周期 owner；Desk 已在保持相同 interaction contract 的前提下迁移，Settlement、Replay/Compare 留待后续逐页迁移。

## Phase 18 迁移准则

1. 启动时并行读取 config、Volume 和 active Run；只有进入某场 Crisis Cover 或 active Run 时才读取该 Crisis detail。
2. 首页改为 Volume Home，只显示独立的 Crisis 目录；不根据 Active Run 或历史 ID 猜测可玩角色。
3. Crisis Cover 从 `playable_actor_ids` 投影的 `actors[].playable` 生成 Watch 与每位可接管主体入口。
4. 创建 Run 明确传入当前 Cover 的 `crisis_id` 和选中的 `human_actor_id`；不使用默认角色或 `/api/crisis` 作为 UI state。
5. 保留 live-only 创建、runtime lock、captured textarea、unknown-result reconciliation 与 perspective boundary。

## 验证边界

- 静态：`node --check` 覆盖每个模块；前端复制/路径 contract 测试覆盖 Volume、generic actor 和 `/api/volume` / `/api/crises/{id}`。
- API fixture：两个 Crisis detail 都能驱动 Cover，任意 `playable` actor 能被带入 `POST /api/runs` payload。
- 浏览器：后续以隔离 fixture server 检查 1440、768、390 的 Volume → Cover 路径；它只证明本地 fixture/API 的页面状态，不能替代 live Hermes 验收。
- 不在本阶段引入 Compare、Settlement 页面、Operation/Offer composer 或真正 live Run 验收。

## Phase 19 验证结果

Desk 没有建立新的前端状态模型：后端在当前 Actor 的 `product_perspective` 中提供一个小型 `desk` 投影，里面只有该主体已合法收到的 arrivals、真实需要判断的 unresolved、自己的 ongoing 世界对象和自己参与的 active agreements。`web/pages/desk.js` 与三个无状态文书组件只呈现该投影；`app.js` 保留请求互斥、输入捕获、未知结果核对和事件委托。

递归静态测试拒绝旧的 `outgoing_messages` Desk 拼接，并覆盖新模块边界。fixture/API 测试证明私有调查回报、来信式 Offer、协议与 ongoing 行动不会跨 Perspective 泄漏。隔离临时 fixture 浏览器在 Takeover 桌面中观察到来信、未决条件、进行中行动、协议、Surface、提交后回信和自动扩展输入框；390 宽度无横向溢出。该浏览器过程没有创建真实 Hermes Profile，仍仅是本地 fixture/API/UI 证据。
