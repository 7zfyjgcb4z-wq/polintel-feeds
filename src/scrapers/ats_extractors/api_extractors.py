"""API-based ATS extractors — call JSON/XML endpoints directly.

Each extractor is an async class with a single extract(source) method.
source dict must have: name, category, country, org_static (or name), partisan_lean (optional).
For platform-specific credentials, source must have an 'identifier' dict.
"""
from __future__ import annotations

import asyncio
import html as _html_mod
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import USER_AGENT

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(30.0)
_DETAIL_DELAY = 0.5
_MAX_DESCRIPTIONS = 30


def _strip_html(s: str) -> str:
    if not s:
        return ""
    # Some APIs (e.g. Greenhouse) return HTML as entity-encoded text (&lt;div&gt;).
    # unescape first so BeautifulSoup sees real tags and get_text() strips them.
    decoded = _html_mod.unescape(s)
    return BeautifulSoup(decoded, "html.parser").get_text(" ", strip=True)


def _clip(s: str, n: int = 2000) -> str:
    return s[:n] if len(s) > n else s


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=_TIMEOUT,
    )


class BaseATSExtractor:
    async def extract(self, source: dict) -> list[Job]:
        raise NotImplementedError

    @staticmethod
    def _base(source: dict) -> dict[str, Any]:
        return dict(
            organisation=source.get("org_static") or source.get("name", ""),
            source_name=source.get("name", ""),
            category=source.get("category", "general"),
            country=source.get("country", "uk"),
            partisan_lean=source.get("partisan_lean"),
        )


class GreenhouseAPIExtractor(BaseATSExtractor):
    """GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        token = identifier.get("token", "")
        if not token:
            log.warning("Greenhouse: missing identifier.token for %s", source.get("name"))
            return []
        base = self._base(source)
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
        async with _client() as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                log.info("Greenhouse: board %r not found (empty or wrong token)", token)
                return []
            resp.raise_for_status()
            data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            title = (item.get("title") or "").strip()
            job_url = item.get("absolute_url", "")
            if not title or not job_url:
                continue
            location = (item.get("location") or {}).get("name")
            content = item.get("content") or ""
            description = _clip(_strip_html(content)) if content else ""
            posted_date = item.get("first_published") or item.get("updated_at")
            jobs.append(Job(title=title, url=job_url, description=description, location=location, posted_date=posted_date, **base))
        log.info("Greenhouse %s: %d jobs", token, len(jobs))
        return jobs


class LeverAPIExtractor(BaseATSExtractor):
    """GET https://api.lever.co/v0/postings/{company}?mode=json"""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        company = identifier.get("company", "")
        if not company:
            log.warning("Lever: missing identifier.company for %s", source.get("name"))
            return []
        base = self._base(source)
        url = f"https://api.lever.co/v0/postings/{company}?mode=json"
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        jobs = []
        for item in data:
            title = (item.get("text") or "").strip()
            job_url = item.get("hostedUrl", "")
            if not title or not job_url:
                continue
            cats = item.get("categories") or {}
            location = cats.get("location")
            plain = item.get("descriptionPlain") or ""
            description = _clip(plain) if plain else (cats.get("team") or "")
            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("Lever %s: %d jobs", company, len(jobs))
        return jobs


class AshbyAPIExtractor(BaseATSExtractor):
    """GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        board = identifier.get("board", "")
        if not board:
            log.warning("Ashby: missing identifier.board for %s", source.get("name"))
            return []
        base = self._base(source)
        url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            title = (item.get("title") or "").strip()
            job_url = item.get("jobUrl", "")
            if not title or not job_url:
                continue
            location = item.get("location")
            plain = item.get("descriptionPlain") or ""
            raw_html = item.get("descriptionHtml") or ""
            description = _clip(plain or _strip_html(raw_html))
            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("Ashby %s: %d jobs", board, len(jobs))
        return jobs


class BambooHRAPIExtractor(BaseATSExtractor):
    """List: GET https://{company}.bamboohr.com/careers/list
    Detail: GET https://{company}.bamboohr.com/careers/{id}/detail
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        company = identifier.get("company", "")
        if not company:
            log.warning("BambooHR: missing identifier.company for %s", source.get("name"))
            return []
        base = self._base(source)
        list_url = f"https://{company}.bamboohr.com/careers/list"
        async with _client() as client:
            resp = await client.get(list_url)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            fetched = 0
            for item in data.get("result", []):
                job_id = item.get("id")
                title = (item.get("jobOpeningName") or "").strip()
                if not title or not job_id:
                    continue
                job_url = f"https://{company}.bamboohr.com/careers/{job_id}"
                loc_obj = item.get("location") or {}
                if isinstance(loc_obj, dict):
                    parts = [loc_obj.get("city", ""), loc_obj.get("state", ""), loc_obj.get("country", "")]
                    location: str | None = ", ".join(p for p in parts if p) or None
                else:
                    location = str(loc_obj) if loc_obj else None
                description = ""
                posted_date = None
                if fetched < _MAX_DESCRIPTIONS:
                    try:
                        dr = await client.get(f"https://{company}.bamboohr.com/careers/{job_id}/detail")
                        if dr.status_code == 200:
                            dd = dr.json()
                            # Response: {result: {jobOpening: {description: ..., datePosted: ...}}}
                            job_opening = (dd.get("result") or {}).get("jobOpening") or dd
                            desc_html = job_opening.get("description") or ""
                            description = _clip(_strip_html(desc_html)) if desc_html else ""
                            posted_date = job_opening.get("datePosted")
                        fetched += 1
                        await asyncio.sleep(_DETAIL_DELAY)
                    except Exception as exc:
                        log.debug("BambooHR detail failed for id=%s: %s", job_id, exc)
                jobs.append(Job(title=title, url=job_url, description=description, location=location, posted_date=posted_date, **base))
        log.info("BambooHR %s: %d jobs", company, len(jobs))
        return jobs


class SmartRecruitersAPIExtractor(BaseATSExtractor):
    """GET https://api.smartrecruiters.com/v1/companies/{company_id}/postings"""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        company_id = identifier.get("company_id", "")
        if not company_id:
            log.warning("SmartRecruiters: missing identifier.company_id for %s", source.get("name"))
            return []
        base = self._base(source)
        url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings"
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            jobs = []
            fetched = 0
            for item in data.get("content", []):
                title = (item.get("name") or "").strip()
                posting_id = item.get("id", "")
                if not title:
                    continue
                job_url = item.get("ref") or f"https://jobs.smartrecruiters.com/{company_id}/{posting_id}"
                loc_obj = item.get("location") or {}
                if isinstance(loc_obj, dict):
                    parts = [loc_obj.get("city", ""), loc_obj.get("region", ""), loc_obj.get("country", "")]
                    location: str | None = ", ".join(p for p in parts if p) or None
                else:
                    location = None
                description = ""
                if fetched < _MAX_DESCRIPTIONS and posting_id:
                    try:
                        dr = await client.get(
                            f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{posting_id}"
                        )
                        if dr.status_code == 200:
                            dd = dr.json()
                            sections = (dd.get("jobAd") or {}).get("sections") or {}
                            desc_text = (sections.get("jobDescription") or {}).get("text", "")
                            description = _clip(_strip_html(desc_text)) if desc_text else ""
                        fetched += 1
                        await asyncio.sleep(_DETAIL_DELAY)
                    except Exception as exc:
                        log.debug("SmartRecruiters detail failed for %s: %s", posting_id, exc)
                jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("SmartRecruiters %s: %d jobs", company_id, len(jobs))
        return jobs


class WorkableAPIExtractor(BaseATSExtractor):
    """GET https://{account}.workable.com/spi/v3/jobs; falls back to apply.workable.com on 401."""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        account = identifier.get("account", "")
        if not account:
            log.warning("Workable: missing identifier.account for %s", source.get("name"))
            return []
        base = self._base(source)
        async with _client() as client:
            spi_url = f"https://{account}.workable.com/spi/v3/jobs"
            resp = await client.get(spi_url)
            if resp.status_code == 401:
                log.info("Workable SPI 401 for %s — trying apply API", source.get("name"))
                apply_url = f"https://apply.workable.com/api/v3/accounts/{account}/jobs"
                resp = await client.get(apply_url, params={"status": "published", "limit": 100})
                resp.raise_for_status()
            else:
                resp.raise_for_status()
            data = resp.json()
        jobs = []
        for item in data.get("results", []):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            job_url = item.get("url") or item.get("shortlink") or item.get("application_url") or ""
            loc = item.get("location") or {}
            if isinstance(loc, dict):
                location: str | None = loc.get("city") or loc.get("country_code")
            else:
                location = str(loc) if loc else None
            description = _clip(_strip_html(item.get("description") or ""))
            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("Workable %s: %d jobs", account, len(jobs))
        return jobs


class RecruiteeAPIExtractor(BaseATSExtractor):
    """GET https://{company}.recruitee.com/api/offers/"""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        company = identifier.get("company", "")
        if not company:
            log.warning("Recruitee: missing identifier.company for %s", source.get("name"))
            return []
        base = self._base(source)
        url = f"https://{company}.recruitee.com/api/offers/"
        async with _client() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        jobs = []
        for item in data.get("offers", []):
            title = (item.get("title") or "").strip()
            job_url = item.get("careers_url", "")
            if not title or not job_url:
                continue
            location = item.get("location") or item.get("city")
            desc_html = item.get("description") or ""
            description = _clip(_strip_html(desc_html)) if desc_html else ""
            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("Recruitee %s: %d jobs", company, len(jobs))
        return jobs


class WorkdayAPIExtractor(BaseATSExtractor):
    """POST https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    Paginates via offset. Derives tenant/dc/site from source URL when identifier absent.
    """

    _URL_RE = re.compile(
        r"https?://([^.]+)\.([^.]+)\.myworkdayjobs\.com(?:/[a-z]{2}-[A-Z]{2})?/([^/?#]+)"
    )

    def _parse_url(self, url: str) -> tuple[str, str, str] | None:
        m = self._URL_RE.match(url)
        return (m.group(1), m.group(2), m.group(3)) if m else None  # tenant, dc, site

    async def extract(self, source: dict, prefilter=None, postfilter=None) -> list[Job]:
        identifier = source.get("identifier") or {}
        tenant = identifier.get("tenant", "")
        dc = identifier.get("dc", "")
        site = identifier.get("site", "")
        if not all([tenant, dc, site]):
            parsed = self._parse_url(source.get("url", ""))
            if parsed:
                tenant, dc, site = parsed
                log.info("Workday %s: derived tenant=%r dc=%r site=%r", source.get("name"), tenant, dc, site)
            else:
                log.warning(
                    "Workday: cannot determine tenant/dc/site for %s — add identifier.tenant/dc/site",
                    source.get("name"),
                )
                return []
        base = self._base(source)
        jobs_url = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
        all_postings: list[dict] = []
        limit, offset = 20, 0
        total: int | None = None
        async with _client() as client:
            while True:
                resp = await client.post(
                    jobs_url,
                    json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""},
                )
                resp.raise_for_status()
                data = resp.json()
                if total is None:
                    total = data.get("total", 0)
                batch = data.get("jobPostings", [])
                all_postings.extend(batch)
                offset += limit
                if not batch or offset >= (total or 0):
                    break
        log.info("Workday %s/%s: %d postings (total=%d)", tenant, site, len(all_postings), total or 0)
        if prefilter is not None:
            _pre = len(all_postings)
            all_postings = [p for p in all_postings if prefilter(p)]
            log.info("Workday %s/%s: prefilter %d → %d", tenant, site, _pre, len(all_postings))
        detail_base = f"https://{tenant}.{dc}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
        jobs = []
        fetched = 0
        async with _client() as client:
            for p in all_postings:
                title = (p.get("title") or "").strip()
                ext_path = p.get("externalPath", "")
                if not title or not ext_path:
                    continue
                job_url = f"https://{tenant}.{dc}.myworkdayjobs.com/{site}{ext_path}"
                location = p.get("locationsText") or p.get("locationHierarchyReference")
                description_full = ""
                description = ""
                posted_date = None
                closing_date = None
                if fetched < _MAX_DESCRIPTIONS:
                    try:
                        dr = await client.get(f"{detail_base}{ext_path}")
                        if dr.status_code == 200:
                            dd = dr.json()
                            info = dd.get("jobPostingInfo", {})
                            desc_html = info.get("jobDescription") or ""
                            description_full = _strip_html(desc_html) if desc_html else ""
                            description = _clip(description_full) if description_full else ""
                            posted_date = info.get("startDate")
                            closing_date = info.get("endDate")
                        fetched += 1
                        await asyncio.sleep(_DETAIL_DELAY)
                    except Exception as exc:
                        log.debug("Workday detail failed for %s: %s", ext_path, exc)
                if postfilter is not None and not postfilter(title, description_full):
                    continue
                jobs.append(Job(
                    title=title, url=job_url, description=description,
                    location=location, posted_date=posted_date, closing_date=closing_date,
                    **base,
                ))
        return jobs


class OracleHCMAPIExtractor(BaseATSExtractor):
    """Oracle Recruiting Cloud (HCM CE).
    GET https://{api_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
    Identifier keys: api_host, site (site number e.g. CX_1001).
    """

    _FACETS = (
        "LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORY;"
        "BEREAVEMENT;FULL_PART_TIME;REGULAR_TEMPORARY;POSTING_DATES;FLEX_FIELDS"
    )

    async def extract(self, source: dict, prefilter=None, postfilter=None) -> list[Job]:
        identifier = source.get("identifier") or {}
        api_host = identifier.get("api_host", "")
        site = identifier.get("site", "")
        if not api_host or not site:
            log.warning("OracleHCM: missing identifier.api_host or identifier.site for %s", source.get("name"))
            return []
        base = self._base(source)
        base_url = f"https://{api_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        limit = 25
        offset = 0
        all_reqs: list[dict] = []
        total: int | None = None
        async with _client() as client:
            while True:
                finder = (
                    f"findReqs;siteNumber={site},"
                    f"facetsList={self._FACETS.replace(';', '%3B')},"
                    f"limit={limit},offset={offset},sortBy=POSTING_DATES_DESC"
                )
                params = {
                    "onlyData": "true",
                    "expand": "requisitionList.secondaryLocations,flexFieldsFacet.values",
                    "finder": finder,
                }
                resp = await client.get(base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
                item = data.get("items", [{}])[0] if data.get("items") else {}
                if total is None:
                    total = item.get("TotalJobsCount", 0)
                batch = item.get("requisitionList", [])
                all_reqs.extend(batch)
                offset += limit
                if not batch or offset >= (total or 0):
                    break
        log.info("OracleHCM %s/%s: %d jobs (total=%d)", api_host, site, len(all_reqs), total or 0)
        if prefilter is not None:
            _pre = len(all_reqs)
            all_reqs = [req for req in all_reqs if prefilter(req)]
            log.info("OracleHCM %s/%s: prefilter %d → %d", api_host, site, _pre, len(all_reqs))
        portal_base = f"https://{api_host}/hcmUI/CandidateExperience/en/sites/{site}"
        detail_base = f"https://{api_host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        jobs = []
        fetched = 0
        async with _client() as client:
            for req in all_reqs:
                job_id = req.get("Id")
                title = (req.get("Title") or "").strip()
                if not title or not job_id:
                    continue
                job_url = f"{portal_base}/job/{job_id}"
                location = req.get("PrimaryLocation") or None
                posted_date = req.get("PostedDate")
                closing_date = None
                description_full = ""
                description = ""
                if fetched < _MAX_DESCRIPTIONS:
                    try:
                        dr = await client.get(
                            detail_base,
                            params={"onlyData": "true", "finder": f"ById;Id={job_id},siteNumber={site}"},
                        )
                        if dr.status_code == 200:
                            dd = dr.json()
                            detail = (dd.get("items") or [{}])[0]
                            desc_html = detail.get("ExternalDescriptionStr") or ""
                            description_full = _strip_html(desc_html) if desc_html else ""
                            description = _clip(description_full) if description_full else ""
                            closing_date = detail.get("ExternalPostedEndDate")
                        fetched += 1
                        await asyncio.sleep(_DETAIL_DELAY)
                    except Exception as exc:
                        log.debug("OracleHCM detail failed for id=%s: %s", job_id, exc)
                if postfilter is not None and not postfilter(title, description_full):
                    continue
                jobs.append(Job(
                    title=title, url=job_url, description=description,
                    location=location, posted_date=posted_date, closing_date=closing_date,
                    **base,
                ))
        return jobs


class PaylocityExtractor(BaseATSExtractor):
    """Parses window.pageData.Jobs[] from the Paylocity recruiting HTML page.
    Identifier key: guid (the UUID in the /recruiting/jobs/All/{guid}/... URL).
    Optional: slug (company name slug for URL construction; defaults to 'careers').
    """

    _PAGE_DATA_RE = re.compile(r"window\.pageData\s*=\s*(\{.*?\});", re.DOTALL)

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        guid = identifier.get("guid", "")
        slug = identifier.get("slug", "careers")
        if not guid:
            log.warning("Paylocity: missing identifier.guid for %s", source.get("name"))
            return []
        base = self._base(source)
        page_url = f"https://recruiting.paylocity.com/recruiting/jobs/All/{guid}/{slug}"
        async with _client() as client:
            resp = await client.get(page_url)
            resp.raise_for_status()
            html = resp.text
        m = self._PAGE_DATA_RE.search(html)
        if not m:
            log.warning("Paylocity: window.pageData not found for %s", source.get("name"))
            return []
        try:
            page_data = __import__("json").loads(m.group(1))
        except Exception as exc:
            log.warning("Paylocity: failed to parse pageData for %s: %s", source.get("name"), exc)
            return []
        raw_jobs = page_data.get("Jobs") or []
        jobs = []
        for item in raw_jobs:
            title = (item.get("JobTitle") or "").strip()
            job_id = item.get("JobId") or item.get("Id")
            if not title or not job_id:
                continue
            job_url = f"https://recruiting.paylocity.com/Recruiting/Jobs/Details/{guid}/{job_id}"
            location = (
                item.get("LocationName")
                or item.get("Location")
                or (item.get("JobLocation") or {}).get("Name")
                or None
            )
            desc_html = item.get("Description") or item.get("JobDescription") or ""
            description = _clip(_strip_html(desc_html)) if desc_html else ""
            posted_date = item.get("PublishedDate")
            jobs.append(Job(title=title, url=job_url, description=description, location=location, posted_date=posted_date, **base))
        log.info("Paylocity %s: %d jobs", guid[:8], len(jobs))
        return jobs


class PersonioAPIExtractor(BaseATSExtractor):
    """GET https://{subdomain}.jobs.personio.de/xml (falls back to .com on 404). Parses XML with lxml."""

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        subdomain = identifier.get("subdomain", "")
        if not subdomain:
            log.warning("Personio: missing identifier.subdomain for %s", source.get("name"))
            return []
        base = self._base(source)
        async with _client() as client:
            resp = await client.get(f"https://{subdomain}.jobs.personio.de/xml")
            if resp.status_code == 404:
                log.info("Personio .de 404 for %s — trying .com", source.get("name"))
                resp = await client.get(f"https://{subdomain}.jobs.personio.com/xml")
            resp.raise_for_status()
            xml_bytes = resp.content
        from lxml import etree  # noqa: PLC0415
        try:
            root = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError:
            root = etree.fromstring(xml_bytes, parser=etree.XMLParser(recover=True))
        jobs = []
        for position in root.iter("position"):
            title_el = position.find("name")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue
            id_el = position.find("id")
            job_id = (id_el.text or "").strip() if id_el is not None else ""
            if not job_id:
                continue
            job_url = f"https://{subdomain}.jobs.personio.de/job/{job_id}"
            office_el = position.find("office")
            location: str | None = (office_el.text or "").strip() if office_el is not None else None
            location = location or None
            desc_html = ""
            desc_el = position.find("description")
            if desc_el is not None:
                desc_html = etree.tostring(desc_el, encoding="unicode", method="html")
            else:
                for jd in position.iter("jobDescription"):
                    val = jd.find("value")
                    if val is not None:
                        desc_html += etree.tostring(val, encoding="unicode", method="html")
            description = _clip(_strip_html(desc_html)) if desc_html else ""
            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
        log.info("Personio %s: %d jobs", subdomain, len(jobs))
        return jobs


class TeamTailorAPIExtractor(BaseATSExtractor):
    """TeamTailor careers portal via JSON Feed 1.1.
    GET https://{base_url}/jobs.json — paginated via next_url in feed root.
    Identifier key: base_url (e.g. careers.idea.int).
    Full description from _jobposting.description; location from _jobposting.jobLocation.
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        base_url = identifier.get("base_url", "")
        if not base_url:
            log.warning("TeamTailor: missing identifier.base_url for %s", source.get("name"))
            return []
        base = self._base(source)
        feed_url: str | None = f"https://{base_url}/jobs.json"
        all_items: list[dict] = []
        async with _client() as client:
            while feed_url:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                data = resp.json()
                all_items.extend(data.get("items", []))
                feed_url = data.get("next_url")
        jobs = []
        for item in all_items:
            title = (item.get("title") or "").strip()
            job_url = item.get("url") or ""
            if not title or not job_url:
                continue
            jp = item.get("_jobposting") or {}
            desc_html = jp.get("description") or item.get("content_html") or ""
            description = _clip(_strip_html(desc_html)) if desc_html else ""
            posted_date = jp.get("datePosted") or item.get("date_published")
            closing_date = jp.get("validThrough")
            loc_list = jp.get("jobLocation") or []
            if isinstance(loc_list, dict):
                loc_list = [loc_list]
            addr = (loc_list[0] if loc_list else {}).get("address") or {}
            location = addr.get("addressLocality") or addr.get("addressCountry") or None
            jobs.append(Job(
                title=title, url=job_url, description=description,
                location=location, posted_date=posted_date, closing_date=closing_date,
                **base,
            ))
        log.info("TeamTailor %s: %d jobs", base_url, len(jobs))
        return jobs


class ICIMSExtractor(BaseATSExtractor):
    """iCIMS careers portal — parses the public search iframe HTML.
    Identifier key: subdomain (e.g. 'careers-brookings' for careers-brookings.icims.com).
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        subdomain = identifier.get("subdomain", "")
        if not subdomain:
            log.warning("iCIMS: missing identifier.subdomain for %s", source.get("name"))
            return []
        base = self._base(source)
        search_url = f"https://{subdomain}.icims.com/jobs/search?searchResults=true&ss=1&in_iframe=1"
        async with _client() as client:
            resp = await client.get(search_url)
            resp.raise_for_status()
            html = resp.text
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for card in soup.select("li.iCIMS_JobCardItem"):
            title_el = card.select_one(".title h3") or card.select_one("h3")
            link_el = card.select_one("a.iCIMS_Anchor") or card.select_one("a[href]")
            if not title_el or not link_el:
                continue
            title = title_el.get_text(" ", strip=True)
            href = link_el.get("href", "")
            if not href:
                continue
            job_url = href if href.startswith("http") else f"https://{subdomain}.icims.com{href}"
            location_el = card.select_one(".iCIMS_ListJobLocation") or card.select_one(".job-location")
            location: str | None = location_el.get_text(" ", strip=True) if location_el else None
            jobs.append(Job(title=title, url=job_url, description="", location=location, **base))
        log.info("iCIMS %s: %d jobs", subdomain, len(jobs))
        return jobs


class CornerstoneExtractor(BaseATSExtractor):
    """Cornerstone OnDemand (csod.com) careers site — scrapes the HTML listing page.
    Identifier keys: account (e.g. 'worldbank'), site_id (numeric career site ID, e.g. '1').
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        account = identifier.get("account", "")
        site_id = identifier.get("site_id", "1")
        if not account:
            log.warning("Cornerstone: missing identifier.account for %s", source.get("name"))
            return []
        base = self._base(source)
        list_url = f"https://{account}.csod.com/ux/ats/careersite/{site_id}/home"
        async with _client() as client:
            resp = await client.get(list_url)
            resp.raise_for_status()
            html = resp.text
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        # Cornerstone renders a JSON array in a script tag: window.__csodInitialState__
        import json as _json
        for script in soup.find_all("script"):
            text = script.string or ""
            if "__csodInitialState__" in text or "requisitions" in text.lower():
                # Try to extract JSON
                m = re.search(r"window\.__csodInitialState__\s*=\s*(\{.*\})", text, re.DOTALL)
                if m:
                    try:
                        state = _json.loads(m.group(1))
                        reqs = (
                            state.get("careerSiteJobListState", {})
                            .get("jobList", {})
                            .get("requisitionList", [])
                        )
                        for req in reqs:
                            title = (req.get("RequisitionTitle") or "").strip()
                            req_id = req.get("RequisitionId") or req.get("Id")
                            if not title or not req_id:
                                continue
                            job_url = f"https://{account}.csod.com/ux/ats/careersite/{site_id}/requisition/{req_id}"
                            location = req.get("JobLocation") or req.get("Location") or None
                            desc_html = req.get("JobDescription") or ""
                            description = _clip(_strip_html(desc_html)) if desc_html else ""
                            jobs.append(Job(title=title, url=job_url, description=description, location=location, **base))
                        if jobs:
                            log.info("Cornerstone %s (JSON): %d jobs", account, len(jobs))
                            return jobs
                    except Exception as exc:
                        log.debug("Cornerstone JSON parse failed for %s: %s", account, exc)
        # Fallback: try HTML cards
        for card in soup.select(".csod-job-item, li.requisition-item, div.job-listing-item"):
            link_el = card.select_one("a[href]")
            if not link_el:
                continue
            title = link_el.get_text(" ", strip=True)
            href = link_el.get("href", "")
            job_url = href if href.startswith("http") else f"https://{account}.csod.com{href}"
            jobs.append(Job(title=title, url=job_url, description="", **base))
        log.info("Cornerstone %s (HTML): %d jobs", account, len(jobs))
        return jobs


class ApplicantProExtractor(BaseATSExtractor):
    """ApplicantPro (isolved Talent Acquisition) — parses the public job listing page.
    Identifier key: subdomain (e.g. 'carnegieendowment' for carnegieendowment.applicantpro.com).
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        subdomain = identifier.get("subdomain", "")
        if not subdomain:
            log.warning("ApplicantPro: missing identifier.subdomain for %s", source.get("name"))
            return []
        base = self._base(source)
        list_url = f"https://{subdomain}.applicantpro.com/jobs/"
        async with _client() as client:
            resp = await client.get(list_url)
            resp.raise_for_status()
            html = resp.text
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for card in soup.select("li.list-group-item, div.job-item"):
            link_el = card.select_one("h3.list-group-item-heading a, h3 a, a.job-title")
            if not link_el:
                continue
            title = link_el.get_text(" ", strip=True)
            href = link_el.get("href", "")
            if not href:
                continue
            job_url = href if href.startswith("http") else f"https://{subdomain}.applicantpro.com{href}"
            jobs.append(Job(title=title, url=job_url, description="", **base))
        log.info("ApplicantPro %s: %d jobs", subdomain, len(jobs))
        return jobs


class ApplicantStackExtractor(BaseATSExtractor):
    """ApplicantStack (WizeHire) — parses the public openings page.
    Identifier key: subdomain (e.g. 'heritage' for heritage.applicantstack.com).
    """

    async def extract(self, source: dict) -> list[Job]:
        identifier = source.get("identifier") or {}
        subdomain = identifier.get("subdomain", "")
        if not subdomain:
            log.warning("ApplicantStack: missing identifier.subdomain for %s", source.get("name"))
            return []
        base = self._base(source)
        list_url = f"https://{subdomain}.applicantstack.com/x/openings"
        async with _client() as client:
            resp = await client.get(list_url)
            resp.raise_for_status()
            html = resp.text
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        for row in soup.select("tr.as-job-row, div.opening-item, li.opening"):
            link_el = row.select_one("a[href]")
            if not link_el:
                continue
            title = link_el.get_text(" ", strip=True)
            href = link_el.get("href", "")
            if not href:
                continue
            job_url = href if href.startswith("http") else f"https://{subdomain}.applicantstack.com{href}"
            location_el = row.select_one(".location, td.location-col")
            location: str | None = location_el.get_text(" ", strip=True) if location_el else None
            jobs.append(Job(title=title, url=job_url, description="", location=location, **base))
        log.info("ApplicantStack %s: %d jobs", subdomain, len(jobs))
        return jobs


# ── Registry ──────────────────────────────────────────────────────────────────

PLATFORM_EXTRACTORS: dict[str, BaseATSExtractor] = {
    "greenhouse": GreenhouseAPIExtractor(),
    "lever": LeverAPIExtractor(),
    "ashby": AshbyAPIExtractor(),
    "bamboohr": BambooHRAPIExtractor(),
    "smartrecruiters": SmartRecruitersAPIExtractor(),
    "workable": WorkableAPIExtractor(),
    "recruitee": RecruiteeAPIExtractor(),
    "workday": WorkdayAPIExtractor(),
    "personio": PersonioAPIExtractor(),
    "oracle_hcm": OracleHCMAPIExtractor(),
    "paylocity": PaylocityExtractor(),
    "teamtailor": TeamTailorAPIExtractor(),
    "icims": ICIMSExtractor(),
    "cornerstone": CornerstoneExtractor(),
    "applicantpro": ApplicantProExtractor(),
    "applicantstack": ApplicantStackExtractor(),
}

# ── URL-pattern detection (no HTTP call) ─────────────────────────────────────

_URL_PATTERNS: list[tuple[str, str]] = [
    ("boards.greenhouse.io", "greenhouse"),
    ("job-boards.greenhouse.io", "greenhouse"),
    ("jobs.lever.co", "lever"),
    ("ashbyhq.com", "ashby"),
    (".bamboohr.com", "bamboohr"),
    ("jobs.smartrecruiters.com", "smartrecruiters"),
    (".workable.com", "workable"),
    (".recruitee.com", "recruitee"),
    ("myworkdayjobs.com", "workday"),
    ("jobs.personio.de", "personio"),
    ("jobs.personio.com", "personio"),
    (".pinpointhq.com", "pinpoint"),
    ("career.teamtailor.com", "teamtailor"),
    ("app.beapplied.com", "applied"),
    ("applytojob.com", "jazzhr"),
    ("jazzhrhire.com", "jazzhr"),
    ("taleo.net", "taleo"),
    ("recruiting.paylocity.com", "paylocity"),
    ("fa.em1.ukg.oraclecloud.com", "oracle_hcm"),
    ("fa.em2.ukg.oraclecloud.com", "oracle_hcm"),
    ("fa.eu.oraclecloud.com", "oracle_hcm"),
    (".icims.com", "icims"),
    ("icims.com", "icims"),
    (".csod.com", "cornerstone"),
    ("csod.com", "cornerstone"),
    (".applicantpro.com", "applicantpro"),
    ("applicantpro.com", "applicantpro"),
    (".applicantstack.com", "applicantstack"),
    ("applicantstack.com", "applicantstack"),
    (".workable.com/spi", "workable"),
    ("apply.workable.com", "workable"),
]


def detect_ats_by_url(url: str) -> str | None:
    """Detect ATS platform from URL pattern alone (no HTTP call)."""
    if not url:
        return None
    u = url.lower()
    for pattern, platform in _URL_PATTERNS:
        if pattern in u:
            return platform
    return None
