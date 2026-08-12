# Chronicle · 甲申

> 在同一卷历史里，先看世界，再接过其中一段人生的下一步。

Chronicle 是一个本地运行、以 V5 `Volume Worldline` 为根的历史体验原型。它不让用户扮演全知的历史作者，也不把人物当成可以随意切换的 NPC；它要验证的是一种更克制的体验：

**你暂时离开某段人生之后，世界和其他人仍然继续拥有自己的下一步。**

默认内容是 `jiashen` Volume「甲申」：一个共享世界、6 条持久 Lifetime、3 个彼此交织的 Crisis knot。Crisis 是局部因果密度，不是产品的根目录；整卷的时间、人物身份、Archive 和最终清理都归 Volume 所有。

## 先看结论

当前仓库处于 **V5 candidate** 状态：

- V5 Volume、Global World Tick、Persistent Lifetime、Inhabit/Leave、Pending Logical Moment、跨 Crisis 传播、Archive/Ending 和 vanilla 前端已经落地；
- Source/Scenario/Volume validators、自动化回归、前端静态检查和隔离 live Hermes 证据已归档；
- 当前代码不是一个已经完成最终用户验收的产品。P5 的真实试玩回答和正式 Completion Challenge 仍未完成；完整边界见 [`docs/V5_ACCEPTANCE.md`](docs/V5_ACCEPTANCE.md)。

因此，README 里的“已支持”指代码和相应证据层已经存在，不等于所有真实 Hermes 行为或最终体验已经通过验收。

## 五分钟启动：只跑本地 fixture

### 环境

- Python `>=3.11`
- [`uv`](https://docs.astral.sh/uv/)
- 浏览器访问 `http://127.0.0.1:<port>/`
- 真实 Hermes 只在 live 验证时需要；fixture 不依赖模型调用

### 安装和校验

```bash
cd /Users/koala/work/product/chronicle
uv sync

uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
```

### 启动隔离 fixture

fixture 只应使用临时数据库和临时 Hermes Home，不要把项目默认 `data/` 或 `.chronicle/` 当作实验垃圾桶：

```bash
V5_TMP="$(mktemp -d -t chronicle-v5.XXXXXX)"

CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$V5_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$V5_TMP/hermes-home" \
uv run chronicle serve --host 127.0.0.1 --port 8711
```

打开 [http://127.0.0.1:8711/](http://127.0.0.1:8711/)，即可体验：

```text
Volume → World → Follow → Inhabit → Life Desk → Leave → Archive / Ending
```

停止服务后，只删除本次命令创建的 `$V5_TMP`。不要递归清理未知目录，也不要停止无法确认归属的 Hermes 或 Gateway。

## 用户会经历什么

| 页面 | 它回答的问题 | 可见边界 |
| --- | --- | --- |
| Volume | 这一卷历史从哪里展开？ | 只介绍卷册和阅读方式 |
| World | 此刻哪里正在变得重要？ | 只展示公共世界、公开位置和公开事实 |
| Follow | 如果只跟着这段人生，会看到什么？ | 只展示外部可见轨迹，不窥视内里 |
| Inhabit | 我要不要接过这段人生？ | Human 一次只能接过一条 Lifetime |
| Life Desk | 这个人现在收到什么、知道什么、还承担什么？ | 只展示当前 Lifetime 的私有上下文 |
| Leave | 我是否把下一步交还给世界？ | 只改变 controller/presence，不重置人物或时间 |
| Archive / Ending | 这一卷怎样成为过去？ | 只有 Volume 到达结构边界后才能封存和回看 |

普通用户不需要理解 Profile、Wake、Session、Memory 或 Runtime。这些是执行边界，不是产品页面的心智模型。

## V5 的核心模型

### Volume、Crisis 和 Worldline

`Volume Worldline` 是整卷历史的生命周期根，拥有共享世界、全局时钟、Lifetime、Profile 绑定和最终清理。一个 Crisis settlement 只留下局部 Meaning，不能直接封存整卷。

### Lifetime 不是 Session

`Lifetime` 是持久的人生身份，跨 Crisis、controller、dormancy 和进程重启继续存在。Hermes Profile 是该 Lifetime 的执行资源；Session 可以刷新，不能代替人物的长期身份。

### Host 保持世界权威

主体可以解释自己收到的上下文、等待、通信、更新计划和提出有限意图，但不能直接改写世界。Host 负责：

- 唯一的 Volume world tick；
- Truth、Visibility、Knowledge、Belief 的边界；
- 消息发送、在途和抵达；
- 权限、资源、状态效果和幂等；
- Human/Agent Pending Logical Moment 的冻结、stage 和 atomic commit。

一封消息发出不等于已经抵达；世界发生变化也不等于每个人都知道。未送达内容、其他 Lifetime 的私有计划/信念和内部 runtime 字段不能进入公共页面或别人的 Perspective。

### Archive 是结构边界，不是按钮效果

```text
Crisis Instance SETTLED / SUPPRESSED
        ↓  Volume 仍保持 ACTIVE
没有 pending moment、due wake、在途消息或待应用 Field Event
        ↓
结构性 boundary ready
        ↓
VOLUME_SEALED / ARCHIVED
        ↓
撤销 bindings，清理只属于本卷册的 Profile/Gateway 资源
```

Public Replay 默认只返回公共轨迹；选择某一 Lifetime 后，才显示该人物的 selected replay，并区分“当时知道”“后来才知道”和“当时仍未知”。

## 本地运行方式

### `serve` 和 `start`

```bash
# 开发 fixture：允许 reload，不执行 live Volume 的生产式启动管理
uv run chronicle serve --host 127.0.0.1 --port 8711

# 本地产品启动：对 active/cleanup-pending live Volume 执行 fail-closed reconcile
uv run chronicle start --host 127.0.0.1 --port 8711

# 检查配置、素材、数据库、Hermes CLI 和前置路由
uv run chronicle doctor
```

两种启动方式都只允许 loopback 绑定。当前应用没有登录层，不要绑定到局域网或公网。

### live Hermes 的配置边界

真实 V5 live 路径需要独立的 SQLite、Hermes Home、loopback Gateway 和模型配置。常用配置项如下：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `CHRONICLE_DEV` | 是否允许 `live: false` fixture | 关闭 |
| `CHRONICLE_DATABASE_URL` | SQLite 数据库 URL | `sqlite:///./data/chronicle.db` |
| `CHRONICLE_HERMES_HOME` | 本项目拥有的 Hermes Home | `.chronicle/hermes-home` |
| `CHRONICLE_HERMES_BASE_URL` | Hermes Gateway 地址 | `http://127.0.0.1:8642` |
| `CHRONICLE_HERMES_BIN` | Hermes CLI 路径 | 自动查找 `hermes` |
| `CHRONICLE_LLM_BASE_URL` | 模型 Provider 地址 | 空 |
| `CHRONICLE_LLM_API_KEY` | 模型密钥 | 空 |
| `CHRONICLE_LLM_MODEL` | 模型名称 | 空 |
| `CHRONICLE_LLM_API_MODE` | Provider 协议模式 | `chat_completions` |
| `CHRONICLE_LLM_TIMEOUT` | Provider 请求超时秒数 | `180` |

Secret 只放在被忽略且权限受控的 runtime env/Profile env 中；不要写入 README、日志、测试产物或 Git。

## V5 Product API

正式产品 API 的生命周期根是 `/api/worldlines`，而不是旧的 `/api/runs` 或单独的 Crisis：

```text
POST /api/worldlines                         创建 Volume
GET  /api/worldlines/active                  读取当前 Volume
GET  /api/worldlines/{id}/world              公共 World
GET  /api/worldlines/{id}/lifetimes           可接近的 Lifetimes
GET  /api/worldlines/{id}/follow/{lifetime}   公共 Follow
GET  /api/worldlines/{id}/desk                当前 inhabited Lifetime 的 Desk
POST /api/worldlines/{id}/inhabit             接过一段人生
POST /api/worldlines/{id}/leave               离席
POST /api/worldlines/{id}/continue            推进到下一逻辑时刻
POST /api/worldlines/{id}/decision             提交受限意图
GET  /api/worldlines/{id}/archive             公共回看
GET  /api/worldlines/{id}/archive?lifetime_id=... 选择一段人生回看
POST /api/worldlines/{id}/seal                申请整卷封存
```

开发模式才允许创建 `live: false` fixture；正式路径使用 `live: true`，并由 Host 负责 Profile materialization、Wake、Perspective、MCP staging 和 atomic moment commit。

旧 V4 `/api/runs`、`entry_id`、Compare 和 legacy replay 仍为兼容边界，服务已有数据和回归；它们不是 V5 新产品入口。

## 开发和验收

每次源码、内容或前端变更后，至少运行：

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle scripts tests

uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate

set -o noglob
for file in $(git ls-files '*.js'); do
  node --check "$file" || exit 1
done

git diff --check
```

浏览器验收至少覆盖 1440、1280、768、390 四种宽度，并检查：

- Volume、World、Follow、Inhabit、Desk、Leave、Archive、Ending 可到达；
- 页面无横向溢出，手机宽度仍可读；
- public World/Follow/Replay 不泄漏私有 state；
- mutation lock 防止重复提交；
- 页面不出现 Agent/Profile/Session/Memory/Runtime 等内部产品术语。

证据必须分层理解：fixture、自动化测试、浏览器、Doctor、Hermes readiness 和真实 live 业务链互相不能替代。当前逐项结果和 blocker 见 [`docs/V5_ACCEPTANCE.md`](docs/V5_ACCEPTANCE.md)。

## 设计边界和明确不做的事

V5 不是：

- 第二套 Agent Harness 或通用历史/workflow DSL；
- React/Vite 重写或平台化 dashboard；
- 全知的 LLM World Master/Judge；
- 完整战争/策略模拟、mass Agent society 或唯一“正确历史”；
- Vector DB、关系图、Theory of Mind、Skill Evolution 或跨世界线 Compare 新语义。

如果一个功能不能直接服务“同一卷历史中，几段人生在用户视线之外仍各自拥有下一步”，就不应悄悄加入 V5。

## 文档导航

| 你想了解什么 | 入口 |
| --- | --- |
| 产品旅程、用户价值、页面边界 | [`PRODUCT.md`](PRODUCT.md) |
| Volume/Lifetime/Host/Archive 架构 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 页面状态、文案、隐私和响应式合同 | [`docs/FRONTEND.md`](docs/FRONTEND.md) |
| 本地启动、隔离、迁移、Hermes 和清理 | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| V5 迁移原则和 invariants | [`docs/V5_MIGRATION.md`](docs/V5_MIGRATION.md) |
| 史料、来源和建模盲区 | [`docs/HISTORY.md`](docs/HISTORY.md) |
| 当前验收矩阵、证据和 blocker | [`docs/V5_ACCEPTANCE.md`](docs/V5_ACCEPTANCE.md) |

## License

见 [`LICENSE`](LICENSE)。
