"""Parse read-only git status --porcelain output."""

from __future__ import annotations


def parse_porcelain_status(output: str) -> tuple[list[str], list[str], bool]:
    """
    Parse porcelain status lines into staged paths, modified paths, and dirty flag.

    Follows git status --porcelain v1 format (XY PATH).

    Untracked (`??`) entries are deliberately excluded from both lists and
    from the dirty flag: they describe files/directories git doesn't track
    yet, not uncommitted changes to tracked content. A working tree with
    only untracked files (build output, scratch folders, a `scripts/` dir
    never added — all common and not "uncommitted work" in any meaningful
    sense) must report as clean, not dirty. Previously `??` lines were
    folded into `modified`, so their mere presence made `is_dirty` true —
    reproduced live: a repo with a single untracked directory and zero
    changes to any tracked file still showed the "Dirty" badge.
    """
    staged: list[str] = []
    modified: list[str] = []
    seen_staged: set[str] = set()
    seen_modified: set[str] = set()

    for raw_line in output.splitlines():
        line = raw_line.rstrip("\r")
        if not line or len(line) < 3:
            continue

        x_status = line[0]
        y_status = line[1]

        if x_status == "?" and y_status == "?":
            continue

        path = _extract_path(line[3:])

        if x_status != " " and x_status != "?":
            if path not in seen_staged:
                staged.append(path)
                seen_staged.add(path)

        if y_status != " " and y_status != "?":
            if path not in seen_modified:
                modified.append(path)
                seen_modified.add(path)

    is_dirty = bool(staged or modified)
    return staged, modified, is_dirty


def _extract_path(raw: str) -> str:
    """Extract path from porcelain line, handling quoted paths and renames."""
    text = raw.strip()
    if " -> " in text:
        text = text.split(" -> ", 1)[1].strip()
    if text.startswith('"') and text.endswith('"'):
        return _decode_git_quoted_path(text[1:-1])
    return text


def _decode_git_quoted_path(inner: str) -> str:
    """Decode git porcelain quoted path (C-style escapes including octal UTF-8 bytes)."""
    raw = bytearray()
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch != "\\":
            raw.extend(ch.encode("utf-8"))
            i += 1
            continue
        if i + 1 >= len(inner):
            raw.extend(b"\\")
            break
        esc = inner[i + 1]
        if esc == "n":
            raw.append(0x0A)
            i += 2
        elif esc == "t":
            raw.append(0x09)
            i += 2
        elif esc in ('"', "\\"):
            raw.append(ord(esc))
            i += 2
        elif "0" <= esc <= "7":
            oct_digits = esc
            j = i + 2
            while j < len(inner) and len(oct_digits) < 3 and "0" <= inner[j] <= "7":
                oct_digits += inner[j]
                j += 1
            raw.append(int(oct_digits, 8))
            i = j
        else:
            raw.append(ord(esc))
            i += 2
    return raw.decode("utf-8")
