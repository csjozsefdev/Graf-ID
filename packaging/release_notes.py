"""Print one version's section of CHANGELOG.md, for use as GitHub Release notes.

    python packaging/release_notes.py 1.0.0 > notes.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"


def extract(changelog: str, version: str) -> str:
    """The body under ``## [version]`` up to the next ``## [`` heading, without the heading."""
    text = changelog.replace("\r\n", "\n")
    heading = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n", text, re.MULTILINE)
    if heading is None:
        raise LookupError(f"CHANGELOG.md has no section for version {version}")
    rest = text[heading.end():]
    following = re.search(r"^## \[", rest, re.MULTILINE)
    body = rest[: following.start()] if following else rest
    return body.strip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_notes.py <version>", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(extract(CHANGELOG.read_text(encoding="utf-8"), argv[1].lstrip("v")))
    except LookupError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
