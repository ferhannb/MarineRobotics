from __future__ import annotations

import os
from pathlib import Path


def load_local_env(path: Path | str = ".env") -> None:
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("'\"")
        if name and name not in os.environ:
            os.environ[name] = value


load_local_env()


DEFAULT_TIMEZONE = "Europe/Amsterdam"

RELEVANCE_THRESHOLD = float(os.getenv("MARITIME_WATCH_RELEVANCE_THRESHOLD", "4.0"))
SOURCE_LIMIT = int(os.getenv("MARITIME_WATCH_SOURCE_LIMIT", "15"))
DAILY_MAX_ITEMS = int(os.getenv("MARITIME_WATCH_DAILY_MAX_ITEMS", "24"))
WEEKLY_MAX_ITEMS_PER_SECTION = int(os.getenv("MARITIME_WATCH_WEEKLY_MAX_ITEMS_PER_SECTION", "5"))

DEDUPLICATION_METHOD = "DOI, canonical URL, source ID, and normalized title"

KEYWORDS = (
    "maritime autonomy",
    "marine robotics",
    "autonomous vessel",
    "autonomous mission",
    "autonomous surface vessel",
    "autonomous underwater vehicle",
    "unmanned surface vehicle",
    "unmanned underwater vehicle",
    "unmanned naval",
    "unmanned systems",
    "naval autonomy",
    "USV",
    "USV autonomy",
    "AUV",
    "AUV navigation",
    "UUV",
    "robotic perception marine",
    "underwater robotics",
)

DEFAULT_RSS_FEEDS = (
    "https://www.navalnews.com/feed/",
    "https://www.marinelink.com/news/rss",
    "https://www.defensenews.com/arc/outboundfeeds/rss/category/naval/",
    "https://www.defensenews.com/arc/outboundfeeds/rss/category/unmanned/",
    "https://www.defensenews.com/arc/outboundfeeds/rss/category/industry/",
)


def configured_rss_feeds() -> tuple[str, ...]:
    raw = os.getenv("MARITIME_WATCH_RSS_FEEDS", "")
    if not raw.strip():
        return DEFAULT_RSS_FEEDS
    return tuple(feed.strip() for feed in raw.split(",") if feed.strip())


def elsevier_api_key() -> str:
    return os.getenv("ELSEVIER_API_KEY") or os.getenv("SCOPUS_API_KEY", "")
