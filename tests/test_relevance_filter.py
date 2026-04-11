from __future__ import annotations

import pytest

from src.filters.relevance import is_relevant, filter_relevant_jobs
from src.models.job import Job


# ── Hard exclusion tests ─────────────────────────────────────────────────────

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
    # "cook" matches but "cookson" should not
    assert is_relevant("Production Cook") is False
    assert is_relevant("Cookson Policy Adviser") is True


# ── Hard exclusions: the listed titles are never rescued ─────────────────────

def test_hard_excludes_security_guard_no_rescue():
    assert is_relevant("Security Guard", "UK Parliament") is False


def test_hard_excludes_security_officer_no_rescue():
    assert is_relevant("Security Officer", "Cabinet Office") is False


def test_hard_excludes_cctv_operator_no_rescue():
    assert is_relevant("CCTV Operator", "Westminster City Council") is False


def test_hard_excludes_parking_attendant_no_rescue():
    assert is_relevant("Parking Attendant", "Parliament") is False


def test_hard_excludes_traffic_warden_no_rescue():
    assert is_relevant("Traffic Warden", "Policy Exchange") is False


def test_hard_excludes_customer_service_advisor_no_rescue():
    assert is_relevant("Customer Service Advisor", "NGO Policy Forum") is False


def test_hard_excludes_call_centre_no_rescue():
    assert is_relevant("Call Centre Manager", "EU Parliament") is False


def test_hard_excludes_contact_centre_no_rescue():
    assert is_relevant("Contact Centre Advisor", "Government") is False


def test_hard_excludes_accountant_no_rescue():
    assert is_relevant("Accountant", "NGO Finance Team") is False


def test_hard_excludes_bookkeeper_no_rescue():
    assert is_relevant("Bookkeeper", "Think Tank") is False


def test_hard_excludes_payroll_no_rescue():
    assert is_relevant("Payroll Officer", "Parliament") is False


def test_hard_excludes_receptionist_no_rescue():
    assert is_relevant("Receptionist", "Cabinet Office") is False


def test_hard_excludes_typist_no_rescue():
    assert is_relevant("Typist", "Policy Unit") is False


def test_hard_excludes_filing_clerk_no_rescue():
    assert is_relevant("Filing Clerk", "Westminster") is False


def test_hard_excludes_switchboard_no_rescue():
    assert is_relevant("Switchboard Operator", "Parliament") is False


def test_hard_excludes_librarian_no_rescue():
    assert is_relevant("Librarian", "House of Commons") is False


def test_hard_excludes_library_assistant_no_rescue():
    assert is_relevant("Library Assistant", "Parliament") is False


# ── Hard exclusions: inclusion keywords in title do NOT rescue ───────────────

def test_hard_excludes_clinical_policy_not_rescued():
    # "Clinical" is hard-excluded — "Policy" in title cannot rescue it
    assert is_relevant("Clinical Policy Adviser") is False


def test_hard_excludes_nursing_policy_not_rescued():
    # "Nursing" is hard-excluded
    assert is_relevant("Nursing Policy Lead") is False


def test_hard_excludes_teacher_parliament_org_not_rescued():
    # "Teacher" is hard-excluded — Parliament org cannot rescue it
    assert is_relevant("Teacher of Political Theory", "Parliament") is False


def test_hard_excludes_support_worker_ngo_org_not_rescued():
    # "Support Worker" is hard-excluded — NGO org cannot rescue it
    assert is_relevant("Support Worker", "International NGO Consortium") is False


def test_hard_excludes_clinical_legislative_not_rescued():
    # "Clinical" is hard-excluded — "Legislative" in title cannot rescue it
    assert is_relevant("Clinical Legislative Affairs Manager") is False


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
    assert is_relevant("Director of Operations") is True


# ── Soft exclusion: Administrator is the only rescuable title ───────────────

def test_excludes_bare_administrator():
    assert is_relevant("Administrator") is False


def test_excludes_database_administrator():
    assert is_relevant("Database Administrator") is False


def test_rescues_parliamentary_administrator():
    # "Parliamentary" in title triggers rescue
    assert is_relevant("Parliamentary Administrator") is True


def test_rescues_administrator_parliament_org():
    # "Parliament" in org triggers rescue
    assert is_relevant("Administrator", "UK Parliament") is True


def test_rescues_administrator_policy_org():
    # "Policy" in org triggers rescue
    assert is_relevant("Administrator", "Centre for Policy Studies") is True


def test_does_not_rescue_administrator_generic_org():
    # No inclusion keyword in title or org
    assert is_relevant("Administrator", "City Council") is False


def test_rescues_administrator_eu_org():
    assert is_relevant("Administrator", "EU Affairs Consultancy") is True


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


def test_filter_hard_excludes_nurse_even_with_policy_org():
    # Nurse is hard-excluded — "Health Policy Team" in org makes no difference
    jobs = [_make_job("Nurse", "UK Parliament Health Policy Team")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 0


def test_filter_rescues_administrator_at_parliament():
    jobs = [_make_job("Administrator", "UK Parliament")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 1


def test_filter_drops_administrator_at_generic_org():
    jobs = [_make_job("Administrator", "City Council")]
    result = filter_relevant_jobs(jobs)
    assert len(result) == 0
