from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DEDUPLICATION_METHOD, DEFAULT_TIMEZONE, RELEVANCE_THRESHOLD, WEEKLY_MAX_ITEMS_PER_SECTION
from .markdown import parse_daily_items, parse_failed_sources, parse_source_statuses, render_weekly_report
from .models import FailedSource, ReportItem, SourceStatus
from .scoring import deduplicate_items


def generate_weekly_report(
    week: str | None = None,
    reports_root: Path | str = "reports",
    reference_date: date | None = None,
) -> Path:
    if week:
        year, week_number = parse_week_label(week)
    else:
        year, week_number = previous_completed_iso_week(reference_date or current_date())

    week_label = f"{year}-W{week_number:02d}"
    reports_root = Path(reports_root)
    daily_paths = daily_paths_for_week(reports_root / "daily", year, week_number)

    items: list[ReportItem] = []
    failed_sources: list[FailedSource] = []
    source_statuses: list[SourceStatus] = []
    for path in daily_paths:
        markdown = path.read_text(encoding="utf-8")
        items.extend(parse_daily_items(markdown))
        failed_sources.extend(parse_failed_sources(markdown))
        source_statuses.extend(parse_source_statuses(markdown))

    items = deduplicate_items(items)
    output_dir = reports_root / "weekly"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_label}.md"
    output_path.write_text(
        render_weekly_report(
            week_label=week_label,
            week_number=week_number,
            year=year,
            generated_at=datetime.now(ZoneInfo(DEFAULT_TIMEZONE)),
            daily_paths=daily_paths,
            items=items,
            failed_sources=deduplicate_failed_sources(failed_sources),
            source_statuses=merge_source_statuses(source_statuses),
            relevance_threshold=RELEVANCE_THRESHOLD,
            deduplication_method=DEDUPLICATION_METHOD,
            max_items_per_section=WEEKLY_MAX_ITEMS_PER_SECTION,
        ),
        encoding="utf-8",
    )
    return output_path


def current_date() -> date:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()


def previous_completed_iso_week(today: date) -> tuple[int, int]:
    previous_week_day = today - timedelta(days=7)
    iso = previous_week_day.isocalendar()
    return iso.year, iso.week


def daily_paths_for_week(daily_dir: Path, year: int, week_number: int) -> list[Path]:
    start = date.fromisocalendar(year, week_number, 1)
    days = [start + timedelta(days=offset) for offset in range(7)]
    return [daily_dir / f"{day.isoformat()}.md" for day in days if (daily_dir / f"{day.isoformat()}.md").exists()]


def parse_week_label(value: str) -> tuple[int, int]:
    try:
        year_text, week_text = value.split("-W", 1)
        year = int(year_text)
        week_number = int(week_text)
        date.fromisocalendar(year, week_number, 1)
    except ValueError as exc:
        raise SystemExit(f"Invalid --week value {value!r}; expected YYYY-Www") from exc
    return year, week_number


def deduplicate_failed_sources(failed_sources: list[FailedSource]) -> list[FailedSource]:
    seen: set[tuple[str, str]] = set()
    result: list[FailedSource] = []
    for failed in failed_sources:
        key = (failed.name, failed.reason)
        if key not in seen:
            seen.add(key)
            result.append(failed)
    return result


def merge_source_statuses(statuses: list[SourceStatus]) -> list[SourceStatus]:
    if not statuses:
        return []
    merged: dict[str, SourceStatus] = {}
    priority = {"enabled": 3, "partial": 2, "disabled": 1, "failed": 0}
    for status in statuses:
        current = merged.get(status.name)
        if current is None or priority.get(status.status, 0) > priority.get(current.status, 0):
            merged[status.name] = status
    return list(merged.values())


def release_tag_for_week(week: str) -> str:
    year, week_number = parse_week_label(week)
    return f"weekly-{year}-W{week_number:02d}"


def release_title_for_week(week: str) -> str:
    year, week_number = parse_week_label(week)
    return f"Maritime Autonomy Watch — Week {week_number:02d}, {year}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Maritime Autonomy Watch weekly summary report.")
    parser.add_argument("--week", help="ISO week as YYYY-Www. Defaults to the previous completed ISO week.")
    parser.add_argument("--reports-root", default="reports", help="Reports root directory.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = generate_weekly_report(week=args.week, reports_root=args.reports_root)
    print(output_path)


if __name__ == "__main__":
    main()
