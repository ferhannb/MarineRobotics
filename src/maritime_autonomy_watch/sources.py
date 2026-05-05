from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser

from .config import KEYWORDS, SOURCE_LIMIT, configured_rss_feeds, elsevier_api_key
from .models import FailedSource, ReportItem, SourceStatus
from .scoring import classify_item, relevance_score


def collect_items(report_date: date) -> tuple[list[ReportItem], list[FailedSource], list[SourceStatus]]:
    items: list[ReportItem] = []
    failed: list[FailedSource] = []
    statuses: list[SourceStatus] = []

    collectors = (
        ("arXiv", collect_arxiv),
        ("OpenAlex", collect_openalex),
        ("RSS feeds", collect_rss),
        ("SMI MASG News", collect_masg_news),
        ("IEEE Xplore", collect_ieee),
        ("Elsevier Scopus", collect_scopus),
        ("NewsAPI", collect_newsapi),
    )

    for name, collector in collectors:
        try:
            collected, status = collector(report_date)
            items.extend(collected)
            statuses.append(status)
        except Exception as exc:
            failed.append(FailedSource(name=name, reason=str(exc)))
            statuses.append(SourceStatus(name=name, status="failed", notes=str(exc)))

    return items, failed, statuses


def collect_arxiv(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    query = " OR ".join(f'all:"{keyword}"' for keyword in KEYWORDS[:8])
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": SOURCE_LIMIT,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    root = fetch_xml(f"https://export.arxiv.org/api/query?{params}")
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items: list[ReportItem] = []
    for entry in root.findall("atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        abstract = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        url = entry.findtext("atom:id", default="", namespaces=ns)
        published = entry.findtext("atom:published", default=report_date.isoformat(), namespaces=ns)[:10]
        authors = tuple(
            clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        )
        score = relevance_score(title, abstract, "arXiv")
        items.append(
            ReportItem(
                title=title,
                url=url,
                source="arXiv",
                date=published,
                category="academic",
                relevance_score=score,
                summary=abstract,
                abstract=abstract,
                authors=authors,
            )
        )
    return items, SourceStatus("arXiv", "enabled", f"API source, {len(items)} items fetched")


def collect_openalex(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    search = " ".join(KEYWORDS[:5])
    params = urllib.parse.urlencode(
        {
            "search": search,
            "per-page": SOURCE_LIMIT,
            "sort": "publication_date:desc",
        }
    )
    data = fetch_json(f"https://api.openalex.org/works?{params}")
    items: list[ReportItem] = []
    for result in data.get("results", []):
        title = clean_text(result.get("title") or "")
        abstract = clean_text(reconstruct_openalex_abstract(result.get("abstract_inverted_index") or {}))
        url = result.get("doi") or result.get("id") or ""
        published = result.get("publication_date") or report_date.isoformat()
        authorships = result.get("authorships") or []
        authors = tuple(
            clean_text((authorship.get("author") or {}).get("display_name") or "")
            for authorship in authorships[:8]
        )
        doi = (result.get("doi") or "").replace("https://doi.org/", "")
        score = relevance_score(title, abstract, "OpenAlex")
        items.append(
            ReportItem(
                title=title,
                url=url,
                source="OpenAlex",
                date=published,
                category="academic",
                relevance_score=score,
                summary=abstract,
                abstract=abstract,
                authors=tuple(author for author in authors if author),
                doi=doi,
            )
        )
    return items, SourceStatus("OpenAlex", "enabled", f"API source, {len(items)} items fetched")


def collect_rss(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    items: list[ReportItem] = []
    failures: list[str] = []
    for feed in configured_rss_feeds():
        try:
            root = fetch_xml(feed)
            items.extend(parse_feed(root, feed, report_date))
        except Exception as exc:
            failures.append(f"{feed}: {exc}")
    status = "partial" if failures and items else "failed" if failures else "enabled"
    notes = f"{len(items)} RSS items fetched"
    if failures:
        notes = f"{notes}; failures: {'; '.join(failures[:3])}"
    return items, SourceStatus("RSS feeds", status, notes)


def collect_masg_news(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    url = "https://www.maritimeindustries.org/specialist-groups/maritime-autonomous-systems-group/masg-news"
    html = fetch_text(url)
    items = parse_masg_news(html, report_date)
    return items, SourceStatus("SMI MASG News", "enabled", f"HTML source, {len(items)} items fetched")


def collect_ieee(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    api_key = os.getenv("IEEE_XPLORE_API_KEY")
    if not api_key:
        return [], SourceStatus("IEEE Xplore", "disabled", "Missing IEEE_XPLORE_API_KEY")
    params = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "format": "json",
            "max_records": SOURCE_LIMIT,
            "sort_order": "desc",
            "sort_field": "publication_year",
            "querytext": " OR ".join(KEYWORDS[:5]),
        }
    )
    data = fetch_json(f"https://ieeexploreapi.ieee.org/api/v1/search/articles?{params}")
    items: list[ReportItem] = []
    for article in data.get("articles", []):
        title = clean_text(article.get("title") or "")
        summary = clean_text(article.get("abstract") or "")
        url = article.get("html_url") or article.get("pdf_url") or ""
        score = relevance_score(title, summary, "IEEE Xplore")
        items.append(
            ReportItem(
                title=title,
                url=url,
                source="IEEE Xplore",
                date=str(article.get("publication_year") or report_date.year),
                category="academic",
                relevance_score=score,
                summary=summary,
                abstract=summary,
                doi=article.get("doi") or "",
            )
        )
    return items, SourceStatus("IEEE Xplore", "enabled", f"API source, {len(items)} items fetched")


def collect_scopus(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    api_key = elsevier_api_key()
    if not api_key:
        return [], SourceStatus("Elsevier Scopus", "disabled", "Missing ELSEVIER_API_KEY or SCOPUS_API_KEY")
    query = urllib.parse.quote(" OR ".join(KEYWORDS[:5]))
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    data = fetch_json(f"https://api.elsevier.com/content/search/scopus?query={query}&count={SOURCE_LIMIT}", headers=headers)
    items: list[ReportItem] = []
    for entry in (data.get("search-results") or {}).get("entry", []):
        title = clean_text(entry.get("dc:title") or "")
        summary = clean_text(entry.get("dc:description") or "")
        url = entry.get("prism:url") or ""
        score = relevance_score(title, summary, "Elsevier Scopus")
        items.append(
            ReportItem(
                title=title,
                url=url,
                source="Elsevier Scopus",
                date=entry.get("prism:coverDate") or report_date.isoformat(),
                category="academic",
                relevance_score=score,
                summary=summary,
                abstract=summary,
                doi=entry.get("prism:doi") or "",
            )
        )
    return items, SourceStatus("Elsevier Scopus", "enabled", f"API source, {len(items)} items fetched")


def collect_newsapi(report_date: date) -> tuple[list[ReportItem], SourceStatus]:
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return [], SourceStatus("NewsAPI", "disabled", "Missing NEWS_API_KEY")
    params = urllib.parse.urlencode(
        {
            "q": " OR ".join(f'"{keyword}"' for keyword in KEYWORDS[:5]),
            "sortBy": "publishedAt",
            "pageSize": SOURCE_LIMIT,
            "language": "en",
            "apiKey": api_key,
        }
    )
    data = fetch_json(f"https://newsapi.org/v2/everything?{params}")
    items: list[ReportItem] = []
    for article in data.get("articles", []):
        title = clean_text(article.get("title") or "")
        summary = clean_text(article.get("description") or article.get("content") or "")
        source_name = clean_text((article.get("source") or {}).get("name") or "NewsAPI")
        score = relevance_score(title, summary, source_name)
        items.append(
            ReportItem(
                title=title,
                url=article.get("url") or "",
                source=source_name,
                date=(article.get("publishedAt") or report_date.isoformat())[:10],
                category=classify_item(title, summary, source_name),
                relevance_score=score,
                summary=summary,
            )
        )
    return items, SourceStatus("NewsAPI", "enabled", f"API source, {len(items)} items fetched")


def parse_feed(root: ET.Element, feed_url: str, report_date: date) -> list[ReportItem]:
    items: list[ReportItem] = []
    if root.tag.endswith("feed"):
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns)[:SOURCE_LIMIT]:
            title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
            summary = clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
            link = entry.find("atom:link", ns)
            url = link.attrib.get("href", "") if link is not None else ""
            published = entry.findtext("atom:published", default=report_date.isoformat(), namespaces=ns)[:10]
            score = relevance_score(title, summary, feed_url)
            items.append(
                ReportItem(
                    title=title,
                    url=url,
                    source=feed_url,
                    date=published,
                    category=classify_item(title, summary, feed_url),
                    relevance_score=score,
                    summary=summary,
                )
            )
        return items

    channel = root.find("channel")
    entries = channel.findall("item") if channel is not None else root.findall(".//item")
    for entry in entries[:SOURCE_LIMIT]:
        title = clean_text(entry.findtext("title", default=""))
        summary = clean_text(entry.findtext("description", default=""))
        url = clean_text(entry.findtext("link", default=""))
        published = parse_pub_date(entry.findtext("pubDate", default=""), report_date)
        score = relevance_score(title, summary, feed_url)
        items.append(
            ReportItem(
                title=title,
                url=url,
                source=feed_url,
                date=published,
                category=classify_item(title, summary, feed_url),
                relevance_score=score,
                summary=summary,
            )
        )
    return items


class MasgNewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None
        self.in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        classes = set(attrs_dict.get("class", "").split())
        if tag == "div" and "news-outer" in classes:
            self._finalize_current()
            self.current = {"date": "", "title": "", "url": "", "summary": ""}
            return
        if self.current is None:
            return
        if tag == "span" and "date" in classes:
            self.capture = "date"
        elif tag == "h3":
            self.in_heading = True
        elif tag == "a" and self.in_heading:
            self.current["url"] = attrs_dict.get("href", "")
            self.capture = "title"
        elif tag == "p":
            self.capture = "summary"

    def handle_endtag(self, tag: str) -> None:
        if tag in {"span", "a", "p"}:
            self.capture = None
        if tag == "h3":
            self.in_heading = False

    def handle_data(self, data: str) -> None:
        if self.current is None or self.capture is None:
            return
        self.current[self.capture] = clean_text(f"{self.current[self.capture]} {data}")

    def close(self) -> None:
        super().close()
        self._finalize_current()

    def _finalize_current(self) -> None:
        if self.current and self.current.get("title") and self.current.get("url"):
            self.items.append(self.current)
        self.current = None
        self.capture = None
        self.in_heading = False


def parse_masg_news(html: str, report_date: date) -> list[ReportItem]:
    parser = MasgNewsParser()
    parser.feed(html)
    parser.close()
    items: list[ReportItem] = []
    for entry in parser.items[:SOURCE_LIMIT]:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", ""))
        source = "maritimeindustries.org"
        score = relevance_score(title, summary, source)
        items.append(
            ReportItem(
                title=title,
                url=entry.get("url", ""),
                source=source,
                date=parse_masg_date(entry.get("date", ""), report_date),
                category=classify_item(title, summary, source),
                relevance_score=score,
                summary=summary,
            )
        )
    return items


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "maritime-autonomy-watch/0.1", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "maritime-autonomy-watch/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc


def fetch_xml(url: str) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": "maritime-autonomy-watch/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return ET.fromstring(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
    except ET.ParseError as exc:
        raise RuntimeError(f"Invalid XML from {url}: {exc}") from exc


def reconstruct_openalex_abstract(index: dict[str, list[int]]) -> str:
    if not index:
        return ""
    words: list[str] = [""] * (max(position for positions in index.values() for position in positions) + 1)
    for word, positions in index.items():
        for position in positions:
            words[position] = word
    return " ".join(words)


def clean_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(value.replace("\n", " ").split())


def parse_pub_date(value: str, fallback: date) -> str:
    if not value:
        return fallback.isoformat()
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError):
        return value[:10]


def parse_masg_date(value: str, fallback: date) -> str:
    if not value:
        return fallback.isoformat()
    try:
        return datetime.strptime(value.strip(), "%d %B %Y").date().isoformat()
    except ValueError:
        return fallback.isoformat()
