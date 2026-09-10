"""Tests for per-country health monitoring (Step 1-3 of feeds-health-visibility)."""

from __future__ import annotations

import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

from src.feed.generator import (
    _bare_path,
    _compute_status_enum,
    _count_xml_items,
    _extract_links,
    generate_alerts,
    generate_health,
    generate_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_status(directory: str, country: str, per_source: list[dict]) -> None:
    """Write a minimal status-<country>.json fixture."""
    status = {
        "last_run": "2026-09-01T12:00:00Z",
        "country": country,
        "sources_checked": len(per_source),
        "per_source": per_source,
    }
    with open(os.path.join(directory, f"status-{country}.json"), "w") as f:
        json.dump(status, f)


def _write_rss(path: str, items: list[dict]) -> None:
    """Write a minimal RSS file with the given items (each has 'link')."""
    root = ET.Element("rss", version="2.0")
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "Test"
    for item in items:
        el = ET.SubElement(channel, "item")
        ET.SubElement(el, "link").text = item.get("link", "https://example.com/job/1")
        if "title" in item:
            ET.SubElement(el, "title").text = item["title"]
    tree = ET.ElementTree(root)
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def _make_db(path: str, rows: list[dict]) -> None:
    """Create a minimal jobs.db with the given rows."""
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            guid TEXT PRIMARY KEY,
            source_name TEXT,
            is_active INTEGER DEFAULT 1,
            description_source TEXT,
            date_first_seen TEXT,
            date_last_seen TEXT,
            closing_date TEXT
        )"""
    )
    for row in rows:
        conn.execute(
            "INSERT INTO jobs (guid, source_name, is_active, description_source, date_first_seen, date_last_seen, closing_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                row["guid"],
                row.get("source_name", "test"),
                row.get("is_active", 1),
                row.get("description_source", "api"),
                row.get("date_first_seen"),
                row.get("date_last_seen"),
                row.get("closing_date"),
            ),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Step 1: Per-country baseline isolation
# ---------------------------------------------------------------------------

class TestPerCountryBaselineIsolation:
    """A UK run must not consume a US baseline and vice versa."""

    def test_uk_run_uses_uk_baseline_not_us(self, tmp_path):
        """When a US baseline has a source with prev_found > 0, a UK run that
        checks that same source name should NOT trigger zero_result_after_success
        if there is no UK baseline for it."""
        output_dir = str(tmp_path)

        # Write a US status showing "SourceA" found 5 jobs last run.
        _write_status(output_dir, "us", [
            {"name": "SourceA", "status": "success", "jobs_found": 5},
        ])

        # UK run: SourceA found 0 jobs (no UK baseline exists yet).
        uk_sources = [{"name": "SourceA", "status": "success", "jobs_found": 0}]
        generate_alerts(
            output_dir=output_dir,
            current_per_source=uk_sources,
            previous_status_path="",
            previous_alerts_path="",
            country="uk",
        )

        with open(os.path.join(output_dir, "alerts-uk.json")) as f:
            alerts_data = json.load(f)

        # No baseline for UK => no zero_result_after_success alert should fire.
        zero_alerts = [a for a in alerts_data["alerts"] if a["type"] == "zero_result_after_success"]
        assert zero_alerts == [], (
            "UK zero-result alert fired against a US baseline instead of a UK one"
        )

    def test_us_run_uses_us_baseline_not_uk(self, tmp_path):
        """A US run that follows a UK run should compare against the US baseline."""
        output_dir = str(tmp_path)

        # Write a UK status showing "SourceB" found 10 jobs.
        _write_status(output_dir, "uk", [
            {"name": "SourceB", "status": "success", "jobs_found": 10},
        ])

        # US run: SourceB found 0. No US baseline => no alert.
        us_sources = [{"name": "SourceB", "status": "success", "jobs_found": 0}]
        generate_alerts(
            output_dir=output_dir,
            current_per_source=us_sources,
            previous_status_path="",
            previous_alerts_path="",
            country="us",
        )

        with open(os.path.join(output_dir, "alerts-us.json")) as f:
            alerts_data = json.load(f)

        zero_alerts = [a for a in alerts_data["alerts"] if a["type"] == "zero_result_after_success"]
        assert zero_alerts == []

    def test_uk_alert_fires_against_uk_baseline(self, tmp_path):
        """A source that returned jobs in a previous UK run and now returns 0 does trigger an alert."""
        output_dir = str(tmp_path)

        # Establish UK baseline.
        _write_status(output_dir, "uk", [
            {"name": "SourceC", "status": "success", "jobs_found": 8},
        ])

        # UK run: same source now finds 0.
        uk_sources = [{"name": "SourceC", "status": "success", "jobs_found": 0}]
        generate_alerts(
            output_dir=output_dir,
            current_per_source=uk_sources,
            previous_status_path="",
            previous_alerts_path="",
            country="uk",
        )

        with open(os.path.join(output_dir, "alerts-uk.json")) as f:
            alerts_data = json.load(f)

        zero_alerts = [a for a in alerts_data["alerts"] if a["type"] == "zero_result_after_success"]
        assert len(zero_alerts) == 1
        assert zero_alerts[0]["source"] == "SourceC"
        assert zero_alerts[0]["previous_count"] == 8


# ---------------------------------------------------------------------------
# Step 1: Zero-sources guard
# ---------------------------------------------------------------------------

class TestZeroSourcesGuard:
    """A run that checked zero sources must not overwrite the country baseline."""

    def test_zero_sources_does_not_overwrite_country_baseline(self, tmp_path):
        output_dir = str(tmp_path)

        # Write an existing UK baseline.
        baseline = {
            "last_run": "2026-08-01T12:00:00Z",
            "country": "uk",
            "sources_checked": 5,
            "per_source": [{"name": "SourceD", "status": "success", "jobs_found": 3}],
        }
        country_path = os.path.join(output_dir, "status-uk.json")
        with open(country_path, "w") as f:
            json.dump(baseline, f)

        # Run generate_status with sources_checked=0 (regenerate-only path).
        generate_status(
            output_dir=output_dir,
            country="uk",
            sources_checked=0,
            sources_succeeded=0,
            sources_failed=0,
        )

        # The country baseline must be unchanged.
        with open(country_path) as f:
            on_disk = json.load(f)
        assert on_disk["sources_checked"] == 5, (
            "Zero-sources run overwrote the UK baseline"
        )

    def test_zero_sources_still_writes_status_json(self, tmp_path):
        """Even with sources_checked=0, status.json (the aggregate) is updated."""
        output_dir = str(tmp_path)
        generate_status(
            output_dir=output_dir,
            country="uk",
            sources_checked=0,
        )
        assert os.path.exists(os.path.join(output_dir, "status.json"))

    def test_non_zero_sources_writes_country_baseline(self, tmp_path):
        output_dir = str(tmp_path)
        generate_status(
            output_dir=output_dir,
            country="uk",
            sources_checked=3,
            per_source=[{"name": "S", "status": "success", "jobs_found": 1}],
        )
        country_path = os.path.join(output_dir, "status-uk.json")
        assert os.path.exists(country_path)
        with open(country_path) as f:
            data = json.load(f)
        assert data["sources_checked"] == 3


# ---------------------------------------------------------------------------
# Step 2: Status enum boundaries
# ---------------------------------------------------------------------------

class TestStatusEnum:
    """One test per branch of _compute_status_enum."""

    _base = dict(
        enabled=True,
        last_success_at="2026-09-10T00:00:00Z",  # today
        new_7d=5,
        new_28d=20,
        new_prev_28d=20,
        consecutive_zero_runs=0,
        is_cyclical=False,
        last_run_failed=False,
        is_intl_graduate=False,
    )

    def test_off_when_disabled(self):
        assert _compute_status_enum(**{**self._base, "enabled": False}) == "off"

    def test_healthy_when_all_good(self):
        assert _compute_status_enum(**self._base) == "healthy"

    def test_dead_when_last_success_older_than_7_days(self):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_status_enum(**{**self._base, "last_success_at": old_ts})
        assert result == "dead"

    def test_dead_when_3_consecutive_zero_runs_non_cyclical(self):
        result = _compute_status_enum(
            **{**self._base, "consecutive_zero_runs": 3, "new_7d": 0, "new_28d": 0}
        )
        assert result == "dead"

    def test_cyclical_not_dead_on_3_zero_runs(self):
        """Cyclical sources are exempt from the consecutive-zero-runs dead rule."""
        result = _compute_status_enum(
            **{**self._base, "consecutive_zero_runs": 3, "is_cyclical": True, "new_7d": 0, "new_28d": 0}
        )
        assert result != "dead"

    def test_declining_when_new_28d_less_than_half_prev(self):
        result = _compute_status_enum(
            **{**self._base, "new_28d": 5, "new_prev_28d": 25}
        )
        assert result == "declining"

    def test_not_declining_when_prev_period_too_small(self):
        """prev_28d < 20 means the threshold is not met."""
        result = _compute_status_enum(
            **{**self._base, "new_28d": 5, "new_prev_28d": 10}
        )
        assert result != "declining"

    def test_stale_when_no_new_in_7d_but_last_run_succeeded(self):
        result = _compute_status_enum(
            **{**self._base, "new_7d": 0, "last_run_failed": False}
        )
        assert result == "stale"

    def test_not_stale_when_last_run_failed(self):
        """A failed run with no new rows in 7d should not be stale — it is dead or healthy."""
        old_ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        result = _compute_status_enum(
            **{**self._base, "new_7d": 0, "last_run_failed": True, "last_success_at": old_ts}
        )
        assert result != "stale"


# ---------------------------------------------------------------------------
# Step 3: Same-link detection
# ---------------------------------------------------------------------------

class TestSameLinkDetection:
    """generate_health must flag feeds where >= 5 items share a full link."""

    def test_exact_duplicate_link_flagged(self, tmp_path):
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])

        # Write a feed with 5 items sharing the same link.
        feed_path = str(tmp_path / "uk-general.xml")
        shared = "https://example.com/jobs/1"
        _write_rss(feed_path, [{"link": shared}] * 5)

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        dup_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "duplicate_link" and w.get("feed") == "uk-general.xml"
        ]
        assert dup_warnings, "Expected duplicate_link warning for uk-general.xml"
        assert shared in dup_warnings[0]["links"]

    def test_four_duplicates_not_flagged(self, tmp_path):
        """Fewer than 5 exact duplicates should not raise a warning."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])

        feed_path = str(tmp_path / "uk-general.xml")
        shared = "https://example.com/jobs/1"
        _write_rss(feed_path, [{"link": shared}] * 4 + [{"link": "https://example.com/jobs/2"}])

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        dup_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "duplicate_link" and w.get("feed") == "uk-general.xml"
        ]
        assert not dup_warnings

    def test_query_string_distinguishes_items(self, tmp_path):
        """Links differing only by query string are counted as distinct (full link comparison)."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])

        feed_path = str(tmp_path / "us-us-congress.xml")
        # Five links with distinct query strings -- should NOT trigger duplicate_link.
        links = [f"https://example.com/job?id={i}" for i in range(5)]
        _write_rss(feed_path, [{"link": l} for l in links])

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        dup_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "duplicate_link" and w.get("feed") == "us-us-congress.xml"
        ]
        assert not dup_warnings

    def test_bare_path_collision_reported(self, tmp_path):
        """Items sharing scheme+host+path but differing by query are reported as query_identified_items."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])

        feed_path = str(tmp_path / "us-us-congress.xml")
        # Two items with same bare path but different queries.
        links = [
            "https://example.com/job?id=1",
            "https://example.com/job?id=2",
            "https://other.com/job",
        ]
        _write_rss(feed_path, [{"link": l} for l in links])

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        qi_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "query_identified_items" and w.get("feed") == "us-us-congress.xml"
        ]
        assert qi_warnings, "Expected query_identified_items warning"
        assert qi_warnings[0]["count"] >= 2


# ---------------------------------------------------------------------------
# Step 3: Closing-soon detection
# ---------------------------------------------------------------------------

class TestClosingSoonDetection:
    """Sources where >= 80% of active rows close within 3 days of first seen are flagged."""

    def test_closing_soon_flagged(self, tmp_path):
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")

        now = datetime.now(timezone.utc)
        # All 5 rows close within 3 days.
        rows = []
        for i in range(5):
            first_seen = (now - timedelta(days=10)).isoformat()
            close_dt = (now - timedelta(days=10) + timedelta(days=2)).isoformat()[:10]
            rows.append({
                "guid": f"g{i}",
                "source_name": "FastClose",
                "is_active": 1,
                "description_source": "api",
                "date_first_seen": first_seen,
                "date_last_seen": first_seen,
                "closing_date": close_dt,
            })
        _make_db(db_path, rows)

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        cs_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "closing_soon" and w.get("source") == "FastClose"
        ]
        assert cs_warnings, "Expected closing_soon warning for FastClose"

    def test_below_threshold_not_flagged(self, tmp_path):
        """79% close-soon share should not trigger a warning."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")

        now = datetime.now(timezone.utc)
        rows = []
        for i in range(10):
            first_seen = (now - timedelta(days=10)).isoformat()
            # 7 close within 3 days, 3 do not (70% < 80%)
            if i < 7:
                close_dt = (now - timedelta(days=10) + timedelta(days=2)).isoformat()[:10]
            else:
                close_dt = (now - timedelta(days=10) + timedelta(days=14)).isoformat()[:10]
            rows.append({
                "guid": f"g{i}",
                "source_name": "SlowClose",
                "is_active": 1,
                "description_source": "api",
                "date_first_seen": first_seen,
                "date_last_seen": first_seen,
                "closing_date": close_dt,
            })
        _make_db(db_path, rows)

        generate_health(output_dir=output_dir, db_path=db_path)

        with open(os.path.join(output_dir, "health.json")) as f:
            health = json.load(f)

        cs_warnings = [
            w for w in health.get("warnings", [])
            if w.get("type") == "closing_soon" and w.get("source") == "SlowClose"
        ]
        assert not cs_warnings


# ---------------------------------------------------------------------------
# Step 2: health.json validity
# ---------------------------------------------------------------------------

class TestHealthJsonValidity:
    """health.json must be valid JSON and contain all enabled sources."""

    def test_health_json_is_valid_json(self, tmp_path):
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])
        generate_health(output_dir=output_dir, db_path=db_path)
        health_path = os.path.join(output_dir, "health.json")
        assert os.path.exists(health_path)
        with open(health_path) as f:
            data = json.load(f)  # Must not raise
        assert "sources" in data
        assert "generated_at" in data

    def test_health_json_has_required_top_level_keys(self, tmp_path):
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])
        generate_health(output_dir=output_dir, db_path=db_path)
        with open(os.path.join(output_dir, "health.json")) as f:
            data = json.load(f)
        for key in ("generated_at", "country_last_run", "feed_item_counts", "warnings", "sources"):
            assert key in data, f"Missing top-level key: {key}"

    def test_health_json_never_raises_on_missing_db(self, tmp_path):
        """generate_health must not raise even when jobs.db does not exist."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "missing.db")
        # Should complete without exception.
        generate_health(output_dir=output_dir, db_path=db_path)

    def test_health_json_never_raises_on_bad_status_files(self, tmp_path):
        """Corrupt status-*.json files must be silently skipped."""
        output_dir = str(tmp_path)
        db_path = str(tmp_path / "jobs.db")
        _make_db(db_path, [])
        with open(os.path.join(output_dir, "status-uk.json"), "w") as f:
            f.write("not json{{{")
        generate_health(output_dir=output_dir, db_path=db_path)
        assert os.path.exists(os.path.join(output_dir, "health.json"))


# ---------------------------------------------------------------------------
# Alerts merged view
# ---------------------------------------------------------------------------

class TestAlertsMergedView:
    """alerts.json is the merged view of all country-level alerts files."""

    def test_merged_alerts_contains_all_country_alerts(self, tmp_path):
        output_dir = str(tmp_path)

        # Simulate UK run producing an alert.
        _write_status(output_dir, "uk", [
            {"name": "UKSource", "status": "success", "jobs_found": 5},
        ])
        generate_alerts(
            output_dir=output_dir,
            current_per_source=[{"name": "UKSource", "status": "success", "jobs_found": 0}],
            previous_status_path="",
            previous_alerts_path="",
            country="uk",
        )

        # Simulate US run producing an alert.
        _write_status(output_dir, "us", [
            {"name": "USSource", "status": "success", "jobs_found": 10},
        ])
        generate_alerts(
            output_dir=output_dir,
            current_per_source=[{"name": "USSource", "status": "success", "jobs_found": 0}],
            previous_status_path="",
            previous_alerts_path="",
            country="us",
        )

        with open(os.path.join(output_dir, "alerts.json")) as f:
            merged = json.load(f)

        sources_in_merged = {a["source"] for a in merged["alerts"]}
        assert "UKSource" in sources_in_merged
        assert "USSource" in sources_in_merged

    def test_per_country_file_written(self, tmp_path):
        output_dir = str(tmp_path)
        generate_alerts(
            output_dir=output_dir,
            current_per_source=[],
            previous_status_path="",
            previous_alerts_path="",
            country="brussels",
        )
        assert os.path.exists(os.path.join(output_dir, "alerts-brussels.json"))
