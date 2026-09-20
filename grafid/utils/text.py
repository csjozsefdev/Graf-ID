"""Small text helpers shared across layers."""

from __future__ import annotations

from collections.abc import Callable, Iterable


def clean_optional_text(value: object | None) -> str | None:
    """``str(value)`` stripped, or ``None`` when ``value`` is ``None`` or blank."""
    if value is None:
        return None
    return str(value).strip() or None


def dedupe(
    items: Iterable[str],
    *,
    limit: int | None = None,
    clean: Callable[[str], str] | None = None,
) -> list[str]:
    """Drop empty and case-insensitive duplicate items, keeping first-seen order.

    ``clean`` normalizes each item first (e.g. collapse whitespace or clip);
    ``limit`` stops after that many kept items.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        text = clean(item) if clean else item
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        kept.append(text)
        if limit is not None and len(kept) >= limit:
            break
    return kept
