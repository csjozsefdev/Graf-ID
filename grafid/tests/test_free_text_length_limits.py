"""Milestone 5B regression tests: real audit finding L1.

The original finding: project `notes` and session `exit_note`/`blocker`/
`next_step` have no length limit. Fixed with a single shared constant
(MAX_FREE_TEXT_FIELD_CHARS) enforced only at the write boundary:

- over-limit input raises a deterministic domain error (never silently
  truncated)
- CLI and IPC both funnel through the same service methods
  (ProjectRegistryService.update / SessionService.end_session), so there is
  one validation implementation, not two
- existing stored data is never touched, truncated, or deleted by this
  change (it is a write-time guard, not a read-time/migration check)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from grafid.core.constants import MAX_FREE_TEXT_FIELD_CHARS
from grafid.core.exceptions import SessionError, ValidationError
from grafid.models.session import ExitNoteInput
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.session_service import SessionService

LIMIT = MAX_FREE_TEXT_FIELD_CHARS


# ---------------------------------------------------------------------------
# Project notes (the only write path that accepts notes is `update`)
# ---------------------------------------------------------------------------


def test_notes_limit_minus_one_is_accepted(db_path: Path, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    text = "a" * (LIMIT - 1)
    updated = registry.update(project_id, notes=text)
    assert updated.notes == text


def test_notes_exact_limit_is_accepted(db_path: Path, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    text = "a" * LIMIT
    updated = registry.update(project_id, notes=text)
    assert updated.notes == text


def test_notes_limit_plus_one_is_rejected(db_path: Path, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    text = "a" * (LIMIT + 1)
    with pytest.raises(ValidationError):
        registry.update(project_id, notes=text)


def test_notes_very_large_input_is_rejected_not_truncated(
    db_path: Path, project_id: int
) -> None:
    registry = ProjectRegistryService(db_path)
    huge = "a" * (LIMIT * 50)
    with pytest.raises(ValidationError):
        registry.update(project_id, notes=huge)
    # Nothing must have been silently stored (partially or truncated).
    record = registry.get_info(str(project_id))
    assert record.notes is None


def test_notes_unicode_multibyte_characters_counted_as_characters(
    db_path: Path, project_id: int
) -> None:
    registry = ProjectRegistryService(db_path)
    at_limit = "🚀" * LIMIT  # 4-byte UTF-8 code point each — must count as 1 char
    updated = registry.update(project_id, notes=at_limit)
    assert updated.notes == at_limit

    over_limit = "🚀" * (LIMIT + 1)
    with pytest.raises(ValidationError):
        registry.update(project_id, notes=over_limit)


def test_notes_empty_string_is_accepted_not_an_error(db_path: Path, project_id: int) -> None:
    """
    Empty/whitespace-only notes must not raise (they're simply not "content" to
    length-check). Note: update_metadata's own "None means keep existing value"
    convention means this does not actually clear previously-set notes — that's
    pre-existing behavior unrelated to this length-limit fix, left unchanged.
    """
    registry = ProjectRegistryService(db_path)
    updated = registry.update(project_id, notes="")
    assert updated is not None


def test_notes_whitespace_only_is_accepted_not_an_error(db_path: Path, project_id: int) -> None:
    registry = ProjectRegistryService(db_path)
    updated = registry.update(project_id, notes="   \n\t  ")
    assert updated is not None


def test_notes_over_limit_with_surrounding_whitespace_still_rejected(
    db_path: Path, project_id: int
) -> None:
    """Padding can't be used to dodge the limit — it's checked on stripped text."""
    registry = ProjectRegistryService(db_path)
    text = "  " + ("a" * (LIMIT + 1)) + "  "
    with pytest.raises(ValidationError):
        registry.update(project_id, notes=text)


def test_notes_untouched_when_update_omits_the_field(db_path: Path, project_id: int) -> None:
    """Passing notes=None (field omitted) must leave existing notes alone."""
    registry = ProjectRegistryService(db_path)
    registry.update(project_id, notes="existing note")
    updated = registry.update(project_id, status="paused")
    assert updated.notes == "existing note"


# ---------------------------------------------------------------------------
# Session exit_note / blocker / next_step (write path: SessionService.end_session,
# reached identically by both the CLI and the IPC handler)
# ---------------------------------------------------------------------------

FIELDS = ("exit_note", "blocker", "next_step")


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_limit_minus_one_is_accepted(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    text = "a" * (LIMIT - 1)
    ended = service.end_session(session.id, notes=ExitNoteInput(**{field: text}))
    assert getattr(ended, field) == text


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_exact_limit_is_accepted(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    text = "a" * LIMIT
    ended = service.end_session(session.id, notes=ExitNoteInput(**{field: text}))
    assert getattr(ended, field) == text


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_limit_plus_one_is_rejected(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    text = "a" * (LIMIT + 1)
    with pytest.raises(SessionError):
        service.end_session(session.id, notes=ExitNoteInput(**{field: text}))


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_rejection_leaves_session_open(
    db_path: Path, project_id: int, field: str
) -> None:
    """An over-limit note must not close the session — nothing partially applied."""
    service = SessionService(db_path)
    session = service.start_session(project_id)
    text = "a" * (LIMIT + 1)
    with pytest.raises(SessionError):
        service.end_session(session.id, notes=ExitNoteInput(**{field: text}))
    active = service.get_active_session(project_id)
    assert active is not None
    assert active.id == session.id


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_very_large_input_is_rejected(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    huge = "a" * (LIMIT * 50)
    with pytest.raises(SessionError):
        service.end_session(session.id, notes=ExitNoteInput(**{field: huge}))


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_unicode_multibyte_characters_counted_as_characters(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)

    session_ok = service.start_session(project_id)
    at_limit = "🚀" * LIMIT
    ended = service.end_session(session_ok.id, notes=ExitNoteInput(**{field: at_limit}))
    assert getattr(ended, field) == at_limit

    session_over = service.start_session(project_id)
    over_limit = "🚀" * (LIMIT + 1)
    with pytest.raises(SessionError):
        service.end_session(session_over.id, notes=ExitNoteInput(**{field: over_limit}))


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_empty_string_is_treated_as_absent(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    ended = service.end_session(session.id, notes=ExitNoteInput(**{field: ""}))
    assert getattr(ended, field) is None


@pytest.mark.parametrize("field", FIELDS)
def test_session_field_whitespace_only_is_treated_as_absent(
    db_path: Path, project_id: int, field: str
) -> None:
    service = SessionService(db_path)
    session = service.start_session(project_id)
    ended = service.end_session(session.id, notes=ExitNoteInput(**{field: "   \n\t  "}))
    assert getattr(ended, field) is None


def test_close_active_session_for_project_also_enforces_the_limit(
    db_path: Path, project_id: int
) -> None:
    """The interactive close path (CLI/IPC entry point) shares the same validation."""
    service = SessionService(db_path)
    service.start_session(project_id)
    text = "a" * (LIMIT + 1)
    with pytest.raises(SessionError):
        service.close_active_session_for_project(project_id, notes=ExitNoteInput(exit_note=text))
    active = service.get_active_session(project_id)
    assert active is not None
