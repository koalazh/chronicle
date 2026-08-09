# Hermes Runtime：原生边界与现场证据

## V2 lazy branch lifetime

V2 不在用户进入 Entry 时预先创建所有 Agent Profile。只有分支专属观察真正
抵达某个 Agent Seat 时，runtime 才按 worldline_id 和 seat 创建动态、稳定命名
的 branch Profile，并以 Entry 进入时保存的 memory snapshot 初始化其记忆。

每次 branch wake 都使用 fresh session，不复用 Canon 或旧 Worldline 的 transcript。
live Hermes 创建 Profile、写入 snapshot 或执行 wake 任一步失败都会停在 live
边界并返回可读错误；fixture 只在显式 fixture 模式中生效，不作为 live fallback。

若 branch Profile 已创建但后续 readiness、Fresh Session、模型响应或 SQLite moment
提交失败，Host 会按 worldline_id 和 seat 校验 genesis marker，并清理这次尚未写入
Worldline Lifetime 的精确 Profile；清理失败会以 live 错误显式暴露。普通 Live Wake
在模型调用失败后也会检查并回滚 native Memory，避免 Hermes 外部状态先于 Ledger 成功。

V2 仍把 Hermes 现场证据拆成三层：gateway/provider probe、Profile/lifetime
创建、真实业务 wake。前一层成功不能替代后一层。

Chronicle 到 project-local Hermes Gateway 的 HTTP 请求会显式禁用进程级代理环境，
避免 `HTTP_PROXY`/`ALL_PROXY` 把 `127.0.0.1:8642` 的 readiness 请求转发到外部代理；
Provider 的用户连接测试仍按其自身 URL 策略执行。

Chronicle 使用本机 Hermes Agent CLI 创建三个同源 profile：

- `chronicle-seat-a`
- `chronicle-seat-b`
- `chronicle-seat-c`

它们来自同一个 `hermes/chronicle-actor` Actor Distribution，差异由 Host 传入的 Seat authority、opaque input 和独立 session 体现。

Actor Distribution 对 API server 明确只开放 `memory`。当前 Hermes 会把近期新增的 builtin toolset 默认补回平台列表，因此项目配置同时记录 `bfl` 为已拒绝项；最终是否成立仍以现场 `/v1/toolsets` 探针为准。

## Project-local Home

Bootstrap 使用 `CHRONICLE_HERMES_HOME`，默认是项目内 `.chronicle/hermes-home`，不会修改用户的全局 Hermes Home。runtime secret 写入 `.chronicle/runtime.env`，权限为 `0600`，并被 `.gitignore` 忽略。

## 每次 Wake

1. Host 根据当前 tick 计算已送达 observation 和当前 belief。
2. Host 创建新的 Hermes session，并发送结构化 wake input。
3. Hermes 通过原生 `/api/sessions` 和 `/v1/chat/completions` 或 `/v1/responses` 边界处理请求。
4. Host 解析 `ActorWakeResponse`，校验 memory action 和 authority。
5. Actor 只在 Reflection 中调用 Hermes 内置 `memory` tool；Host 比较 profile `memories/MEMORY.md` 的前后 hash。
6. Host 写入 Life Record；SQLite 的 `memory_versions` 是审计镜像和 lineage 索引，不是 live Hermes memory 的替代品。

每次 session 的 ID 与标题都包含唯一 ID，避免重复 wake 在 Hermes 的标题去重规则下被错误拒绝。

普通 Wake 如果改变了 native Memory，Host 会保存前后快照和 unified diff，恢复原文件，并在 append-only `protocol_violations` 中记录原因、hash、diff 和 rollback 结果。Reflection 才能创建 `memory_versions`；其 previous hash、内容 hash 和 source Life Record 会在写入时校验。

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
