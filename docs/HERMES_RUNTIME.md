# Hermes Runtime：原生边界与现场证据

Chronicle 使用本机 Hermes Agent CLI 创建三个同源 profile：

- `chronicle-seat-a`
- `chronicle-seat-b`
- `chronicle-seat-c`

它们来自同一个 `hermes/chronicle-actor` Actor Distribution，差异由 Host 传入的 Seat authority、opaque input 和独立 session 体现。

## Project-local Home

Bootstrap 使用 `CHRONICLE_HERMES_HOME`，默认是项目内 `.chronicle/hermes-home`，不会修改用户的全局 Hermes Home。runtime secret 写入 `.chronicle/runtime.env`，权限为 `0600`，并被 `.gitignore` 忽略。

## 每次 Wake

1. Host 根据当前 tick 计算已送达 observation 和当前 belief。
2. Host 创建新的 Hermes session，并发送结构化 wake input。
3. Hermes 通过原生 `/api/sessions` 和 `/v1/chat/completions` 或 `/v1/responses` 边界处理请求。
4. Host 解析 `ActorWakeResponse`，校验 memory action 和 authority。
5. Actor 只在 Reflection 中调用 Hermes 内置 `memory` tool；Host 比较 profile `memories/MEMORY.md` 的前后 hash。
6. Host 写入 Life Record；SQLite 的 `memory_versions` 是审计镜像和 lineage 索引，不是 live Hermes memory 的替代品。

普通 wake 和 Reflection 使用不同的 wake type，但均不共享聊天 transcript。Hermes session ID、runtime epoch、source、native memory hash 和协议状态会进入审计记录。Fixture mode 为没有 Hermes gateway 的自动化测试提供确定性替身，不会被当作 live Hermes 证据。

## 能力分级

### 确定性证明

- profile distribution 文件存在且可校验；
- Host 使用 Fresh Session API 的代码路径存在；
- fixture wake、协议解析、memory gate 和 append-only 约束通过测试；
- Hermes CLI 版本可读取。

### 现场 Hermes 证明

只有在本机 project-local Hermes Gateway 启动、provider key 有效、三个 profile 安装成功，并用 Python HTTP probe 得到健康响应后，才能声称 live Hermes 已接通。健康或 `/v1/models` 只证明 gateway/provider 边界，不等于已经完成一次真实业务 wake；业务 wake 还要保存对应的 session、response 和 Life Record。

Chronicle 的 `doctor` 还会逐个检查三个 Profile 的路由、有效 key 与交叉 key 隔离，以及 `/v1/toolsets` 的实际启用项。只有实际启用项严格为 `memory` 时，toolset restriction 才会通过；Actor Distribution 配置文本本身不能替代现场探针。

`bootstrap` 负责创建或同步 project-local Profiles，并返回独立的 `ready` 与 `readiness` 字段。Profile 文件生成不等于 Gateway 已就绪；若现场探针失败，CLI 以非零状态退出，API 保留可读的未就绪结果，前端不得显示“人物已准备好”。

live Wake 的 Hermes Session、路由、toolset 或模型调用失败会在 live 边界抛出安全错误，不再静默回退到 fixture。fixture 只能在显式的非 live 请求中使用。

当前实现不把这些现场结果硬编码为测试通过，也不打印 API Key。
