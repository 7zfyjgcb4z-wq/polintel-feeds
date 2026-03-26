"""
Tier 2: Generic AI-powered scraper using Claude API.

Cost discipline:
- Page hash caching skips API calls when content is unchanged.
- dry_run=True fetches + cleans HTML but never calls the Anthropic API.
- Call count is tracked via module-level counter (reset per process).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re

import httpx
from bs4 import BeautifulSoup

from src.db.store import JobStore
from src.models.job import Job
from src.scrapers.base import USER_AGENT, fetch_with_retry

log = logging.getLogger(__name__)

# ── HTML cleaning ────────────────────────────────────────────────────────────

STRIP_TAGS = [
    "nav", "header", "footer", "aside", "script", "style",
    "noscript", "iframe", "svg", "form", "button",
]

STRIP_CLASSES_RE = re.compile(
    r"sidebar|cookie|banner|newsletter|subscribe|social|breadcrumb|pagination",
    re.I,
)

# Maximum characters of cleaned text to send to Claude
MAX_CONTENT_CHARS = 12000


def clean_html(html: str) -> str:
    """Strip boilerplate and return main content as plain text."""
    soup = BeautifulSoup(html, "lxml")

    # Remove noisy tags
    for tag in soup(STRIP_TAGS):
        tag.decompose()

    # Remove elements whose class/id suggests boilerplate
    for el in soup.find_all(True):
        attrs = getattr(el, "attrs", None) or {}
        classes = " ".join(attrs.get("class") or [])
        el_id = attrs.get("id") or ""
        if STRIP_CLASSES_RE.search(classes) or STRIP_CLASSES_RE.search(el_id):
            el.decompose()

    # Prefer <main> or a well-known main-content container
    main = (
        soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.find(id=re.compile(r"main.content|content.main|main", re.I))
        or soup.find(class_=re.compile(r"main.content|page.content|entry.content", re.I))
    )
    root = main if main else (soup.body or soup)
    text = root.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_CONTENT_CHARS]


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


# ── Claude prompt ────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM = (
    "You are a job listing extractor. Given text from a career/jobs page, extract all "
    "current job vacancies. Return ONLY a JSON array with no other text. "
    "If there are no current vacancies, return []."
)

EXTRACTION_USER_TMPL = """\
Extract all current job vacancies from the page content below.

Each job object must have:
- title (string): Job title
- url (string): Direct link to the job listing (absolute URL). \
If only a relative path, prepend the base URL: {base_url}
- organisation (string): Hiring organisation name
- description (string): Brief description, max 500 chars
- location (string or null): Location if stated
- closing_date (string or null): Closing/deadline date if stated, ISO format YYYY-MM-DD

Do NOT include:
- Generic CTAs ("View all jobs", "Sign up", "Register interest")
- Expired or closed listings
- Non-job content (events, publications, news, courses)

The organisation (if not stated on the page) is: {source_name}

--- PAGE CONTENT ---
{cleaned_text}
--- END PAGE CONTENT ---"""


# ── JSON response parsing ────────────────────────────────────────────────────

def parse_claude_json(text: str) -> list[dict]:
    """
    Extract a JSON array from Claude's response, handling common wrapping:
    - Clean JSON array
    - Fenced with ```json ... ``` or ``` ... ```
    - Preamble text before the array
    - 'No jobs found' or similar non-JSON
    """
    text = text.strip()

    if not text:
        return []

    # Strip markdown code fences
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Find outermost JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        else:
            log.debug(f"No JSON array found in response: {text[:100]!r}")
            return []

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error: {e} — raw: {text[:200]!r}")
        return []

    if not isinstance(result, list):
        log.warning(f"Expected list, got {type(result).__name__}")
        return []

    return result


# ── Job object construction ──────────────────────────────────────────────────

def items_to_jobs(
    items: list[dict],
    source_name: str,
    category: str,
    country: str,
) -> list[Job]:
    jobs: list[Job] = []
    for item in items:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        if not title or not url:
            log.debug(f"{source_name}: skipping item missing title/url: {item}")
            continue
        if not url.startswith("http"):
            log.debug(f"{source_name}: skipping item with relative URL: {url!r}")
            continue
        jobs.append(
            Job(
                title=title,
                url=url,
                organisation=(item.get("organisation") or source_name).strip(),
                description=(item.get("description") or "")[:500],
                source_name=source_name,
                category=category,
                country=country,
                location=item.get("location") or None,
                closing_date=item.get("closing_date") or None,
            )
        )
    return jobs


# ── HTML fetch ───────────────────────────────────────────────────────────────

async def fetch_html(url: str, requires_js: bool = False) -> str:
    if requires_js:
        from playwright.async_api import async_playwright  # noqa: PLC0415

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                extra_http_headers={"User-Agent": USER_AGENT}
            )
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            await browser.close()
            return html

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30.0
    ) as client:
        response = await fetch_with_retry(client, url)
        return response.text


# ── Main entry point ─────────────────────────────────────────────────────────

async def generic_scrape(
    source: dict,
    db: JobStore,
    dry_run: bool = False,
) -> list[Job]:
    """
    Scrape a generic source via Claude API extraction.

    dry_run=True: fetch + clean HTML, check hash, print what would be sent —
    but NEVER call the Anthropic API.
    """
    name: str = source["name"]
    url: str = source["url"]
    category: str = source.get("category", "general")
    country: str = source.get("country", "uk")
    requires_js: bool = source.get("requires_js", False)

    # 1. Fetch HTML
    try:
        html = await fetch_html(url, requires_js)
    except Exception as e:
        raise RuntimeError(f"Fetch failed for {name}: {e}") from e

    # 2. Clean
    cleaned = clean_html(html)
    content_hash = _hash_content(cleaned)

    # 3. Hash check — skip if page unchanged
    stored_hash = db.get_page_hash(name)
    if stored_hash == content_hash:
        log.info(f"  {name}: page unchanged (hash match), skipping API call")
        return []

    token_estimate = estimate_tokens(EXTRACTION_USER_TMPL.format(
        base_url=url, source_name=name, cleaned_text=cleaned
    ))

    if dry_run:
        log.info(
            f"  [DRY RUN] {name}: page changed — would call Claude API "
            f"(~{token_estimate} input tokens, {len(cleaned)} chars)"
        )
        return []

    # 4. Call Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set")

    raw_items = await _extract_with_claude(name, url, cleaned, api_key)

    # 5. Build Job objects
    jobs = items_to_jobs(raw_items, name, category, country)

    # 6. Update stored hash only after successful extraction
    db.set_page_hash(name, url, content_hash)

    log.info(f"  {name}: {len(jobs)} jobs extracted via Claude API")
    return jobs


async def _extract_with_claude(
    source_name: str,
    base_url: str,
    cleaned_text: str,
    api_key: str,
) -> list[dict]:
    import anthropic  # noqa: PLC0415

    client = anthropic.AsyncAnthropic(api_key=api_key)
    user_content = EXTRACTION_USER_TMPL.format(
        base_url=base_url,
        source_name=source_name,
        cleaned_text=cleaned_text,
    )
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    raw_text = message.content[0].text.strip()
    log.debug(f"{source_name} raw response: {raw_text[:300]!r}")
    return parse_claude_json(raw_text)
