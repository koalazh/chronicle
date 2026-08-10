# Chronicle · 甲申

> 一个世界，几个人；每个人只活在自己收到的消息里。

Chronicle 是一场有边界的历史主体实验。它让李自成、吴三桂和多尔衮在同一段尚未决定的时间里各自生活：他们有自己的责任、消息、判断和计划，世界事实则由一个确定性的 Host 记录、推进和裁定。

它不是历史聊天机器人，不是策略游戏，也不是让一个中央模型替所有人写结局。第一版只做一件事：把“谁知道什么、谁选择了什么、消息何时抵达”讲清楚。

## 当前危局

正式入口只有一场 Crisis，叫“山海关之前”。起点使用史料能够支撑的相对时间窗，而不强行换算成未经复核的现代公历日期。

| 项目 | 当前定义 |
| --- | --- |
| 主体 | 李自成、吴三桂、多尔衮 |
| 起点 | 顺治元年四月中旬前；吴三桂首封求助信已发出，但尚未抵达多尔衮 |
| 走廊 | 北京 → 永平 → 山海关 → 辽西行军路 |
| 主体可以提出 | 通信、等待、有限准备、有限移动、更新计划、安排未来复查 |
| 本场停止 | 需要裁定山海关大规模直接交战时停止；第 9 日是安全上限 |

这些定义不是“完整复原明清战争”。起点、路线时长、在途信件和后续历史锚点都在 [历史与视野](docs/HISTORY.md) 中标出史实、争议和建模假设。

## 两种进入方式

**Watch · 旁观**：三位主体都由 Hermes 运行。你可以在世界视野和三个人物视野之间切换，观察同一件事如何在不同主体那里变成不同的知识、判断和计划。点击“继续”会推进到下一个有意义的模拟时刻，而不是机械地加一天。

**Takeover · 成为吴三桂**：李自成和多尔衮继续自主运行，吴三桂由你控制。活动期间你只能看到吴三桂已经收到的信息；你的自然语言会被解释成有限的世界请求，再经过与 Agent 相同的权限、路线、资源、边界和原子提交检查。空文本加“继续”就是沉默。

两种模式使用同一个 Run Engine。Watch 不能在中途变成 Takeover；想亲自做一次决定，就从同一个 Crisis checkpoint 新开一局。

## 本地启动

### 安装与确定性检查

```bash
uv sync
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
uv run pytest -q
uv run ruff check .
node --check web/app.js
```

### 启动页面

```bash
uv run chronicle serve
```

打开 <http://127.0.0.1:8711>。Chronicle 只绑定本机回环地址，当前没有登录层，不要把它暴露到局域网或公网。

首次使用，在“设置”填写模型服务地址、API Key、模型和接口类型，点击“保存并核对”。原始 Key 只写入被忽略的 `.chronicle/runtime.env`，接口不会把它返回给浏览器。

正式页面只创建 live Run。模型服务未配置、Provider 不可用或 Hermes 前置条件未满足时，入口会说明下一步并停止；不会静默改成 fixture。

### 真实 Hermes 的顺序

真实运行使用项目私有 `.chronicle/hermes-home`。顺序是：停止旧的项目私有 Gateway，在页面创建 Watch 或 Takeover，启动 Gateway，运行 `uv run chronicle doctor` 确认 `READY`，再回到页面点击“继续”。`READY` 只表示运行前置条件满足；真实业务是否完成，要看同一局中的 Profile、fresh Session、World MCP、Life State、后续 Wake、消息送达和封存结果是否能够关联起来。完整命令见 [运维与验收](docs/OPERATIONS.md)，现场记录见 [验收记录](docs/ACCEPTANCE.md)。

## 文档导航

| 你要解决的问题 | 从这里开始 |
| --- | --- |
| 第一次了解产品 | 本页 → [产品说明](PRODUCT.md) |
| 明确用户旅程和范围 | [产品说明](PRODUCT.md) |
| 明确页面行为、文案和视觉 | [前端合同](docs/FRONTEND.md) |
| 理解 Run、主体、调度、Hermes 和迁移 | [架构](docs/ARCHITECTURE.md) |
| 理解史料、争议和信息盲区 | [历史与视野](docs/HISTORY.md) |
| 启动、迁移、排障和验收 | [运维与验收](docs/OPERATIONS.md) → [验收记录](docs/ACCEPTANCE.md) |
| 了解 V2 如何退出正式路径 | [V2 迁移归档](docs/archive/v2/V2_MIGRATION.md) |

## 证据和安全边界

fixture、自动化测试、浏览器检查、Doctor 和真实 Hermes 业务 Run 是不同证据层。页面能动、测试通过或 Doctor 为 `READY`，都不能单独写成“真实 Agent 业务已打通”。

不要提交 `.env`、`.chronicle/`、SQLite 数据库、完整模型正文、Profile 私钥或带凭据的日志。迁移和实验都使用副本或新路径，不要删除真实数据库或 Hermes Home 来“重置”。
