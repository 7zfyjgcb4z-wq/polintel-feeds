from __future__ import annotations

import pytest

from src.filters.relevance import is_relevant, filter_relevant_jobs
from src.models.job import Job


# ── Exclusion tests ──────────────────────────────────────────────────────────

def test_excludes_cleaner():
    assert is_relevant("Cleaner") is False


def test_excludes_cleaner_case_insensitive():
    assert is_relevant("cleaner") is False
    assert is_relevant("CLEANER") is False


def test_excludes_multiword_phrase():
    assert is_relevant("Kitchen Assistant") is False
    assert is_relevant("Kitchen Porter") is False
    assert is_relevant("Healthcare Assistant") is False


def test_excludes_nurse():
    assert is_relevant("Nurse") is False
    assert is_relevant("Staff Nurse") is False


def test_excludes_chef():
    assert is_relevant("Chef") is False
    assert is_relevant("Head Chef") is False


def test_excludes_teacher():
    assert is_relevant("Class Teacher") is False


def test_excludes_support_worker():
    assert is_relevant("Support Worker") is False


def test_excludes_word_boundary_only():
    # "cook" should match, but "cookson" or "cookbook" should not
    assert is_relevant("Production Cook") is False
    assert is_relevant("Cookson Policy Adviser") is True


# ── Clean pass tests ─────────────────────────────────────────────────────────

def test_keeps_policy_analyst():
    assert is_relevant("Policy Analyst") is True


def test_keeps_parliamentary_adviser():
    assert is_relevant("Parliamentary Adviser") is True


def test_keeps_head_of_policy():
    assert is_relevant("Head of Policy") is True


def test_keeps_communications_officer():
    assert is_relevant("Communications Officer") is True


def test_keeps_research_fellow():
    assert is_relevant("Research Fellow") is True


def test_keeps_director():
    # Generic director — not excluded, not rescued, still relevant
    assert is_relevant("Director of Operations") is True


# ── Inclusion rescue tests ───────────────────────────────────────────────────

def test_rescues_clinical_policy_adviser():
    # "Clinical" is an exclusion keyword, but "Policy" rescues it
    assert is_relevant("Clinical Policy Adviser") is True


def test_rescues_nursing_policy_role():
    # "Nursing" excluded, "Policy" rescues
    assert is_relevant("Nursing Policy Lead") is True


def test_rescues_teacher_via_org():
    # "Teacher" excluded, but org is "Parliament" (inclusion keyword)
    assert is_relevant("Teacher of Political Theory", "Parliament") is True


def test_rescues_support_worker_via_org():
    # "Support Worker" excluded, but org contains "NGO" (inclusion keyword)
    assert is_relevant("Support Worker", "International NGO Consortium") is True


def test_does_not_rescue_random_cleaner():
    # "Cleaner" excluded, no rescue keywords
    assert is_relevant("Cleaner", "City Council") is False


def test_rescues_via_legislative_in_title():
    # "Clinical" excluded, "Legislative" rescues
    assert is_relevant("Clinical Legislative Affairs Manager") is True


# ── filter_relevant_jobs ─────────────────────────────────────────────────────

def _make_job(title: str, org: str = "Org") -> Job:
    return Job(
        title=title,
        url=f"https://example.com/{title.lower().replace(' ', '-')}",
        organisation=org,
        description="",
        source_name="test",
    )


def test_filter_removes_irrelevant():
    jobs = [_make_job("Cleaner"), _make_job("Policy Analyst")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 1
    assert result[0].title == "Policy Analyst"


def test_filter_keeps_all_relevant():
    jobs = [_make_job("Policy Analyst"), _make_job("Research Fellow"), _make_job("Head of Policy")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 3


def test_filter_empty_list():
    assert filter_relevant_jobs([]) == []


def test_filter_rescues_via_org():
    jobs = [_make_job("Nurse", "UK Parliament Health Policy Team")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 1
