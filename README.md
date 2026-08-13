# Chronicle · 甲申

> 在同一卷历史里，先看世界，再接过其中一段人生的下一步。

Chronicle 是一个本地运行的历史体验原型。你可以先观察共享世界，再接过其中一段已经活到这里的人生；离席后，世界和其他人生仍然继续，最后整卷历史会成为可以回看的过去。

它不要求你扮演全知的历史作者，也不把人物当成可随时切换的 NPC。产品要验证的是一种更克制的体验：你没有看见的那些人，也拥有自己的下一步。

## 当前产品

默认内容是 `jiashen` Volume「甲申」：一个共享世界、6 条持久 Lifetime、3 个相互影响但各自有边界的局部危局。当前实现提供：

- Volume、World、Follow、Inhabit、Life Desk、Leave、Archive 和 Ending 的完整本地旅程；
- 持久 Current Course、Knowledge/Attention 分离、HOLD/REVISE 判断和连续 Human judgment；
- 有发送、在途、抵达时刻的消息，以及 Offer/Agreement 和受权限约束的 Operation；
- 结构性封存、选定人生的判断回看和按卷册归属的资源清理；
- 可选的真实 Hermes 运行路径，以及不含 Secret 的工程验收记录。

当前状态是“可运行、可验证的研究型原型”。自动化、浏览器和一次真实 Hermes 轨迹各有自己的证据边界；真人主观反馈尚未收集，不会被自动化结果代替。结论和边界见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。

## 五分钟启动

### 环境

- Python `>=3.11`
- [`uv`](https://docs.astral.sh/uv/)
- 仅支持 loopback 浏览器访问：`http://127.0.0.1:<port>/`
- 本地 fixture 不需要模型调用；真实 Hermes 只在隔离业务验证时使用

### 安装和校验

```bash
cd /path/to/chronicle
uv sync

uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
```

### 启动本地 fixture

fixture 必须使用临时数据库和临时 Hermes Home，不要把项目默认 `data/` 或 `.chronicle/` 当作实验垃圾桶：

```bash
CHRONICLE_TMP="$(mktemp -d -t chronicle-dev.XXXXXX)"

CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$CHRONICLE_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$CHRONICLE_TMP/hermes-home" \
uv run chronicle serve --host 127.0.0.1 --port 8711
```

打开 [http://127.0.0.1:8711/](http://127.0.0.1:8711/)，按以下顺序体验：

```text
Volume → World → Follow → Inhabit → Life Desk → Leave → Archive / Ending
```

停止服务后只删除本次命令创建的 `$CHRONICLE_TMP`。不要递归清理未知目录，也不要停止无法确认归属的 Hermes 或 Gateway。

## 用户旅程

| 页面 | 它回答的问题 | 可见边界 |
| --- | --- | --- |
| Volume | 这一卷历史从哪里展开？ | 介绍卷册和阅读方式 |
| World | 此刻哪里正在变得重要？ | 只展示公共世界和公开事实 |
| Follow | 这段人生为什么值得接近？ | 只展示合法可见的外部轨迹 |
| Inhabit | 我要不要接过这段人生？ | 一次只能接过一条 Lifetime |
| Life Desk | 这个人现在知道什么、承担什么？ | 只展示当前 Lifetime 的私有上下文 |
| Leave | 我是否把下一步交还给世界？ | 只改变控制权，不重置人物或时间 |
| Archive / Ending | 这一卷怎样成为过去？ | 只有结构边界满足时才能封存 |

普通用户不需要理解 Profile、Wake、Session、Memory 或 Runtime。这些是执行边界，不是产品页面的心智模型。封存后选定一段人生，可以回看当时的判断、后来抵达的事实和可见后果，但不会看到未落笔的思考。

## 核心规则

- Volume 拥有整卷的时间、人物身份、公共世界和最终清理权；局部危局结算不会自动封存整卷。
- Lifetime 是持久的人生身份，跨离席、控制权变化和进程重启继续存在。
- Host 负责世界时钟、来源、位置、路线、消息抵达、权限、资源、状态效果、幂等和原子提交。
- 发生事件不等于所有人知道；消息发出不等于已经抵达；Belief、Plan 和 Memory 不能冒充公共事实。
- Human 与 Hermes 都只能提交受限意图；世界效果由 Host 校验后在一个 Logical Moment 中原子收束。
- Archive 是结构边界之后的只读回看，不是一个把当前状态改成结束的按钮。

## 常用命令

```bash
# 开发模式：允许 fixture 和 reload
uv run chronicle serve --host 127.0.0.1 --port 8711

# 产品启动：启动时对活动真实卷册做 fail-closed reconcile
uv run chronicle start --host 127.0.0.1 --port 8711

# 检查配置、素材、数据库、Hermes CLI 和前置路由
uv run chronicle doctor
```

真实运行需要独立 SQLite、Hermes Home、loopback Gateway 和模型配置。密钥只放在受控且被忽略的 runtime/Profile env 中，绝不写入文档、日志、测试产物或 Git。更多隔离、清理、迁移和故障恢复规则见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。

## 产品 API（开发者参考）

产品页面使用 `/api/worldlines` 作为生命周期入口：

```text
POST /api/worldlines                         创建 Volume
GET  /api/worldlines/active                  读取当前 Volume
GET  /api/worldlines/{id}/world              公共 World
GET  /api/worldlines/{id}/lifetimes          可接近的 Lifetimes
GET  /api/worldlines/{id}/follow/{lifetime}  公共 Follow
GET  /api/worldlines/{id}/desk               当前 Life Desk
POST /api/worldlines/{id}/inhabit             接过一段人生
POST /api/worldlines/{id}/leave               离席
POST /api/worldlines/{id}/continue            推进到下一逻辑时刻
POST /api/worldlines/{id}/decision            提交受限意图
GET  /api/worldlines/{id}/archive             公共回看
GET  /api/worldlines/{id}/archive?lifetime_id=...  选定人生回看
POST /api/worldlines/{id}/seal                申请整卷封存
```

旧数据仍有兼容读取路径，但新产品页面不依赖它们；新增功能应沿当前 Volume API、Host 和 Ledger 边界实现。

## 开发与验收

源码、内容或前端变更后至少运行：

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle crisis validate
git diff --check
```

浏览器验收覆盖 1440、1280、768、390 四种宽度，并检查页面可达、无横向溢出、无私有状态泄漏、非空判断不因重绘丢失、重复提交被锁住、没有内部执行术语。完整矩阵见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。

## 文档

| 你想了解什么 | 入口 |
| --- | --- |
| 产品旅程和用户价值 | [`PRODUCT.md`](PRODUCT.md) |
| 系统如何保持世界权威和因果 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| 页面、文案、隐私和响应式合同 | [`docs/FRONTEND.md`](docs/FRONTEND.md) |
| 启动、隔离、Hermes 和清理 | [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| 当前验收、证据层和限制 | [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md) |
| 史料与 Perspective 边界 | [`docs/HISTORY.md`](docs/HISTORY.md) |
| 当前/归档文档总览 | [`docs/README.md`](docs/README.md) |

历史实施、迁移和阶段性验收统一在 [`docs/archive/README.md`](docs/archive/README.md) 中，不作为当前产品入口。

## License

见 [`LICENSE`](LICENSE)。
