from __future__ import annotations

import logging
import re
from typing import Optional

from src.models.job import Job

log = logging.getLogger(__name__)

# ── Keyword lists ─────────────────────────────────────────────────────────────

EXCLUSION_KEYWORDS = [
    "Cleaner", "Cleaning", "Janitor", "Housekeeper", "Housekeeping",
    "Cook", "Chef", "Kitchen Assistant", "Kitchen Porter", "Catering",
    "Catering Assistant", "Catering Supervisor", "Dining", "Dishwasher",
    "Plumber", "Plumbing", "Electrician", "Joiner", "Carpenter", "Bricklayer",
    "Roofer", "Plasterer", "Painter", "Decorator", "Glazier", "Welder",
    "Forklift", "Warehouse", "Warehouse Operative", "HGV Driver", "Van Driver",
    "Bus Driver", "Refuse", "Bin Collection", "Street Cleaner", "Road Worker",
    "Groundskeeper", "Gardener", "Tree Surgeon", "Pest Control",
    "Nurse", "Nursing", "Healthcare Assistant", "Midwife", "Physiotherapist",
    "Occupational Therapist", "Radiographer", "Dentist", "Dental",
    "Veterinary", "Pharmacist", "Optometrist", "Surgeon", "Clinical",
    "Doctor", "Paramedic", "Care Worker", "Care Assistant", "Support Worker",
    "Social Worker", "Teacher", "Teaching Assistant", "Lecturer",
    "Head Teacher", "SENCO", "Classroom Assistant", "Playground Supervisor",
    "School Crossing Patrol", "Lunchtime Supervisor", "Librarian",
    "Library Assistant", "Leisure Attendant", "Fitness Instructor", "Gym",
    "Personal Trainer", "Lifeguard", "Swimming", "Prison Officer",
    "Probation Officer", "Firefighter", "Fire Officer", "Security Guard",
    "Security Officer", "CCTV Operator", "Parking Attendant",
    "Traffic Warden", "Retail Assistant", "Shop Assistant", "Sales Assistant",
    "Cashier", "Store Manager", "Customer Service Advisor", "Call Centre",
    "Contact Centre", "Accountant", "Bookkeeper", "Payroll", "Receptionist",
    "Typist", "Filing Clerk", "Switchboard", "Forklift Driver", "Stockperson",
    "Farm", "Agricultural", "Fisheries", "Marine", "Laboratory",
    "Lab Technician", "Mortuary", "Coroner",
]

INCLUSION_KEYWORDS = [
    "Parliamentary", "Parliament", "Constituency", "MP", "Political",
    "Politics", "Policy", "Public Affairs", "Public Policy",
    "Government Affairs", "Lobbying", "Advocacy", "Campaign", "Regulatory",
    "Legislation", "Legislative", "Minister", "Ministerial", "Cabinet",
    "Whitehall", "Westminster", "Civil Service", "Diplomat", "Foreign Affairs",
    "International Relations", "International Development", "Defence Policy",
    "Security Policy", "Intelligence", "Think Tank", "Research Fellow",
    "Policy Analyst", "Policy Advisor", "Policy Officer", "Policy Manager",
    "Communications Officer", "Press Officer", "Media Relations",
    "Public Relations", "Stakeholder", "Government Relations",
    "Chief of Staff", "Special Adviser", "SpAd", "Head of Policy",
    "Director of Policy", "Governance", "Democratic", "Democracy",
    "Electoral", "Constitution", "Human Rights", "NGO", "European", "EU",
    "NATO", "United Nations", "UN", "Commonwealth",
]

_WORD_BOUNDARY = re.compile(r"\s")


def _build_pattern(keyword: str) -> re.Pattern:
    if " " in keyword.strip():
        return re.compile(re.escape(keyword), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE)


_EXCLUSION_PATTERNS = [(kw, _build_pattern(kw)) for kw in EXCLUSION_KEYWORDS]
_INCLUSION_PATTERNS = [(kw, _build_pattern(kw)) for kw in INCLUSION_KEYWORDS]


def is_relevant(title: str, organisation: Optional[str] = None) -> bool:
    """Returns True if the job should be kept, False if it should be discarded."""
    # Step 1: check for exclusion match
    matched_exclusion = None
    for keyword, pattern in _EXCLUSION_PATTERNS:
        if pattern.search(title):
            matched_exclusion = keyword
            break

    if matched_exclusion is None:
        return True

    # Step 2: check for inclusion rescue in title OR organisation
    check_texts = [title]
    if organisation:
        check_texts.append(organisation)

    for text in check_texts:
        for keyword, pattern in _INCLUSION_PATTERNS:
            if pattern.search(text):
                return True

    return False


def filter_relevant_jobs(
    jobs: list[Job],
    exclusions_path: str = "src/config/exclusions.yaml",
) -> list[Job]:
    """Filter jobs using the is_relevant function. exclusions_path kept for API compat."""
    kept: list[Job] = []
    excluded_count = 0

    for job in jobs:
        if is_relevant(job.title, job.organisation):
            kept.append(job)
        else:
            log.info(
                f'EXCLUDED: "{job.title}" at {job.organisation} — matched exclusion keyword'
            )
            excluded_count += 1

    log.info(
        f"Relevance filter: {len(kept)} kept, {excluded_count} excluded from {len(jobs)} total"
    )
    return kept
