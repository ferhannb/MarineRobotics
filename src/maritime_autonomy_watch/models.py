from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class ReportItem:
    title: str
    url: str
    source: str
    date: str
    category: str
    relevance_score: float
    summary: str = ""
    why_it_matters: str = ""
    authors: tuple[str, ...] = field(default_factory=tuple)
    doi: str = ""
    abstract: str = ""


@dataclass(frozen=True)
class FailedSource:
    name: str
    reason: str


@dataclass(frozen=True)
class SourceStatus:
    name: str
    status: str
    notes: str


@dataclass(frozen=True)
class DailyReport:
    report_date: date
    generated_at: datetime
    items: tuple[ReportItem, ...]
    failed_sources: tuple[FailedSource, ...]
    source_statuses: tuple[SourceStatus, ...]
    relevance_threshold: float
    deduplication_method: str
