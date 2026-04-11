from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from bs4 import BeautifulSoup

_DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}[/-]\d{1,2}|\d{4})\b", re.I)
_LOCATION_RE = re.compile(r"\b(london|manchester|birmingham|edinburgh|glasgow|remote|hybrid|uk|england|scotland|wales)\b", re.I)


def detect_pattern(html: str) -> Optional[dict]:
    """Analyses HTML and returns suggested selectors, or None if no pattern found."""
    soup = BeautifulSoup(html, "lxml")
    body = soup.body or soup

    counts: Counter = Counter()
    for el in body.descendants:
        if not hasattr(el, "name") or not el.name:
            continue
        classes = el.get("class") or []
        if not classes:
            continue
        key = (el.name, " ".join(sorted(classes)))
        counts[key] += 1

    # Find the most repeated element with 3+ occurrences
    candidates = [(tag, cls, n) for (tag, cls), n in counts.items() if n >= 3 and cls]
    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[2])
    card_tag, card_cls, _ = candidates[0]
    card_cls_first = card_cls.split()[0]
    card_selector = f".{card_cls_first}"

    # Look inside a sample card for sub-elements
    sample_cards = soup.select(card_selector)
    if not sample_cards:
        return None

    sample = sample_cards[0]
    title_sel = None
    link_sel = None
    date_hint = None
    location_hint = None

    # Find links as probable title
    for a in sample.find_all("a", href=True):
        text = a.get_text(strip=True)
        if text and len(text) > 5:
            a_cls = a.get("class", [])
            if a_cls:
                title_sel = f".{a_cls[0]} a"
                link_sel = f".{a_cls[0]} a[href]"
            else:
                title_sel = f"{card_selector} a"
                link_sel = f"{card_selector} a[href]"
            break

    # Find date/location hints in sub-elements
    for el in sample.descendants:
        if not hasattr(el, "name") or not el.name:
            continue
        text = el.get_text(strip=True)
        if not date_hint and _DATE_RE.search(text):
            el_cls = el.get("class", [])
            if el_cls:
                date_hint = f".{el_cls[0]}"
        if not location_hint and _LOCATION_RE.search(text):
            el_cls = el.get("class", [])
            if el_cls:
                location_hint = f".{el_cls[0]}"

    result = {
        "job_card": card_selector,
        "probable_title": title_sel or f"{card_selector} a",
        "probable_link": link_sel or f"{card_selector} a[href]",
    }
    if date_hint:
        result["probable_date"] = date_hint
    if location_hint:
        result["probable_location"] = location_hint

    return result
