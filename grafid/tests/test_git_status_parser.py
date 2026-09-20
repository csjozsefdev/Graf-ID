"""Unit tests for git porcelain status parsing (no git executable required)."""

from __future__ import annotations

from grafid.git.status_parser import parse_porcelain_status


def test_first_line_unstaged_modification() -> None:
    staged, modified, dirty = parse_porcelain_status(" M tracked.txt\n")

    assert staged == []
    assert modified == ["tracked.txt"]
    assert dirty is True


def test_untracked_file_alone_is_not_dirty() -> None:
    """Regression: untracked (??) entries used to be folded into `modified`,
    so a working tree with nothing but an untracked file/dir reported dirty.
    An untracked file is not an uncommitted change to tracked content."""
    staged, modified, dirty = parse_porcelain_status("?? new.txt\n")

    assert staged == []
    assert modified == []
    assert dirty is False


def test_untracked_directory_alone_is_not_dirty() -> None:
    """Same bug, reproduced with the exact shape seen in real use: git
    collapses a wholly-untracked directory into one `??` porcelain line."""
    staged, modified, dirty = parse_porcelain_status("?? scripts/\n")

    assert staged == []
    assert modified == []
    assert dirty is False


def test_completely_clean_tree_is_not_dirty() -> None:
    staged, modified, dirty = parse_porcelain_status("")

    assert staged == []
    assert modified == []
    assert dirty is False


def test_staged_only_is_dirty() -> None:
    staged, modified, dirty = parse_porcelain_status("A  new_tracked.txt\n")

    assert staged == ["new_tracked.txt"]
    assert modified == []
    assert dirty is True


def test_deleted_tracked_file_is_dirty() -> None:
    staged, modified, dirty = parse_porcelain_status(" D removed.txt\n")

    assert staged == []
    assert modified == ["removed.txt"]
    assert dirty is True


def test_untracked_plus_modified_is_dirty_and_excludes_untracked_from_modified() -> None:
    output = "?? scratch/\n M tracked.txt\n"
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == []
    assert modified == ["tracked.txt"]
    assert dirty is True


def test_staged_and_unstaged_separate() -> None:
    output = "M  staged.txt\n M both.txt\n"
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == ["staged.txt"]
    assert modified == ["both.txt"]
    assert dirty is True


def test_rename_uses_destination_path() -> None:
    staged, modified, dirty = parse_porcelain_status("R  old.txt -> new.txt\n")

    assert staged == ["new.txt"]
    assert modified == []
    assert dirty is True


def test_quoted_unicode_path_untracked_is_not_dirty() -> None:
    output = '?? "café rené.txt"\n'
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == []
    assert modified == []
    assert dirty is False


def test_git_octal_escaped_unicode_path_untracked_is_not_dirty() -> None:
    # Git porcelain quotes non-ASCII bytes as octal: café = caf + \303\251
    output = '?? "caf\\303\\251 ren\\303\\251.txt"\n'
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == []
    assert modified == []
    assert dirty is False


def test_quoted_unicode_path_still_extracted_when_tracked_and_modified() -> None:
    """The quoted-path decoding itself is unaffected by the untracked fix —
    still exercised via a tracked, modified (not untracked) path."""
    output = ' M "café rené.txt"\n'
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == []
    assert modified == ["café rené.txt"]
    assert dirty is True


def test_git_octal_escaped_rename_destination() -> None:
    output = 'R  old.txt -> "caf\\303\\251.txt"\n'
    staged, modified, dirty = parse_porcelain_status(output)

    assert staged == ["café.txt"]
    assert modified == []
    assert dirty is True
