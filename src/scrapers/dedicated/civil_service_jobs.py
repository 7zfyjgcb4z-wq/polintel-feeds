"""
Civil Service Jobs scraper.

Anti-bot: ALTCHA SHA-512 proof-of-work challenge. Solved in pure Python.
Pagination: SID-encoded base64 querystrings; we follow "Next" links from the HTML.
Search mode: Runs targeted keyword searches instead of a blank all-results search.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from src.models.job import Job
from src.scrapers.base import BaseScraper, USER_AGENT, REQUEST_DELAY

log = logging.getLogger(__name__)

BASE = "https://www.civilservicejobs.service.gov.uk"
JOBS_URL = f"{BASE}/csr/jobs.cgi"
INDEX_URL = f"{BASE}/csr/index.cgi"
MAX_PAGES_PER_KEYWORD = 10  # 25 results/page → up to 250 per keyword

# Sort value for the "Refresh sort" GET form on the results page
# (<select name="sort" id="new_search_sort_order">; value "opening" = Most recent).
# The initial esearch POST ignores this parameter; the sort must be applied by
# following the results-page Refresh sort form (GET /csr/index.cgi?sort=opening&…).
# Diagnosis: DIAGNOSTIC_csj_capture_2026-09-09.md — Step 1 measurement.
CSJ_SORT = "opening"

# Keyword list trimmed 2026-09-10 (fix/csj-sort-newest-first).
# Under sort=opening (most-recent), the first 75 most-recently-posted civil service
# jobs match every broad keyword; 19 of 25 original keywords contributed zero unique
# rows at 3-page (75-row) depth.  The six below are retained: the first four because
# they are mandatory keeps per the design spec, the last two because they may surface
# niche cohorts (Fast Stream, Diplomatic) that sit deeper in the result sets.
SEARCH_KEYWORDS = [
    "policy",
    "analyst",
    "parliamentary",
    "diplomatic",
    "graduate scheme",
    "fast stream",
]


# Parameters within the decoded SID blob that identify a specific vacancy.
# All other inner params are either session-bound or navigational.
_CSJ_VACANCY_PARAMS = frozenset({"joblist_view_vac", "jcode"})

# Parameters that are session-bound at the top-level query string (non-SID URLs).
_CSJ_SESSION_PARAMS = frozenset({
    "SID", "usersearchcontext", "reqsig", "csession", "lastpage",
    "searchpage", "id_postcodeselectorid",
})

# Inner params (inside the decoded SID blob) that are session-bound and vary per ALTCHA solve.
_CSJ_SESSION_INNER_PARAMS = frozenset({
    "usersearchcontext", "reqsig", "csession", "lastpage",
    "searchpage", "id_postcodeselectorid",
})


def _canonical_csj_url(raw_url: str) -> str:
    """
    Return a stable canonical URL for a CSJ vacancy.

    CSJ vacancy URLs use a single ``SID`` query parameter that is a base64-encoded
    query string containing both the stable vacancy identifier (``joblist_view_vac``)
    and session-bound values (``usersearchcontext``, ``reqsig``) that change with
    every ALTCHA solve.  The canonical form decodes the blob and retains only the
    vacancy identifier, yielding a URL that is stable across scraper runs.

    Falls back to the raw URL unchanged if decoding fails or no vacancy identifier
    can be extracted.
    """
    parsed = urlparse(raw_url)
    qs = parse_qs(parsed.query, keep_blank_values=False)

    if "SID" in qs:
        # The SID value is a base64-encoded inner query string.
        try:
            sid_raw = qs["SID"][0]
            # Pad to a valid base64 length before decoding.
            inner_qs_str = base64.b64decode(sid_raw + "==").decode("utf-8", errors="replace")
            inner_params = parse_qs(inner_qs_str, keep_blank_values=False)
            stable = {k: v for k, v in inner_params.items() if k in _CSJ_VACANCY_PARAMS}
            if stable:
                # Sort for deterministic ordering across runs.
                canonical_query = urlencode(sorted(stable.items()), doseq=True)
                return parsed._replace(query=canonical_query).geturl()
        except Exception:
            pass
        # Could not extract a vacancy identifier; return the original URL unchanged.
        return raw_url

    # Non-SID URL (e.g. a direct jobs.cgi?jcode=... link): strip session-bound params.
    stable = {k: v for k, v in qs.items() if k not in _CSJ_SESSION_PARAMS}
    if stable:
        canonical_query = urlencode(sorted(stable.items()), doseq=True)
        return parsed._replace(query=canonical_query).geturl()
    return raw_url


class Scraper(BaseScraper):
    async def scrape(self) -> list[Job]:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            try:
                await self._solve_altcha(client)
            except Exception as e:
                self.log.error(f"ALTCHA failed: {e}")
                raise

            all_jobs: list[Job] = []
            seen_urls: set[str] = set()

            for keyword in SEARCH_KEYWORDS:
                keyword_jobs = await self._search_keyword(client, keyword, seen_urls)
                all_jobs.extend(keyword_jobs)
                self.log.info(
                    f"Keyword '{keyword}': {len(keyword_jobs)} new unique jobs"
                )

            self.log.info(
                f"Total: {len(all_jobs)} unique jobs across {len(SEARCH_KEYWORDS)} keyword searches"
            )
            return all_jobs

    async def _search_keyword(
        self, client: httpx.AsyncClient, keyword: str, seen_urls: set[str]
    ) -> list[Job]:
        """Run a single keyword search and paginate through results."""
        # Fetch home page for a fresh esearch form + SID for each keyword
        try:
            r_home = await client.get(JOBS_URL)
            r_home.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
        except Exception as e:
            self.log.warning(f"Home page fetch failed for keyword '{keyword}': {e}")
            return []

        soup_home = BeautifulSoup(r_home.text, "lxml")
        esearch_form = soup_home.find(
            "form", {"action": lambda x: x and "esearch" in x}
        )
        if not esearch_form:
            self.log.warning(
                f"Could not find esearch form for keyword '{keyword}'"
            )
            return []

        esearch_action = esearch_form["action"]
        sid_input = esearch_form.find("input", {"name": "SID"})
        if not sid_input:
            self.log.warning(f"No SID input for keyword '{keyword}'")
            return []
        search_sid = sid_input["value"]

        form_data = {
            "id_postcodeselectorid": "#where",
            "distance": "10",
            "units": "miles",
            "SID": search_sid,
            "csource": "csqsearch",
            "easting": "",
            "northing": "",
            "region": "",
            "whatoption": "words",
            "overseas": "1",
            "keyword": keyword,
        }

        try:
            r_results = await client.post(esearch_action, data=form_data)
            r_results.raise_for_status()
            await asyncio.sleep(REQUEST_DELAY)
        except Exception as e:
            self.log.warning(f"Search POST failed for keyword '{keyword}': {e}")
            return []

        keyword_jobs: list[Job] = []
        current_soup = BeautifulSoup(r_results.text, "lxml")

        # Apply CSJ_SORT via the results-page "Refresh sort" form (GET index.cgi).
        # The initial esearch POST always returns sort=closing (server default);
        # the sort control is only honoured through this extra GET step.
        sort_url = self._sort_refresh_url(current_soup)
        if sort_url:
            try:
                r_sorted = await client.get(sort_url)
                r_sorted.raise_for_status()
                await asyncio.sleep(REQUEST_DELAY)
                current_soup = BeautifulSoup(r_sorted.text, "lxml")
                r_results = r_sorted
            except httpx.HTTPError as e:
                self.log.warning(
                    f"Sort refresh failed for keyword '{keyword}': {e}; "
                    "falling back to closing-date sort"
                )
        else:
            self.log.warning(
                f"'Refresh sort' form not found for keyword '{keyword}'; "
                "falling back to closing-date sort"
            )

        page_num = 0

        while page_num < MAX_PAGES_PER_KEYWORD:
            page_num += 1

            if "Quick Check Needed" in r_results.text:
                self.log.warning(
                    f"ALTCHA re-triggered on keyword '{keyword}', stopping pagination"
                )
                break

            page_jobs = self._parse_jobs(current_soup)
            for job in page_jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    keyword_jobs.append(job)

            self.log.debug(
                f"Keyword '{keyword}' page {page_num}: {len(page_jobs)} jobs on page"
            )

            if not page_jobs:
                break

            next_url = self._next_page_url(current_soup)
            if not next_url:
                break

            try:
                r_next = await client.get(next_url)
                r_next.raise_for_status()
                await asyncio.sleep(REQUEST_DELAY)
                current_soup = BeautifulSoup(r_next.text, "lxml")
                r_results = r_next
            except httpx.HTTPError as e:
                self.log.error(
                    f"Page {page_num + 1} fetch failed for keyword '{keyword}': {e}"
                )
                break

        return keyword_jobs

    # ------------------------------------------------------------------ #
    # ALTCHA solver                                                         #
    # ------------------------------------------------------------------ #

    async def _solve_altcha(self, client: httpx.AsyncClient) -> None:
        """Solve the ALTCHA SHA-512 proof-of-work and establish session."""
        # Step 1: fetch challenge JSON
        r = await client.get(f"{JOBS_URL}?ProtectCaptcha=1")
        r.raise_for_status()
        challenge_data = r.json()

        salt = challenge_data["salt"]
        challenge = challenge_data["challenge"]
        max_number = int(challenge_data.get("maxnumber", 300000))
        algorithm = challenge_data.get("algorithm", "SHA-512").upper()

        self.log.debug(f"ALTCHA challenge received (max_number={max_number})")

        # Step 2: brute-force PoW
        number = None
        for i in range(max_number + 1):
            if algorithm == "SHA-256":
                digest = hashlib.sha256(f"{salt}{i}".encode()).hexdigest()
            else:
                digest = hashlib.sha512(f"{salt}{i}".encode()).hexdigest()
            if digest == challenge:
                number = i
                break

        if number is None:
            raise RuntimeError(f"ALTCHA PoW unsolvable in {max_number} iterations")

        self.log.debug(f"ALTCHA solved: number={number}")

        # Step 3: build base64 payload
        payload = {
            "algorithm": challenge_data.get("algorithm", "SHA-512"),
            "challenge": challenge,
            "number": number,
            "salt": salt,
            "signature": challenge_data["signature"],
        }
        payload_b64 = base64.b64encode(json.dumps(payload).encode()).decode()

        # Step 4: fetch base page to get originalRequestToken
        r2 = await client.get(JOBS_URL)
        r2.raise_for_status()
        soup2 = BeautifulSoup(r2.text, "lxml")
        token_input = soup2.find("input", {"name": "originalRequestToken"})
        if not token_input:
            raise RuntimeError("originalRequestToken not found on challenge page")
        token = token_input["value"]

        # Step 5: POST solution — server sets session cookies
        r3 = await client.post(
            JOBS_URL,
            data={"altcha": payload_b64, "originalRequestToken": token},
        )
        r3.raise_for_status()
        self.log.debug("ALTCHA session established")

    # ------------------------------------------------------------------ #
    # Parsing                                                               #
    # ------------------------------------------------------------------ #

    def _parse_jobs(self, soup: BeautifulSoup) -> list[Job]:
        jobs: list[Job] = []
        _logged_samples = 0  # Log up to 5 before/after URL pairs per call for verification.
        for li in soup.select("li.search-results-job-box"):
            title_el = li.select_one(".search-results-job-box-title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            raw_url = href if href.startswith("http") else f"{BASE}/csr/{href}"
            url = _canonical_csj_url(raw_url)
            if _logged_samples < 5:
                self.log.info(
                    "CSJ URL canonical sample %d:\n  raw: %s\n  canonical: %s",
                    _logged_samples + 1, raw_url, url,
                )
                _logged_samples += 1

            org_el = li.select_one(".search-results-job-box-department")
            org = self._content_text(org_el) if org_el else "Civil Service"

            loc_el = li.select_one(".search-results-job-box-location")
            location = self._content_text(loc_el) if loc_el else None

            close_el = li.select_one(".search-results-job-box-closingdate")
            closing = self._parse_date(self._content_text(close_el)) if close_el else None

            salary_el = li.select_one(".search-results-job-box-salary")
            salary = self._content_text(salary_el) if salary_el else ""
            salary = salary.lstrip(":").strip()  # HTML has ":£X" after stripping the h4 label

            desc_parts = []
            if location:
                desc_parts.append(f"Role at {org} in {location}.")
            else:
                desc_parts.append(f"Role at {org}.")
            if salary:
                desc_parts.append(f"Salary: {salary}.")
            if closing:
                desc_parts.append(f"Closing: {closing}.")
            desc = " ".join(desc_parts)

            jobs.append(
                Job(
                    title=title,
                    url=url,
                    organisation=org,
                    description=desc,
                    source_name=self.name,
                    category=self.category,
                    country=self.country,
                    location=location,
                    closing_date=closing,
                )
            )
        return jobs

    def _sort_refresh_url(self, soup: BeautifulSoup) -> str | None:
        """
        Build the URL for the results-page 'Refresh sort' GET form, overriding
        the sort value with CSJ_SORT.

        The form is a GET form targeting /csr/index.cgi that carries the current
        search contextid in its SID.  Submitting it with sort=CSJ_SORT re-renders
        the same keyword search in a different order.  Pagination links on the
        returned page encode sort=CSJ_SORT in their SID, preserving order across pages.

        Returns None if the form is absent (caller falls back to default sort).
        """
        form = None
        for f in soup.find_all("form"):
            if f.get("method", "").upper() == "GET" and f.find("select", {"name": "sort"}):
                form = f
                break
        if not form:
            return None

        action = form.get("action", "/csr/index.cgi")
        if not action.startswith("http"):
            action = f"{BASE}{action}"

        sid_el = form.find("input", {"name": "SID"})
        reqsig_el = form.find("input", {"name": "reqsig"})
        sid = sid_el["value"] if sid_el else ""
        reqsig = reqsig_el["value"] if reqsig_el else ""

        params = {
            "SID": sid,
            "sort": CSJ_SORT,
            "submit_results_sort_form": "Refresh sort",
            "reqsig": reqsig,
        }
        return f"{action}?{urlencode(params)}"

    def _next_page_url(self, soup: BeautifulSoup) -> str | None:
        """Find the 'Next page' pagination link."""
        paging = soup.select_one(".search-results-paging-menu")
        if not paging:
            return None
        for a in paging.find_all("a"):
            text = a.get_text(strip=True).lower().replace("\xa0", " ").strip()
            title_attr = (a.get("title") or "").lower()
            if "next" in text or "next" in title_attr:
                href = a.get("href", "")
                if not href:
                    continue
                return href if href.startswith("http") else f"{BASE}/csr/{href}"
        return None

    @staticmethod
    def _content_text(el) -> str:
        """Get text from a div, stripping any sr-only <h4> label children."""
        if el is None:
            return ""
        # Remove the sr-only h4 label (e.g. "Department", "Location")
        for h4 in el.find_all("h4"):
            h4.decompose()
        return el.get_text(strip=True)

    @staticmethod
    def _parse_date(text: str) -> str | None:
        """Parse dates like '11:55 pm on Wednesday 25th March 2026'."""
        match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4})", text)
        if match:
            try:
                day, month, year = match.groups()
                return datetime.strptime(f"{day} {month} {year}", "%d %B %Y").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None
