"""Positive internship/graduate signal screening.

Detects early-career intent in job title and description, multilingual.
Used as a routing/prioritisation layer for the internship_graduate pipeline.
This is NOT a hard exclusion filter and does NOT set experience_level.
The existing classifier assigns canonical bands; internship is set only from
a genuine internship signal in the classifier, never inferred here.

Sources marked curated=true (dedicated internship boards) are exempt from
this check — their output is already early-career by definition.
"""

from __future__ import annotations

import re

# ── Keyword lists by language ─────────────────────────────────────────────────

_EN = [
    "intern", "internship", "trainee", "traineeship", "graduate", "grad scheme",
    "summer associate", "summer analyst", "placement", "year in industry",
    "sandwich placement", "fellowship", "apprentice", "early careers",
    "entry level", "entry-level", "work experience", "industrial placement",
    "vacation scheme", "junior analyst", "junior associate",
]

_DE = [
    "praktikum", "praktikant", "praktikantin", "werkstudent", "werkstudentin",
    "traineeprogramm", "trainee", "absolvent", "absolventin", "berufseinsteiger",
    "berufseinstieg", "volontariat", "volontär",
]

_FR = [
    "stage", "stagiaire", "alternance", "alternant", "apprentissage",
    "jeune diplômé", "jeune diplome", "programme jeunes diplômés",
    "contrat d'apprentissage", "volontaire",
]

_ES = [
    "prácticas", "practicas", "becario", "becaria", "recién titulado",
    "recien titulado", "recién graduado", "recien graduado",
]

_IT = [
    "tirocinio", "tirocinante", "stage", "neolaureato", "neolaureata",
    "apprendistato", "praticante",
]

_NL = [
    "stage", "stagiair", "stagiaire", "traineeship", "trainee",
    "starter", "afgestudeerde", "afstudeerstage",
]

_NORDIC = [
    "praktik", "praktikant", "praktikum", "trainee", "trainee-program",
    "nyutdannet", "nyutexaminerad", "juniorkonsulent", "sommarjobb",
]

_PL = [
    "staż", "stażysta", "praktykant", "absolwent", "trainee",
]

_ALL_TERMS = _EN + _DE + _FR + _ES + _IT + _NL + _NORDIC + _PL


def _build(term: str) -> re.Pattern:
    escaped = re.escape(term)
    if " " in term or "-" in term:
        return re.compile(escaped, re.IGNORECASE)
    return re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)


_PATTERNS: list[re.Pattern] = [_build(t) for t in _ALL_TERMS]

# ── Seniority exclusion for stage-1 pre-detail prefilter ─────────────────────
# Used by oracle_hcm/workday internship_graduate sources to drop unambiguously
# non-early-career titles before spending the description-fetch budget.
_SENIOR_RE = re.compile(
    r"\b(senior|director|head|vp|vice\s+president|svp|evp|chief|"
    r"principal|partner|managing\s+director|president|leader|lead|manager)\b",
    re.IGNORECASE,
)


def is_senior_title(title: str) -> bool:
    """True if the title contains an unambiguous seniority marker.

    Only drops titles that are unambiguously NOT early-career.
    Neutral titles like 'Research Analyst' or 'Data Associate' return False.
    """
    return bool(_SENIOR_RE.search(title))


def has_internship_signal(title: str, body: str = "") -> bool:
    """True if title or body contains at least one early-career keyword."""
    for pattern in _PATTERNS:
        if pattern.search(title):
            return True
    if body:
        for pattern in _PATTERNS:
            if pattern.search(body):
                return True
    return False


def filter_by_internship_signal(
    jobs: list,
    source_is_curated: bool = False,
) -> tuple[list, int]:
    """Apply positive signal filter. Returns (kept_jobs, discarded_count).

    If source_is_curated is True, all jobs are kept (dedicated board).
    Otherwise only jobs with an internship/graduate signal in title or description
    are kept.
    """
    if source_is_curated:
        return jobs, 0
    kept = []
    discarded = 0
    for job in jobs:
        if has_internship_signal(job.title, job.description or ""):
            kept.append(job)
        else:
            discarded += 1
    return kept, discarded
