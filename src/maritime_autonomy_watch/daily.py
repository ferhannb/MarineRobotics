from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DAILY_MAX_ITEMS, DEDUPLICATION_METHOD, DEFAULT_TIMEZONE, RELEVANCE_THRESHOLD
from .markdown import clean_report_text, default_why_it_matters, render_daily_report
from .models import DailyReport, ReportItem
from .scoring import deduplicate_items
from .sources import collect_items
from .visuals import write_daily_category_snapshot

ACADEMIC_API_SOURCES = ("arXiv", "OpenAlex", "IEEE Xplore", "Elsevier Scopus")
NEWS_MAX_AGE_DAYS = 45
ACADEMIC_MAX_AGE_DAYS = 180
STALE_HIGH_RELEVANCE_SCORE = 8.0


def generate_daily_report(report_date=None, reports_root: Path | str = "reports") -> Path:
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    if report_date is None:
        report_date = now.date()

    items, failed_sources, source_statuses = collect_items(report_date)
    selected = select_daily_items(items, report_date=report_date)

    report = DailyReport(
        report_date=report_date,
        generated_at=now,
        items=tuple(selected),
        failed_sources=tuple(failed_sources),
        source_statuses=tuple(source_statuses),
        relevance_threshold=RELEVANCE_THRESHOLD,
        deduplication_method=DEDUPLICATION_METHOD,
    )

    output_dir = Path(reports_root) / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{report_date.isoformat()}.md"
    write_daily_category_snapshot(report, reports_root=reports_root)
    output_path.write_text(render_daily_report(report), encoding="utf-8")
    return output_path


def select_daily_items(items, report_date: date | None = None) -> list:
    candidates = [
        polish_item(item)
        for item in deduplicate_items(items)
        if item.relevance_score >= RELEVANCE_THRESHOLD
        and item.title
        and item.url
        and is_fresh_enough(item, report_date)
    ]
    selected = candidates[:DAILY_MAX_ITEMS]

    for source in ACADEMIC_API_SOURCES:
        if any(item.source == source for item in selected):
            continue
        candidate = next((item for item in candidates if item.source == source), None)
        if candidate is None:
            continue
        if len(selected) < DAILY_MAX_ITEMS:
            selected.append(candidate)
        elif selected:
            selected[-1] = candidate
        selected = sorted(selected, key=lambda item: item.relevance_score, reverse=True)

    return selected


def polish_item(item: ReportItem) -> ReportItem:
    summary = clean_report_text(item.summary)
    abstract = clean_report_text(item.abstract)
    why_it_matters = clean_report_text(item.why_it_matters) or default_why_it_matters(
        replace(item, summary=summary, abstract=abstract)
    )
    return replace(
        item,
        title=clean_report_text(item.title),
        summary=summary,
        abstract=abstract,
        why_it_matters=why_it_matters,
    )


def is_fresh_enough(item: ReportItem, report_date: date | None) -> bool:
    if report_date is None:
        return True
    item_date = parse_item_date(item.date)
    if item_date is None or item_date > report_date:
        return True
    age_days = (report_date - item_date).days
    if item.relevance_score >= STALE_HIGH_RELEVANCE_SCORE:
        return True
    if item.category == "academic":
        return age_days <= ACADEMIC_MAX_AGE_DAYS
    return age_days <= NEWS_MAX_AGE_DAYS


def parse_item_date(value: str) -> date | None:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Maritime Autonomy Watch daily report.")
    parser.add_argument("--date", help="Report date as YYYY-MM-DD. Defaults to today in Europe/Amsterdam.")
    parser.add_argument("--reports-root", default="reports", help="Reports root directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    output_path = generate_daily_report(report_date=report_date, reports_root=args.reports_root)
    print(output_path)


if __name__ == "__main__":
    main()
