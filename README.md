# Maritime Autonomy Watch

Maritime Autonomy Watch publishes daily and weekly GitHub Release notes for maritime autonomy, marine robotics, unmanned surface and underwater systems, and naval autonomy.

## Report Archive

Report releases:

- [GitHub Releases archive](https://github.com/ferhannb/MarineRobotics/releases)

Daily GitHub Releases use:

```text
tag: daily-YYYY-MM-DD
title: Maritime Autonomy Watch — YYYY-MM-DD
```

Weekly GitHub Releases use:

```text
tag: weekly-YYYY-Www
title: Maritime Autonomy Watch — Week ww, YYYY
```

Daily releases are the detailed logs. Weekly releases summarize and index the week instead of duplicating all daily content.

## Running Locally

Generate today's daily report file locally:

```bash
python -m maritime_autonomy_watch.daily
```

Generate a daily report for a specific date:

```bash
python -m maritime_autonomy_watch.daily --date 2026-05-05
```

Generate the previous completed ISO week summary:

```bash
python -m maritime_autonomy_watch.weekly
```

Generate a specific ISO week:

```bash
python -m maritime_autonomy_watch.weekly --week 2026-W19
```

For local development without installation, run commands with:

```bash
PYTHONPATH=src python -m maritime_autonomy_watch.daily
```

## Sources

Enabled by default:

- arXiv
- OpenAlex
- Configurable RSS feeds

Default news sources include Naval News, MarineLink, Defense News, Ocean Science & Technology, MASSworld, Ocean News, Naval Technology, and SMI MASG News.

Optional paid/API-key sources:

- IEEE Xplore, via `IEEE_XPLORE_API_KEY`
- Elsevier Scopus, via `ELSEVIER_API_KEY` or legacy `SCOPUS_API_KEY`
- NewsAPI, via `NEWS_API_KEY`

Missing optional keys do not fail the run. The report records those sources as disabled.

For local runs, copy `.env.example` to `.env` and set your private keys there:

```bash
cp .env.example .env
```

The `.env` file is ignored by git and loaded automatically by the Python package.

RSS feeds can be configured with a comma-separated environment variable:

```bash
MARITIME_WATCH_RSS_FEEDS="https://example.com/feed.xml,https://example.org/rss"
```

## GitHub Actions

`.github/workflows/daily_report.yml` runs every morning Amsterdam time and publishes the daily report as a GitHub Release. If the release already exists, the workflow updates its notes.

`.github/workflows/weekly_release.yml` runs Monday morning Amsterdam time, rebuilds the week from daily release notes, and publishes the weekly report as a GitHub Release. If the release already exists, the workflow updates its notes.

Both workflows also support manual execution through `workflow_dispatch`.

## Tests

```bash
python -m unittest discover -s tests
```
