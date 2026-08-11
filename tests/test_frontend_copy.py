from pathlib import Path

ROOT = Path(__file__).parents[1]


def _frontend_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((ROOT / "web").rglob("*.js"))
    )


def test_frontend_uses_chinese_product_language():
    source = _frontend_source()
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    for forbidden in (
        "DIGITAL HISTORICAL OBSERVATORY",
        "CURRENT EVENT",
        "WHO KNOWS?",
        "Wake this Lifetime",
        "Open Lifetime",
        "The model ends here",
        "No durable memory yet",
        "SCENARIO / ROUTES",
        "SOURCE INSPECTOR",
        "NORMALIZED EVIDENCE",
        "PRIMARY SOURCES",
        "Runtime settings",
        "Test connection",
        "Configure Chronicle",
        "Save runtime",
        "DAY ",
        "Seat A /",
        "chronicle-seat-a",
        "runtime_alias",
        "/api/lifetimes/",
        "受限推演",
        "记录一次观察",
        "/api/branch",
        'cx="58"',
        'd="M13 64',
        "observationCopies",
        "mapObservationMarkers",
        "/api/worldlines/",
        "Agent Dashboard",
        "Worldline Tree",
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "旁观这场危局",
        "世界视野",
        "人物视野",
        "送入这段历史",
        "暂不追加命令，继续",
        "回看这一局",
        "几条人生如何相遇",
        "在你看不见的地方",
        "封存后全景",
        "封存卷册",
        "史实背景",
        "runtime_phase",
        "runtimeFolio",
        "retry-cleanup",
        "runtime_wake_unresolved",
        "/runtime/retry",
        "runtimeTransitionLocked",
        'kind: "runtime", phase: "bootstrapping"',
        "AbortController",
        "surfaceMarkup",
        "/api/runs/active",
        "/api/runs/${state.active.id}/decision",
    ):
        assert required in source

    assert "corridorMarkup" not in source
    assert "成为吴三桂" not in source
    assert "吴三桂的书案" not in source
    assert "volumePage" in source
    assert "crisisCoverPage" in source
    assert "data-human-actor-id" in source


def test_product_start_is_live_only_and_fail_closed_in_the_ui():
    source = _frontend_source()

    assert "crisis_id: state.crisis.summary.id" in source
    assert "payload.human_actor_id = actor.id" in source
    assert "body: JSON.stringify(payload)" in source
    assert "const useLive" not in source
    assert "config?.setup_required" in source
    start_run = source[source.index("async function startRun"):source.index("async function continueRun")]
    assert 'state.config = await api("/api/config")' in start_run
    assert start_run.index('state.config = await api("/api/config")') < start_run.index("loadRunView()")


def test_frontend_surfaces_boot_failure_instead_of_staying_on_placeholder():
    source = _frontend_source()
    render = source[source.index("function render"):source.index("async function refreshActive")]

    assert "卷册暂时打不开" in render
    assert "state.error" in render
    assert 'data-action="retry-boot"' in render

    boot = source[source.index("async function boot"):]
    assert "const bootTimeoutMs = 15_000" in boot
    assert 'api("/api/config", { timeoutMs: bootTimeoutMs })' in boot
    assert 'api("/api/volume", { timeoutMs: bootTimeoutMs })' in boot


def test_frontend_uses_a_scroll_activity_state_and_keeps_decisions_locked():
    source = _frontend_source()

    for required in (
        "activity: null",
        "operationSeq: 0",
        "pending-folio",
        "activity-banner",
        'aria-busy="true"',
        "decisionSlotCommitted",
        "decisionSlotState",
        "syncDecisionActivity",
        'data-action="reconcile-run"',
        'error.code === "decision_already_exists" && error.state === "COMMITTED"',
        'error.code === "decision_in_progress" && error.state === "RUNNING"',
        'error.code === "decision_failed" && error.state === "FAILED"',
        "history.replaceState",
        "setActivityPhase(seq, \"advancing\")",
        "can_continue",
        "desk-continue",
        "deskDocumentPage",
        "你准备怎么处置？",
        "resizeDecisionTextarea",
        'rows="4"',
    ):
        assert required in source

    assert "当前模拟日已经提交过决定" not in source
    assert "当前没有新的触发；可以封存这一局。" not in source


def test_frontend_uses_volume_and_generic_crisis_cover_modules():
    source = _frontend_source()

    for path in (
        "web/api.js",
        "web/state.js",
        "web/router.js",
        "web/pages/volume.js",
        "web/pages/crisis.js",
        "web/pages/desk.js",
        "web/pages/settlement.js",
        "web/pages/compare.js",
        "web/components/letter.js",
        "web/components/ongoing.js",
        "web/components/agreement.js",
        "web/surfaces/spatial.js",
        "web/surfaces/political.js",
    ):
        assert (ROOT / path).exists()

    assert 'api("/api/volume"' in source
    assert 'api(`/api/crises/${encodeURIComponent(crisisId)}`)' in source
    assert 'location.hash = `#/crisis/${encodeURIComponent(crisisId)}`' in source
    assert 'data-action="start-takeover" data-human-actor-id=' in source
    assert "before-shanhaiguan" not in source
    assert "wu-sangui" not in source


def test_frontend_compares_two_settled_runs_without_a_worldline_tree():
    source = _frontend_source()
    compare = (ROOT / "web" / "pages" / "compare.js").read_text(encoding="utf-8")

    for required in (
        "goCompare",
        "loadCompare",
        "/api/compare?left=",
        "compareLeftRunId",
        "compareRightRunId",
        "compareSelectedRunId",
        "first_material_divergence",
        "consequence_paths",
        "outcome_difference",
        "data-compare-run-id",
        "data-compare-replay-id",
        "#/compare/${encodeURIComponent(leftRunId)}/${encodeURIComponent(rightRunId)}",
    ):
        assert required in source

    assert "Worldline Tree" not in compare
    assert "resolution_variant" not in compare
    assert "final_stakes" not in compare
    assert "event-" not in compare


def test_frontend_routes_automatic_settlement_to_a_restrained_outcome_page():
    source = _frontend_source()
    settlement = (ROOT / "web" / "pages" / "settlement.js").read_text(encoding="utf-8")

    for required in (
        "goSettlement",
        "loadSettlement",
        "currentRouteHash",
        'result.run?.crisis_phase === "SETTLED"',
        'api(`/api/runs/${encodeURIComponent(runId)}/outcome`)',
        "open-settlement-replay",
        "RESOLUTION_PENDING",
    ):
        assert required in source

    assert "resolution_variant" not in settlement
    assert "final_stakes" not in settlement
    assert "#/settlement/${encodeURIComponent(state.settlementRunId)}" in source


def test_frontend_desk_consumes_only_product_world_objects():
    source = _frontend_source()

    for required in (
        "view.desk",
        "arrivals",
        "unresolved",
        "ongoing",
        "agreements",
        "arrivalLetterMarkup",
        "ongoingMarkup",
        "agreementMarkup",
    ):
        assert required in source

    assert "known_situation || []" in source
    assert "outgoing_messages || []" not in source
