from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from .models import DailyReport, FailedSource, ReportItem, SourceStatus


SECTION_TITLES = {
    "academic": "Academic Papers",
    "industry": "Industry and Company News",
    "defense": "Defense and Naval Autonomy News",
}


def render_daily_report(report: DailyReport, repository: str = "MarineRobotics") -> str:
    counts = Counter(item.category for item in report.items)
    lines: list[str] = [
        f"# Maritime Autonomy Watch — {report.report_date.isoformat()}",
        "",
        "## Executive Summary",
        "",
        f"- Total selected items: {len(report.items)}",
        f"- Academic papers: {counts['academic']}",
        f"- Industry/company news: {counts['industry']}",
        f"- Defense/naval autonomy news: {counts['defense']}",
        f"- Failed/inaccessible sources: {len(report.failed_sources)}",
        "",
        "### Category Snapshot",
        "",
        "| Category | Selected items |",
        "|---|---:|",
        f"| Academic papers | {counts['academic']} |",
        f"| Industry/company news | {counts['industry']} |",
        f"| Defense/naval autonomy news | {counts['defense']} |",
        "",
        "## Contents",
        "",
        "- [Academic Papers](#academic-papers)",
        "- [Industry and Company News](#industry-and-company-news)",
        "- [Defense and Naval Autonomy News](#defense-and-naval-autonomy-news)",
        "- [Source Status Summary](#source-status-summary)",
        "",
    ]

    for category, title in SECTION_TITLES.items():
        lines.extend([f"## {title}", ""])
        category_items = [item for item in report.items if item.category == category]
        lines.extend([f"_Selected items: {len(category_items)}_", ""])
        if not category_items:
            lines.extend(["No selected items.", ""])
            continue
        for item in category_items:
            lines.extend(render_item(item))

    lines.extend(render_failed_sources(report.failed_sources))
    lines.extend(render_source_statuses(report.source_statuses))
    lines.extend(
        [
            "## Metadata",
            "",
            f"- Generated at: {report.generated_at.isoformat()}",
            f"- Date: {report.report_date.isoformat()}",
            f"- Repository: {repository}",
            f"- Relevance threshold: {report.relevance_threshold}",
            f"- Deduplication method: {report.deduplication_method}",
            "",
        ]
    )
    return "\n".join(lines)


def render_weekly_report(
    week_label: str,
    week_number: int,
    year: int,
    generated_at: datetime,
    daily_paths: list[Path],
    items: list[ReportItem],
    failed_sources: list[FailedSource],
    source_statuses: list[SourceStatus],
    relevance_threshold: float,
    deduplication_method: str,
    repository: str = "ferhannb/MarineRobotics",
    max_items_per_section: int = 5,
) -> str:
    counts = Counter(item.category for item in items)
    lines: list[str] = [
        f"# Maritime Autonomy Watch — Week {week_label}",
        "",
        "## Executive Summary",
        "",
        f"- Daily reports included: {len(daily_paths)}",
        f"- Total selected items: {len(items)}",
        f"- Academic papers: {counts['academic']}",
        f"- Industry/company news: {counts['industry']}",
        f"- Defense/naval autonomy news: {counts['defense']}",
        f"- Failed/inaccessible sources: {len(failed_sources)}",
        "",
        "### Weekly Snapshot",
        "",
        "| Category | Selected items |",
        "|---|---:|",
        f"| Academic papers | {counts['academic']} |",
        f"| Industry/company news | {counts['industry']} |",
        f"| Defense/naval autonomy news | {counts['defense']} |",
        f"| Failed/inaccessible sources | {len(failed_sources)} |",
        "",
        "## Contents",
        "",
        "- [Main Signals This Week](#main-signals-this-week)",
        "- [Top Academic Papers](#top-academic-papers)",
        "- [Top Industry and Company News](#top-industry-and-company-news)",
        "- [Top Defense and Naval Autonomy News](#top-defense-and-naval-autonomy-news)",
        "- [Daily Reports Included](#daily-reports-included)",
        "- [Source Status Summary](#source-status-summary)",
        "",
        "## Main Signals This Week",
        "",
    ]
    lines.extend(main_signals(items))
    lines.append("")

    section_specs = (
        ("academic", "Top Academic Papers"),
        ("industry", "Top Industry and Company News"),
        ("defense", "Top Defense and Naval Autonomy News"),
    )
    for category, section_title in section_specs:
        lines.extend([f"## {section_title}", ""])
        top_items = [item for item in items if item.category == category][:max_items_per_section]
        lines.extend([f"_Selected top items: {len(top_items)}_", ""])
        if not top_items:
            lines.extend(["No selected items.", ""])
            continue
        for item in top_items:
            lines.extend(render_item(item))

    lines.extend(["## Daily Reports Included", ""])
    if daily_paths:
        for path in daily_paths:
            report_date = path.stem
            lines.append(f"- [{report_date}](https://github.com/{repository}/releases/tag/daily-{report_date})")
    else:
        lines.append("- No daily reports found for this week.")
    lines.append("")

    lines.extend(render_failed_sources(tuple(failed_sources)))
    lines.extend(render_source_statuses(tuple(source_statuses)))
    lines.extend(
        [
            "## Metadata",
            "",
            f"- Generated at: {generated_at.isoformat()}",
            f"- Week: {week_label}",
            f"- Repository: {repository}",
            f"- Relevance threshold: {relevance_threshold}",
            f"- Deduplication method: {deduplication_method}",
            "",
        ]
    )
    return "\n".join(lines)


def render_item(item: ReportItem) -> list[str]:
    lines = [
        f"### [{item.title}]({item.url})",
        "",
        f"- Source: {display_source(item.source)}",
        f"- Date: {item.date}",
        f"- Relevance score: {item.relevance_score:g}",
    ]
    if item.authors:
        lines.append(f"- Authors: {', '.join(item.authors)}")
    if item.doi:
        lines.append(f"- DOI: {item.doi}")

    abstract_title = "Abstract" if item.category == "academic" else "Summary"
    abstract_text = item.abstract or item.summary or "No summary available."
    lines.extend(
        [
            "",
            f"**{abstract_title}**",
            "",
            abstract_text.strip(),
            "",
            "**Why it matters**",
            "",
            item.why_it_matters.strip() or default_why_it_matters(item),
            "",
            "---",
            "",
        ]
    )
    return lines


def display_source(source: str) -> str:
    parsed = urlsplit(source)
    if parsed.netloc:
        return parsed.netloc.removeprefix("www.")
    return source


def render_failed_sources(failed_sources: tuple[FailedSource, ...]) -> list[str]:
    lines = ["## Inaccessible or Failed Sources", ""]
    if not failed_sources:
        lines.append("- None")
    else:
        for failed in failed_sources:
            lines.append(f"- {failed.name}: {failed.reason}")
    lines.append("")
    return lines


def render_source_statuses(source_statuses: tuple[SourceStatus, ...]) -> list[str]:
    lines = [
        "## Source Status Summary",
        "",
        "| Source | Status | Notes |",
        "|---|---|---|",
    ]
    for status in source_statuses:
        lines.append(f"| {status.name} | {status.status} | {status.notes} |")
    lines.append("")
    return lines


def default_why_it_matters(item: ReportItem) -> str:
    if item.category == "academic":
        return "This paper may influence autonomy, perception, planning, or control work for maritime robotic systems."
    if item.category == "defense":
        return "This item may signal operational adoption, procurement priorities, or naval autonomy doctrine shifts."
    return "This item may signal product, market, or deployment momentum in maritime autonomy."


def main_signals(items: list[ReportItem]) -> list[str]:
    if not items:
        return ["- No high-relevance items were selected this week."]
    words: Counter[str] = Counter()
    for item in items:
        for word in re.findall(r"[A-Za-z][A-Za-z-]{3,}", f"{item.title} {item.summary}"):
            lowered = word.lower()
            if lowered not in {"with", "from", "this", "that", "autonomy", "maritime"}:
                words[lowered] += 1
    signals = [word for word, _ in words.most_common(3)]
    if not signals:
        return ["- Maritime autonomy activity remained broad across research, industry, and defense sources."]
    return [f"- Repeated signal around {word} across selected items." for word in signals]


ITEM_RE = re.compile(
    r"^### \[(?P<title>[^\]]+)\]\((?P<url>[^)]+)\)\n\n"
    r"(?P<meta>(?:- .+\n)+)\n"
    r"\*\*(?:Abstract|Summary)\*\*\n\n"
    r"(?P<body>.*?)\n\n"
    r"\*\*Why it matters\*\*\n\n"
    r"(?P<why>.*?)\n\n---",
    re.MULTILINE | re.DOTALL,
)


def parse_daily_items(markdown: str) -> list[ReportItem]:
    items: list[ReportItem] = []
    current_category = "industry"
    for chunk in re.split(r"(^## .+$)", markdown, flags=re.MULTILINE):
        if chunk.startswith("## Academic Papers"):
            current_category = "academic"
            continue
        if chunk.startswith("## Industry and Company News"):
            current_category = "industry"
            continue
        if chunk.startswith("## Defense and Naval Autonomy News"):
            current_category = "defense"
            continue
        for match in ITEM_RE.finditer(chunk):
            meta = parse_meta(match.group("meta"))
            authors = tuple(part.strip() for part in meta.get("Authors", "").split(",") if part.strip())
            items.append(
                ReportItem(
                    title=match.group("title").strip(),
                    url=match.group("url").strip(),
                    source=meta.get("Source", ""),
                    date=meta.get("Date", ""),
                    category=current_category,
                    relevance_score=float(meta.get("Relevance score", "0") or 0),
                    summary=match.group("body").strip(),
                    abstract=match.group("body").strip() if current_category == "academic" else "",
                    why_it_matters=match.group("why").strip(),
                    authors=authors,
                    doi=meta.get("DOI", ""),
                )
            )
    return items


def parse_failed_sources(markdown: str) -> list[FailedSource]:
    section = extract_section(markdown, "Inaccessible or Failed Sources")
    failed: list[FailedSource] = []
    for line in section.splitlines():
        if not line.startswith("- ") or line == "- None":
            continue
        name, _, reason = line[2:].partition(":")
        failed.append(FailedSource(name=name.strip(), reason=reason.strip() or "Unknown"))
    return failed


def parse_source_statuses(markdown: str) -> list[SourceStatus]:
    section = extract_section(markdown, "Source Status Summary")
    statuses: list[SourceStatus] = []
    for line in section.splitlines():
        if not line.startswith("|") or "---" in line or "Source | Status" in line:
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if len(parts) == 3:
            statuses.append(SourceStatus(name=parts[0], status=parts[1], notes=parts[2]))
    return statuses


def extract_section(markdown: str, title: str) -> str:
    match = re.search(rf"^## {re.escape(title)}\n(?P<body>.*?)(?=^## |\Z)", markdown, re.MULTILINE | re.DOTALL)
    return match.group("body") if match else ""


def parse_meta(meta_block: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        meta[key.strip()] = value.strip()
    return meta
