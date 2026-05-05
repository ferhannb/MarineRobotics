---

## Weekly Release Archive

In addition to daily Markdown reports, the project should create a weekly release archive.

Daily reports should be saved under:

```text
reports/daily/YYYY-MM-DD.md
```

Weekly summary reports should be saved under:

```text
reports/weekly/YYYY-Www.md
```

Example:

```text
reports/weekly/2026-W19.md
```

Every week, the system should create a GitHub Release containing the weekly report and references to all daily reports from that week.

The release tag format should be:

```text
weekly-YYYY-Www
```

Example:

```text
weekly-2026-W19
```

The release title format should be:

```text
Maritime Autonomy Watch — Week ww, YYYY
```

Example:

```text
Maritime Autonomy Watch — Week 19, 2026
```

The weekly release should include:

- Weekly executive summary
- Top papers of the week
- Top industry/company news of the week
- Top defense/naval autonomy news of the week
- Main technical signals of the week
- Links to all daily reports from that week
- Failed or inaccessible sources observed during the week
- Source status summary

The weekly release should not duplicate all daily content blindly. It should summarize and index the week.

Daily reports remain the detailed logs.
Weekly releases are the clean archive snapshots.

---

## Weekly Report Structure

The weekly report should use this structure:

```markdown
# Maritime Autonomy Watch — Week YYYY-Www

## Executive Summary

- Daily reports included:
- Total selected items:
- Academic papers:
- Industry/company news:
- Defense/naval autonomy news:
- Failed/inaccessible sources:

## Main Signals This Week

- Signal 1
- Signal 2
- Signal 3

## Top Academic Papers

### [Paper Title](https://example.com)

- Source:
- Date:
- Authors:
- DOI:
- Relevance score:

**Abstract**

Paper abstract.

**Why it matters**

Short domain-specific explanation.

---

## Top Industry and Company News

### [News Title](https://example.com)

- Source:
- Date:
- Relevance score:

**Summary**

Short summary.

**Why it matters**

Short domain-specific explanation.

---

## Top Defense and Naval Autonomy News

### [News Title](https://example.com)

- Source:
- Date:
- Relevance score:

**Summary**

Short summary.

**Why it matters**

Short domain-specific explanation.

---

## Daily Reports Included

- [2026-05-04](../daily/2026-05-04.md)
- [2026-05-05](../daily/2026-05-05.md)
- [2026-05-06](../daily/2026-05-06.md)
- [2026-05-07](../daily/2026-05-07.md)
- [2026-05-08](../daily/2026-05-08.md)
- [2026-05-09](../daily/2026-05-09.md)
- [2026-05-10](../daily/2026-05-10.md)

## Inaccessible or Failed Sources

- Source name: reason

## Source Status Summary

| Source | Status | Notes |
|---|---|---|
| arXiv | enabled | API source |
| OpenAlex | enabled | API source |
| IEEE Xplore | disabled | Missing API key |
| Elsevier Scopus | disabled | Missing API key |

## Metadata

- Generated at:
- Week:
- Repository:
- Relevance threshold:
- Deduplication method:
```

---

## Weekly Release Workflow

Add a separate GitHub Actions workflow:

```text
.github/workflows/weekly_release.yml
```

This workflow should:

1. Run once per week.
2. Support manual execution with `workflow_dispatch`.
3. Generate a weekly report from the daily reports.
4. Commit the weekly report under `reports/weekly/`.
5. Create a GitHub Release with tag `weekly-YYYY-Www`.
6. Attach or include the weekly report as release notes.
7. Not fail if a release already exists.

Suggested workflow:

```yaml
name: Weekly Maritime Autonomy Release

on:
  schedule:
    - cron: "0 8 * * 1"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  weekly-release:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Generate weekly report
        run: |
          python -m maritime_autonomy_watch.weekly

      - name: Commit weekly report
        run: |
          git config user.name "maritime-autonomy-watch-bot"
          git config user.email "maritime-autonomy-watch-bot@users.noreply.github.com"
          git add reports/weekly
          git commit -m "Add weekly maritime autonomy report" || echo "No changes to commit"
          git push

      - name: Create weekly release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          WEEK_TAG=$(python -c "from datetime import date; y,w,_=date.today().isocalendar(); print(f'weekly-{y}-W{w:02d}')")
          WEEK_FILE=$(python -c "from datetime import date; y,w,_=date.today().isocalendar(); print(f'reports/weekly/{y}-W{w:02d}.md')")
          WEEK_TITLE=$(python -c "from datetime import date; y,w,_=date.today().isocalendar(); print(f'Maritime Autonomy Watch — Week {w:02d}, {y}')")

          if gh release view "$WEEK_TAG" >/dev/null 2>&1; then
            echo "Release $WEEK_TAG already exists."
          else
            gh release create "$WEEK_TAG" \
              --title "$WEEK_TITLE" \
              --notes-file "$WEEK_FILE"
          fi
```

---

## Weekly Generator

Create a new module:

```text
src/maritime_autonomy_watch/weekly.py
```

It should:

- Find daily reports from the current ISO week.
- Extract selected items if possible.
- Rank items by relevance score.
- Generate `reports/weekly/YYYY-Www.md`.
- Include links to all daily reports.
- Include failed source summaries.
- Keep the weekly report concise.

The weekly report should be a summary, not a full copy of all daily reports.

---

## Updated Report Storage Rule

Daily reports:

```text
reports/daily/YYYY-MM-DD.md
```

Weekly reports:

```text
reports/weekly/YYYY-Www.md
```

GitHub Releases:

```text
weekly-YYYY-Www
```

Example:

```text
reports/daily/2026-05-05.md
reports/weekly/2026-W19.md
release tag: weekly-2026-W19
```

---

## Definition of Done for Weekly Archive

This feature is complete when:

- Daily reports are saved under `reports/daily/`.
- Weekly summaries are saved under `reports/weekly/`.
- A weekly GitHub Action exists.
- The weekly action creates a GitHub Release.
- The release uses the weekly report as release notes.
- The workflow does not crash if the release already exists.
- The README explains the daily report and weekly release archive system.
