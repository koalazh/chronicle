# Chronicle 前端合同

本文合并页面产品约定与视觉约定。它回答“用户应该看到什么”，不把 Profile、Wake、数据库或技术日志当成用户心智；实现以 `web/` 下的 ES modules、`web/index.html`、`web/styles.css` 和当前 API 为准。

> V4 状态：Phase 21 已实现 Volume Home、Crisis Cover、任意 playable Actor 入口、`SPATIAL` / `POLITICAL` Surface、私有 Perspective 驱动的 Takeover Desk、从自动 Settlement 进入的 Outcome 页面，以及同一危局的两卷对照。Replay 的 V4 分层呈现与 live Hermes 验收仍由后续 Phase 完成；本文件不会把当前 fixture/API 或静态页面证据写成 live Hermes 验收。

## 首次打开

用户第一次打开首页应立即明白四件事：这是“甲申”这一 Volume；其中有两场彼此独立的危局；每一场由少数主体在有限信息中行动；可以先旁观，或成为该场中任一可玩的关键主体。

首页先讲 Volume、两个 Crisis 的日期/一句危局描述和入口，不先讲 Profile、Wake、Session 或数据库。进入 Crisis Cover 后才展开该场的检查点、未决问题、主体、Surface 和入口。模型服务未配置时仍可阅读 Cover，开始入口禁用并告诉用户去“设置”；内部异常不能原样倒进页面。

## 页面合同

### Volume 首页与 Crisis Cover

Volume 首页展示“甲申”、简短的卷册说明和两场 Crisis 的目录。它不把一场 alternate outcome 接到另一场的开始；每一场都从自己经校验的 checkpoint 启动。

Crisis Cover 回答四件事：现在发生什么、真正未决的问题、谁在其中、可以旁观还是成为谁。入口从 `actors[].playable` 动态生成：一个 Watch 和每位 playable Actor 一个 Takeover。创建请求明确携带 `crisis_id` 与该 Actor ID，不由首页默认人选或历史 ID 推断。

### Watch

提供世界和当前 Crisis Actor 集合生成的视野。世界视野展示地点、在途/抵达的信件和公开事实；主体视野只展示该主体已经收到的 Knowledge、Belief、Plan、Revisit、位置和资源。切换视野不能改变 Run，也不能泄漏其他主体私态。

“继续”推进到下一个有意义的 simulated moment，而不是把日期机械加一天。消息抵达、移动完成和主体 Wake 都要被翻译成领域语言；没有 trigger 不产生 Wake。live 未 READY 时，前端禁用继续，后端也必须拒绝。

### Takeover Desk

书案是一页连续的历史文书，而不是六张并列的状态卡。它依次呈现：**新到**（来信、调查回报、可见世界观察、行动结果）、**尚未解决**（需要回应的条件、已到期的 Revisit、已进入不可逆节点的选择）、**正在进行**（调查、行动与仍在途的书信）、在确实约束当前主体时出现的**已经作出的约定**，以及**已知世界 / Crisis Surface**。

每一项都来自当前主体的私有 Perspective `desk` 投影：前端不读取 Ledger、不由世界全貌推断隐藏事件，也不将其它主体的私态拼成所谓“全局情况”。来信中的 Offer 先作为一封信呈现，并在正文下自然说明“对方希望你明确”；协议只在它仍真实约束当前主体时出现。

决定区只问“你准备怎么处置”。用户可以输入一段自然语言，也可以不输入而点击“继续”；输入框初始为四行并随内容自然展开。提交前先捕获 textarea，再进入 busy 状态，不能因为重绘把文字清空成沉默。书案不展示“我的 Plan”任务管理器、内部 Event ID 或其它主体的私有活动。

当 World 已进入 `RESOLUTION_PENDING`，书案不展示战斗面板或 Resolver factors；它只把右侧改成“局势已进入不可逆节点”，允许当前 Human 写下最后处置，或继续让世界形成局部答案。进入 `AFTERMATH` 后仍回到同一张书案，让新的结果、通信和有限后续行动安静地抵达。

### Settlement

只有由世界自动形成的 `SETTLED` 危局才进入 `#/settlement/{run_id}`。这页首先显示“某危局之后”，用 3–5 句确定性 Outcome 文本说明世界最终形成了什么、仍留下哪些真实条件，并明确 Chronicle 不会替后续整段历史编造命运；不展示分数、因子面板、Resolver ID 或 raw state。然后只给“回看这一局”和“回到甲申”。

用户主动封存的未结算 Run 仍进入原有回看/卷册路径，不能伪装成一个世界已回答的 Settlement。若 live Run 的本地资源仍在收束，Settlement 先保留可回看 Outcome，再单独提供“再次收束”。

### 两卷对照

Compare 只从封存卷册进入：用户先选择一卷已 `SETTLED` 的 V4 Crisis，再从**同一 Crisis 且相同内容版本**选择第二卷。旧版留存、手动封存但未形成 Outcome 的卷册，以及不同 Crisis／不同内容 pin 的卷册都不能被拼成比较；页面与后端都拒绝它们，而不是把不同 checkpoint 或不同规则误当作同一场重玩。

页面是两份并置的结局文书，不是世界线树或数据仪表盘。先展示两份 Outcome 的确定性摘要、进入结果的关键现实、仍有约束力或已经兑现的约定，以及与真实后续的必要前提关系；随后才展示“第一次出现分歧”。

这处 First Material Divergence 只能来自结构化 Ledger 世界事实：实体状态、Offer／Agreement 生命周期、Operation／Movement、Pressure，或已经取得的 Observation。信件正文措辞、Plan、Reflection、Revisit 和 Event ID 都不参与判定。这样两封语气不同却没有改变可执行现实的信，不会被误报为历史分叉。每一卷下方只压缩展示能从 Ledger 直接追到 `CRISIS_SETTLED` 的后续路径；没有这种直接路径时，页面说明证据边界并保留各自 Outcome，绝不补写因果。

### 回看、卷册、史实和设置

Watch 回看默认是“封存后全景”，标题为“几条人生如何相遇”；Takeover 回看默认是“当时可见”，第一屏回答“在你看不见的地方发生了什么”。回看要能读出“计划 → 发信 → 收信 → 收信人改计划”，不能只显示内部事件名或工具调用次数。

封存卷册只列已封存的危局，旧 V2 数据标成“旧版留存”；史实背景解释来源、证据状态、争议和建模边界；设置收集模型服务地址、API Key、模型和接口类型，“保存并核对”先测试 Provider，再保存 Secret。

封存请求即使遇到本地资源收束失败，也先打开可回看的卷册；卷册和回看页会保留“再次收束”入口，不把失败伪装成已经清理完成。

## 视觉方向

Chronicle 是可交互的 Living Historical Document，不是策略游戏 HUD、地图编辑器或 Agent 控制台。纸色承载阅读，墨色建立层级，朱红标记当前危局/未决选择/封存边界，蓝灰表示在途、未抵达或尚未确认的信息。

当前 CSS 的语义 token 是 `--paper`、`--ink`、`--red`、`--blue`；标题使用 serif，界面信息使用 sans。视觉首先回答“谁知道什么”和“下一件有意义的事是什么”，不依靠头像、能力值、网络拓扑或“正在思考”动画制造主体感。

## Crisis Surface

Surface 是 Crisis 自己提供的投影，前端只实现两种 renderer：

- `SPATIAL`：有序地点、主体位置、在途消息与移动；山海关仍使用走廊表达相对位置、距离和消息路线，不冒充精确地图。
- `POLITICAL`：候选、制度程序、可见支持和公开文书的“尚未定稿的政治事实”；南都不画关系图、不显示隐藏状态。

Surface 在宽屏横向、手机按内容单列；信件显示“在途中”或“已抵达”和预计抵达日；未知主体不默认放入地点；Takeover 只显示该 Human Actor 合法知道的状态。不能帮助理解地点、政治事实、移动、延迟或已知/未知的装饰不应占用空间。

## 状态和响应式

未配置时入口禁用；未就绪时继续、决定和沉默不可提交；忙碌时先捕获输入再重绘；视角切换只重新加载合法投影；封存时说明停止原因并打开回看；空状态和错误使用领域语言，不显示 traceback、token、Session ID 或 HTTP 状态码。

live Run 的 `BOOTSTRAPPING`、`RECONCILING`、`FAILED`、`SEALING` 和 `CLEANUP_PENDING` 用现有纸页、朱印与细蓝线显示为一张轻量的“待续页”。它只说明已知状态：正在建立、正在恢复、尚未准备好或已经封存；不显示假进度、倒计时或“主体正在思考”。建立、恢复、推进、决定和封存共享一个 mutation lock，书案在这段时间展示已提交文字的只读纸条。`FAILED` 只提供“重新准备”或封存，不允许继续输入。

至少检查 1440、1280、768 和 390 宽度：没有横向溢出，Corridor 方向正确，Desk 文书、Settlement 行动与两卷 Compare 文书在手机为单列，按钮、label、textarea 可键盘操作并有清晰 disabled 状态。浏览器截图只证明当时本地 API/fixture 的页面状态。

## 前后端接缝

前端只加载产品投影、呈现状态和提交用户意图，不复制 scheduler、权限校验或世界裁定。

| 用途 | 当前入口 |
| --- | --- |
| Volume 与危局目录 | `GET /api/volume`、`GET /api/crises` |
| 一场 Crisis Cover | `GET /api/crises/{crisis_id}` |
| 设置与就绪状态 | `GET /api/config`、`POST /api/setup/test`、`POST /api/setup/configure` |
| 创建/恢复一局 | `POST /api/runs`、`GET /api/runs/active`、`POST /api/runs/{id}/runtime/retry` |
| 合法视野 | `GET /api/runs/{id}/world`、`GET /api/runs/{id}/perspective/{actor}` |
| 推进/决定/封存 | `POST /api/runs/{id}/continue`、`POST /api/runs/{id}/decision`、`POST /api/runs/{id}/seal` |
| Outcome/回看/对照/卷册/史实 | `GET /api/runs/{id}/outcome`、`GET /api/runs/{id}/replay`、`GET /api/compare?left=...&right=...`、`GET /api/archive`、`GET /api/crises/{id}/history` |
| 原始诊断 | `/api/dev/*`，仅开发模式开放 |

后端错误要翻译成下一步可执行的产品语言；主产品不展示 Profile、Wake、Session、Memory hash、Worldline、ActionType、HTTP 状态码、原始模型配置或数据库表名。
