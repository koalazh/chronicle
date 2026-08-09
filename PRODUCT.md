# Chronicle: 甲申

Chronicle 是一个围绕“有限信息如何进入长期存在的主体”的历史观测台。V2 将一次反事实收敛为一条可恢复、可封存的 Worldline，主路径是 Observe → Enter → Live → Debrief。场景仍是甲申年间，从崇祯十七年正月初一到三月十九日的 Canon 时间窗。

## 产品承诺

- Canon 由 Chronicle Host 持有：时间、事件、地点状态、消息送达和 Worldline 边界不由 Agent 决定。
- Knowledge 经过传播：一个事件发生，不代表三个 Seat 同时知道。
- Lifetime 不是聊天记录：Life Record 记录实际经历，Hermes Memory 只记录 Reflection 后被主体携带的有限经验。
- Agent 只能产生判断和受权限约束的意图；Host 校验并应用世界效果。
- 历史未知处停止：V2 的 Worldline 只从一个有来源的 Entry 开始，最多推进十四天；到达边界后封存，不继续补写未知历史。

## 四个产品阶段

1. Observe：按事件浏览 Canon、来源和 Who Knows。
2. Enter：在唯一 Entry “太子抚军江南”进入经历。
3. Live：以 Seat A 的已知信息和自然语言意图推进，不显示分支全局真相。
4. Debrief：封存后分别查看所见、Host 投影、因果变化和停止原因。

## 运行方式

```bash
uv sync
cp .env.example .env
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle doctor
uv run chronicle serve
```

首次打开页面会进入 Setup。Provider 只需满足 OpenAI-compatible Chat Completions 或 Responses 接口；API Key 由服务端写入 `.chronicle/runtime.env`，不会回显到浏览器。

服务部署边界是本机 loopback：Chronicle 不接受通过 `--host` 或 `CHRONICLE_HOST` 直接暴露到局域网/公网。Setup 会先校验 Provider URL，再只向其 `/models` 端点发送连接测试；私网、metadata、嵌入凭据和不支持的模型会被拒绝。

## 证据等级

UI 会将内容分成 `historical`、`modeled`、`branch_derived`。Source Pack 的断言和来源链接可从 Source Inspector 打开。Hermes/LLM 的现场调用、模型版本和网络状态不会被确定性测试冒充。

V1 到 V2 的迁移、API、数据库和证据边界见 [V2 migration](docs/V2_MIGRATION.md)。

更完整的约束见：

- [历史方法](docs/HISTORICAL_METHOD.md)
- [历史盲区](docs/HISTORICAL_BLINDNESS.md)
- [世界模型](docs/WORLD_MODEL.md)
- [反事实方法](docs/COUNTERFACTUAL_METHOD.md)
- [Hermes 运行时](docs/HERMES_RUNTIME.md)
- [运维与验证](docs/OPERATIONS.md)
