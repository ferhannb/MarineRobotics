from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from .config import KEYWORDS
from .models import ReportItem


ACADEMIC_HINTS = ("arxiv", "openalex", "doi", "journal", "conference", "paper")
DEFENSE_HINTS = ("naval", "navy", "defense", "defence", "military", "darpa", "fleet", "warfare")
INDUSTRY_HINTS = ("company", "startup", "contract", "product", "launch", "funding", "shipyard")
USV_TERMS_RE = re.compile(r"\busvs?\b")
USV_DIRECT_TOPICS = (
    "path planning",
    "path following",
    "path tracking",
    "route planning",
    "motion planning",
    "trajectory",
    "trajectory tracking",
    "trajectory planning",
    "trajectory optimization",
)


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", ""))


def relevance_score(title: str, summary: str, source: str = "") -> float:
    text = f"{title} {summary} {source}".lower()
    score = 0.0
    for keyword in KEYWORDS:
        if keyword.lower() in text:
            score += 2.0
    for token in ("autonomous", "autonomy", "robot", "unmanned", "marine", "maritime", "underwater", "surface vessel"):
        if token in text:
            score += 0.75
    for acronym in ("auv", "auvs", "uuv", "uuvs"):
        if re.search(rf"\b{acronym}\b", text):
            score += 1.5
    for acronym in ("usv", "usvs"):
        if re.search(rf"\b{acronym}\b", text):
            score += 2.5
    for phrase in (
        "path planning",
        "trajectory tracking",
        "formation tracking",
        "position control",
        "obstacle avoidance",
    ):
        if phrase in text:
            score += 0.75
    if USV_TERMS_RE.search(text) and any(topic in text for topic in USV_DIRECT_TOPICS):
        score += 2.0
    return min(10.0, round(score, 2))


def classify_item(title: str, summary: str, source: str = "") -> str:
    text = f"{title} {summary} {source}".lower()
    if any(hint in text for hint in DEFENSE_HINTS):
        return "defense"
    if source.lower() in {"arxiv", "openalex"} or any(hint in text for hint in ACADEMIC_HINTS):
        return "academic"
    if any(hint in text for hint in INDUSTRY_HINTS):
        return "industry"
    return "industry"


def deduplicate_items(items: list[ReportItem]) -> list[ReportItem]:
    seen: set[str] = set()
    unique: list[ReportItem] = []
    for item in sorted(items, key=lambda candidate: candidate.relevance_score, reverse=True):
        keys = item_identity_keys(item)
        if seen.intersection(keys):
            continue
        seen.update(keys)
        unique.append(item)
    return unique


def item_identity_keys(item: ReportItem) -> set[str]:
    keys = {f"title:{normalize_title(item.title)}"}
    if item.doi:
        keys.add(f"doi:{item.doi.lower()}")
    if item.url:
        keys.add(f"url:{canonical_url(item.url)}")
    return keys
