# 运维与验证

## V2 数据迁移

V2 初始化会按 schema version 做 additive migration。旧数据库会先生成
带时间戳的 SQLite backup，再创建 worldlines、worldline_events、
worldline_snapshots 和 worldline_lifetimes。旧 Branch 表不删除；已有记录导入
为 SEALED legacy Worldline，并保留 LEGACY_IMPORT 事件作为审计入口。

不要删除数据库或 Hermes Home 来“重置”迁移。需要隔离实验时，使用新的显式
CHRONICLE_DATABASE_URL 或 CHRONICLE_HERMES_HOME。

## V2 旅程检查

fixture 验证应覆盖 Observe → Enter → Live → Debrief：进入后刷新仍恢复同一
active Worldline；Archivist 读取在 423 Locked；自然语言输入返回明确的
interaction status；高影响动作需要确认；advance 处理 Canon、观察 delivery 和 message delivery，并按 wake policy 决定是否唤醒人物模型；
输入的 context、原文和结果事件在同一 SQLite moment 中提交；失败不能留下半条输入或
虚假的 current tick。seal 后 debrief 不含 score 或 LLM 事后总结。

V2 API 的完整清单和证据边界见 V2_MIGRATION.md。浏览器截图只能证明当前本地
fixture/API 状态；不能代替 Hermes provider、真实业务 wake 或外部服务证据。

## 日常检查

```bash
uv sync
uv run chronicle source validate
uv run chronicle scenario validate
uv run ruff check chronicle
uv run pytest -q
uv run chronicle doctor
```

`doctor` 的 `NOT_READY` 是有意义的结果：它表示 provider、project-local Hermes profile 或 gateway 仍未完成，而不是把缺少外部依赖伪装成成功。

## Setup 与 Bootstrap

1. 启动服务并打开 `/`。
2. 在 Setup 填写 OpenAI-compatible base URL、API Key、model 和 mode。
3. Test connection 只调用 provider 的 `/models` 端点。
4. Configure 将配置写入 server-side runtime env。
5. 在另一个终端启动项目私有 Gateway：`HERMES_HOME="$PWD/.chronicle/hermes-home" hermes gateway run --external-supervisor`。
6. 使用 CLI 或后续 UI Bootstrap 创建 project-local profiles；只有 Gateway 已监听且现场能力检查通过时，Bootstrap 才会返回 `ready=true`。

服务启动只接受 loopback host（`127.0.0.1`、`::1`、`localhost`）。不要通过
`--host 0.0.0.0` 或 `CHRONICLE_HOST` 将当前无登录层的 UI/API 暴露到网络；这类配置会在
应用创建或 CLI 启动前失败。Setup 的 Provider URL 必须是 `http`/`https`，不能带用户凭据，
并且不能解析到私网、link-local、metadata、保留或组播地址；远程 Provider 使用 HTTPS。
连接测试只向经过校验的 Provider `/models` 发送一次带凭据的请求，并要求返回的模型列表
包含用户选择的模型。

Bootstrap 不会覆盖带有 Chronicle genesis marker 的 Home；V1 不实现原地 reset，`--force-reset` 会明确返回未实现错误。需要全新实验时，应显式指定一个新的项目私有 `CHRONICLE_HERMES_HOME`，不要删除现有 Home 或数据库。

## 证据记录

将确定性测试、浏览器截图、Hermes probe、真实 wake 和 LLM response 分开保存。截图只说明对应 fixture/API 状态下的 UI；不能替代 live provider 或持久化验证。

## Live acceptance smoke

Live Hermes 是 V2 的运行门槛，不以 doctor 单独通过作为完整业务证据。使用项目私有
Hermes Home 启动 Gateway：

~~~bash
HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes gateway run --external-supervisor --accept-hooks
~~~

另一个终端确认：

~~~bash
uv run chronicle doctor
~~~

必须同时看到 READY、shared listener reachable、profile routes reachable、
memory only 和 valid/cross-profile key isolation。随后在隔离的临时 SQLite 数据库
上执行 Observe → Enter → Live → Debrief：

1. POST /api/canon/advance 到 Entry tick；
2. POST /api/worldlines，live=true；
3. POST /api/worldlines/{id}/input；
4. POST /api/worldlines/{id}/advance，live=true；
5. 核对 agent_wakes 中 source=hermes、Fresh Session ID 和结构化 ActorWakeResponse；
6. 核对 Worldline Ledger 中的 MESSAGE_DELIVERED、AGENT_WAKE 和 lazy branch Profile；
7. POST /api/worldlines/{id}/seal，再 GET /api/worldlines/{id}/debrief。

只有真实业务 Wake、Session、Ledger 和 Debrief 都存在时，才可以声称 live 链路已打通。
临时数据库与临时 HTTP 服务不能替代正式用户数据；不要把响应正文、API Key 或运行时
Home 提交到仓库。

## 数据安全

不要提交 `.env`、`.chronicle/`、SQLite 数据库或 runtime screenshot。不要在日志、错误页面、测试快照或 issue 中粘贴 API Key。更换 provider 时，新的 runtime epoch 会隔离后续 Lifetime 解释。
