"""Editor presets: the single source of truth for "Open projects with".

Every place that needs to know which editors exist - Settings options, opener
validation, alias handling, executable lookup and auto-detection - reads this
registry instead of keeping its own list. Coding agents have their own registry
in ``coding_agents.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_OPENER = "system"
SYSTEM_OPENER_LABEL = "Auto Detect (System default)"
_SYSTEM_ALIASES = ("auto detect", "auto detect (system default)")


@dataclass(frozen=True)
class EditorPreset:
    """One way to open a project: an editor CLI, Explorer, or a user-chosen program."""

    id: str
    name: str
    """Name used in messages ("Started a session and opened X in VS Code")."""
    executables: tuple[str, ...] = ()
    """Executable names tried on PATH, in order (empty for Explorer and Custom)."""
    aliases: tuple[str, ...] = ()
    """Extra lower-case spellings accepted for the id."""
    auto_detect: tuple[str, ...] = ()
    """PATH probes for "Auto Detect"; presets are tried in registry order."""
    option_label: str | None = None
    """Settings label when it differs from ``name``."""
    launches_editor: bool = True

    @property
    def label(self) -> str:
        return self.option_label or self.name


EDITOR_PRESETS: tuple[EditorPreset, ...] = (
    EditorPreset("cursor", "Cursor", ("cursor", "cursor.cmd"), auto_detect=("cursor",)),
    EditorPreset(
        "vscode",
        "VS Code",
        ("code", "code.cmd"),
        aliases=("code", "vs code", "vs_code", "visual studio code"),
        auto_detect=("code",),
    ),
    EditorPreset(
        "pycharm",
        "PyCharm",
        ("pycharm", "pycharm64", "pycharm.exe", "pycharm64.exe"),
        aliases=("py charm",),
        auto_detect=("pycharm", "pycharm64"),
    ),
    EditorPreset(
        "intellij",
        "IntelliJ IDEA",
        ("idea", "idea64", "idea.exe", "idea64.exe"),
        aliases=("intellij idea",),
    ),
    EditorPreset(
        "visualstudio",
        "Visual Studio",
        ("devenv", "devenv.exe"),
        aliases=("visual studio",),
    ),
    EditorPreset(
        "notepadpp",
        "Notepad++",
        ("notepad++", "notepad++.exe"),
        aliases=("notepad++", "notepad plus plus"),
    ),
    EditorPreset(
        "explorer",
        "Explorer",
        aliases=("explorer only", "folder", "file explorer"),
        option_label="Explorer only",
        launches_editor=False,
    ),
    EditorPreset("custom", "Custom editor", option_label="Custom Path"),
)

_BY_ID = {preset.id: preset for preset in EDITOR_PRESETS}
_ALIASES: dict[str, str] = {alias: preset.id for preset in EDITOR_PRESETS for alias in preset.aliases}
_ALIASES.update({alias: SYSTEM_OPENER for alias in _SYSTEM_ALIASES})


def editor_preset(editor_id: str) -> EditorPreset | None:
    return _BY_ID.get(editor_id)


def editor_display_name(editor_id: str) -> str:
    """Human name for messages; unknown ids are shown as-is."""
    preset = _BY_ID.get(editor_id)
    return preset.name if preset else editor_id


def editor_ids() -> tuple[str, ...]:
    """Ids of every editor preset (without the virtual ``system`` opener)."""
    return tuple(_BY_ID)


def opener_tokens() -> frozenset[str]:
    """Every value the ``default_project_opener`` setting may hold (besides ``agent:<id>``)."""
    return frozenset({SYSTEM_OPENER, *_BY_ID})


def _human_list(items: tuple[str, ...]) -> str:
    return ", ".join(items[:-1]) + ", or " + items[-1]


def opener_token_list() -> str:
    """The valid opener tokens in Settings order ("system, cursor, ..., or custom")."""
    return _human_list((SYSTEM_OPENER, *_BY_ID))


def editor_id_list() -> str:
    """The editor ids in Settings order ("cursor, ..., or custom"), for error messages."""
    return _human_list(tuple(_BY_ID))


def canonical_token(value: str) -> str:
    """Lower-cased ``value`` with known aliases resolved (unknown values pass through)."""
    token = value.strip().lower()
    return _ALIASES.get(token, token)


def opener_options() -> list[dict[str, str]]:
    """Options for the Settings UI, in display order."""
    options = [{"id": SYSTEM_OPENER, "label": SYSTEM_OPENER_LABEL}]
    options += [{"id": preset.id, "label": preset.label} for preset in EDITOR_PRESETS]
    return options


def auto_detect_candidates() -> list[tuple[str, tuple[str, ...]]]:
    """(editor id, PATH probes) in the order "Auto Detect" tries them."""
    return [(preset.id, preset.auto_detect) for preset in EDITOR_PRESETS if preset.auto_detect]
