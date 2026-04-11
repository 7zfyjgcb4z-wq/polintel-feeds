from __future__ import annotations

import pytest

from src.scrapers.rss_feed_scraper import RSSFeedScraper, _strip_html, _is_thin_description

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Policy Jobs</title>
    <link>https://example.com</link>
    <description>Policy jobs feed</description>
    <item>
      <title>Senior Policy Analyst</title>
      <link>https://example.com/jobs/1</link>
      <author>Institute for Government</author>
      <description>A detailed role working on fiscal policy, budgeting, and public finance reform.
        The successful candidate will support senior fellows and produce high-quality research outputs
        on behalf of a leading Westminster think tank. Based in central London with hybrid working options
        available. Salary competitive. Applications open to all.</description>
      <pubDate>Fri, 11 Apr 2026 09:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Head of Communications</title>
      <link>https://example.com/jobs/2</link>
      <author>jobs@example.com</author>
      <description>Short desc</description>
      <category>Public Affairs</category>
      <pubDate>Fri, 10 Apr 2026 09:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Parliamentary Affairs Officer</title>
      <link>https://example.com/jobs/3</link>
      <description>Policy | Westminster | £35,000</description>
      <pubDate>Thu, 09 Apr 2026 09:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""

FIELD_MAP = {
    "title": "title",
    "organisation": "author",
    "description": "description",
    "link": "link",
    "date": "published",
}

SOURCE_CONFIG = {
    "name": "Test Feed",
    "category": "general",
    "country": "uk",
}


@pytest.mark.asyncio
async def test_scrape_from_string_url(tmp_path):
    """Use a local file path as RSS URL."""
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert len(jobs) == 3


@pytest.mark.asyncio
async def test_extracts_title(tmp_path):
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert jobs[0].title == "Senior Policy Analyst"
    assert jobs[1].title == "Head of Communications"


@pytest.mark.asyncio
async def test_extracts_link(tmp_path):
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert jobs[0].url == "https://example.com/jobs/1"


@pytest.mark.asyncio
async def test_ignores_email_author(tmp_path):
    """Author with @ should be ignored; falls back to source_name."""
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert jobs[1].organisation == "Test Feed"


@pytest.mark.asyncio
async def test_keeps_valid_author(tmp_path):
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert jobs[0].organisation == "Institute for Government"


@pytest.mark.asyncio
async def test_thin_description_flagged(tmp_path):
    """Short or pipe-delimited descriptions should be flagged for enrichment."""
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert getattr(jobs[1], "_needs_enrichment", False) is True
    assert getattr(jobs[2], "_needs_enrichment", False) is True


@pytest.mark.asyncio
async def test_substantive_description_not_flagged(tmp_path):
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, SOURCE_CONFIG)
    assert getattr(jobs[0], "_needs_enrichment", True) is False


@pytest.mark.asyncio
async def test_org_static_overrides_author(tmp_path):
    rss_file = tmp_path / "feed.xml"
    rss_file.write_text(SAMPLE_RSS)
    config = {**SOURCE_CONFIG, "org_static": "W4MP"}
    scraper = RSSFeedScraper()
    jobs = await scraper.scrape(str(rss_file), FIELD_MAP, config)
    assert all(j.organisation == "W4MP" for j in jobs)


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert _strip_html("") == ""


def test_is_thin_description():
    assert _is_thin_description("") is True
    assert _is_thin_description("Short text") is True
    assert _is_thin_description("Policy | Westminster | £35,000") is True
    long = "x" * 250
    assert _is_thin_description(long) is False
