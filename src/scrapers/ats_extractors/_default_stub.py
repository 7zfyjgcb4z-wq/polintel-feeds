from __future__ import annotations

import logging
from typing import List

from src.models.job import Job

log = logging.getLogger(__name__)


def extract_default(html: str, url: str, source_config: dict, ats_type: str = "unknown") -> List[Job]:
    """Stub for ATS platforms that don't have a dedicated extractor yet."""
    log.warning(
        f"ATS extractor not yet implemented for {ats_type} — skipping "
        f"({source_config.get('name', url)})"
    )
    return []
