from pathlib import Path

ROOT = Path(__file__).parents[1]
FORMAL_FILES = (
    ROOT / "web" / "app.js",
    ROOT / "web" / "api.js",
    ROOT / "web" / "state.js",
    ROOT / "web" / "router.js",
    ROOT / "web" / "components" / "html.js",
)


def _frontend_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in FORMAL_FILES)


def test_frontend_uses_the_v6_product_language_and_ia():
    source = _frontend_source()
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for forbidden in (
        "旁观这场危局",
        "Watch",
        "Takeover",
        "start-takeover",
        "Agent",
        "Runtime",
        "AI resumed",
        "crisisCoverPage",
        "data-human-actor-id",
        "/api/runs",
        "Crisis Engine",
        "Public Replay",
        "Lifetime Replay",
        "Agent is thinking",
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "甲申",
        "世界",
        "当前人物",
        "过去",
        "开始这一卷",
        "继续这一卷",
        "现在什么还没有定下来？",
        "让世界继续",
        "走近",
        "接过这一次判断",
        "参考草稿",
        "交还给世界",
        'data-action="inhabit"',
        'data-action="leave-life"',
        "/api/worldlines",
        "/api/worldlines/active",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/world",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/desk",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/decision",
        "AbortController",
        "aria-live",
    ):
        assert required in source or required in index
    assert "接过这段人生" not in source


def test_frontend_keeps_a_small_mutation_lock_and_boot_error_state():
    source = _frontend_source()

    for required in (
        "busy: false",
        "if (state.busy) return",
        "state.busy = true",
        "state.busy = false",
        'api("/api/config"',
        'api("/api/volume"',
        'api("/api/worldlines/active"',
        "卷册暂时打不开",
        'data-action="retry-boot"',
    ):
        assert required in source


def test_frontend_makes_long_operations_visible_and_recoverable():
    source = _frontend_source()
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

    for required in (
        "activity-banner",
        "aria-busy=\"true\"",
        "停止等待并核对",
        "核对当前卷册",
        "cancelActivity",
        "reconcileActivity",
        "state.activity.controller",
        "lastContinueStatus",
        "world.continuation?.status",
        "no_future_trigger",
        "世界暂时停在这里",
        "走近一段人生",
        "主动定一个方向",
        "focus-people",
    ):
        assert required in source
    assert ".activity-banner" in styles
    assert "ink-breathe" in styles


def test_frontend_notices_do_not_block_life_actions():
    styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

    assert ".notice-stack" in styles
    assert "pointer-events: none" in styles


def test_frontend_captures_the_human_judgment_before_busy_rerender():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    submit_handler = source.split('root.addEventListener("submit"', 1)[1]
    decision_mutation = source.split("async function submitDecision", 1)[1].split(
        "async function openArchive", 1
    )[0]

    assert 'const value = event.target.querySelector("#decision")?.value.trim() || "";' in (
        submit_handler
    )
    assert 'const action = event.submitter?.dataset.judgmentAction || "CHANGE";' in submit_handler
    assert 'run(() => submitDecision(action, value), { kind: "decision" });' in submit_handler
    assert 'document.querySelector("#decision")' not in decision_mutation


def test_frontend_does_not_expose_internal_backend_errors():
    source = (ROOT / "web" / "api.js").read_text(encoding="utf-8")

    for required in (
        "userFacingErrorMessage",
        "there are no due Subject Wakes to freeze",
        "当前这一刻没有需要你处理的下一步。",
        "当前这一刻还没有可以落笔的下一步。",
        "请求没有完成，请稍后再试。",
    ):
        assert required in source


def test_frontend_does_not_render_internal_ids_as_product_copy():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for forbidden in (
        "item.message_id",
        "item.observation_id",
        "item.event_id",
        "row.volume_id || row.id",
        "entity.state ||",
        "VOLUME ENDING",
    ):
        assert forbidden not in source
    for required in (
        "item.observation",
        "archiveKindText",
        "archiveStatusText",
        "这一卷最后成了什么？",
        "judgmentHistoryMarkup",
        "判断回看",
        "consequenceMarkup",
        "item.actor?.display_name",
    ):
        assert required in source


def test_frontend_world_and_reconsideration_copy_are_state_bounded():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "world.open_questions || []" in source
    assert "world.present_reality || []" in source
    assert "worldSections ||" in source
    assert "眼前没有新的事情需要你介入。" in source
    assert "reconsideration.voluntary && hasCourse" in source
    assert "voluntaryReconsideration ? \"你主动重新考虑了这份判断。\"" in source
    assert "current_course" in source


def test_frontend_routes_only_formal_v6_pages():
    router = (ROOT / "web" / "router.js").read_text(encoding="utf-8")

    for required in ("volume", "world", "follow", "desk", "archive", "goFollow"):
        assert required in router
    for forbidden in ("ending", "crisis", "watch", "takeover", "compare", "settlement"):
        assert forbidden not in router.lower()


def test_frontend_does_not_expose_a_seal_action_or_bypass_runtime_eligibility():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "/seal" not in source
    assert "const canEnter = person.available || person.inhabited;" in source
    assert '${canEnter ? "" : "disabled"}' in source
