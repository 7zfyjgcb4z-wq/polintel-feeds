from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup


def detect_ats(html: str, url: str) -> Optional[str]:
    """Returns ATS name string (e.g. 'greenhouse') or None if unrecognised."""
    soup = BeautifulSoup(html, "lxml")

    def _has_link(domain: str) -> bool:
        for tag in soup.find_all(href=True):
            if domain in (tag.get("href") or ""):
                return True
        for tag in soup.find_all(src=True):
            if domain in (tag.get("src") or ""):
                return True
        return False

    def _has_iframe(domain: str) -> bool:
        for iframe in soup.find_all("iframe"):
            if domain in (iframe.get("src") or ""):
                return True
        return False

    # Greenhouse
    if (
        soup.find(id="grnhse_app")
        or soup.find("div", class_="opening")
        or _has_link("boards.greenhouse.io")
        or _has_iframe("boards.greenhouse.io")
    ):
        return "greenhouse"

    # Lever
    if (
        _has_link("jobs.lever.co")
        or soup.find("div", class_="postings-group")
    ):
        return "lever"

    # Workday
    if (
        _has_link("myworkdayjobs.com")
        or _has_iframe("myworkdayjobs.com")
        or soup.find(attrs={"data-automation-id": True})
        or "wd5.myworkdayjobs" in html
    ):
        return "workday"

    # BambooHR
    if (
        _has_link("bamboohr.com/jobs")
        or "BambooHR" in html
    ):
        return "bamboohr"

    # SmartRecruiters
    if (
        _has_link("jobs.smartrecruiters.com")
        or soup.find("meta", attrs={"name": "smartrecruiters"})
    ):
        return "smartrecruiters"

    # Applied
    if (
        _has_link("app.beapplied.com")
        or _has_iframe("app.beapplied.com")
    ):
        return "applied"

    # Pinpoint
    if (
        _has_link("pinpointhq.com")
        or _has_iframe("pinpointhq.com")
    ):
        return "pinpoint"

    # TeamTailor
    if (
        _has_link("career.teamtailor.com")
        or _has_link("jobs.teamtailor.com")
        or soup.find(id="tt-careers")
    ):
        return "teamtailor"

    # Recruitee
    if (
        _has_link("recruitee.com")
        or _has_iframe("recruitee.com")
    ):
        return "recruitee"

    # Personio
    if (
        _has_link("personio.de")
        or _has_link("jobs.personio.com")
        or _has_iframe("personio.de")
        or _has_iframe("jobs.personio.com")
    ):
        return "personio"

    # JazzHR
    if (
        _has_link("jazzhrhire.com")
        or _has_link("applytojob.com")
        or _has_iframe("jazzhrhire.com")
    ):
        return "jazzhr"

    # Taleo
    if (
        _has_link("taleo.net")
        or _has_iframe("taleo.net")
        or "taleo.net" in html
    ):
        return "taleo"

    # Ashby
    if (
        _has_link("jobs.ashbyhq.com")
        or "ashbyhq" in html
    ):
        return "ashby"

    # Workable
    if (
        _has_link("workable.com")
        or _has_iframe("workable.com")
        or soup.find(id="whr_embed_hook")
        or "whr_workable" in html
        or "apply.workable.com" in html
    ):
        return "workable"

    # iCIMS
    if (
        _has_link("icims.com")
        or _has_iframe("icims.com")
        or soup.find(class_=re.compile(r"^iCIMS_", re.I))
        or soup.find(id="iCIMS_Content")
        or "iCIMS" in html
    ):
        return "icims"

    # Cornerstone OnDemand (csod.com)
    if (
        _has_link("csod.com")
        or _has_iframe("csod.com")
        or "cornerstone ondemand" in html.lower()
        or "csod.com" in html
    ):
        return "cornerstone"

    # ApplicantPro (isolved Talent Acquisition)
    if (
        _has_link("applicantpro.com")
        or _has_iframe("applicantpro.com")
        or "applicantpro.com" in html
    ):
        return "applicantpro"

    # ApplicantStack (WizeHire)
    if (
        _has_link("applicantstack.com")
        or _has_iframe("applicantstack.com")
        or "applicantstack.com" in html
    ):
        return "applicantstack"

    # Oracle Recruiting Cloud (HCM)
    if (
        "oraclecloud.com/hcmUI" in html
        or _has_link("oraclecloud.com/hcmUI")
        or _has_iframe("fa.em1.ukg.oraclecloud.com")
        or _has_iframe("fa.em2.ukg.oraclecloud.com")
        or _has_iframe("fa.eu.oraclecloud.com")
        or "talent.oracle.com" in html
        or "oraclehcm" in html.lower()
    ):
        return "oracle_hcm"

    return None
