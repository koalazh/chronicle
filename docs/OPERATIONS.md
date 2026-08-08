# 运维与验证

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

Bootstrap 不会覆盖带有 Chronicle genesis marker 的 Home；V1 不实现原地 reset，`--force-reset` 会明确返回未实现错误。需要全新实验时，应显式指定一个新的项目私有 `CHRONICLE_HERMES_HOME`，不要删除现有 Home 或数据库。

## 证据记录

将确定性测试、浏览器截图、Hermes probe、真实 wake 和 LLM response 分开保存。截图只说明对应 fixture/API 状态下的 UI；不能替代 live provider 或持久化验证。

## 数据安全

不要提交 `.env`、`.chronicle/`、SQLite 数据库或 runtime screenshot。不要在日志、错误页面、测试快照或 issue 中粘贴 API Key。更换 provider 时，新的 runtime epoch 会隔离后续 Lifetime 解释。
