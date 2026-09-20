"""CLI tests for resume command invocation (Typer option ordering)."""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from grafid.cli.main import app
from grafid.config.manager import ConfigManager

runner = CliRunner()

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(text: str) -> str:
    """Rich/Typer's --help output can carry color codes depending on how the
    environment is detected (observed varying by CI runner, not just OS) —
    strip them so text assertions check content, not terminal styling."""
    return _ANSI_ESCAPE_RE.sub("", text)


@pytest.fixture
def cli_env(config_manager: ConfigManager, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point CLI runtime at the isolated test config directory."""
    monkeypatch.setenv("GRAFID_DATA_DIR", str(config_manager.config_dir))


def _output(result) -> str:
    return f"{result.stdout}\n{result.stderr}"


def test_resume_help_lists_project_and_options() -> None:
    """
    Checks CLI semantics (the identifier argument and both mode options are
    documented), not decorative help formatting. `resume.py` never declares
    an explicit `metavar` for `identifier`, so its exact on-screen casing/
    bracketing (`IDENTIFIER` vs `{identifier}`, ASCII vs Unicode box-drawing)
    is decided entirely by whichever Typer/Click version happens to resolve
    from the unpinned `typer>=0.12` dependency — confirmed by comparing
    output across typer 0.25.1 (Click-based) and 0.27.2 (Click-free); not a
    GRAF-ID CLI contract worth pinning a test to. A wide COLUMNS avoids
    Rich wrapping option text across lines on narrow CI terminals, and
    stripping ANSI color codes avoids a second, independent source of
    substring-match flakiness seen on GitHub's Windows CI runner.
    """
    result = runner.invoke(app, ["resume", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    output = _strip_ansi(result.stdout)
    assert "identifier" in output.lower()
    assert "--short" in output
    assert "--detailed" in output


def test_resume_project_then_short_option(cli_env, project_id: int) -> None:
    """Natural order: graf-id resume <project> --short"""
    result = runner.invoke(app, ["resume", "test-project", "--short"])
    assert result.exit_code == 0, _output(result)
    assert "resume_id:" in result.stdout
    assert "history:" in result.stdout


def test_resume_short_option_before_project(cli_env, project_id: int) -> None:
    """Also valid: graf-id resume --short <project>"""
    result = runner.invoke(app, ["resume", "--short", "test-project"])
    assert result.exit_code == 0, _output(result)
    assert "resume_id:" in result.stdout


def test_resume_default_is_short_mode(cli_env, project_id: int) -> None:
    result = runner.invoke(app, ["resume", "test-project"])
    assert result.exit_code == 0, _output(result)
    assert "resume_id:" in result.stdout


def test_resume_latest_command(cli_env, project_id: int) -> None:
    runner.invoke(app, ["resume", "test-project", "--short"])
    result = runner.invoke(app, ["resume-latest", "test-project", "--short"])
    assert result.exit_code == 0, _output(result)
    assert "resume_id:" in result.stdout


def test_resume_missing_project_shows_error() -> None:
    result = runner.invoke(app, ["resume"])
    assert result.exit_code != 0
    combined = _output(result)
    assert "IDENTIFIER" in combined or "Missing" in combined
