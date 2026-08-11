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


def test_frontend_uses_the_v5_product_language_and_ia():
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
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "Volume",
        "World",
        "Follow",
        "Life Desk",
        "Archive",
        "开始这一卷",
        "继续这一卷",
        "此刻哪里值得我去活？",
        "进入这段人生",
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


def test_frontend_routes_only_formal_v5_pages():
    router = (ROOT / "web" / "router.js").read_text(encoding="utf-8")

    for required in ("volume", "world", "follow", "desk", "archive", "ending", "goFollow"):
        assert required in router
    for forbidden in ("crisis", "watch", "takeover", "compare", "settlement"):
        assert forbidden not in router.lower()
