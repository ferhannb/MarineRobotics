from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .models import DailyReport, ReportItem


CATEGORY_LABELS = {
    "academic": "Academic papers",
    "industry": "Industry/company news",
    "defense": "Defense/naval autonomy news",
}

CATEGORY_COLORS = {
    "academic": "#1f77b4",
    "industry": "#2ca02c",
    "defense": "#d62728",
}


def daily_asset_path(report_date, reports_root: Path | str = "reports") -> Path:
    return Path(reports_root) / "assets" / "daily" / f"{report_date.isoformat()}-category-snapshot.svg"


def write_daily_category_snapshot(report: DailyReport, reports_root: Path | str = "reports") -> Path:
    output_path = daily_asset_path(report.report_date, reports_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_category_snapshot_svg(report), encoding="utf-8")
    return output_path


def render_category_snapshot_svg(report: DailyReport) -> str:
    counts = Counter(item.category for item in report.items)
    topic_counts = topic_tag_counts(report.items)
    quality_flags = sum(len(item.quality_flags) for item in report.items)
    enabled_sources = sum(1 for status in report.source_statuses if status.status == "enabled")
    problem_sources = sum(1 for status in report.source_statuses if status.status in {"failed", "partial", "disabled"})
    total = sum(counts.values())
    width = 760
    height = 360
    max_count = max([counts[key] for key in CATEGORY_LABELS] + [1])

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f"<title>Maritime Autonomy Watch dashboard for {escape(report.report_date.isoformat())}</title>",
        "<desc>Daily selected item counts, source health, topic signals, and quality flags.</desc>",
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
        '<text x="32" y="38" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#111827">Daily intelligence dashboard</text>',
        f'<text x="32" y="64" font-family="Arial, sans-serif" font-size="13" fill="#475569">{total} selected items</text>',
        metric_card(32, 82, "Items", str(total), "#1f77b4"),
        metric_card(206, 82, "Enabled sources", str(enabled_sources), "#2ca02c"),
        metric_card(380, 82, "Source issues", str(problem_sources), "#d62728"),
        metric_card(554, 82, "Quality flags", str(quality_flags), "#9467bd"),
    ]

    y = 164
    for category, label in CATEGORY_LABELS.items():
        count = counts[category]
        bar_width = 520 * count / max_count if max_count else 0
        color = CATEGORY_COLORS[category]
        lines.extend(
            [
                f'<text x="32" y="{y + 16}" font-family="Arial, sans-serif" font-size="14" fill="#111827">{escape(label)}</text>',
                f'<rect x="240" y="{y}" width="520" height="24" rx="4" fill="#e5e7eb"/>',
                f'<rect x="240" y="{y}" width="{bar_width:.1f}" height="24" rx="4" fill="{color}"/>',
                f'<text x="250" y="{y + 17}" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#ffffff">{count}</text>',
            ]
        )
        y += 42

    lines.append('<text x="32" y="312" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#111827">Top topic signals</text>')
    topic_x = 32
    for topic, count in topic_counts.most_common(4):
        label = f"{topic}: {count}"
        lines.append(
            f'<text x="{topic_x}" y="338" font-family="Arial, sans-serif" font-size="12" fill="#334155">{escape(label)}</text>'
        )
        topic_x += 180

    lines.append("</svg>")
    return "\n".join(lines)


def metric_card(x: int, y: int, label: str, value: str, color: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="150" height="54" rx="6" fill="#ffffff" stroke="#cbd5e1"/>'
        f'<text x="{x + 12}" y="{y + 21}" font-family="Arial, sans-serif" font-size="12" fill="#64748b">{escape(label)}</text>'
        f'<text x="{x + 12}" y="{y + 43}" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="{color}">{escape(value)}</text>'
    )


def topic_tag_counts(items: tuple[ReportItem, ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        counts.update(item.topic_tags)
    return counts
