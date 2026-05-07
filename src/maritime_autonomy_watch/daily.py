from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import (
    DAILY_HISTORY_LOOKBACK_DAYS,
    DAILY_MAX_ITEMS,
    DEDUPLICATION_METHOD,
    DEFAULT_TIMEZONE,
    RELEVANCE_THRESHOLD,
)
from .markdown import parse_daily_items, render_daily_report
from .models import DailyReport
from .scoring import deduplicate_items, item_identity_keys
from .sources import collect_items


def generate_daily_report(report_date=None, reports_root: Path | str = "reports") -> Path:
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    if report_date is None:
        report_date = now.date()

    items, failed_sources, source_statuses = collect_items(report_date)
    reports_root = Path(reports_root)
    selected = select_daily_items(items, reports_root=reports_root, report_date=report_date)

    report = DailyReport(
        report_date=report_date,
        generated_at=now,
        items=tuple(selected),
        failed_sources=tuple(failed_sources),
        source_statuses=tuple(source_statuses),
        relevance_threshold=RELEVANCE_THRESHOLD,
        deduplication_method=DEDUPLICATION_METHOD,
    )

    output_dir = reports_root / "daily"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{report_date.isoformat()}.md"
    output_path.write_text(render_daily_report(report), encoding="utf-8")
    return output_path


def select_daily_items(items, reports_root: Path | str = "reports", report_date: date | None = None) -> list:
    candidates = [
        item
        for item in deduplicate_items(items)
        if item.relevance_score >= RELEVANCE_THRESHOLD and item.title and item.url
    ]
    if report_date is None:
        report_date = datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()

    history_keys = historical_item_keys(
        recent_daily_paths(Path(reports_root) / "daily", report_date, DAILY_HISTORY_LOOKBACK_DAYS)
    )
    return [item for item in candidates if item_identity_keys(item).isdisjoint(history_keys)][:DAILY_MAX_ITEMS]


def recent_daily_paths(daily_dir: Path, report_date: date, lookback_days: int) -> list[Path]:
    paths: list[Path] = []
    for offset in range(1, lookback_days + 1):
        path = daily_dir / f"{(report_date - timedelta(days=offset)).isoformat()}.md"
        if path.is_file():
            paths.append(path)
    return paths


def historical_item_keys(paths: list[Path]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for item in parse_daily_items(markdown):
            keys.update(item_identity_keys(item))
    return keys


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
