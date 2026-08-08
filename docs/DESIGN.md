# Design System：纸、墨与朱

Chronicle 的界面是一个编辑型观测台，不是游戏 HUD。

## 视觉语言

- `paper` 是主背景，像一张长期摊开的档案纸。
- `ink` 用于主要叙事文字和数据，控制高对比阅读。
- `vermillion` 标记当前事件、分叉和需要注意的边界。
- `blue` 只表示消息在途、知识延迟和观察状态。
- Serif 用于事件标题和历史层级；sans-serif 用于控件、标签和运行时字段。

## 页面层级

- Cover 先给出时间窗与一句方法承诺。
- Chronicle 采用左时间线、中地图/事件、右 Who Knows 三栏。
- Source Inspector 从右侧抽屉进入，不离开当前事件上下文。
- Lifetimes 先选主体，再看 Life Record 和 Memory lineage。
- Branch 固定为 Canon / Branch 双栏，并始终显示边界。
- About 把 Truth、Knowledge、Belief 的差异写成可读方法，而不是装饰。

## 交互约束

- 时间线按钮、来源按钮、Seat 切换和 Branch action 都有明确文字。
- Setup/Settings 不把 secret 重新填入 value；已有 key 只显示掩码。
- 移动端三栏收敛为单列，仍保留事件、来源和边界顺序。
- 页面使用原生按钮、label 和 aria 属性；不依赖鼠标悬停才能理解状态。

UI 截图属于视觉证据，只能说明对应 API/fixture 状态下的布局和交互，不代表 live Hermes 或真实模型结果。
