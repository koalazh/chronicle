# 运维与验收操作手册

> 读者：开发者与运维人员。本文包含隔离目录、环境变量、端口、数据库和真实模型运行术语；普通用户只需阅读 [README](../README.md)。

这是当前产品的本地 runbook。它把“服务能启动”“代码合同通过”“Hermes 环境可用”“真实业务成立”和“浏览器体验合格”分开记录。任何一层都不能替代另一层。

## 1. 安全边界

- 只绑定 `127.0.0.1`、`localhost` 或其他明确的 loopback 地址；当前没有登录层，不得暴露到局域网或公网；
- Provider URL 不嵌入凭据，不指向私网、link-local、metadata、reserved 或 multicast 地址；
- API key 只写入被忽略且权限为 `0600` 的 runtime env/Profile env；日志和文档不记录 key、token、完整模型正文或 private response；
- 真实业务验证使用独立 SQLite、Hermes Home、loopback 端口和临时目录，不覆盖项目 `data/`、`.chronicle/`、全局 Hermes Home 或其他服务；
- 不用 SQL 直接制造 `SEALED`、`READY` 或 successful outcome；不以删除目录“修复”未知归属；
- Profile/MCP/Gateway 清理只能在 Volume 已原子 seal 且 marker/owner 可证明属于该 Worldline 时执行。

## 2. 确定性检查

每次源码、内容或前端变更后先运行：

```bash
uv sync
uv run chronicle volume validate
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts

set -o noglob
for file in $(find web -type f -name '*.js'); do
  node --check "$file" || exit 1
done

git diff --check
```

需要做脱敏检查时，运行仓库既有的 Secret scan，并确认没有 key、token、完整 response 或 private prompt 命中；依赖的 deprecation warning 原样保留，不把 warning 写成“已消除”。

## 3. 本地服务与 fixture

CLI 入口：

```bash
uv run chronicle --help
uv run chronicle serve --host 127.0.0.1 --port 8711
uv run chronicle start --host 127.0.0.1 --port 8711
uv run chronicle doctor
```

`serve` 适合开发；`start` 会在启动时对活动或待清理的真实 Volume 执行 Profile、binding、token、MCP 和 Pending Logical Moment reconcile；失败会 fail closed，不接管未知资源。二者都只绑定 loopback。

开发 fixture 必须使用临时状态：

```bash
CHRONICLE_TMP="$(mktemp -d -t chronicle-dev.XXXXXX)"
CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$CHRONICLE_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$CHRONICLE_TMP/hermes-home" \
uv run chronicle serve --host 127.0.0.1 --port 18711
```

fixture 只能替代模型输出；它仍必须走 Host、Global Tick、message delivery、Perspective、Pending Logical Moment、permission、idempotency、Ledger 和 Archive 代码。关闭服务后只清理由当前命令创建的临时目录。

## 4. 真实 Hermes 前置条件

真实路径需要：

1. 独立 SQLite 数据库和独立 Hermes Home；
2. loopback Gateway 与本卷册专属 Profile/binding；
3. 下面两种认证方式之一，以及明确的模型名；
4. `chronicle doctor` 返回 `READY`，并通过 Profile 路由、key isolation、toolset 和 fresh Session 检查。

配置文件的职责不同，不能用一个文件代替另一个：

- 根目录 `.env` 是 Chronicle 的基础配置来源；
- `.chronicle/runtime.env` 是 Chronicle Web 配置保存的运行配置，并覆盖基础配置；
- `.chronicle/hermes-home/.env` 是 Hermes Gateway/Profile/MCP 的运行环境；
- OAuth token 由 Hermes 存在同一个 Hermes Home 的 credential store 中，不能通过写入 `.env` 生成，也不应把 token 写进仓库文件。

因此，“模型和认证模式已写入 `.env`”只表示 Chronicle 知道要走哪条路径；它不等于 OAuth 已经完成登录。

### 4.1 API key

`.env` 中保持默认模式并填写兼容 OpenAI API 的 Provider：

```dotenv
CHRONICLE_LLM_AUTH_MODE=api_key
CHRONICLE_LLM_BASE_URL=https://your-provider.example/v1
CHRONICLE_LLM_API_KEY=your-api-key
CHRONICLE_LLM_MODEL=your-model
CHRONICLE_LLM_API_MODE=chat_completions
```

### 4.2 Hermes OAuth

OAuth 模式不把模型 API key 写入 Profile env。先在与 Chronicle 相同的 Hermes Home 中完成一次 Hermes 的 Codex 登录：

```bash
HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes auth add openai-codex --type oauth

HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes auth status openai-codex
```

看到 `openai-codex: logged in` 后，不需要在每次启动前重复登录。后续直接运行：

```bash
uv run chronicle start --host 127.0.0.1 --port 8711
```

再在另一个终端检查：

```bash
uv run chronicle doctor
```

`HERMES_HOME=...` 是给 Hermes CLI 指定项目级 credential store；`CHRONICLE_HERMES_HOME` 是 Chronicle 的应用配置名，Hermes CLI 不会自动把它当作 `HERMES_HOME` 读取。

在根目录 `.env` 中设置，或通过 Chronicle Web 配置写入 `.chronicle/runtime.env`：

```dotenv
CHRONICLE_LLM_AUTH_MODE=oauth
CHRONICLE_LLM_MODEL=gpt-5.6-luna
CHRONICLE_LLM_API_MODE=responses
CHRONICLE_LLM_REASONING_EFFORT=max
```

Chronicle 会把每个 Lifetime Profile 配置为 Hermes 内置的 `openai-codex` provider 和 `codex_responses`，OAuth 状态由该 Hermes Home 管理；`CHRONICLE_LLM_API_KEY` 和 `CHRONICLE_LLM_BASE_URL` 在此模式下不会作为模型凭据使用。

如果服务可以打开但真实 Profile 调用失败，先看 `doctor`：`llm_config=true, llm_auth=false` 表示运行参数已经配置，但这个项目 Hermes Home 没有有效 OAuth token。ChatGPT/Codex 客户端的登录态不会自动成为 Hermes credential；OAuth 登录只需首次完成一次，除非 token 被注销或失效。

`doctor`、Gateway health、Profile route 或一次 chat 只能证明前置能力。它们不能单独证明 Human↔Hermes continuity、跨主体因果、消息抵达、结算或 Archive。

创建真实 Volume 后，普通 wake 从同一 Lifetime Profile 创建 fresh Session，读取冻结 Perspective，经 Profile 专属 World MCP staging 一个受限意图，再由 Host 完成 atomic moment commit。普通 wake 的 Memory mutation 会 rollback；没有结构化意图不会静默降级成等待。

## 5. Volume 生命周期和恢复

```text
VOLUME ACTIVE
  → Crisis Instance SETTLED/SUPPRESSED（Volume 仍 ACTIVE）
  → structural boundary ready
  → VOLUME_SEALED / ARCHIVED
  → revoke bindings + cancel queued wakes
  → cleanup owned Profiles/MCP entries
```

封存前必须确认没有 pending moment、due wake、在途消息、待应用 Field Event 或 next tick，且所有 Crisis Instance 已有结果。Seal 失败只返回领域冲突，不改变状态；重复请求只重试属于本卷册的清理。

如果清理失败：

1. 保留 sealed Worldline、Ledger、Snapshot 和 Archive；
2. 不把旧 Profile 加入下一卷册；
3. 记录可重试的 owner/cleanup 状态，不猜测未知进程归属；
4. 下一次 recovery 只针对同一 Worldline。

检查任务资源时使用精确目标：

```bash
lsof -nP -iTCP:<port> -sTCP:LISTEN
```

只有确认 owner marker、PID 起始信息和 Worldline 一致后，才允许停止或清理。未知端口和全局 Hermes Home 不在本操作手册的权限范围内。

## 6. 数据边界

当前数据库只接受 schema marker `10`。新库只创建 V6 Volume 所需的表；既有 schema `10` 数据库只做当前 Lifetime 列形状的窄补齐，不恢复 V1–V5 迁移链、旧 Branch/Run 读取或旧 API。旧 schema 和没有 schema marker 的非空数据库会在任何建表写入前拒绝打开。

需要处理旧数据时，先复制到隔离目录并确认它是当前 V6 schema `10`，再运行 doctor；不直接修改真实数据库的 `status`、`runtime_phase`、`outcome_json` 或 binding 来制造验收结果。

副本检查：

```bash
CHRONICLE_DATABASE_URL=sqlite:////absolute/copy.db \
CHRONICLE_HERMES_HOME=/absolute/temp/hermes-home \
uv run chronicle doctor
```

V1–V5 的迁移边界、旧数据和验收记录只作为历史归档阅读；当前产品的运行入口不依赖旧 API、旧 replay 或旧迁移脚本。

## 7. 浏览器检查

浏览器验收至少覆盖 1440、1280、768 和 390 宽度：

- Volume、World、Follow、Inhabit、Desk、Leave、Archive、Ending 都能到达；
- 无横向溢出，World/Follow/Desk/Archive 在手机可读；
- Follow 和 public replay 不泄漏 private state；
- textarea 在 rerender 前被捕获，busy mutation 不能 double-submit；
- 页面不出现 Agent/Profile/Session/Memory、crisis dashboard、meter 或 AI thinking animation。

最近一次隔离浏览器流程已覆盖页面旅程、Archive、选定 Wu 的判断回看、四种 viewport、no-overflow、内部术语扫描和空 error/warn logs。浏览器工件与真实业务链分层保存，当前结论见 [当前验收](ACCEPTANCE.md)。

## 8. 证据记录

每次验收只保留可复核且不含 Secret 的信息：commit、命令、退出码、validator 摘要、临时资源范围、Profile/Session 数量、事件类型、tick、状态和失败边界。不要保存 API key、Profile token、完整模型 response、private prompt 或原始 `runtime.env`。

最近一次真实 Volume 在独立产品端 `18786`、Gateway `18886` 上完成封存后检查：状态为 `SEALED/ARCHIVED`，六条 binding 为 `REVOKED`，Profile 目录为空，owner 文件不存在，任务端口释放；可恢复的临时目录移入用户 Trash，未写入仓库。未知 Gateway `18851` 未被触碰。

更完整的矩阵、计数和已知限制见 [当前验收](ACCEPTANCE.md)；阶段性原始记录见 [历史归档](archive/README.md)。
