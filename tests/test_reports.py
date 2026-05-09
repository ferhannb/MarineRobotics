from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from maritime_autonomy_watch import config
from maritime_autonomy_watch.daily import is_fresh_enough, is_similar_to_any_title, select_daily_items, title_tokens
from maritime_autonomy_watch.markdown import (
    clean_report_text,
    default_why_it_matters,
    parse_daily_items,
    render_daily_report,
)
from maritime_autonomy_watch.models import DailyReport, ReportItem, SourceStatus
from maritime_autonomy_watch.sources import parse_masg_news
from maritime_autonomy_watch.visuals import daily_asset_path, render_category_snapshot_svg
from maritime_autonomy_watch.weekly import (
    daily_paths_for_week,
    generate_weekly_report,
    previous_completed_iso_week,
    release_tag_for_week,
    release_title_for_week,
)
from maritime_autonomy_watch.scoring import relevance_score


def unique_topic(index: int) -> str:
    topics = (
        "harbor docking perception lidar benchmark",
        "polar navigation acoustic mapping trial",
        "offshore inspection cable route survey",
        "coastal bathymetry adaptive sampler",
        "wave disturbance station keeping controller",
        "subsea pipeline anomaly detector",
        "surface convoy collision avoidance",
        "underwater modem network scheduler",
        "reef monitoring visual localization",
        "mine countermeasure mission planner",
        "ice edge tracking sonar fusion",
        "port security patrol coordination",
        "long endurance energy manager",
        "payload calibration fault diagnosis",
        "environmental plume tracking estimator",
        "ship traffic encounter prediction",
        "launch recovery deck alignment",
        "deep ocean terrain following",
    )
    if index < len(topics):
        return topics[index]
    return f"distinct sensor{index} planner{index} controller{index} estimator{index}"


class ReportTests(unittest.TestCase):
    def test_elsevier_api_key_prefers_elsevier_env(self) -> None:
        previous_elsevier = os.environ.get("ELSEVIER_API_KEY")
        previous_scopus = os.environ.get("SCOPUS_API_KEY")
        try:
            os.environ["ELSEVIER_API_KEY"] = "elsevier-key"
            os.environ["SCOPUS_API_KEY"] = "scopus-key"
            self.assertEqual(config.elsevier_api_key(), "elsevier-key")

            del os.environ["ELSEVIER_API_KEY"]
            self.assertEqual(config.elsevier_api_key(), "scopus-key")
        finally:
            if previous_elsevier is None:
                os.environ.pop("ELSEVIER_API_KEY", None)
            else:
                os.environ["ELSEVIER_API_KEY"] = previous_elsevier
            if previous_scopus is None:
                os.environ.pop("SCOPUS_API_KEY", None)
            else:
                os.environ["SCOPUS_API_KEY"] = previous_scopus

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
        self.assertIn("## Analyst Brief", markdown)
        self.assertIn("## Must Read", markdown)
        self.assertIn("## Top Signals Today", markdown)
        self.assertIn("## Topic Signals", markdown)
        self.assertIn("## Freshness and Coverage", markdown)
        self.assertIn("## Quality Notes", markdown)
        self.assertIn("## Watchlist", markdown)
        self.assertIn("```mermaid", markdown)
        self.assertIn(
            "https://github.com/ferhannb/MarineRobotics/releases/download/daily-2026-05-05/2026-05-05-category-snapshot.svg",
            markdown,
        )
        parsed = parse_daily_items(markdown)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].title, item.title)
        self.assertEqual(parsed[0].category, "academic")
        self.assertEqual(parsed[0].doi, "10.123/example")

    def test_daily_render_and_parse_quality_metadata(self) -> None:
        item = ReportItem(
            title="Future dated USV paper",
            url="https://example.com/future",
            source="Elsevier Scopus",
            date="2026-12-01",
            category="academic",
            relevance_score=4.25,
            abstract="",
            signal="Research signal: USV operations",
            quality_flags=("missing-summary", "date-anomaly"),
            topic_tags=("USV operations", "planning/control"),
            also_reported_by=("OpenAlex",),
        )
        report = DailyReport(
            report_date=date(2026, 5, 5),
            generated_at=datetime(2026, 5, 5, 9, 0),
            items=(item,),
            failed_sources=(),
            source_statuses=(),
            relevance_threshold=4.0,
            deduplication_method="test",
        )

        markdown = render_daily_report(report)
        parsed = parse_daily_items(markdown)

        self.assertIn("- Quality flags: missing-summary, date-anomaly", markdown)
        self.assertIn("- Also reported by: OpenAlex", markdown)
        self.assertEqual(parsed[0].quality_flags, item.quality_flags)
        self.assertEqual(parsed[0].topic_tags, item.topic_tags)
        self.assertEqual(parsed[0].also_reported_by, item.also_reported_by)

    def test_clean_report_text_removes_rss_boilerplate_and_spacing_glitches(self) -> None:
        cleaned = clean_report_text(
            "MBARI deployed an AUV under ice... The post Compact Autonomous Robot appeared first on Ocean Science & Technology ."
        )
        self.assertEqual(cleaned, "MBARI deployed an AUV under ice.")

        self.assertEqual(
            clean_report_text("The underwater drone.Including AUV sensors , navigation ."),
            "The underwater drone. Including AUV sensors, navigation.",
        )

    def test_freshness_filter_excludes_stale_items_except_high_relevance(self) -> None:
        stale_news = ReportItem(
            title="Old autonomous vessel partnership",
            url="https://example.com/old-news",
            source="Example News",
            date="2025-11-01",
            category="industry",
            relevance_score=7.5,
        )
        high_relevance_stale_news = ReportItem(
            title="Strategic USV critical infrastructure contract",
            url="https://example.com/high-news",
            source="Example News",
            date="2025-11-01",
            category="industry",
            relevance_score=8.0,
        )
        stale_academic = ReportItem(
            title="Old AUV navigation paper",
            url="https://example.com/old-paper",
            source="OpenAlex",
            date="2025-01-01",
            category="academic",
            relevance_score=7.5,
        )

        self.assertFalse(is_fresh_enough(stale_news, date(2026, 5, 7)))
        self.assertTrue(is_fresh_enough(high_relevance_stale_news, date(2026, 5, 7)))
        self.assertFalse(is_fresh_enough(stale_academic, date(2026, 5, 7)))

        selected = select_daily_items(
            [stale_news, high_relevance_stale_news, stale_academic],
            report_date=date(2026, 5, 7),
        )
        self.assertEqual([item.title for item in selected], ["Strategic USV critical infrastructure contract"])

    def test_domain_specific_why_it_matters(self) -> None:
        item = ReportItem(
            title="USV swarm obstacle avoidance for naval harbor defense",
            url="https://example.com/item",
            source="Naval News",
            date="2026-05-07",
            category="defense",
            relevance_score=9,
            summary="The system coordinates unmanned surface vessels for collision avoidance.",
        )

        why = default_why_it_matters(item)

        self.assertIn("surface-vessel operations", why)
        self.assertIn("multi-vehicle coordination", why)
        self.assertIn("operational concepts", why)

    def test_category_snapshot_svg_contains_counts(self) -> None:
        report = DailyReport(
            report_date=date(2026, 5, 5),
            generated_at=datetime(2026, 5, 5, 9, 0),
            items=(
                ReportItem("AUV paper", "https://example.com/a", "OpenAlex", "2026-05-05", "academic", 8),
                ReportItem("USV contract", "https://example.com/b", "News", "2026-05-05", "industry", 7),
                ReportItem("Naval UUV trial", "https://example.com/c", "Naval News", "2026-05-05", "defense", 7),
            ),
            failed_sources=(),
            source_statuses=(),
            relevance_threshold=4.0,
            deduplication_method="test",
        )

        svg = render_category_snapshot_svg(report)

        self.assertIn("<svg", svg)
        self.assertIn("Academic papers", svg)
        self.assertIn("Industry/company news", svg)
        self.assertIn("Defense/naval autonomy news", svg)
        self.assertIn("3 selected items", svg)
        self.assertIn("Daily intelligence dashboard", svg)
        self.assertIn("Enabled sources", svg)
        self.assertIn("Quality flags", svg)

    def test_generate_daily_report_writes_markdown_and_svg(self) -> None:
        from maritime_autonomy_watch.daily import generate_daily_report

        item = ReportItem(
            title="AUV obstacle avoidance paper",
            url="https://example.com/paper",
            source="OpenAlex",
            date="2026-05-05",
            category="academic",
            relevance_score=8,
            abstract="AUV obstacle avoidance research.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("maritime_autonomy_watch.daily.collect_items") as collect_items:
                collect_items.return_value = ([item], [], [SourceStatus("OpenAlex", "enabled", "API source")])
                output = generate_daily_report(report_date=date(2026, 5, 5), reports_root=root)

            self.assertTrue(output.is_file())
            self.assertTrue(daily_asset_path(date(2026, 5, 5), root).is_file())

    def test_generate_daily_report_enriches_items_with_topics_and_quality_flags(self) -> None:
        from maritime_autonomy_watch.daily import generate_daily_report

        item = ReportItem(
            title="Digital twin-driven swarm of autonomous underwater vehicles for marine exploration",
            url="https://example.com/paper",
            source="Elsevier Scopus",
            date="2026-12-01",
            category="academic",
            relevance_score=4.25,
            abstract="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("maritime_autonomy_watch.daily.collect_items") as collect_items:
                collect_items.return_value = ([item], [], [SourceStatus("Elsevier Scopus", "enabled", "API source")])
                output = generate_daily_report(report_date=date(2026, 5, 5), reports_root=root)

            markdown = output.read_text(encoding="utf-8")

        self.assertIn("missing-summary", markdown)
        self.assertIn("date-anomaly", markdown)
        self.assertIn("swarm autonomy", markdown)

    def test_daily_paths_for_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            daily = Path(tmp)
            (daily / "2026-05-04.md").write_text("x", encoding="utf-8")
            (daily / "2026-05-06.md").write_text("x", encoding="utf-8")
            paths = daily_paths_for_week(daily, 2026, 19)
            self.assertEqual([path.name for path in paths], ["2026-05-04.md", "2026-05-06.md"])

    def test_title_only_auv_and_usv_papers_clear_threshold(self) -> None:
        self.assertGreaterEqual(
            relevance_score(
                "Event-triggered prescribed-time position control for AUVs with input constraints",
                "",
                "Elsevier Scopus",
            ),
            4.0,
        )
        self.assertGreater(
            relevance_score(
                "A hybrid APF-DQN framework with transformer-based current prediction for USV path planning",
                "",
                "Elsevier Scopus",
            ),
            relevance_score(
                "A hybrid APF-DQN framework with transformer-based current prediction for AUV path planning",
                "",
                "Elsevier Scopus",
            ),
        )

    def test_usv_path_or_trajectory_work_is_directly_relevant(self) -> None:
        self.assertGreaterEqual(
            relevance_score(
                "USV trajectory optimization under dynamic ocean currents",
                "",
                "Elsevier Scopus",
            ),
            4.0,
        )
        self.assertGreaterEqual(
            relevance_score(
                "Adaptive guidance for unmanned vehicles",
                "The proposed method improves USV path trajectory tracking in constrained waters.",
                "Elsevier Scopus",
            ),
            4.0,
        )

    def test_daily_selection_keeps_relevant_scopus_item(self) -> None:
        items = [
            ReportItem(
                title=f"High scoring arXiv paper {index}",
                url=f"https://example.com/arxiv/{index}",
                source="arXiv",
                date="2026-05-06",
                category="academic",
                relevance_score=5.0,
            )
            for index in range(config.DAILY_MAX_ITEMS)
        ]
        items.append(
            ReportItem(
                title="Digital twin-driven swarm of autonomous underwater vehicles for marine exploration",
                url="https://example.com/scopus",
                source="Elsevier Scopus",
                date="2026-05-06",
                category="academic",
                relevance_score=4.25,
                doi="10.123/scopus",
            )
        )

        selected = select_daily_items(items)

        self.assertEqual(len(selected), config.DAILY_MAX_ITEMS_PER_CATEGORY)
        self.assertTrue(any(item.source == "Elsevier Scopus" for item in selected))
        self.assertGreaterEqual(
            relevance_score(
                "A hybrid APF-DQN framework with transformer-based current prediction for USV path planning",
                "",
                "Elsevier Scopus",
            ),
            4.0,
        )

    def test_daily_selection_balances_categories(self) -> None:
        items = []
        source_by_category = {
            "academic": "OpenAlex",
            "industry": "MarineLink",
            "defense": "Naval News",
        }
        for category_index, category in enumerate(("academic", "industry", "defense")):
            items.extend(
                ReportItem(
                    title=(
                        f"{category} {index} {unique_topic(category_index * 18 + index)} "
                        f"vessel{category_index}_{index} mission{category_index}_{index}"
                    ),
                    url=f"https://example.com/{category}/{index}",
                    source=source_by_category[category],
                    date="2026-05-06",
                    category=category,
                    relevance_score=9 - index * 0.01,
                )
                for index in range(18)
            )

        selected = select_daily_items(items, report_date=date(2026, 5, 7))
        counts = {category: sum(1 for item in selected if item.category == category) for category in ("academic", "industry", "defense")}

        self.assertEqual(len(selected), config.DAILY_MAX_ITEMS)
        self.assertLessEqual(max(counts.values()), config.DAILY_MAX_ITEMS_PER_CATEGORY)
        self.assertGreater(counts["academic"], 0)
        self.assertGreater(counts["industry"], 0)
        self.assertGreater(counts["defense"], 0)

    def test_similar_recent_titles_are_excluded(self) -> None:
        repeated = ReportItem(
            title="Hybrid APF DQN framework for USV path planning",
            url="https://example.com/repeated",
            source="OpenAlex",
            date="2026-05-06",
            category="academic",
            relevance_score=9,
        )
        similar = ReportItem(
            title="A hybrid APF-DQN framework for USV path planning in dynamic ocean environments",
            url="https://example.com/similar",
            source="Elsevier Scopus",
            date="2026-05-07",
            category="academic",
            relevance_score=10,
        )
        fresh = ReportItem(
            title="New acoustic localization for cooperative AUV navigation",
            url="https://example.com/fresh",
            source="arXiv",
            date="2026-05-07",
            category="academic",
            relevance_score=8,
        )
        old_report = DailyReport(
            report_date=date(2026, 5, 6),
            generated_at=datetime(2026, 5, 6, 9, 0),
            items=(repeated,),
            failed_sources=(),
            source_statuses=(),
            relevance_threshold=4.0,
            deduplication_method="test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily"
            daily.mkdir()
            (daily / "2026-05-06.md").write_text(render_daily_report(old_report), encoding="utf-8")

            selected = select_daily_items([similar, fresh], reports_root=root, report_date=date(2026, 5, 7))

        self.assertEqual([item.title for item in selected], ["New acoustic localization for cooperative AUV navigation"])
        self.assertTrue(is_similar_to_any_title(similar.title, (title_tokens(repeated.title),)))

    def test_daily_selection_skips_recently_reported_items(self) -> None:
        repeated = ReportItem(
            title="Repeated Autonomous Surface Vessel Planning",
            url="https://example.com/repeated",
            source="arXiv",
            date="2026-05-05",
            category="academic",
            relevance_score=9,
            abstract="Already reported.",
        )
        fresh = ReportItem(
            title="Fresh Underwater Robotics Navigation",
            url="https://example.com/fresh",
            source="OpenAlex",
            date="2026-05-06",
            category="academic",
            relevance_score=8,
            abstract="New item.",
        )
        old_report = DailyReport(
            report_date=date(2026, 5, 5),
            generated_at=datetime(2026, 5, 5, 9, 0),
            items=(repeated,),
            failed_sources=(),
            source_statuses=(),
            relevance_threshold=4.0,
            deduplication_method="test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily = root / "daily"
            daily.mkdir()
            (daily / "2026-05-05.md").write_text(render_daily_report(old_report), encoding="utf-8")

            selected = select_daily_items([repeated, fresh], reports_root=root, report_date=date(2026, 5, 6))

        self.assertEqual([item.title for item in selected], ["Fresh Underwater Robotics Navigation"])

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
            self.assertIn(
                "[2026-05-05](https://github.com/ferhannb/MarineRobotics/releases/tag/daily-2026-05-05)",
                markdown,
            )

    def test_parse_masg_news(self) -> None:
        html = """
        <div class="news-outer">
          <div class="cont-outer">
            <span class="date">23 April 2026</span>
            <h3><a href="https://www.maritimeindustries.org/news/example">Autonomous Vessel Trial Announced</a></h3>
            <p>A maritime autonomy company announced a new uncrewed surface vessel trial.</p>
          </div>
        </div>
        """
        items = parse_masg_news(html, date(2026, 5, 5))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Autonomous Vessel Trial Announced")
        self.assertEqual(items[0].date, "2026-04-23")
        self.assertEqual(items[0].source, "maritimeindustries.org")


if __name__ == "__main__":
    unittest.main()
