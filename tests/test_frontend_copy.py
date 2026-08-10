from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_frontend_uses_chinese_product_language():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
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
        "成为吴三桂",
        "山海关之前",
        "世界视野",
        "人物视野",
        "吴三桂的书案",
        "送入这段历史",
        "暂不追加命令，继续",
        "回看这一局",
        "三条人生如何相遇",
        "在你看不见的地方",
        "封存后全景",
        "封存卷册",
        "史实背景",
        "hermes_ready",
        "AbortController",
        "corridorMarkup",
        "/api/runs/active",
        "/api/runs/${state.active.id}/decision",
    ):
        assert required in source


def test_product_start_is_live_only_and_fail_closed_in_the_ui():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

    assert 'body: JSON.stringify({ mode, live: true })' in source
    assert "const useLive" not in source
    assert "state.config.setup_required ? \"disabled\"" in source
    start_run = source[source.index("async function startRun"):source.index("async function continueRun")]
    assert 'state.config = await api("/api/config")' in start_run
    assert start_run.index('state.config = await api("/api/config")') < start_run.index("loadRunView()")


def test_frontend_surfaces_boot_failure_instead_of_staying_on_placeholder():
    source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    render = source[source.index("function render"):source.index("async function refreshActive")]

    assert "观测台暂时打不开" in render
    assert "state.error" in render
    assert 'data-action="retry-boot"' in render

    boot = source[source.index("async function boot"):]
    assert "const bootTimeoutMs = 15_000" in boot
    assert 'api("/api/config", { timeoutMs: bootTimeoutMs })' in boot
