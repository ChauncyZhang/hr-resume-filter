from uuid import UUID

import pytest

from server.app.identity.policy import Principal
from server.app.recruiting.authorization import RecruitingAction, RecruitingAuthorizationService
from server.app.recruiting.http import content_disposition, derive_cursor_key


def principal(role: str) -> Principal:
    return Principal(UUID(int=1), UUID(int=2), frozenset({role}), True)


@pytest.mark.parametrize(
    ("role", "action", "allowed"),
    [
        ("recruiting_admin", action, True) for action in RecruitingAction
    ] + [
        ("recruiter", RecruitingAction.READ, True),
        ("recruiter", RecruitingAction.COMMENT, True),
        ("recruiter", RecruitingAction.MANAGE_CANDIDATE, True),
        ("recruiter", RecruitingAction.MANAGE_JOB, True),
        ("recruiter", RecruitingAction.CREATE_VERSION, True),
        ("recruiter", RecruitingAction.TRANSITION, True),
        ("recruiter", RecruitingAction.PREVIEW, True),
        ("recruiter", RecruitingAction.ISSUE_TICKET, True),
        ("recruiter", RecruitingAction.DOWNLOAD, True),
        ("recruiter", RecruitingAction.RECOMMEND, False),
        ("hiring_manager", RecruitingAction.READ, True),
        ("hiring_manager", RecruitingAction.COMMENT, True),
        ("hiring_manager", RecruitingAction.RECOMMEND, True),
        ("hiring_manager", RecruitingAction.MANAGE_CANDIDATE, False),
        ("hiring_manager", RecruitingAction.MANAGE_JOB, False),
        ("hiring_manager", RecruitingAction.CREATE_VERSION, False),
        ("hiring_manager", RecruitingAction.TRANSITION, False),
        ("hiring_manager", RecruitingAction.PREVIEW, True),
        ("hiring_manager", RecruitingAction.ISSUE_TICKET, False),
        ("hiring_manager", RecruitingAction.DOWNLOAD, False),
    ] + [
        (role, action, False)
        for role in ("system_admin", "interviewer")
        for action in RecruitingAction
    ],
)
def test_action_matrix_is_centralized(role, action, allowed):
    assert RecruitingAuthorizationService.role_allows(principal(role), action) is allowed


@pytest.mark.parametrize(
    ("filename", "expected_ascii", "expected_encoded"),
    [
        ("resume.pdf", "resume.pdf", "resume.pdf"),
        ('a"b.pdf', "a_b.pdf", "a%22b.pdf"),
        ("../folder/resume.pdf", "resume.pdf", "resume.pdf"),
        ("候选人.pdf", "download.pdf", "%E5%80%99%E9%80%89%E4%BA%BA.pdf"),
        ("x" * 400 + ".pdf", "x" * 115 + ".pdf", "x" * 115 + ".pdf"),
    ],
)
def test_content_disposition_has_safe_ascii_and_rfc5987(filename, expected_ascii, expected_encoded):
    value = content_disposition(filename)
    assert value == f"attachment; filename=\"{expected_ascii}\"; filename*=UTF-8''{expected_encoded}"


@pytest.mark.parametrize("filename", ["bad\rname.pdf", "bad\nname.pdf", "bad\x00name.pdf", "\x1fname.pdf"])
def test_content_disposition_rejects_controls(filename):
    with pytest.raises(ValueError):
        content_disposition(filename)


def test_cursor_key_uses_domain_separated_hkdf():
    source = b"a" * 32
    key = derive_cursor_key(source)
    assert len(key) == 32
    assert key != source
    assert key == derive_cursor_key(source)
