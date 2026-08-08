# Chronicle 前端产品化改进长程 Handoff

状态：READY_FOR_FOLLOW_UP（第一轮前端产品化已实现）

目标执行者：后续 coding agent

项目：/Users/koala/work/product/chronicle

形成日期：2026-08-08

## 1. 这份 Handoff 要解决什么

Chronicle 当前已经具备可运行的后端、Source Pack、确定性 Host、部分真实 Hermes 接线和一套视觉方向，但前端仍然像“技术演示页面”：

- 内部实现术语直接暴露给普通用户；
- 中英文混用，英文小标题和状态词比产品叙事更显眼；
- Seat、Runtime、Canon、Branch、Wake、epoch、profile 等内部概念占据了用户注意力；
- 页面有导航和卡片，但没有形成“我正在观察什么、下一步可以做什么、为什么这件事重要”的产品心智；
- Setup、人物经历、史料依据、受限推演之间没有连续的首次使用路径；
- UI 文字暗示了比当前真实运行时更完整的能力，例如把 fixture Wake、Hermes Memory 和真实业务闭环混成一个体验；
- 移动端虽然没有明显溢出，但信息密度、按钮语义和层级仍然偏 demo。

这不是一次换颜色或补中文的视觉重 skin，而是一次前端产品化收敛：

用户先理解甲申观测台的价值，再逐步看到历史节点、人物实际收到的信息、史料依据和一个有边界的受限推演；内部实现细节只在用户主动打开技术说明时出现。

## 2. 已知事实与不可忽略的边界

本 Handoff 建立在当前项目源码、测试、运行态和浏览器检查之上。不要把旧截图、自报 PASS 或架构意图当成当前能力证明。

### 当前已经存在

- 项目入口是静态前端：web/index.html、web/app.js、web/styles.css。
- 后端已有：
  - /api/scenario
  - /api/timeline
  - /api/events/{event_id}
  - /api/sources/{assertion_id}
  - /api/who-knows
  - /api/lifetimes/{seat}
  - /api/lifetimes/{seat}/wake
  - /api/lifetimes/{seat}/reflect
  - /api/branch
  - /api/branch/{branch_id}
  - /api/branch/{branch_id}/step
  - /api/config
  - /api/setup/test
  - /api/setup/configure
  - /api/bootstrap
- Source Pack 当前有 36 个事件、36 个 assertion、4 个来源，窗口为崇祯十七年正月初一至三月十九。
- UI 当前已经有 Cover、Chronicle、Lifetimes、Branch、About、Source Drawer、Runtime 设置的基础实现。
- 现有纸张、墨色、朱砂色、青蓝色和自绘路线图是可保留的视觉资产。
- 现有 API 数据结构和历史边界应优先复用，不为了改文案把后端改成另一套模型。

### 前一轮审计基线（已进入主 Task Loop 修复）

以下是前端产品化开始时确认的基线；它们保留在这里用于解释为什么后续修复不能只做视觉包装：

1. Hermes 真实运行时曾暴露 bfl + memory；现已由项目配置记录 bfl opt-out，并由现场 probe 验证 memory-only。
2. Memory Integrity Guard 曾缺少 snapshot、diff、rollback 和 ProtocolViolation；现已由 Host/SQLite 约束覆盖。
3. Branch 曾缺少 fork tick、路线、收件人和行动前提校验；现已由服务端边界覆盖。
4. 部分 Source Pack world effects 曾未还原；现已保留原始 effects 并投影到 world state。
5. Lifetimes 的 UI Wake 曾固定发送 live=false；现已根据 readiness 在 live/fixture 间切换，并对 live 失败 fail-closed。
6. 项目仍没有独立的 Playwright/E2E 测试套件；本轮用真实浏览器路径、截图和 API/Host 自动化检查覆盖相应证据，未把它们混称为 E2E。

前端任务本身只负责信息架构、语言、首次使用流程和诚实表达；跨边界能力由主 Task Loop 的独立修复 checkpoint 负责，前端不代替后端证据。

## 3. 产品目标

### 核心目标

让第一次打开 Chronicle 的用户在 30 秒内理解：

1. 这是一座观察历史如何被不同人物分别知道、理解和记住的观测台；
2. 时间线展示的是已经发生的历史，人物只知道已经送达给自己的信息；
3. 用户可以查看人物经历和史料依据；
4. 到达真实历史节点后，才可以进入唯一的“太子抚军江南”受限推演；
5. 推演有明确边界，不是预测器，也不是自由改史游戏。

### 产品语气

- 克制、编辑式、中文优先、有历史感，但不要故作古雅。
- 先讲用户能理解的事情，再讲内部机制。
- 每个页面只回答一个主要问题。
- 解释术语时使用一句自然语言，不堆定义。
- 不用“AI agent demo”的语气，不用系统自嗨式的工程状态墙。
- 所有面向用户的按钮、标题、状态、错误和辅助说明均使用中文。
- 允许保留的专业名词只有产品名和必要技术名：Chronicle、Hermes、API、Source Pack、Memory 等；它们不能代替中文语义。

## 4. 用户可见术语规范

这是必须执行的文案映射，不允许各页面自由发挥。

| 内部术语 | 用户主界面用语 | 技术详情中的可选说明 |
| --- | --- | --- |
| Chronicle | 甲申观测台 | Chronicle |
| Canon | 既定历史 | Canon |
| Timeline | 历史时间线 | Canon 时间线 |
| Who Knows? | 谁已经知道 | 信息送达与知识范围 |
| Seat / Seat A/B/C | 人物 / 崇祯、李自成、吴三桂 | Seat A/B/C |
| Lifetimes | 人物经历 | Lifetime |
| Life Record | 经历记录 | Life Record |
| Wake | 记录一次观察 / 更新经历 | Observation Wake |
| Reflection | 重新理解 | Reflection |
| Memory | 长期记忆 | Hermes Memory |
| Source Inspector | 史料依据 | Source Inspector |
| evidence_status | 证据状态 | evidence_status |
| provenance | 内容来源 | provenance |
| historical | 史料事实 | historical |
| modeled | 研究性建模 | modeled |
| branch_derived | 推演产生 | branch_derived |
| corroborated | 多来源印证 | corroborated |
| single_attested | 单一来源 | single_attested |
| disputed | 存在争议 | disputed |
| approximate | 时间约略化 | approximate |
| Branch | 受限推演 | Branch |
| Fork | 历史分叉点 | Fork |
| Runtime settings | 模型设置 | Runtime |
| Runtime Epoch | 配置版本 | Runtime Epoch |
| profile | 人物模型配置 | Hermes Profile |
| API server | 本地模型连接 | API server |
| model boundary | 模型边界 | Model Boundary |
| No World Master LLM | 不由模型续写历史 | World Master LLM |

### 绝对不要在主界面出现的内容

- chronicle-seat-a、chronicle-seat-b、chronicle-seat-c；
- epoch-xxxxxxxx、wake id、life id、assertion id 作为主要按钮文案；
- DAY、CURRENT EVENT、RUNTIME、LIFETIMES、BRANCH / ONE CURATED FORK 等英文大标题；
- “Wake this Lifetime”“Open Lifetime”“Submit intention”等英文动作；
- “The model ends here”“No durable memory yet”等英文状态；
- API key、provider base URL、模型原始配置、toolset 名称；
- 面向普通用户的 JSON、HTTP 状态码、数据库表名、Host 内部类名。

ID 和内部别名只有在用户主动展开“技术详情”或史料审计细节时才允许出现，并且必须是次要信息。

## 5. 目标信息架构

### 5.1 Cover：先解释为什么值得进入

主标题：甲申

副标题建议：

“最后一个春天，三个人只知道各自收到的消息。”

首屏必须让用户看到：

- 一句话产品价值；
- 时间范围：崇祯十七年正月初一至三月十九；
- 三个可理解的承诺：
  - 看见历史如何发生；
  - 看见消息如何抵达；
  - 看见一次有边界的历史分叉；
- 唯一主按钮：“开始观测”；
- 如果需要配置模型，使用温和的状态提示：“首次使用需要连接模型”，而不是直接把用户扔进 Runtime settings。

Cover 不要出现“DIGITAL HISTORICAL OBSERVATORY”这类英文副标题，也不要用大量装饰线代替产品解释。

### 5.2 全局导航：用用户任务命名

导航建议：

- 观测台
- 人物经历
- 受限推演
- 方法与边界
- 模型设置

“受限推演”只有在当前时间线已经抵达 fork 节点并且后端允许创建时才可以成为可操作入口。不能让前端看起来可以随时分叉。

移动端导航可压缩为：

- 观测
- 经历
- 推演
- 更多

### 5.3 观测台：回答“发生了什么，谁知道”

页面结构：

1. 页面标题：“谁已经知道，谁还不知道？”
2. 页面说明：用两句话解释既定历史、消息送达和人物知识范围。
3. 历史时间线：
   - 每项只显示日期、事件标题、简短证据状态；
   - 不显示 world、fork、marker 等内部 tag；
   - 当前事件清晰标出“正在查看”；
   - 在手机端允许横向滚动，但首项和当前项必须可见。
4. 中央观测区：
   - 日期写“崇祯十七年正月初五”；
   - 辅助写“观测台第 5 天”，不要写 DAY 04 / CANON WINDOW；
   - 主按钮“推进一天”；
   - 地图标题“路线与消息”；
   - 图例使用“历史路线”“传递中的消息”；
   - 地图标签默认中文显示，技术 alias 不显示。
5. 当前事件：
   - 小标题“当前节点”；
   - 证据状态使用中文 badge；
   - 主文案是自然语言；
   - 按钮“查看史料依据”；
   - 只有在当前 tick 已经到达 fork 且选择的是 fork 事件时显示“进入受限推演”。
6. 右侧知识区：
   - 标题“谁已经知道”；
   - 只显示人物姓名、状态“已知道 / 尚未知道”和一句说明；
   - 不显示 Seat、profile、runtime alias。

### 5.4 史料依据：回答“这句话从哪里来”

Source Drawer 改成真正的“史料依据”面板：

- 证据状态：多来源印证 / 单一来源 / 存在争议 / 时间约略化；
- 事件说明；
- “归一化说明”可以改成“研究说明”；
- 来源列表显示书名、卷章、链接；
- assertion ID 默认隐藏；
- historical / modeled / branch_derived 只在“技术详情”中作为次级字段显示；
- 所有空值要有自然中文提示，不显示 undefined、SOURCE 或原始字段名。

### 5.5 人物经历：回答“这个人真正经历过什么”

人物列表：

- 标题“人物经历”；
- 三张人物入口卡只展示人物名、所处位置的自然语言描述和三项统计：
  - 收到的信息；
  - 做出的判断；
  - 留下的长期记忆；
- 使用“查看经历”，不要使用“打开 Lifetime”。

人物详情：

- 标题“崇祯的经历”而不是“LIFETIME / Seat A”；
- 说明：“这里只记录他真正收到并处理过的信息。”
- 时间线条目使用：
  - “收到一条消息”
  - “形成判断”
  - “重新理解”
  - “留下长期记忆”
- 隐藏 observation_ids、runtime epoch、profile 名；
- 如果展示配置版本，放在折叠的“技术详情”里；
- 没有记忆时写：“目前还没有形成长期记忆。只有重新理解之后，经验才会被保留下来。”
- Wake 操作写“记录一次观察”或“更新这段经历”，不得出现 Wake；
- Reflection 操作写“重新理解这段经历”，但只有后端真实支持时才提供可操作按钮；
- 如果当前走的是确定性 fixture 路径，不要写“已调用 Hermes”或“模型已完成判断”。

### 5.6 受限推演：回答“如果这个真实提议被接受，会发生什么”

页面名称：“受限推演”

起点说明：

“这里不是自由改史。它只从‘太子抚军江南’这个真实提出过、但未被采纳的节点开始，并且最多向前走十四天。”

双栏：

- 左栏“既定历史”
- 右栏“受限推演”

用户看到的是：

- 起点；
- 当前模拟日；
- 已接受的消息/命令；
- 与既定历史的差异；
- 模型边界。

动作选择器：

- 等待
- 传递消息
- 发出命令
- 准备移动

内部值可以继续使用 WAIT、SEND_MESSAGE、ISSUE_ORDER、PREPARE_MOVEMENT，但绝不能出现在用户看到的 option label、状态或结果中。

边界状态：

- 标题：“模型边界已到”
- 说明：“继续往前需要新的历史假设，观测台不会替模型续写。”
- 列表：
  - 当前状态仍可追溯；
  - 既定历史与受限推演仍然分开；
  - 继续推演需要额外证据或规则。

### 5.7 方法与边界：回答“这不是一个什么产品”

用中文解释：

- 不是历史聊天机器人；
- 不是角色扮演；
- 不是策略游戏；
- 不是预测器；
- 不是自由改史工具。

用简单句解释：

- 事实、知道和相信不是一回事；
- 人物不能看见尚未收到的消息；
- 模型只负责解释，不负责替历史安排结果；
- 史料不足时，系统会停下来。

技术名词放在折叠的“技术说明”中，不放在首屏大标题。

### 5.8 模型设置与首次使用

设置窗口改成“模型连接”：

步骤：

1. 连接模型；
2. 检查连接；
3. 创建三个人物；
4. 返回观测台。

输入标签：

- 接口地址
- API Key
- 模型名称
- 调用方式
- 推理强度（可选）

说明：

“API Key 只保存在本机服务端，不会显示在浏览器或页面内容中。”

行为要求：

- Test connection 的成功/失败文案全部中文；
- Configure 成功后应明确告诉用户是否还需要创建三个 Hermes Profile；
- 如果调用后端 bootstrap，展示“正在创建三个人物”，成功后展示“人物已准备好”；
- bootstrap 失败时显示可理解的失败原因和下一步；
- 不要显示原始 traceback、HTTP 400、profile key、环境变量名；
- 模型配置已存在时，设置页显示“当前已连接”以及上次保存的模型名，但不显示 key。

如果本次实现不修改后端 bootstrap 行为，前端至少要把配置和 bootstrap 的分步关系解释清楚，不得让用户以为保存配置就等于三个 Profile 已经完成。

## 6. 视觉与交互要求

### 保留

- 纸张背景与细线；
- serif 标题与 sans 正文的对比；
- 朱砂色作为动作/警示色；
- 青蓝色作为路线/事实辅助色；
- 自绘地图；
- 大留白和编辑式页面节奏。

### 必须改掉

- 英文 uppercase kicker 大面积占据视觉层级；
- 一页中同时出现三套英文系统词；
- 卡片墙式的“统计 + 按钮”排列；
- 技术 ID 与用户任务并排；
- 页面只有静态文本而没有主任务反馈；
- button 看起来像普通文字链接但没有 hover/focus/disabled 反馈；
- 移动端把一整套桌面信息压缩成难读的小字。

### 交互状态矩阵

| 页面 | 正常 | 加载 | 空状态 | 错误 | 操作后反馈 |
| --- | --- | --- | --- | --- | --- |
| Cover / 设置 | 未配置 | 正在读取 | 未连接 | 连接失败 | 保存成功 / 创建中 |
| 观测台 | 当前节点 | 事件加载 | 无事件 | 事件读取失败 | 推进成功 |
| 史料依据 | 有出处 | 打开中 | 无细粒度出处 | 来源读取失败 | 关闭/返回 |
| 人物经历 | 有记录 | 读取中 | 尚无记录 | 读取失败 | 观察记录成功 |
| 受限推演 | 可操作 | 创建/推进中 | 尚未到达起点 | 推演失败 | 接受/拒绝/到达边界 |
| 方法与边界 | 正常 | 不适用 | 不适用 | 不适用 | 折叠展开 |

必须检查键盘 focus、按钮 disabled、错误恢复和长文本换行。

## 7. 实现边界

### 允许

- 修改 web/index.html、web/app.js、web/styles.css；
- 增加前端文案映射、状态渲染、错误处理和可访问性属性；
- 为首次使用补充现有 API 的正确调用顺序；
- 增加与前端复制和结构直接相关的轻量测试；
- 同步更新 docs/DESIGN.md、README.md 或本 Handoff 中确实已经过时的前端说明；
- 运行本地 server、浏览器检查和截图。

### 不要做

- 不引入 React/Vite 或新的 UI 组件库；
- 不重写 Hermes、Host、Branch、Memory 的领域模型；
- 不把后端未完成能力在前端包装成已完成；
- 不增加第二个场景、第二个 Fork、A2A、Coordinator、Team 或通用 Agent 平台；
- 不把所有技术细节都删除；技术审计需要保留，但放到次级详情；
- 不为了“看起来高级”增加动画、实时聊天、复杂图表或伪造指标；
- 不提交密钥、数据库、.chronicle、浏览器个人数据或运行日志；
- 不修改无关项目，不 push，不部署。

### 最小后端协同原则

本任务主交付是前端产品化。若发现 Branch、Memory、toolset、真实 Hermes 证据问题，不要用前端修饰掩盖，也不要在本任务里进行大规模后端重构。只有当某个现有 API 的返回值明显阻止诚实的产品流程时，才允许做最小、可单独验证的接口适配，并在最终报告中与纯前端完成度分开说明。

## 8. 验收标准

### 语言与心智模型

- [ ] 主界面、按钮、状态、错误和 aria label 全部中文。
- [ ] Chronicle、Hermes、API、Source Pack 等必要专业名词保留时有中文上下文。
- [ ] 主界面不再出现 Seat、profile、runtime alias、epoch、Wake、Life Record、CURRENT EVENT 等内部术语。
- [ ] 所有英文用户文案都有明确保留理由；没有“为了风格而英文”。
- [ ] 每个页面首屏只有一个主要问题和一个主要动作。

### 用户路径

- [ ] Cover → 开始观测路径自然。
- [ ] 首次未配置时，用户能理解连接模型、检查连接、创建人物、进入观测台的顺序。
- [ ] 观测台 → 选择事件 → 查看谁已经知道 → 查看史料依据可完成。
- [ ] 观测台在未到达 fork 前不提供可误触的分叉动作。
- [ ] 到达 fork 后，用户能理解进入的是受限推演，而非预测或自由改史。
- [ ] 人物经历页面只展示该人物实际收到的经历，技术细节可折叠。
- [ ] fixture、真实 Hermes、未验证能力在 UI 中不会混为一谈。

### 视觉与响应式

- [ ] 1440×1000 桌面视图层级完整，无大面积空洞或英文噪声。
- [ ] 1280 宽度可用。
- [ ] 768 平板视图没有横向溢出，主任务仍然明确。
- [ ] 390 移动视图没有布局损坏，导航、时间线、地图、抽屉和表单可操作。
- [ ] Cover、设置、观测台、史料依据、人物经历、受限推演、模型边界均有可检查状态。
- [ ] 截图或浏览器检查记录必须注明视口、页面、状态和数据来源；DOM viewport 与截图尺寸不可混淆。

### 验证

- [ ] uv run pytest -q 通过。
- [ ] uv run ruff check chronicle 通过。
- [ ] node --check web/app.js 通过，若环境提供 Node。
- [ ] 至少有一项自动化检查能阻止主要英文用户文案回归。
- [ ] 至少完成一次真实本地浏览器路径检查。
- [ ] 最终报告区分：fixture/UI 证据、自动化测试、真实 Hermes 证据和未验证后端边界。

## 9. 推荐执行顺序

1. 盘点并建立可见文案表，先替换导航、页面标题、按钮、状态和错误。
2. 调整全局 shell、Cover、设置和首次使用路径。
3. 调整观测台、时间线、知识面板、史料依据抽屉。
4. 调整人物经历和受限推演，隐藏内部 ID，翻译 action label，修正未到 fork 的 CTA。
5. 调整方法与边界、技术详情和运行状态表达。
6. 只做必要的 CSS 层级、留白、响应式和 focus/disabled 状态收敛。
7. 增加文案回归测试，运行测试和静态检查。
8. 用浏览器检查 1440、1280、768、390，并检查正常、加载、空、错误、成功/边界状态。
9. 做一次反对者视角 Completion Challenge：寻找仍然暴露内部术语、混淆 fixture/live、误导 Branch 能力或在移动端损坏的地方。

## 10. 交付说明

交付时必须说明：

- 修改了哪些文件，以及每个文件对应哪条产品要求；
- 哪些内部术语被隐藏、翻译或下沉到技术详情；
- 哪些 API 和行为保持不变；
- 哪些后端风险仍未解决；
- 测试、浏览器和视觉检查的具体结果；
- 没有把 UI 完成度报告成 Hermes、Branch、Memory 真实完成度。

## 11. 本轮执行快照（2026-08-08）

本轮已按这份 Handoff 完成第一轮前端收敛，后续 coding agent 应在此基础上继续，而不是重新发明一套产品语言。

### 已实现

- web/index.html：页面标题和启动态改为中文产品名。
- web/app.js：
  - Cover、导航、观测台、人物经历、史料依据、受限推演、方法与边界、模型设置全部改为中文优先；
  - 隐藏 Seat、profile、runtime alias、epoch 和原始 action type；
  - 把 tick、Host、approximate、Runtime 等从研究说明映射为用户可理解的中文；
  - 在历史分叉点之前禁用受限推演入口，只有到达 fork tick 后才允许创建；
  - 把终止节点改为“观测台到达边界”，不原样暴露 Source Pack 中的英文标题；
  - 增加模型连接、Bootstrap、人物经历记录、重新理解、操作提示和错误的中文状态；
  - 将技术 ID 仅放入史料面板的折叠技术详情。
- web/styles.css：
  - 去除大面积英文 uppercase 视觉噪声；
  - 增加 focus、disabled、空状态、边界、提示、设置步骤和技术详情样式；
  - 保留纸张、serif、朱砂、青蓝和路线图方向，收敛导航与按钮的产品层级。
- tests/test_frontend_copy.py：阻止已知英文系统文案和内部术语回归到用户可见模板。

### 前端产品化起始证据

- uv run pytest：17 passed；保留 1 条既有 FastAPI/httpx 弃用警告。
- uv run ruff check .：通过。
- node --check web/app.js：通过。
- git diff --check：通过。
- 本地浏览器已检查 Cover、观测台、史料依据、人物经历列表与详情、方法与边界、模型设置，以及隔离数据库中的受限推演建立、推进 14 天和边界状态。
- 浏览器文字扫描确认观测台主界面和史料依据面板没有连续英文用户文案；终止节点和研究说明中的英文内部词已被映射。

### 起始快照的后续修复状态

- 390×844、768×1024、1440×1000 已在真实浏览器设备指标下检查，三个视口均无横向溢出；修复后截图工件保存在被忽略的 `artifacts/ui/08-live-lifetime.png`、`09-live-mobile-chronicle.png`、`10-live-cover.png`。DOM viewport 与图片实际尺寸分别记录在 Task Loop HANDOFF 中。
- 本轮没有独立 Reviewer；Completion Challenge 需要记录为非独立对抗自检，除非后续提供独立只读审查。
- Hermes toolset、Memory Guard、Branch 深层规则和 world effects 已在主 Task Loop 修复并通过 deterministic/live evidence；真实 E2E 套件仍未引入，浏览器检查与真实 Hermes 业务调用分别记录。

### 后续 agent 接手入口

后续维护应继续区分 fixture/UI、自动化测试、浏览器检查和真实 Hermes 业务证据；任何新能力都必须先更新本 Handoff 的事实与验收边界。

### 主 Task Loop 修复摘要（2026-08-08）

- `785fe17`、`c0bd20d`、`20be42b`、`14abfbe`、`c94d522` 分别覆盖 Hermes fail-closed、Memory Guard、Canon/Branch、运行模式 UI 与 live session/异步交互边界。
- 当前 deterministic checks 为 30 tests；现场 project-local Hermes probe 曾返回 `READY`，包括三 Profile 路由、memory-only toolset 和交叉 key 拒绝；Gateway 已在验证完成后主动停止。
