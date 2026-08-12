# Chronicle V5 产品说明

## 一句话

Chronicle 让你进入同一卷历史中的几段人生：你可以先看世界，再接过其中一段已经活到这里的人生；离席后，世界与其他人生继续向前，最后整卷被保存为可回看的过去。

产品不要求用户扮演历史作者，也不把人物当成可配置的 NPC。用户要感受到的是：自己没有看见的那些人，也拥有自己的下一步。

## 正式旅程

### Volume

Volume 是产品的最外层卷册。默认 `jiashen` Volume「甲申」拥有共享 World、6 条持久 Lifetime、3 个彼此交织但各自有边界的 Crisis knot。Crisis 只说明局势在哪里变得密集，不拥有整卷的时间、人物身份或最终清理权。

### World

World 展示公共事实：哪些局势正在收紧、哪些人处在什么公开位置、哪些消息已经成为公共历史。它回答“现在世界哪里值得停留”，不提供全知视角下的私有计划或未送达消息。

### Follow

Follow 只看一条 Lifetime 的合法公共/个人入口信息：这段人生身处何处、为什么当前可能值得接近、有哪些公开可见的未决处。它不是窥视其他人物私有状态的入口。

### Inhabit

Inhabit 将当前 Human controller 绑定到选中的 Lifetime。它不重置人物、不新建人物、不自动推进世界，也不因为切换 controller 强制制造 Reflection。一个时间点只能有一个 Human controller；离席后同一 Lifetime 仍保留原身份和状态。

### Life Desk

Life Desk 是当前 inhabited Lifetime 的书案。它只展示当前人物的合法上下文：

- 已经抵达的消息与证据；
- 当前知道但仍不确定的事情；
- 正在承担的计划、义务和下一步；
- 当前人物的角色与位置；
- 用户可以提交的有限意图，或明确选择等待。

用户写下的文字会变成受限的 intent，由 Host 统一校验、暂存和原子提交；它不是聊天窗口，也不是直接改数据库的命令。

### Leave

Leave 把这段人生交还给世界。它只改变 controller/presence metadata，不清空人物，不抹掉记忆，不改变历史时间，也不凭空触发一次思考。原有触发条件仍归属于同一 Lifetime。

### Archive / Volume Ending

Crisis settlement 只是局部局势留下了 Meaning，Volume 仍保持 `ACTIVE`。只有整卷到达结构性边界——所有 Crisis Instance 已有结果或被抑制、没有待处理 Logical Moment、没有到期唤醒、没有在途消息或待应用历史字段——才允许 Volume Ending 和 Archive。

Archive 默认展示安全的公共回看；用户明确选择某一 Lifetime 后，才增加这一段人生的 selected replay，并区分“当时知道”“后来才知道”和“卷册结束时仍未知”。V6 进一步从 append-only decision-horizon 事件投影“此前的判断、这次决定、为什么重新判断、后来知道的事和之后发生的事”，不把其他 Lifetime 的私有内容拼成全知叙事，也不展示未落笔的思考。

## 产品心智模型

| 概念 | 产品含义 | 用户能看到的边界 |
| --- | --- | --- |
| World truth | Host 已经提交的时间、位置、路线、状态和公开事件 | 公共世界投影 |
| Knowledge | 某 Lifetime 已经收到并能使用的事实 | 当前 Lifetime 的合法上下文 |
| Belief | 该人物对不确定事实的判断 | 仅当前人物私有；不等于史实 |
| Plan / obligation | 该人物准备怎么做、何时重新判断 | 当前 Desk 的有限投影 |
| Message | 一个有发送、在途、抵达时刻的世界对象 | 抵达前不得进入收件人的已知上下文 |

Truth、Visibility、Knowledge、Belief、Plan 和 Memory 不能互相替代。发生事件不等于所有人知道；一封信发出不等于它已经抵达；人物没有明确说出的心理不能由产品补写。

## 世界与主体的分工

Host 负责唯一世界时钟、历史来源、位置、路线、消息抵达、权限、资源、状态效果、幂等和原子 Ledger 提交。主体负责解释自己收到的上下文、等待、通信、更新计划、提出有限意图和选择是否记住长期经验。

同一个 Logical Moment 中，Human 与 Agent 都从冻结的世界和各自 Perspective 出发；任何一方在 commit 前都不能看到另一方尚未提交的世界改变。模型输出的顺序不应改变世界语义。

## 页面边界

页面应该像一份可读的历史文书，而不是技术控制台：

- 不显示 Agent/Profile/Session/Memory/Runtime 等内部术语；
- 不显示关系分、信任表、人格滑杆、AI thinking 动画或世界全知仪表盘；
- 不把 Crisis 变成独立的项目导航，也不把局部 settlement 伪装成整卷 ending；
- 不允许用户从公共 World 反推其他 Lifetime 的私有计划、Belief、未送达消息或工具调用；
- 不把后来的历史锚点自动播放成唯一命运，不用中央模型替所有 Lifetime 决定。

## V6 演进与未完成边界

V5 代码已经提供 Volume/API/Archive 的确定性合同和前端 product shell；V6 在此基础上增加 Course、Attention、deliberation、连续 Human judgment、真实路线上的 Offer/Agreement transport，以及 Archive judgment history。Phase 11 的 fixture/API 与浏览器证据已通过；隔离 live harness 的单 Wake 证据仍不能替代 Phase 12 完整 Hermes 业务链。

当前还没有证明真实 Hermes 在 Human↔Hermes handoff、跨 Subject 因果、Memory 学习和 off-screen continuation 中产生正确行为，也没有真人试玩回答或正式 Completion Challenge。完整状态不以页面可点击或一次 Wake 文本推断，见 [V6 验收记录](docs/V6_ACCEPTANCE.md)。

## 相关文档

- [架构](docs/ARCHITECTURE.md)：Volume、Lifetime、Global Clock、Logical Moment、Ledger 和执行边界。
- [前端合同](docs/FRONTEND.md)：页面状态、文案、隐私、API 接缝和响应式要求。
- [运维与验收](docs/OPERATIONS.md)：安全启动、隔离数据库、Hermes preflight、迁移和清理。
- [V5 验收记录](docs/V5_ACCEPTANCE.md)：逐条 acceptance evidence、P0–P5 和 blocker。
- [V6 实施与验收](docs/V6_IMPLEMENTATION.md)、[V6 验收记录](docs/V6_ACCEPTANCE.md)：Phase 0–11 证据、Phase 12 blocker 和最终挑战边界。
- [历史与视野](docs/HISTORY.md)：史料、争议、建模假设和信息盲区。
