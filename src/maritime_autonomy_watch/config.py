from __future__ import annotations

import os


DEFAULT_TIMEZONE = "Europe/Amsterdam"

RELEVANCE_THRESHOLD = float(os.getenv("MARITIME_WATCH_RELEVANCE_THRESHOLD", "4.0"))
SOURCE_LIMIT = int(os.getenv("MARITIME_WATCH_SOURCE_LIMIT", "15"))
DAILY_MAX_ITEMS = int(os.getenv("MARITIME_WATCH_DAILY_MAX_ITEMS", "24"))
WEEKLY_MAX_ITEMS_PER_SECTION = int(os.getenv("MARITIME_WATCH_WEEKLY_MAX_ITEMS_PER_SECTION", "5"))

DEDUPLICATION_METHOD = "DOI, canonical URL, source ID, and normalized title"

KEYWORDS = (
    "maritime autonomy",
    "marine robotics",
    "autonomous surface vessel",
    "autonomous underwater vehicle",
    "unmanned surface vehicle",
    "unmanned underwater vehicle",
    "naval autonomy",
    "USV autonomy",
    "AUV navigation",
    "robotic perception marine",
    "underwater robotics",
)

DEFAULT_RSS_FEEDS = (
    "https://www.navalnews.com/feed/",
    "https://news.mit.edu/rss/topic/robotics",
)


def configured_rss_feeds() -> tuple[str, ...]:
    raw = os.getenv("MARITIME_WATCH_RSS_FEEDS", "")
    if not raw.strip():
        return DEFAULT_RSS_FEEDS
    return tuple(feed.strip() for feed in raw.split(",") if feed.strip())
