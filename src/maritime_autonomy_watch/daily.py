from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DAILY_MAX_ITEMS, DEDUPLICATION_METHOD, DEFAULT_TIMEZONE, RELEVANCE_THRESHOLD
from .markdown import render_daily_report
from .models import DailyReport
from .scoring import deduplicate_items
from .sources import collect_items

ACADEMIC_API_SOURCES = ("arXiv", "OpenAlex", "IEEE Xplore", "Elsevier Scopus")


def generate_daily_report(report_date=None, reports_root: Path | str = "reports") -> Path:
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    if report_date is None:
        report_date = now.date()

    items, failed_sources, source_statuses = collect_items(report_date)
    selected = select_daily_items(items)

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
    output_path.write_text(render_daily_report(report), encoding="utf-8")
    return output_path


def select_daily_items(items) -> list:
    candidates = [
        item
        for item in deduplicate_items(items)
        if item.relevance_score >= RELEVANCE_THRESHOLD and item.title and item.url
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
