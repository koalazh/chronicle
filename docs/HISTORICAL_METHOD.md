# 历史方法：Source Pack 先于 Agent

Chronicle 不把一段自然语言历史简介直接塞给模型。场景先编译为可审计的 Source Pack，再由事件、观察和 Host 规则消费。

## Source Pack 的层次

1. `sources.yaml` 保存来源、定位信息、URL 和每条断言的证据状态。
2. `events/**/*.yaml` 保存 Canon 事件、断言引用、世界效果和面向 Seat 的观察。
3. `actors.yaml`、`locations.yaml`、`routes.yaml` 保存运行时所需的结构化边界。
4. `fork.yaml` 只允许从一个已有 Canon 事件切出 Branch。

每条断言必须关联至少一个来源。`historical` 表示来源直接支撑的事实；`modeled` 表示为了让 Host 可运行而建模的传播、地点状态或抽象字段；`branch_derived` 只属于分叉后的状态。

## 甲申 V1 的取舍

V1 选择清晰的时间窗和少量关键节点，不试图覆盖整部明末史。正月初一、山西战事、朝廷南迁讨论、东线防务与三月十九日的结局分别由 Source Pack 中的事件和断言承载。未能由来源直接支持的连续行动不被自动补写。

使用的公开来源包括：

- [《明史》卷二十四](https://zh.wikisource.org/wiki/明史/卷24)
- [《明史纪事本末》卷七十九](https://zh.wikisource.org/wiki/明史紀事本末/卷79)
- [《明史纪事本末》卷八十](https://zh.wikisource.org/wiki/明史紀事本末/卷80)
- [《国榷》卷一百](https://zh.wikisource.org/wiki/國榷/卷一百)

这些链接是研究入口，不是 Agent 的运行时输入。运行时只收到对应事件中的 opaque observation payload。

## 维护规则

- 新事实先增加断言和来源，再增加事件引用。
- 新事件必须明确 tick、事件 marker、观察到达时间和证据状态。
- 如果信息来源或日期存在争议，标为 `disputed` 或 `modeled`，不能用 UI 语气掩盖。
- 不以测试、配置或模型输出创造历史事实。
- Source Pack 校验失败时，应用不能进入“看似完成”的展示状态。
