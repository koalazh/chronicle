# Chronicle · 甲申

Chronicle 是一段可以亲自走进去的历史体验：先看共享世界，再接过其中一段人生的下一步。你写下的判断不会直接改写世界；Host 会验证行动，世界按自己的时间继续推进。

默认内容是《甲申》：一卷共享历史、六段相互影响的人生，以及几个正在展开的局势。

## 先启动起来

要求：

- Python 3.11 或更新版本
- [uv](https://docs.astral.sh/uv/)

在项目根目录执行下面整段命令。它使用临时 SQLite 和临时 Hermes Home，不会污染仓库里的默认运行状态，也不需要模型 API Key 就能走本机 fixture 体验。

```bash
uv sync

CHRONICLE_TMP="$(mktemp -d -t chronicle-dev.XXXXXX)"
CHRONICLE_DEV=true \
CHRONICLE_DATABASE_URL="sqlite:///$CHRONICLE_TMP/chronicle.db" \
CHRONICLE_HERMES_HOME="$CHRONICLE_TMP/hermes-home" \
uv run chronicle start --host 127.0.0.1 --port 8711
```

看到服务开始监听后，在浏览器打开：

<http://127.0.0.1:8711/>

也可以在另一个终端确认服务已启动：

```bash
curl -fsS http://127.0.0.1:8711/health
```

预期返回：

```json
{"status":"ok","service":"chronicle-host"}
```

体验顺序是：

```text
卷册首页 → 世界 → 观察一段人生 → Inhabit → 写下 Course → 离席 → Continue → 回看
```

结束时回到运行服务的终端按 `Ctrl-C`。如果确认 `CHRONICLE_TMP` 是本次命令创建的临时目录，再执行：

```bash
rm -rf "$CHRONICLE_TMP"
```

不要用这个命令清理项目目录、`~/.chronicle`、全局 Hermes Home 或其他服务的数据。

## `start` 和 `serve` 的区别

日常打开产品使用 `start`：

```bash
uv run chronicle start --host 127.0.0.1 --port 8711
```

它创建正式的产品 App，并在启动时检查当前 Volume 的恢复边界。

开发前端、需要代码自动重载时才使用 `serve`：

```bash
CHRONICLE_DEV=true uv run chronicle serve --host 127.0.0.1 --port 8711
```

两者都只允许绑定 loopback 地址，不要改成 `0.0.0.0` 对外暴露。端口被占用时，换一个端口，例如 `--port 8712`。

## 常用检查

```bash
uv run chronicle --help
uv run chronicle version
uv run chronicle volume validate
uv run chronicle doctor
```

源码或内容变更后的完整检查：

```bash
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q chronicle tests scripts
git diff --check
```

## 你会看到什么

| 页面 | 作用 |
| --- | --- |
| 卷册首页 | 了解这卷历史从哪里开始 |
| 世界 | 查看公开事实、地点和正在变化的局势 |
| Follow | 先观察某段人生当下知道什么 |
| Inhabit / Life Desk | 接手这一段人生，写下 Course 或选择等待 |
| Leave | 把这段人生交还给世界 |
| Archive / Ending | 历史到达结构边界后，回看公共轨迹或某段人生 |

页面只展示当时已经公开、已经抵达，或该 Lifetime 已经知道的内容。离席以后，世界和其他人仍然继续；一处局势结算，也不代表整卷已经封存。

## 真实 Hermes 运行

上面的启动方式是本机 fixture 体验，不代表真实模型业务链已经配置完成。需要配置 Provider、隔离 SQLite/Hermes Home、Profile/Gateway 和 cleanup 时，阅读 [docs/OPERATIONS.md](docs/OPERATIONS.md)。

## 文档入口

- [产品说明](PRODUCT.md)：Chronicle 想提供什么体验
- [多主体运行说明](docs/MULTI_AGENT.md)：六段人生如何通过已发生的事实互相影响
- [运维与验收操作手册](docs/OPERATIONS.md)：配置、启动、恢复、真实 Hermes 和安全边界
- [当前验收记录](docs/ACCEPTANCE.md)：测试、浏览器、真实业务和已知限制
- [文档索引](docs/README.md)：按读者角色查找其他文档

## 当前边界

这是一个本机、单人使用的研究型原型，不是联网服务，没有账号、多用户或公开部署。测试和一次真实运行只能证明对应路径成立，不能代替不同环境下的长期稳定性或真人体验反馈。

## License

见 [LICENSE](LICENSE)。
