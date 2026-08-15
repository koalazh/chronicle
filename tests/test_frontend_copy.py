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
        "Live World",
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "甲申",
        "世界",
        "当前人物",
        "过去",
        "现实 · 第",
        "开始这一卷",
        "继续这一卷",
        "山海关一线正在向前",
        "三段人生共享同一条现实走廊",
        "我现在知道",
        "哪些过去仍影响我",
        "让世界继续",
        "走近",
        "接过这一次判断",
        "这次判断",
        "交还给世界",
        'data-action="inhabit"',
        'data-action="leave-life"',
        "/api/worldlines",
        "/api/worldlines/active",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/world",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/desk",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/decision",
        "/api/worldlines/${encodeURIComponent(state.active.id)}/decision/retry",
        "AbortController",
        "aria-live",
    ):
        assert required in source or required in index
    assert "接过这段人生" not in source


def test_frontend_keeps_the_judgment_entry_direct_without_background_assist():
    source = _frontend_source()

    assert "这次判断" in source
    assert "参考草稿" not in source
    assert "/assist/draft" not in source
    assert "void requestDraft();" not in source


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
        "agent_retry",
        "agent_failed",
        "这一刻还没有完成回应",
        "这一处回应没有形成判断",
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
    assert ".notice-stack { position: fixed" not in styles


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
        "consequenceMarkup",
        "consequenceSource",
    ):
        assert required in source
    assert "这一项暂未留下文字说明" not in source
    assert "一项已知事实。" in source


def test_frontend_makes_replay_relationship_and_consequence_sources_explicit():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    for required in (
        "先选一段人生",
        "replay-workspace",
        "当前选择",
        "判断回看",
        "replay-selection",
        "selectedLife.later_known?.length",
        "consequence-heading",
        "consequence-source",
        "consequence-body",
        "trace-heading",
        "trace-source",
        "traceBody",
        "source === kind",
        "detail.final_reality?.length",
    ):
        assert required in source
    assert 'class="judgment-history-section"' not in source
    assert "由${text(item.actor.display_name)}留下" not in source
    assert "traceItemMarkup" in source


def test_frontend_keeps_long_actions_at_top_and_reconciles_without_extra_click():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    api_source = (ROOT / "web" / "api.js").read_text(encoding="utf-8")
    cancel_block = source.split("function cancelActivity", 1)[1].split(
        "async function reconcileActivity", 1
    )[0]

    assert 'window.scrollTo({ top: 0, behavior: "auto" })' in source
    assert "activity.controller = null" in cancel_block
    assert "void reconcileActivity();" in cancel_block
    assert "正在自动核对当前卷册" in source
    assert "cannot change controller while a Lifetime wake is running" in api_source


def test_frontend_preserves_drafts_during_reconciliation_and_hides_empty_desk_surfaces():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    load_desk = source.split("async function loadDesk", 1)[1].split(
        "async function loadArchive", 1
    )[0]
    submit_decision = source.split("async function submitDecision", 1)[1].split(
        "async function retryDecision", 1
    )[0]

    assert "state.decisionValue = null" not in load_desk
    assert "state.decisionValue = null" in submit_decision
    assert "desk.known?.length ?" in source
    assert "desk.current_course?.length ?" in source
    assert "desk.waiting_for?.length ?" in source


def test_frontend_loads_archive_after_sealed_continue_without_hashchange_race():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    sealed_branch = source.split('if (result.worldline?.status === "SEALED")', 1)[1].split(
        "if (result.pending_moment", 1
    )[0]

    assert 'state.page = "archive"' in sealed_branch
    assert "await loadArchive();" in sealed_branch
    assert "desk.experiences?.length ?" in source


def test_frontend_world_and_reconsideration_copy_are_state_bounded():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert "world.open_questions || []" in source
    assert "world.present_reality || []" in source
    assert "worldSections ||" in source
    assert "眼前没有新的事情需要你介入。" in source
    assert "reconsideration.voluntary && hasCourse" in source
    assert "AWAITING_CONFIRMATION" in source
    assert "继续确认这次判断" in source
    assert "AGENT_FAILED" in source
    assert "重新检查当前卷册" in source
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
