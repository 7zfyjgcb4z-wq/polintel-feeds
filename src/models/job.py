from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    title: str
    url: str                              # Absolute URL — also serves as GUID
    organisation: str
    description: str                      # Plain text; single 10,000-char clip applied at feed emission
    source_name: str                      # e.g. "Chatham House"
    country: str = "uk"
    category: str = ""                    # Broad slug: "think-tanks", "government", etc.
    location: str | None = None  # Free-text location string e.g. "Brussels, Belgium" or "London" or "Nairobi, Kenya". Mapped to country_code by the Edge Function parser.
    closing_date: str | None = None       # ISO date if known
    posted_date: str | None = None        # ISO date when the job was posted (from ATS)
    date_scraped: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    language: str = "en"
    partisan_lean: str | None = None  # US-only: left, centre-left, centre, centre-right, right, nonpartisan, unknown
    description_source: str = ""  # api | structured | readability | stub | none — set by the layer that produced the body

    def __post_init__(self) -> None:
        # Charset as a shared concern: normalise all text fields once, here.
        for f in ("title", "organisation", "description", "location", "closing_date"):
            v = getattr(self, f)
            if isinstance(v, str):
                setattr(self, f, unicodedata.normalize("NFC", v))
        # Honest default: empty body is 'none'; a non-empty body whose producer
        # did not label it is an excerpt/stub, never assumed to be a full body.
        if not self.description_source:
            self.description_source = "none" if not (self.description or "").strip() else "stub"

    @property
    def guid(self) -> str:
        return self.url
