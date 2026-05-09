from __future__ import annotations

import argparse
import math
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import (
    DAILY_HISTORY_LOOKBACK_DAYS,
    DAILY_MAX_ITEMS,
    DAILY_MAX_ITEMS_PER_CATEGORY,
    DEDUPLICATION_METHOD,
    DEFAULT_TIMEZONE,
    RELEVANCE_THRESHOLD,
)
from .markdown import clean_report_text, default_why_it_matters, parse_daily_items, render_daily_report
from .models import DailyReport, ReportItem
from .scoring import deduplicate_items, item_identity_keys
from .sources import collect_items
from .visuals import write_daily_category_snapshot

ACADEMIC_API_SOURCES = ("arXiv", "OpenAlex", "IEEE Xplore", "Elsevier Scopus")
NEWS_MAX_AGE_DAYS = 45
ACADEMIC_MAX_AGE_DAYS = 180
STALE_HIGH_RELEVANCE_SCORE = 8.0
RECENT_ITEM_BONUS_DAYS = 14
SIMILAR_TITLE_THRESHOLD = 0.5
NOVEL_UNIQUE_RELEVANCE_FLOOR = 3.0
TITLE_STOPWORDS = {
    "and",
    "autonomous",
    "autonomy",
    "for",
    "from",
    "high",
    "into",
    "item",
    "items",
    "marine",
    "maritime",
    "of",
    "on",
    "paper",
    "scoring",
    "the",
    "to",
    "using",
    "with",
}


@dataclass(frozen=True)
class HistoricalItems:
    keys: set[str]
    signature_tokens: tuple[frozenset[str], ...]


def generate_daily_report(report_date=None, reports_root: Path | str = "reports") -> Path:
    now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
    if report_date is None:
        report_date = now.date()

    reports_root = Path(reports_root)
    items, failed_sources, source_statuses = collect_items(report_date)
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
    write_daily_category_snapshot(report, reports_root=reports_root)
    output_path.write_text(render_daily_report(report), encoding="utf-8")
    return output_path


def select_daily_items(items, reports_root: Path | str = "reports", report_date: date | None = None) -> list:
    candidates = [
        polish_item(item)
        for item in deduplicate_items(items)
        if item.relevance_score >= NOVEL_UNIQUE_RELEVANCE_FLOOR
        and item.title
        and item.url
        and is_fresh_enough(item, report_date)
    ]
    if report_date is None:
        report_date = datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()

    history = historical_items(
        recent_daily_paths(Path(reports_root) / "daily", report_date, DAILY_HISTORY_LOOKBACK_DAYS)
    )
    candidates = [
        item
        for item in candidates
        if item_identity_keys(item).isdisjoint(history.keys)
        and not is_similar_to_any_signature(item_signature_tokens(item), history.signature_tokens)
    ]
    candidates = sorted(candidates, key=lambda item: novelty_score(item, report_date), reverse=True)
    selected = balanced_daily_selection(candidates)

    for source in ACADEMIC_API_SOURCES:
        if any(item.source == source for item in selected):
            continue
        candidate = next((item for item in candidates if item.source == source), None)
        if candidate is None:
            continue
        category_counts = Counter(item.category for item in selected)
        if len(selected) < DAILY_MAX_ITEMS and category_counts[candidate.category] < DAILY_MAX_ITEMS_PER_CATEGORY:
            selected.append(candidate)
        elif selected:
            replace_index = lowest_ranked_index(selected, category=candidate.category)
            if replace_index is not None:
                selected[replace_index] = candidate
        selected = sorted(selected, key=lambda item: novelty_score(item, report_date), reverse=True)

    return selected


def balanced_daily_selection(candidates: list[ReportItem]) -> list[ReportItem]:
    selected: list[ReportItem] = []
    category_counts: Counter[str] = Counter()
    selected_signatures: list[frozenset[str]] = []
    for item in candidates:
        if len(selected) >= DAILY_MAX_ITEMS:
            break
        if category_counts[item.category] >= DAILY_MAX_ITEMS_PER_CATEGORY:
            continue
        if is_similar_to_any_signature(item_signature_tokens(item), tuple(selected_signatures)):
            continue
        selected.append(item)
        selected_signatures.append(item_signature_tokens(item))
        category_counts[item.category] += 1
    return selected


def lowest_ranked_index(items: list[ReportItem], category: str) -> int | None:
    candidates = [(index, item) for index, item in enumerate(items) if item.category == category]
    if not candidates:
        return None
    index, _ = min(candidates, key=lambda pair: pair[1].relevance_score)
    return index


def novelty_score(item: ReportItem, report_date: date) -> float:
    score = item.relevance_score
    item_date = parse_item_date(item.date)
    if item_date is None:
        return score
    age_days = max(0, (report_date - item_date).days)
    score += max(0.0, (RECENT_ITEM_BONUS_DAYS - age_days) / RECENT_ITEM_BONUS_DAYS)
    if item.category != "academic" and age_days <= 7:
        score += 0.5
    if age_days > 60:
        score -= math.log10(age_days - 59)
    return round(score, 3)


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


def recent_daily_paths(daily_dir: Path, report_date: date, lookback_days: int) -> list[Path]:
    paths: list[Path] = []
    for offset in range(1, lookback_days + 1):
        path = daily_dir / f"{(report_date - timedelta(days=offset)).isoformat()}.md"
        if path.is_file():
            paths.append(path)
    return paths


def historical_items(paths: list[Path]) -> HistoricalItems:
    keys: set[str] = set()
    historical_signatures: list[frozenset[str]] = []
    for path in paths:
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for item in parse_daily_items(markdown):
            keys.update(item_identity_keys(item))
            historical_signatures.append(item_signature_tokens(item))
    return HistoricalItems(keys=keys, signature_tokens=tuple(historical_signatures))


def historical_item_keys(paths: list[Path]) -> set[str]:
    return historical_items(paths).keys


def title_tokens(title: str) -> frozenset[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", title.lower())
        if (len(token) > 2 or token.isdigit()) and token not in TITLE_STOPWORDS
    }
    return frozenset(tokens)


def title_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left.intersection(right))
    if intersection < 3:
        return 0.0
    jaccard = intersection / len(left.union(right))
    containment = intersection / min(len(left), len(right))
    return max(jaccard, containment)


def is_similar_to_any_title(title: str, historical_titles: tuple[frozenset[str], ...]) -> bool:
    tokens = title_tokens(title)
    return is_similar_to_any_signature(tokens, historical_titles)


def item_signature_tokens(item: ReportItem) -> frozenset[str]:
    text = item.title if item.category == "academic" else f"{item.title} {item.summary}"
    return title_tokens(text)


def is_similar_to_any_signature(tokens: frozenset[str], signatures: tuple[frozenset[str], ...]) -> bool:
    return any(title_similarity(tokens, previous) >= SIMILAR_TITLE_THRESHOLD for previous in signatures)


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
