# Chronicle: 甲申

> **在不知道结局的情况下，重新活过历史。**

Chronicle 是一个数字历史观测台：在崇祯十七年最后一个春天的有限时间窗里，三个长期主体只能接收 Host 送达的有限信息，形成自己的判断，留下有限的主观记忆。历史事实由史料策展与确定性 Host 约束；Agent 不能直接改写世界。

```text
Truth ≠ Knowledge ≠ Belief
```

## Quick start

```bash
uv sync
cp .env.example .env
uv run chronicle source validate
uv run chronicle scenario validate
uv run chronicle serve
```

第一次打开 `http://127.0.0.1:8711` 时，在 Chronicle Setup 输入 OpenAI-compatible Base URL、API Key 和 Model。Secret 只写入被 `.gitignore` 保护的 `.chronicle/runtime.env`，不进入浏览器存储或 API response。

配置成功后运行：

```bash
uv run chronicle bootstrap
uv run chronicle doctor
```

`bootstrap` 使用 Hermes 原生 Profile Distribution 创建 `chronicle-seat-a`、`chronicle-seat-b`、`chronicle-seat-c`，并在项目私有 `CHRONICLE_HERMES_HOME` 下配置共享 multiplexed gateway。若当前 Hermes 不支持某项能力，`doctor` 会显示缺口；Chronicle 不会用自建 Runtime 冒充 Hermes。

## What this is

Chronicle 不是历史聊天机器人、明末策略游戏、预测器或通用多 Agent 框架。V1 只有一个策展场景：正月初一至三月十九，以及唯一的真实反事实节点“太子抚军江南”。Canon 中 Agent 只能理解、相信、意图和记忆；Branch 中每个意图也必须经过确定性 Host 的权限与状态验证。

详细说明见：

- [`PRODUCT.md`](PRODUCT.md)
- [`HISTORICAL_METHOD.md`](docs/HISTORICAL_METHOD.md)
- [`HISTORICAL_BLINDNESS.md`](docs/HISTORICAL_BLINDNESS.md)
- [`WORLD_MODEL.md`](docs/WORLD_MODEL.md)
- [`COUNTERFACTUAL_METHOD.md`](docs/COUNTERFACTUAL_METHOD.md)
- [`HERMES_RUNTIME.md`](docs/HERMES_RUNTIME.md)
- [`DESIGN.md`](docs/DESIGN.md)
- [`OPERATIONS.md`](docs/OPERATIONS.md)
