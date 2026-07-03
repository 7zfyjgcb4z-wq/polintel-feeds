from __future__ import annotations

import xml.etree.ElementTree as ET

from src.db.store import JobStore
from src.feed.generator import POLINTEL_NS, generate_feeds
from src.models.job import Job


def _make_job(**overrides) -> Job:
    defaults = dict(
        title="Policy Officer",
        url="https://example.com/jobs/1",
        organisation="Example Org",
        description="A description of the role.",
        source_name="test-source",
        category="general",
    )
    defaults.update(overrides)
    return Job(**defaults)


def _generate(tmp_path, jobs, country="uk"):
    out_dir = str(tmp_path / "feeds")
    generate_feeds(jobs, out_dir, country=country)
    return out_dir


def _find_item(out_dir, country, category, url):
    tree = ET.parse(f"{out_dir}/{country}-{category}.xml")
    channel = tree.getroot().find("channel")
    for item in channel.findall("item"):
        guid_el = item.find("guid")
        if guid_el is not None and guid_el.text == url:
            return item
    return None


def test_no_posted_date_means_no_pubdate(tmp_path):
    job = _make_job(posted_date=None)
    out_dir = _generate(tmp_path, [job])
    item = _find_item(out_dir, "uk", "general", job.url)
    assert item is not None
    assert item.find("pubDate") is None


def test_posted_date_produces_midnight_utc_pubdate(tmp_path):
    job = _make_job(posted_date="2026-04-23")
    out_dir = _generate(tmp_path, [job])
    item = _find_item(out_dir, "uk", "general", job.url)
    pub_date = item.find("pubDate")
    assert pub_date is not None
    assert pub_date.text == "Thu, 23 Apr 2026 00:00:00 +0000"


def test_closing_date_element_emitted(tmp_path):
    job = _make_job(closing_date="2026-06-08")
    out_dir = _generate(tmp_path, [job])
    item = _find_item(out_dir, "uk", "general", job.url)
    el = item.find(f"{{{POLINTEL_NS}}}closingDate")
    assert el is not None
    assert el.text == "2026-06-08"


def test_every_item_carries_description_source(tmp_path):
    jobs = [
        _make_job(url="https://example.com/jobs/1", description_source="api"),
        _make_job(url="https://example.com/jobs/2", description="", description_source="none"),
    ]
    out_dir = _generate(tmp_path, jobs)
    for job in jobs:
        item = _find_item(out_dir, "uk", "general", job.url)
        el = item.find(f"{{{POLINTEL_NS}}}descriptionSource")
        assert el is not None
        assert el.text == job.description_source


def test_long_description_clipped_at_space(tmp_path):
    long_desc = ("word " * 3000).strip()  # well over 10,000 chars
    job = _make_job(description=long_desc)
    out_dir = _generate(tmp_path, [job])
    item = _find_item(out_dir, "uk", "general", job.url)
    desc_el = item.find("description")
    assert desc_el is not None
    assert len(desc_el.text) <= 10000
    assert not desc_el.text.endswith(" ")


def test_empty_description_still_produces_item(tmp_path):
    job = _make_job(description="")
    out_dir = _generate(tmp_path, [job])
    item = _find_item(out_dir, "uk", "general", job.url)
    assert item is not None
    desc_el = item.find("description")
    assert desc_el is not None
    assert (desc_el.text or "") == ""


def test_organisation_accent_roundtrips_through_db(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)
    try:
        job = _make_job(organisation="Fédération")
        store.upsert_jobs([job])
        jobs = store.get_active_jobs(country="uk")
        assert jobs[0].organisation == "Fédération"

        out_dir = _generate(tmp_path, jobs)
        item = _find_item(out_dir, "uk", "general", job.url)
        creator = item.find("{http://purl.org/dc/elements/1.1/}creator")
        assert creator is not None
        assert creator.text == "Fédération"
    finally:
        store.close()
