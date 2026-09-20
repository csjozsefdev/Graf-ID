"""Shared helpers: optional-text cleaning, order-preserving dedupe, ISO parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from grafid.utils.datetime_utils import parse_iso
from grafid.utils.text import clean_optional_text, dedupe


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), ("   ", None), ("  /opt/editor/bin ", "/opt/editor/bin"), (42, "42")],
)
def test_clean_optional_text(raw: object, expected: str | None) -> None:
    assert clean_optional_text(raw) == expected


def test_dedupe_is_case_insensitive_keeps_first_and_skips_empty() -> None:
    assert dedupe(["Fix login", "fix LOGIN", "", "Add tests", "add tests"]) == ["Fix login", "Add tests"]


def test_dedupe_limit_and_clean() -> None:
    items = ["  a  b ", "A B", "c", "d"]
    assert dedupe(items, limit=2, clean=lambda t: " ".join(t.split())) == ["a b", "c"]


def test_dedupe_without_limit_returns_everything_unique() -> None:
    assert dedupe(str(n % 3) for n in range(9)) == ["0", "1", "2"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-20T10:00:00Z", datetime(2026, 9, 20, 10, 0, tzinfo=UTC)),
        ("2026-09-20T10:00:00+00:00", datetime(2026, 9, 20, 10, 0, tzinfo=UTC)),
        ("2026-09-20T10:00:00", datetime(2026, 9, 20, 10, 0, tzinfo=UTC)),
        ("  2026-09-20T10:00:00Z ", datetime(2026, 9, 20, 10, 0, tzinfo=UTC)),
    ],
)
def test_parse_iso_reads_z_offsets_and_naive_values_as_utc(raw: str, expected: datetime) -> None:
    assert parse_iso(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "not a date", "2026-13-40"])
def test_parse_iso_returns_none_for_unusable_values(raw: str | None) -> None:
    assert parse_iso(raw) is None
