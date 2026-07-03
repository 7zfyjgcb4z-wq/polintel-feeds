"""Deterministic 'Label: value' extraction from a page's visible text.

Config (per source, under key 'labelled_fields' in the source YAML):
  organisation: 'Organization'         # label whose value is the employer
  location: 'Location'
  posted_date: 'Date Posted'
  posted_date_format: '%m/%d/%Y'       # strptime format for the value
  closing_date: 'Closing Date'
  closing_date_format: '%d %B %Y'
Values are matched as 'Label: value' or 'Label\nvalue' on the extracted text.
Ordinal suffixes (1st/2nd/3rd/4th...) are stripped before date parsing.
"""
from __future__ import annotations

import re
from datetime import datetime

_ORDINAL_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)\b")


def _find_value(text: str, label: str) -> str | None:
    m = re.search(rf"{re.escape(label)}\s*:?\s*\n?\s*(.+)", text)
    if not m:
        return None
    val = m.group(1).splitlines()[0].strip()
    return val or None


def _parse_date(raw: str, fmt: str) -> str | None:
    cleaned = _ORDINAL_RE.sub(r"\1", raw).strip()
    try:
        return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_labelled_fields(text: str, cfg: dict) -> dict:
    """Returns any of: organisation, location, posted_date, closing_date. Missing keys omitted."""
    out: dict = {}
    if not text or not cfg:
        return out
    if lbl := cfg.get("organisation"):
        if v := _find_value(text, lbl):
            out["organisation"] = v
    if lbl := cfg.get("location"):
        if v := _find_value(text, lbl):
            out["location"] = v
    if lbl := cfg.get("posted_date"):
        if (v := _find_value(text, lbl)) and (d := _parse_date(v, cfg.get("posted_date_format", "%d %B %Y"))):
            out["posted_date"] = d
    if lbl := cfg.get("closing_date"):
        if (v := _find_value(text, lbl)) and (d := _parse_date(v, cfg.get("closing_date_format", "%d %B %Y"))):
            out["closing_date"] = d
    return out
