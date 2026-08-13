# Chronicle · 甲申

Chronicle 是一段可以亲自走进去的历史体验：先看共享世界，再接过其中一段人生的下一步。你写下的判断不会直接改写世界；Host 会验证行动，世界按自己的时间继续推进。

当前内容是《甲申》：一卷共享历史、六段相互影响的人生，以及几处正在展开的局势。

## 先选择运行方式

| 方式 | 需要模型凭据 | 需要配置 `.env` | 适合什么 |
| --- | --- | --- | --- |
| 本机演示模式 | 不需要 | 不需要 | 体验页面、Host 和 fixture 流程 |
| 真实模型：Hermes OAuth | 需要首次登录一次 | 新环境需要；已有 `runtime.env` 时不需要重复写 | 使用 `openai-codex` / Codex OAuth |
| 真实模型：OpenAI-compatible API | 需要 API key | 需要，或写入 `runtime.env` | 使用任意兼容 OpenAI API 的 Provider |

这里的“需要配置 `.env`”不是绝对要求：如果本地已经有 `.chronicle/runtime.env`，Chronicle 会优先读取它。新 checkout 通常没有这个被忽略的运行文件，需要自己从 `.env.example` 配置一份。

## A. 本机演示模式：不需要 `.env` 和模型

这条路径使用临时 SQLite 和临时 Hermes Home，不会污染项目默认运行状态，也不调用真实模型。

要求：

- Python 3.11 或更新版本
- [uv](https://docs.astral.sh/uv/)

在项目根目录执行：

```bash
uv sync

CHRONICLE_TMP="$(mktemp -d -t chronicle-dev.XXXXXX)"
CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$CHRONICLE_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$CHRONICLE_TMP/hermes-home" \
uv run chronicle start --host 127.0.0.1 --port 8711
```

然后打开 <http://127.0.0.1:8711/>。可以在另一个终端确认服务已启动：

```bash
curl -fsS http://127.0.0.1:8711/health
```

预期返回：

```json
{"status":"ok","service":"chronicle-host"}
```

体验路径大致是：

```text
卷册首页 → 世界 → 观察一段人生 → Inhabit → 写下 Course → 离席 → Continue → 回看
```

结束时回到服务终端按 `Ctrl-C`。确认 `CHRONICLE_TMP` 是本次命令创建的临时目录后，再清理它：

```bash
rm -rf "$CHRONICLE_TMP"
```

不要用这个命令清理项目目录、`.chronicle`、全局 Hermes Home 或其他服务的数据。

## B. 真实模型模式：先配置，再启动

真实模型模式需要同时满足两件事：

1. Chronicle 知道使用哪种认证、哪个模型以及对应的 API 协议；
2. 该认证方式确实有可用凭据。

### 配置文件到底怎么生效

| 文件或来源 | 是否自动读取 | 作用 |
| --- | --- | --- |
| `.env.example` | 否 | 配置模板；复制或参考它，不会自动生效 |
| 根目录 `.env` | 是，可选 | Chronicle 的基础配置 |
| `.chronicle/runtime.env` | 是，可选 | Chronicle 的运行配置；存在时覆盖 `.env` 中同名变量 |
| `.chronicle/hermes-home/.env` | 是，由 Hermes 读取 | Gateway、Profile、MCP 的运行环境；不是 Chronicle 的模型选择文件 |
| Hermes Home credential store | 是，由 Hermes 读取 | 保存 OAuth 登录后的 token；不要手写或提交到仓库 |

因此：

- 只跑上面的本机演示模式：不用配置 `.env`；
- 新环境跑真实模型：如果没有 `.chronicle/runtime.env`，复制 `.env.example` 为 `.env`，并选择下面一种模式；
- 本地已经有 `.chronicle/runtime.env`：不需要再创建根目录 `.env` 来重复配置，先检查它是否已经包含所选模式需要的变量。

`.env.example` 只是模板。可以这样创建基础配置文件：

```bash
cp .env.example .env
```

如果 `.env` 已经存在，不要覆盖它；直接编辑现有文件即可。没有任何 LLM 配置时，Chronicle 默认按 `api_key` 模式读取，但因为缺少 URL、key 或模型，真实模型运行不会就绪，也不会自动切换到 OAuth。

不需要把 `.env.example` 的每一行都改一遍：

- OAuth 只填写认证模式、模型和需要的推理强度；不要填 API key；
- OpenAI-compatible API 填写认证模式、Provider URL、API key 和模型；
- `CHRONICLE_HERMES_HOME`、数据库、主机和端口都有本地默认值，只有需要自定义或隔离时才修改；
- 如果修改了 `CHRONICLE_HERMES_HOME`，执行 OAuth 登录时的 `HERMES_HOME` 必须指向同一个目录。

### 方式一：Hermes OAuth

选择 OAuth 时，`.env` 或 `.chronicle/runtime.env` 至少需要：

```dotenv
CHRONICLE_LLM_AUTH_MODE=oauth
CHRONICLE_LLM_MODEL=gpt-5.6-luna
CHRONICLE_LLM_API_MODE=responses
CHRONICLE_LLM_REASONING_EFFORT=max
```

OAuth 模式下：

- Chronicle 使用 Hermes 内置的 `openai-codex` Provider；
- 不需要填写 `CHRONICLE_LLM_API_KEY`；
- `CHRONICLE_LLM_BASE_URL` 不作为用户自定义 Provider 地址使用；
- 还需要在项目 Hermes Home 中完成一次浏览器登录。

首次登录：

```bash
HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes auth add openai-codex --type oauth

HERMES_HOME="$PWD/.chronicle/hermes-home" \
  hermes auth status openai-codex
```

看到 `openai-codex: logged in` 后，之后不需要重复执行 `hermes auth add`。ChatGPT/Codex 客户端的登录态不会自动成为 Hermes credential。

### 方式二：OpenAI-compatible API

选择兼容 OpenAI API 的 Provider 时，`.env` 或 `.chronicle/runtime.env` 至少需要：

```dotenv
CHRONICLE_LLM_AUTH_MODE=api_key
CHRONICLE_LLM_BASE_URL=https://your-provider.example/v1
CHRONICLE_LLM_API_KEY=your-api-key
CHRONICLE_LLM_MODEL=your-model
CHRONICLE_LLM_API_MODE=chat_completions
```

这种模式下：

- `CHRONICLE_LLM_BASE_URL` 是 Provider 的 OpenAI-compatible 地址；
- `CHRONICLE_LLM_API_KEY` 是该 Provider 的 key，不是 ChatGPT/Codex 登录态；
- `CHRONICLE_LLM_API_MODE` 通常使用 `chat_completions`；只有 Provider 支持时才改为 `responses`；
- 不需要执行 `hermes auth add`；
- API key 只应保存在被忽略且权限为 `0600` 的本地配置中，不要提交到 Git。

### 启动和确认

配置完成后，启动正式产品模式：

```bash
uv run chronicle start
```

另开一个终端运行：

```bash
uv run chronicle doctor
```

检查含义：

- `GET /health` 或服务日志：只能说明 Chronicle 进程活着；
- `chronicle doctor`：检查配置、认证、Gateway、Profile 路由、key isolation 和 MCP 前置条件；
- doctor 通过也只是前置条件通过，不等于完整的真实业务链已经验收。

常见结果：

| 检查结果 | 含义 | 下一步 |
| --- | --- | --- |
| `llm_config=false` | 模型配置缺失或不完整 | 按上面二选一的配置块补齐变量 |
| `llm_config=true`, `llm_auth=false` | 配置已读到，但 OAuth 尚未登录或已失效 | 仅 OAuth 模式执行 `hermes auth add` 并检查 `auth status` |
| `llm_config=true`, `llm_auth=true` | 认证前置条件通过 | 继续检查其余 Gateway/Profile/MCP 项 |

## `start` 和 `serve`

| 命令 | 用途 |
| --- | --- |
| `uv run chronicle start` | 日常使用；启动正式产品 App，并恢复活动 Volume |
| `uv run chronicle serve` | 前端开发；配合 `CHRONICLE_DEV=true` 使用自动重载和 fixture |

两者都只允许绑定 loopback 地址。前端开发时使用：

```bash
CHRONICLE_DEV=true uv run chronicle serve --host 127.0.0.1 --port 8711
```

## 常用检查

```bash
uv run chronicle volume validate
uv run chronicle doctor
```

源码或内容变更后的检查：

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts
git diff --check
```

## 文档入口

- [产品说明](PRODUCT.md)：Chronicle 想提供什么体验
- [多主体运行说明](docs/MULTI_AGENT.md)：六段人生如何通过已发生的事实互相影响
- [运维与验收操作手册](docs/OPERATIONS.md)：配置、启动、恢复、真实 Hermes 和安全边界
- [当前验收记录](docs/ACCEPTANCE.md)：测试、浏览器、真实业务和已知限制
- [文档索引](docs/README.md)：按读者角色查找其他文档

## 当前边界

这是一个本机、单人使用的研究型原型，不是联网服务，没有账号、多用户或公开部署。测试、健康检查和一次真实运行只能证明对应路径成立，不能代替不同环境下的长期稳定性或真人体验反馈。

## License

见 [LICENSE](LICENSE)。
