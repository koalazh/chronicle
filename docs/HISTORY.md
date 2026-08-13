# 历史与视野

> 读者：内容研究人员和建模人员。本文讨论史料和信息边界，不是普通用户的产品说明。

本文记录史料如何进入危局，以及一个主体在当时到底能知道什么。产品旅程见 [产品说明](../PRODUCT.md)，系统实现见 [架构](ARCHITECTURE.md)，当前验收见 [当前验收](ACCEPTANCE.md)。

## 来源先于模型

Chronicle 不把一段“历史简介”直接塞给模型。史料先整理成 Source、Assertion、争议说明和场景假设；运行时只把当前主体合法收到的内容交给它。模型输出、测试结果和 UI 文案都不能创造新的历史事实。

当前 Volume Pack 位于 `scenarios/jiashen/`，由 `volume.yaml`、`lifetimes.yaml`、`world.yaml`、共享地点/路线和 `crises/` 下的 Crisis Pack 组成。每个 Crisis Pack 由 `crisis.yaml` 和 `sources.yaml` 定义检查点、主体、走廊、路线、在途消息、停止边界、历史锚点和断言 ID；当前运行时只读取这套 V6 Volume 结构。

## 断言的两个标签

`provenance` 说明来源：`historical` 是来源直接支撑的事实，`scenario_assumption` 是把检查点变成可运行时间窗的显式假设，`modeled` 是路线或资源粒度等抽象，`volume_derived` 是当前 Volume 内由确定性运行时推导出的结果。

`evidence_status` 说明证据强度：`corroborated`、`single_attested`、`disputed` 或 `approximate`。争议不能被 UI 文案抹平；到达日、路线时长、兵力规模和人物动机排序都要保留对应状态。

## 当前检查点

“山海关之前”放在大规模交战前：李自成已在北京建立新秩序，吴三桂守山海关，多尔衮率军从辽西向西行进；吴的首封求助信仍在路上，三方尚未形成产品替他们决定的不可逆选择。

主要资料包括《清实录·世祖章皇帝实录》卷四、《明季北略》卷二十、《清史稿》卷四百七十四、《明史》卷三百九》和 Frederic Wakeman 的 *The Great Enterprise*。材料的编纂时代、立场和叙事目的不同，不能合并成一条无争议的脚本。不要把陈沅叙事或任何单一私人轶事写成吴三桂的行为规则。

History 通过 `/api/history` 提供来源、断言、证据状态、争议和历史锚点；它们不会以完整来源页面自动进入主体 prompt。主体收到的是对自己合法的 claim 或消息内容，不是 assertion ID、后世总结或整本史料。

## 检查点之后

后来主体行动统一标为 `REFERENCE_ONLY`：可以在 History 页面帮助用户比较“后来发生过什么”，但当前封存后的 Run Replay 只回放已经持久化的分支，不注入这些锚点。它们也不进入 scheduler、主体 prompt 或 Human perspective 作为行动命令。与主体当前选择无关的外生事实才可能标为 `EXOGENOUS`；需要检查前提的未来锚点可使用 `CONDITIONAL_ANCHOR`，但第一场危局不把主体未来行动写成强制脚本。

## Perspective 边界

每次主体 wake 和 Human Inhabit 使用同一种主体 Perspective，包含当前模拟日、自己的位置、已送达 Knowledge、私有 Belief、Plan、Commitment、Resource、Authority 和当前可用的 World tools。

它不包含世界全局投影、尚未送达的消息、其他主体的私有计划/Belief/Memory/Wake、检查点之后的真实历史行动或战后结局。

同一个 Logical Moment 内，Host 先应用到期确定性效果，再冻结所有主体视野，然后运行主体。主体本时刻发出的消息、移动或观察不能被同 tick 的另一个主体立即读到，必须经过未来的 delivery 或 observation moment。

## 代码中的四道门

1. **Projection 门**：人物 Perspective 从已送达事件和自身 Life State 生成，不从世界全局投影复制；
2. **API 门**：活动 Inhabit 访问公共 World 或其他主体 Perspective 返回 403；
3. **MCP 门**：World MCP 不接受 caller 自报的 actor/run/wake 身份，身份来自私有 binding token；
4. **资料门**：后来的主体行动是 `REFERENCE_ONLY`，不进入 scheduler、主体 prompt 或 Human perspective。

这些证据可以证明本次输入投影、API、工具和资料路径没有发现运行时泄漏，但不能证明模型从预训练知识中“真的不知道历史”。发现泄漏时，应缩小数据/API/工具合同并补回归测试。

## 维护规则

- 新事实先增加 Source 和 Assertion，再增加引用；
- actor、location、route、message、source 和 assertion ID 必须唯一且可解析；
- 初始 Knowledge 写可读 claim，不把内部 ID 当作人物知识；
- 消息 dispatch、delivery 和路线时长注明是来源事实还是模型值；
- 有争议的日期、兵力、意图和因果标成 disputed/approximate；
- `volume validate` 失败，都不能宣称当前 Volume 资料就绪；
- 历史材料与当前产品文档分开维护，旧记录进入 [归档](archive/README.md)。
