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
    ):
        assert forbidden not in source
        assert forbidden not in index

    for required in (
        "开始观测",
        "谁已经知道",
        "史料依据",
        "模型设置",
        "受限推演",
        "记录一次观察",
        "方法与边界",
        "hermes_ready",
        "bootstrapResult.ready",
    ):
        assert required in source
