from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from maritime_autonomy_watch.markdown import parse_daily_items, render_daily_report
from maritime_autonomy_watch.models import DailyReport, ReportItem, SourceStatus
from maritime_autonomy_watch.weekly import (
    daily_paths_for_week,
    generate_weekly_report,
    previous_completed_iso_week,
    release_tag_for_week,
    release_title_for_week,
)


class ReportTests(unittest.TestCase):
    def test_release_names(self) -> None:
        self.assertEqual(release_tag_for_week("2026-W19"), "weekly-2026-W19")
        self.assertEqual(release_title_for_week("2026-W19"), "Maritime Autonomy Watch — Week 19, 2026")

    def test_previous_completed_iso_week(self) -> None:
        self.assertEqual(previous_completed_iso_week(date(2026, 5, 11)), (2026, 19))
        self.assertEqual(previous_completed_iso_week(date(2027, 1, 4)), (2026, 53))

    def test_daily_render_and_parse_round_trip(self) -> None:
        item = ReportItem(
            title="Autonomous Surface Vessel Planning",
            url="https://example.com/paper",
            source="arXiv",
            date="2026-05-05",
            category="academic",
            relevance_score=8.5,
            abstract="A paper about maritime autonomy.",
            authors=("A. Researcher",),
            doi="10.123/example",
        )
        report = DailyReport(
            report_date=date(2026, 5, 5),
            generated_at=datetime(2026, 5, 5, 9, 0),
            items=(item,),
            failed_sources=(),
            source_statuses=(SourceStatus("arXiv", "enabled", "API source"),),
            relevance_threshold=4.0,
            deduplication_method="test",
        )
        markdown = render_daily_report(report)
        parsed = parse_daily_items(markdown)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].title, item.title)
        self.assertEqual(parsed[0].category, "academic")
        self.assertEqual(parsed[0].doi, "10.123/example")

    def test_daily_paths_for_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp)
            (daily / "2026-05-04.md").write_text("x", encoding="utf-8")
            (daily / "2026-05-06.md").write_text("x", encoding="utf-8")
            paths = daily_paths_for_week(daily, 2026, 19)
            self.assertEqual([path.name for path in paths], ["2026-05-04.md", "2026-05-06.md"])

    def test_generate_weekly_report_from_daily_files(self) -> None:
        item = ReportItem(
            title="Naval Autonomous Underwater Vehicle Trial",
            url="https://example.com/news",
            source="Naval News",
            date="2026-05-05",
            category="defense",
            relevance_score=7,
            summary="A naval autonomy trial.",
        )
        report = DailyReport(
            report_date=date(2026, 5, 5),
            generated_at=datetime(2026, 5, 5, 9, 0),
            items=(item,),
            failed_sources=(),
            source_statuses=(SourceStatus("Naval News", "enabled", "RSS"),),
            relevance_threshold=4.0,
            deduplication_method="test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily"
            daily.mkdir()
            (daily / "2026-05-05.md").write_text(render_daily_report(report), encoding="utf-8")
            output = generate_weekly_report(week="2026-W19", reports_root=root)
            markdown = output.read_text(encoding="utf-8")
            self.assertIn("# Maritime Autonomy Watch — Week 2026-W19", markdown)
            self.assertIn("Naval Autonomous Underwater Vehicle Trial", markdown)
            self.assertIn("[2026-05-05](../daily/2026-05-05.md)", markdown)


if __name__ == "__main__":
    unittest.main()
