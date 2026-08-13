# 南都定策：历史策展与 Pack 契约

> 读者：内容研究人员和建模人员。本文是史料与实现契约，不是用户指南，也不要求用户理解其中的内部名称。

> 当前状态：Pack、Volume registry 与 `nanjing-succession-v1` deterministic resolver 已接入当前 Volume；确定性 API/fixture、浏览器回看和隔离真实业务链分别有证据。本文是内容与史料契约，不把单层证据扩大解释为全部产品体验。

## 危局边界

本场不是“弘光朝一年”的缩写，也不是把后来的败亡倒灌为开局性格或结果。它只处理甲申四月下旬至五月初的一个局部问题：北京确报抵达南京后，南京如何把一个尚未固定的继统问题转化为可执行、或无法执行的政治现实。

选定 checkpoint 为一个明确的研究性切片：

- 北都陷落与崇祯帝死亡的确报已进入南京政治视野；
- 福王朱由崧已在淮上／仪真方向的政治视野内，潞王朱常淓也是现实候选；
- 南京尚未完成五月初三的监国礼；
- 四月二十七日会议、福王抵仪真和入南京的精确先后，在保留材料中并不完全一致，不能被转换成一个“唯一正确”的日序规则。

因此 Pack 的 `native_date_window` 应写为“崇祯十七年四月下旬”，而不伪造精确公历日。福王的起始状态用 `APPROACHING_NANJING` 表达，而不把有争议的具体停泊地写成世界真相。这个切片是 `scenario_assumption`，不是对某一部材料的断言。

## 史料方法与可用结论

| 材料 | 可用处 | 不能直接写入世界的部分 |
| --- | --- | --- |
| 《明季南略》卷一 | 记录福王在淮上、仪真、入南京、五月初三监国与五月十五即位的一组时序节点。 | 作者与文本形成均晚于事件；四月末各节点的精确先后需与其他材料交叉，不把其叙述当作单一时钟。 |
| 《明季遗闻》卷二 | 记南京得北都消息、候选范围、官员会议和五月初的程序安排。 | 清初叙事有事后组织与人物评价，尤其不把其褒贬改写进 Role Charter。 |
| 《弘光实录钞》卷一 | 保存“史可法等议立”、马士英借既有军政网络迎福王、四镇与定策关系等叙述。 | 黄宗羲的评语和“七不可”等政治文字是立场性材料；只作为当时争议曾被提出的证据，不作为人格事实。 |
| 故宫博物院《南明弘光政权及其覆灭》 | 对四月十二日确报、福／潞两候选、五月初三监国和五月十五即位给出可读的现代概览。 | 不能代替原始／近时材料，也不把其“一场斗争”的叙事压缩为单一人物决定。 |
| 顾诚《南明史》及关于马士英的现代研究 | 用来复核后出人物定型与材料谱系，提醒 Pack 不把“忠／奸”“昏／贤”写成 Agent 性格指令。 | 现代解释不是 Host 的结果规则，也不作为行动成功率或数值加成。 |

以下事实可作为 Pack 的来源断言：

1. 南京在四月中旬才取得北京陷落的确切消息；这使继统成为现实的制度问题。
2. 福王与潞王都进入候选视野；围绕伦序、程序和人选的意见并不一致。
3. 史可法和马士英都拥有持续、不能由确定性 Host 替代的判断空间：前者在南京兵部与官员程序中，后者在凤阳督抚及可见军政网络中。
4. 福王由淮上／仪真方向进入南京、五月初三监国、五月十五即位是后续历史节点；具体四月末到达日及各会议顺序须标为 `approximate` 或 `disputed`。
5. 江北将领与南京军政网络的可见支持，是当时政治可行性的一部分；本场不把它们压缩为精确兵数，更不把每一位将领的后续选择偷偷做成 Host 行为。

## Actor 与 Entity 判定

### Decision Actors：三位，且三位均 playable

| 主体 | 判定 | 原因 | Role Charter 边界 |
| --- | --- | --- | --- |
| 史可法 `shi-kefa` | Actor | 在南京拥有持续的军政与程序判断：可组织会议、公开或保留立场、寻求条件、推动或阻止程序。若拿掉他，Host 必须替他决定如何处理继统程序。 | 责任是维持留都军政连续性、在人选与程序间作判断、面对北方风险；张力是伦序、程序、可执行性与短期秩序之间，不写成“某党代表”或道德模板。 |
| 马士英 `ma-shiying` | Actor | 作为凤阳总督，能够以已有军政网络选择如何把支持、保护与迎立安排带进南京政治过程。若拿掉他，Host 必须替他决定关键的可见动员与条件。 | 责任是维持凤阳—江北方向的可用秩序、判断候选与军政支持怎样进入程序；张力是伦序、可执行支持、程序协商与自身责任之间，不写成“奸臣”或历史结局的预告。 |
| 韩赞周 `han-zanzhou` | Actor | 南京守备／司礼监一侧的权力不是背景装饰：近时叙述将他列入关键会议，现代研究进一步指出其能召集议事、推进程序。若把 `nanjing-court` 直接当 Host 自动完成，等于抹掉这个可改变继统能否进入正式程序的判断。 | 责任是维持留都中枢程序与秩序、决定何时将候选引入可执行礼制；张力是程序连续性、公开正当性与来自官员／军政网络的压力之间，不写成单一派系工具。 |

### 非 Actor 的重要实体

| 主体 | 类型 | 为什么不升为 Hermes Profile |
| --- | --- | --- |
| 福王朱由崧 `fu-prince` | `CLAIMANT` | 在这个窄窗口里，他的到达、被迎立和被制度承认是核心世界事实；但可查材料主要把持续的程序／网络判断放在南京官员与马士英一侧。第一版不让 Host 发明他未被来源证明的持续政策选择。 |
| 潞王朱常淓 `lu-prince` | `CLAIMANT` | 是可行的替代人选与政治现实，而非必然落选的背景板；本场只需要建模其可被引入、被公开支持或失去可行性，不需要替其补写独立政治日程。 |
| 江北四镇、卢九德、刘孔昭、吕大器、高弘图、姜曰广等 | `ASSET`、`INSTITUTION` 或来源所述支持者 | 他们确实重要，但本场第一版只需把其已经可见的网络、支持或程序入口表达为世界事实。若未来玩法证明不把其中一人升为 Actor 就只能由 Host 偷偷决定关键政治行动，必须重新策展，而不是自动扩充 Agent 数量。 |

这一判定不是人物轻重排序。它只回答：在本 Crisis Window 内，谁必须拥有长程、可见且不可替代的自由判断。三位 Actor 让南京的程序入口、军政支持和官员判断都由主体承担；Engine 的 2-Actor 通用约束仍由既有 generic-pack tests 覆盖。

## 最小世界对象

| id | 类型 | 起始状态 | 用途与来源边界 |
| --- | --- | --- | --- |
| `nanjing` | `PLACE` | `OPEN` | 作为留都政治中心；不画地图。 |
| `fengyang-command` | `PLACE` | `OPEN` | 马士英的督抚行动位置，仅保留其军政责任的现实出处。 |
| `north-court-news` | `DOCUMENT` | `CONFIRMED` | 北京确报已到；不是仍要反复调查的谜题。 |
| `nanjing-court` | `INSTITUTION` | `CONVENED` | 官员能够开会、提出与处理程序，但尚未形成可执行继统结果；韩赞周拥有其可启动程序的 Actor authority。 |
| `nanjing-recognition` | `ASSET` | `PENDING` | 世界里的制度承认，而不是“支持度分数”。其可能状态包括 `DELIBERATING`、`FU_RECOGNIZED`、`LU_RECOGNIZED`、`CONTESTED`。 |
| `fu-prince` | `CLAIMANT` | `APPROACHING_NANJING` | 对淮上／仪真精确位置有争议，故以可审计的抽象状态表示。 |
| `lu-prince` | `CLAIMANT` | `AVAILABLE` | 是现实可引入的替代人选，不预写其必然失败。 |
| `jiangbei-military-backing` | `ASSET` | `UNCOMMITTED` | 表示能否被带入继统程序的可见支持，不代表四镇一致意志，也不用兵数。可变为 `FU_BACKED`、`CONTESTED` 或 `WITHHELD`。 |
| `regency-proclamation` | `DOCUMENT` | `NOT_ISSUED` | 让程序完成后产生可见、可传播的政治事实，而不是只改一段文字。 |

这些状态均是质性世界真相。任何“福王七不可”“马士英奸”“某人必然忠诚”之类评价性文本，不能成为 Asset state、precondition、factor 或 Prompt 倾向。

## 最小玩法契约

### Information

`investigate` 只回答尚未被可靠掌握的有限问题，例如：

- `claimant-position-report`：核实福王／潞王是否已可被迎入南京；结果只给出来源、可靠度与局部观察，不替用户裁决谁应当被立。
- `military-backing-report`：核实某一支持讯号是否已经成为可见、可执行的保护安排；不能窥探所有将领的私下意图。

北都确报不应再被设计成反复调查目标；它是已到达、已改变世界的问题。调查结果仍应私有、延迟到达并保存来源与可靠度。

### Bargain / Agreement

只新增一个 Engine 需要理解的 Term type：

```text
type = endorsement
subject = fu-prince | lu-prince
value = public_support
```

它描述两位 Decision Actors 之间对某候选的公开支持安排。三位 Actor 可形成不同的两方安排，例如史可法—韩赞周的程序支持或马士英—韩赞周的候选支持；自然语言信件仍承载条件、保留与理由，结构化 Term 只负责让协议改变后续 affordance。

至少一条 Operation 必须要求一个仍有效的 `endorsement` Agreement：例如完成福王或潞王的制度承认程序。这样协议不是“未来自我提醒”，而是真正改变能否完成程序的世界约束。后续以相反候选公开推进的行为可以造成 `AGREEMENT_BREACHED`，但不由 Host 自动判断背叛动机。

### Operation

第一版只保留以下经过策展的行动，不造通用政治 DSL：

| Operation | 主要 Actor | 需要时间 | 关键世界后果 |
| --- | --- | --- | --- |
| `convene_recognition_assembly` | 韩赞周 | 1 日 | `nanjing-court` 从可开会变为实际进入议程；不是一键决定人选。 |
| `make_fu_backing_visible` | 马士英 | 1 日 | 把可见的江北军政支持变为 `FU_BACKED`；不宣称四镇已被完全控制。 |
| `arrange_fu_entry` / `arrange_lu_entry` | 有合法条件的一方 | 2 日 | 候选从可接触变为在南京可进行程序；这是有限的政治行动，不把本场做成 courier simulator。 |
| `formalize_fu_regency` / `formalize_lu_regency` | 韩赞周 | 1 日 | 只有候选在场、程序开启且韩赞周与另一 Decision Actor 的相应 `endorsement` Agreement 有效时，才能写入候选的制度承认。 |
| `issue_regency_proclamation` | 韩赞周 | 1 日 | `regency-proclamation` 从 `NOT_ISSUED` 变为已发布，使 Resolution 后的 Aftermath 能继续处理可见后果。 |

两条候选承认 Operation 故意分开定义，而不是为了“谁都能选”发明通用继统语言。它们只引用本 Crisis 已验证的对象与状态。

### Pressure

第一版只设置一条外部压力：`institutional-vacuum-tightens`。它在若干内部时刻后把 `nanjing-recognition` 从 `PENDING` 推为 `URGENT`，表示北都确报之后留都无可无限延宕的名义中心。它是带来源的 `scenario_assumption`，而不是自动播放史可法、马士英、福王或任何四镇将领的真实后续行动。

不设置“马士英历史上迫使立福王”“福王历史上进入南京”“四镇历史上表态”为 Pressure。这些若需要发生，只能经 Actor Operation、Agreement 或本局已明确为非 Decision Actor 的可见世界事实发生。

## `nanjing-succession-v1` Resolution Contract 设计

Resolver 只读 Projection 的客观状态：候选是否已在南京、`nanjing-recognition` 的制度状态、已完成程序、可见军政支持、公开文书与仍可行的替代候选。它不读 Plan、Belief、私有信件修辞、历史 anchors 或 LLM 输出。

Resolution Gate 的候选条件：

1. 某候选已到南京，完成可执行程序并取得相应制度承认；或
2. 两个候选均形成不兼容的公开政治事实，以至普通通信和待完成 Operation 已不能消解；或
3. 候选与程序都没有形成可执行结合，且外部压力已把该危局推入可解释的延期状态。

可能的结果仅为：

- `RECOGNIZED_SETTLEMENT`：福王或潞王取得可执行的局部制度承认；
- `CONTESTED_SUCCESSION`：相互不兼容的承认／可见支持形成；
- `FRAGMENTED_SETTLEMENT`：南京程序与可用支持脱钩，不能称作单一认可；
- `DEFERRED`：到 Safety Horizon 仍没有足以诚实结算的政治事实。

这是 Recognition Resolution，不是投票积分、关系分、战斗或“谁更像皇帝”的 LLM 判断。第一版不计划使用随机性；只有未来出现来源允许的、同一 Projection 下多个同样可接受结果时，才允许用 Run pinned seed 选择歧义带内的一个结果。

Resolution 必须写回：候选状态、制度承认、公开文书、有关 Agreement 状态、Actor 知识投递，随后进入 Aftermath。Aftermath 允许史可法、马士英与韩赞周收到结果、重写 Plan、完成有限的文书／军政后续行动，并在局部稳定后 Settlement；不能一进入 Gate 就跳到 Ending Page。

## Historical Compatibility 与禁止事项

Pack 只设置两个 `REFERENCE_ONLY` 后续节点：五月初三的福王监国，及五月十五的福王即位。它们的 Compatibility 仅检查本局是否仍保留福王在南京、`FU_RECOGNIZED` 与公开程序等必要前提；仪式日的具体执行与后来的统治选择若未建模，应返回 `UNKNOWN`，而不是替历史续写。

不得在本 Pack 中：

- 把福王历史上被拥立写成默认 Ending；
- 把史可法、马士英、四镇或候选人的后续真实选择偷注入 Pressure；
- 将“七不可”、党争标签、后世褒贬变成 Role Charter、因子或成功率；
- 以票数、分值、忠诚度、士气或兵额解决 Recognition；
- 让南都只是山海关的长距离送信换皮。

## 实现与验证入口

当前实现提供小型 `POLITICAL` surface：按福王、潞王、制度承认、可见军政支持和公开文书展示 known / unknown / unconfirmed，不画图、不做关系网。Pack 只需声明有序的 `subject_ids` 与 `context_entity_ids`；世界视图可显示实体状态，私有视图只会为当前合法知道的实体带回状态，未获确认的主体显示 `UNCONFIRMED`，其余事实显示 `UNKNOWN`。合法操作或调查的 target 名称本身不构成状态知识：只有自有资产、所在地点、可见行动／Pressure 的效果或已送达的 Resolution 才能让私有 Surface 显示状态。当前确定性回归覆盖福王认可、替代候选认可、争议、碎片化、延期、历史样本型汇合、不同 seed 的字节稳定结果、Agreement 解锁程序 Operation，以及完整的福王承认→Aftermath→Settlement fixture loop。

对应来源数据与已校验 Pack 位于 [`scenarios/jiashen/crises/nanjing-succession/`](../scenarios/jiashen/crises/nanjing-succession/)。它只在 POLITICAL surface、resolver 与 fixture/API 回归同时存在后才加入 `volume.yaml`；仍不把这一层 fixture/API 证据称为完成的 Desk、浏览器或 live Hermes 体验。
