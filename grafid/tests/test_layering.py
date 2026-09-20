"""Import-direction guard for the layers the audit fixed.

The rule: lower layers never import higher ones. Only the boundaries that are
clean today are pinned (services must not know the IPC/CLI front doors; the IPC
handlers must not import the CLI; persistence must not import any of them), so a
regression fails here instead of silently re-creating a dependency cycle.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _imported_packages(package: str) -> dict[str, set[str]]:
    """{module path: top-level grafid packages it imports (incl. function-local imports)}."""
    result: dict[str, set[str]] = {}
    for path in (ROOT / package).rglob("*.py"):
        found: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            for name in names:
                parts = name.split(".")
                if parts[0] == "grafid" and len(parts) > 1:
                    found.add(parts[1])
        result[str(path.relative_to(ROOT))] = found
    return result


@pytest.mark.parametrize(
    ("package", "forbidden"),
    [
        ("services", {"ipc", "cli"}),
        ("ipc", {"cli"}),
        ("db", {"ipc", "cli", "services"}),
        ("config", {"ipc", "cli", "services"}),
        ("handoff", {"ipc", "cli"}),
        ("resume", {"ipc", "cli", "services"}),
    ],
)
def test_lower_layers_do_not_import_higher_ones(package: str, forbidden: set[str]) -> None:
    offenders = {
        module: sorted(imports & forbidden)
        for module, imports in _imported_packages(package).items()
        if imports & forbidden
    }
    assert not offenders, f"{package}/ imports a higher layer: {offenders}"
