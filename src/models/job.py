from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    title: str
    url: str                              # Absolute URL — also serves as GUID
    organisation: str
    description: str                      # Max 500 chars
    source_name: str                      # e.g. "Chatham House"
    country: str = "uk"
    category: str = ""                    # Broad slug: "think-tanks", "government", etc.
    location: str | None = None
    closing_date: str | None = None       # ISO date if known
    date_scraped: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    language: str = "en"

    @property
    def guid(self) -> str:
        return self.url
