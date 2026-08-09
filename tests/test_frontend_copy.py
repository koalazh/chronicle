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
        "live: false",
        "/api/lifetimes/",
        "受限推演",
        "记录一次观察",
        "/api/branch",
        'cx="58"',
        'd="M13 64',
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "开始观测",
        "谁已经知道",
        "史料依据",
        "模型设置",
        "方法与边界",
        "人物经历",
        "经历 → 判断 → 记忆",
        "hermes_ready",
        "pendingAction",
        "正在读取",
        "drawer-loading",
        "mapObservationMarkers",
        "observationCopies",
        "channelLabel(item.channel)",
        "reliabilityLabel(item.reliability_hint)",
        "localizedRuntimeText",
        "response?.assessment",
        "runtimeStatusLabel(config.hermes_status)",
        "进入此刻 · 崇祯",
        "你看见的",
        "分支实际发生的",
        "你改变的",
        "退出并封存",
        "准备人物模型",
        "/api/worldlines/active",
    ):
        assert required in source
