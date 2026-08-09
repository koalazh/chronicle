# Historical Blindness：运行时不应知道的事

Chronicle 的关键约束不是“让模型扮演一个历史人物”，而是让模型无法从运行时输入直接读出展示层才知道的答案。

## V2 的 SeatContextView

V2 不允许 Seat 从页面状态、分支快照或全局 API 拼出自己的输入。Human Seat
和 Agent Seat 都必须由同一个 SeatContextView 构造 prompt/interaction context：
当前 tick、已知世界、已抵达消息、所携带经历、authority、已知不确定性、可见
实体和 assertion ID。

因此 Live 页面展示的是“我此刻能知道什么”，不是“这条 Worldline 的真相”。
Debrief 只在封存后读取 Branch projection；它不能反向污染此前保存的 Seat
context。输入边界由 worldline runtime 的 context builder 和 V2 回归测试共同
维护。

## 三层数据分离

| 层 | 允许内容 | 不允许内容 |
| --- | --- | --- |
| 展示层 | 中文姓名、历史日期、事件标题、来源、结局 | — |
| Host 层 | Canon、投递时间、权限、世界状态、Life Record | 把未投递信息伪装成已知 |
| Seat 输入 | `Seat A/B/C`、opaque alias、已收到的 observation、当前 belief | 人名、地点名、后来的结局、世界全局快照 |

`ScenarioPack` 在加载阶段检查 runtime alias、payload 和 source alias 中的禁用词。Host 的 `_runtime_input()` 只选择已送达 observation，并将 actor authority 作为允许意图列表传入。

## 能证明什么

- `test_runtime_input_is_opaque` 可以证明固定 fixture 没有把展示名称送入 Seat 输入。
- `who-knows` API 可以证明同一条断言按 Seat 和 delivery tick 分开计算。
- Hermes profile 配置可以证明 Actor Distribution 没有浏览器、终端或文件系统工具。

## 不能自动证明什么

Opaque payload 不能证明模型没有从外部世界猜测答案。因此 V1 的 Actor Distribution 只给 API server 暴露 `memory` tool，并禁用 web/browser/terminal/filesystem 等工具；现场 LLM 运行仍需要单独的协议和输出审计。任何“模型真的不知道”都只能在给定输入、工具和版本的范围内表述。

## 泄漏修复原则

发现泄漏时，先缩小 runtime contract：删除不必要的字段、改用 alias、把结局移回 Host，再补回归测试。不要通过提示词中加入“请假装不知道”来替代数据边界。
