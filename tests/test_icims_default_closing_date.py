"""iCIMS publishes validThrough as datePosted plus one year when no deadline was set (Brookings, CFR, AEI)."""
from __future__ import annotations

from pathlib import Path

from src.enrichment.readability_enricher import _parse_job_ld, is_default_valid_through

FIXTURE = Path(__file__).parent / "fixtures" / "icims_brookings_jobposting.html"


def _ld(posted: str, through: str | None) -> str:
    extra = f', "validThrough": "{through}"' if through else ""
    return (
        '<script type="application/ld+json">{"@type": "JobPosting", "title": "x", '
        f'"datePosted": "{posted}"{extra}}}</script>'
    )


def test_brookings_default_closing_date_is_dropped():
    meta = _parse_job_ld(FIXTURE.read_text())
    assert meta["closing_date"] is None
    assert meta["organisation"] == "The Brookings Institution"
    assert meta["location"] == "Washington, DC"


def test_window_is_364_to_366_days():
    for days_through in ("2027-10-22", "2027-10-23", "2027-10-24"):
        assert is_default_valid_through("2026-10-23T04:00:00.000Z", days_through)
    assert not is_default_valid_through("2026-10-23", "2027-10-21")
    assert not is_default_valid_through("2026-10-23", "2027-10-25")


def test_real_deadline_is_kept():
    meta = _parse_job_ld(_ld("2026-10-23T04:00:00.000Z", "2026-11-20T23:59:00.000Z"))
    assert meta["closing_date"] == "2026-11-20"


def test_missing_or_unparseable_dates_keep_the_value():
    assert _parse_job_ld(_ld("2026-10-23", "2027-10-23"))["closing_date"] is None
    assert _parse_job_ld('<script type="application/ld+json">{"@type": "JobPosting", "validThrough": "2027-10-23"}</script>')["closing_date"] == "2027-10-23"
    assert not is_default_valid_through(None, "2027-10-23")
    assert not is_default_valid_through("not a date", "2027-10-23")
