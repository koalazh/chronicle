# Design System：Observe、Live 与 Debrief

Chronicle 的界面是一个编辑型观测台，不是游戏 HUD。

## 视觉语言

- `paper` 是主背景，像一张长期摊开的档案纸。
- `ink` 用于主要叙事文字和数据，控制高对比阅读。
- `vermillion` 标记当前事件、分叉和需要注意的边界。
- `blue` 只表示消息在途、知识延迟和观察状态。
- Serif 用于事件标题和历史层级；sans-serif 用于控件、标签和运行时字段。

## 页面层级

- Observe 先给出时间窗、当前 Canon 节点、地图、Who Knows 和 Entry invitation。
- Enter 是明确的单一 CTA；用户不会在多个 Branch、Seat 或 model 选项之间做隐含选择。
- Live 只显示 Seat 的 Known World、已抵达信息、携带经历和自然语言 action zone。
- Debrief 只在 SEALED Worldline 中出现，分开 What You Saw、What Was True、
  What You Changed 和 Where It Stopped。
- 史料依据从当前事件上下文打开；Archivist API 在 Human Worldline ACTIVE 时
  显示锁定状态。人物经历详情只读取当前/已封存 Worldline 的 Branch Lifetime，
  不从旧的全局 Lifetime API 拼接。

## 交互约束

- 时间线按钮、来源按钮、Seat 切换和 Branch action 都有明确文字。
- Setup/Settings 不把 secret 重新填入 value；已有 key 只显示掩码。
- 移动端三栏收敛为单列，仍保留事件、来源和边界顺序。
- 页面使用原生按钮、label 和 aria 属性；不依赖鼠标悬停才能理解状态。

UI 截图属于视觉证据，只能说明对应 API/fixture 状态下的布局和交互，不代表 live Hermes 或真实模型结果。
