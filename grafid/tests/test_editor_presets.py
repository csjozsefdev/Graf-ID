"""The editor preset registry is the single source of truth for opener choices."""

from __future__ import annotations

import pytest

from grafid.config.editors import (
    EDITOR_PRESETS,
    SYSTEM_OPENER,
    auto_detect_candidates,
    canonical_token,
    editor_display_name,
    editor_ids,
    editor_preset,
    opener_options,
    opener_tokens,
)
from grafid.config.preferences import normalize_default_project_opener
from grafid.core.exceptions import ConfigError, ValidationError
from grafid.services import workflow_launch
from grafid.services.workflow_launch import normalize_ide_token


def test_settings_options_keep_their_documented_order_and_labels() -> None:
    assert [(o["id"], o["label"]) for o in opener_options()] == [
        ("system", "Auto Detect (System default)"),
        ("cursor", "Cursor"),
        ("vscode", "VS Code"),
        ("pycharm", "PyCharm"),
        ("intellij", "IntelliJ IDEA"),
        ("visualstudio", "Visual Studio"),
        ("notepadpp", "Notepad++"),
        ("explorer", "Explorer only"),
        ("custom", "Custom Path"),
    ]


def test_ids_are_unique_and_tokens_are_ids_plus_system() -> None:
    ids = editor_ids()
    assert len(set(ids)) == len(ids)
    assert opener_tokens() == {SYSTEM_OPENER, *ids}


def test_every_launching_preset_can_be_resolved_to_an_executable_or_is_custom() -> None:
    for preset in EDITOR_PRESETS:
        if preset.launches_editor and preset.id != "custom":
            assert preset.executables, preset.id
        else:
            assert not preset.executables, preset.id


@pytest.mark.parametrize(
    ("spelling", "editor"),
    [
        ("code", "vscode"),
        ("VS Code", "vscode"),
        ("visual studio code", "vscode"),
        ("py charm", "pycharm"),
        ("IntelliJ IDEA", "intellij"),
        ("Visual Studio", "visualstudio"),
        ("notepad++", "notepadpp"),
        ("notepad plus plus", "notepadpp"),
        ("Explorer only", "explorer"),
        ("file explorer", "explorer"),
        ("folder", "explorer"),
    ],
)
def test_both_normalizers_accept_the_same_spellings(spelling: str, editor: str) -> None:
    assert canonical_token(spelling) == editor
    assert normalize_ide_token(spelling) == editor
    assert normalize_default_project_opener(spelling) == editor


def test_auto_detect_spellings_only_mean_the_system_opener() -> None:
    assert normalize_default_project_opener("Auto Detect (System default)") == "system"
    with pytest.raises(ValidationError):
        normalize_ide_token("auto detect")


def test_unknown_editor_is_rejected_with_the_full_list() -> None:
    with pytest.raises(ConfigError, match=r"system, cursor, vscode, pycharm, intellij, visualstudio, notepadpp, explorer, or custom"):
        normalize_default_project_opener("eclipse")
    with pytest.raises(ValidationError, match=r"cursor, vscode, pycharm, intellij, visualstudio, notepadpp, explorer, or custom"):
        normalize_ide_token("eclipse")


def test_auto_detect_tries_cursor_then_vscode_then_pycharm(monkeypatch: pytest.MonkeyPatch) -> None:
    assert [editor for editor, _ in auto_detect_candidates()] == ["cursor", "vscode", "pycharm"]
    on_path = {"code", "pycharm64"}
    monkeypatch.setattr(workflow_launch.shutil, "which", lambda name: name if name in on_path else None)
    assert workflow_launch.detect_system_editor() == "vscode"
    on_path.discard("code")
    assert workflow_launch.detect_system_editor() == "pycharm"
    on_path.clear()
    assert workflow_launch.detect_system_editor() is None


def test_display_names_used_in_launch_messages() -> None:
    assert editor_display_name("vscode") == "VS Code"
    assert editor_display_name("custom") == "Custom editor"
    assert editor_display_name("something-else") == "something-else"
    assert editor_preset("explorer") is not None and not editor_preset("explorer").launches_editor
