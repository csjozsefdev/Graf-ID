"""Launch projects in the editor or file manager for workflow continuation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grafid.config.coding_agents import is_agent_opener_value
from grafid.config.editors import (
    auto_detect_candidates,
    canonical_token,
    editor_display_name,
    editor_id_list,
    editor_ids,
    editor_preset,
)
from grafid.config.manager import AppConfig
from grafid.config.preferences import CUSTOM_OPENER_PATH_KEY, opener_to_ide_token
from grafid.core.exceptions import (
    ProjectError,
    SessionError,
    ValidationError,
)
from grafid.models.project import ProjectRecord
from grafid.models.session import WorkSessionRecord
from grafid.services.project_registry import ProjectRegistryService
from grafid.services.project_validation import normalize_project_path
from grafid.services.session_service import SessionService
from grafid.utils.logging_setup import get_logger

logger = get_logger("workflow_launch")

if sys.platform == "win32":
    _SUBPROCESS_CREATE_FLAGS = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
else:
    _SUBPROCESS_CREATE_FLAGS = 0

def detect_system_editor() -> str | None:
    """Pick the first preset whose auto-detect command is on PATH (registry order)."""
    for editor_id, probes in auto_detect_candidates():
        if any(shutil.which(probe) for probe in probes):
            return editor_id
    return None


@dataclass(frozen=True)
class LaunchOutcome:
    """Result of opening a project for continued work."""

    action: str
    editor: str | None
    message: str
    session_id: int | None
    session_started: bool
    fallback_used: bool
    open_explorer: bool
    editor_pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        editor_launched = self.action == "editor" and not self.fallback_used
        return {
            "success": True,
            "message": self.message,
            "editor_launched": editor_launched,
            "explorer_opened": self.open_explorer,
            "fallback_used": self.fallback_used,
            "action": self.action,
            "editor": self.editor,
            "session_id": self.session_id,
            "session_started": self.session_started,
            "editor_pid": self.editor_pid,
        }


class WorkflowLaunchError(ProjectError):
    """User-facing launch failure (missing path, editor, or OS error)."""


def normalize_ide_token(value: str | None) -> str | None:
    """Map config/CLI values to a supported IDE token or None.

    Contract:
    - ``None``, empty, ``-``, ``none``, ``null`` → ``None``
    - Known aliases (e.g. ``code`` → ``vscode``, ``intellij idea`` → ``intellij``)
    - Supported presets: cursor, vscode, pycharm, intellij, visualstudio, notepadpp,
      explorer, custom
    - A coding-agent opener value (``agent:<id>``) → ``None``. Agents are launched
      through a completely separate flow (grafid/services/coding_agent_launch.py)
      that the desktop UI routes to directly; this function never resolves one to
      an editor, so a caller that still reaches here with an agent selected (e.g.
      the CLI) falls through to the Explorer fallback instead of raising.
    - Any other token raises ``ValidationError``
    """
    if value is None:
        return None
    if is_agent_opener_value(value):
        return None
    token = value.strip().lower()
    if not token or token in {"-", "none", "null"}:
        return None
    normalized = canonical_token(token)
    if normalized not in editor_ids():
        raise ValidationError(
            f"Unsupported preferred_ide '{value}'. Use {editor_id_list()}."
        )
    return normalized


def resolve_preferred_ide(
    project: ProjectRecord,
    config: AppConfig,
) -> str | None:
    """Project metadata wins, then default_project_opener."""
    if project.preferred_ide:
        return normalize_ide_token(project.preferred_ide)
    opener = config.default_project_opener or "system"
    ide = opener_to_ide_token(opener)
    if ide is None and opener == "system":
        ide = detect_system_editor()
    return ide


class WorkflowLaunchService:
    """Open folders and resume work in a configured editor."""

    def __init__(self, db_path: Path, registry: ProjectRegistryService) -> None:
        self._db_path = db_path
        self._registry = registry
        self._sessions = SessionService(db_path)

    def open_folder(self, raw_path: str) -> dict[str, Any]:
        """
        Open the registered project root in the file manager (CLI / ipc open-folder).

        Uses the stored registry path only — no subfolder guessing.
        """
        folder = normalize_project_path(raw_path)
        open_folder_in_explorer(folder)
        message = f"Opened folder in File Explorer: {folder}"
        logger.info(message)
        return {"path": str(folder), "message": message}

    def open_project(
        self,
        project_id: int,
        *,
        config: AppConfig,
        launch_explorer: bool = True,
    ) -> tuple[ProjectRecord, LaunchOutcome]:
        """
        Resume workflow: last_opened_at, session, editor launch, optional Explorer.

        When launch_explorer is False (desktop IPC), Explorer is not opened here;
        the UI opens the registered project root once via Rust instead.
        """
        updated = self._registry.open_project(str(project_id))
        try:
            folder = normalize_project_path(updated.path)
        except ValidationError as exc:
            raise WorkflowLaunchError(str(exc)) from exc
        session, session_started = self._ensure_work_session(updated.id)
        ide = resolve_preferred_ide(updated, config)

        if ide == "explorer":
            return updated, self._explorer_outcome(
                updated,
                session,
                session_started,
                fallback_used=False,
                editor=None,
                extra_message=f"Opened {updated.name} in File Explorer.",
                launch_explorer=launch_explorer,
                folder=folder,
            )

        preset = editor_preset(ide) if ide else None
        if preset is not None and preset.launches_editor:
            try:
                editor_pid = launch_editor(ide, folder, config=config)
                label = editor_display_name(ide)
                verb = "Started" if session_started else "Resumed"
                return updated, LaunchOutcome(
                    action="editor",
                    editor=ide,
                    message=f"{verb} session and opened {updated.name} in {label}.",
                    session_id=session.id if session else None,
                    session_started=session_started,
                    fallback_used=False,
                    open_explorer=False,
                    editor_pid=editor_pid,
                )
            except WorkflowLaunchError as exc:
                logger.warning("Editor launch failed (%s); falling back to Explorer", exc)
                label = editor_display_name(ide)
                return updated, self._explorer_outcome(
                    updated,
                    session,
                    session_started,
                    fallback_used=True,
                    editor=ide,
                    extra_message=(
                        f"{label} is not available ({exc}). "
                        f"Opened {updated.name} in File Explorer instead."
                    ),
                    launch_explorer=launch_explorer,
                    folder=folder,
                )

        hint = 'Choose an editor under Settings → "Open projects with".'
        return updated, self._explorer_outcome(
            updated,
            session,
            session_started,
            fallback_used=False,
            editor=None,
            extra_message=(
                f"No editor available for {updated.name}. "
                f"Opened folder in File Explorer. {hint}"
            ),
            launch_explorer=launch_explorer,
            folder=folder,
        )

    def _explorer_outcome(
        self,
        updated: ProjectRecord,
        session: WorkSessionRecord | None,
        session_started: bool,
        *,
        fallback_used: bool,
        editor: str | None,
        extra_message: str,
        launch_explorer: bool,
        folder: Path,
    ) -> LaunchOutcome:
        """Open Explorer once in-process, or defer to desktop Rust (open_explorer=True)."""
        if launch_explorer:
            open_folder_in_explorer(folder)
            open_explorer = False
        else:
            open_explorer = True
        return LaunchOutcome(
            action="explorer",
            editor=editor,
            message=extra_message,
            session_id=session.id if session else None,
            session_started=session_started,
            fallback_used=fallback_used,
            open_explorer=open_explorer,
        )

    def _ensure_work_session(
        self, project_id: int
    ) -> tuple[WorkSessionRecord | None, bool]:
        """Reuse an active session or start a new one for workflow continuity."""
        active = self._sessions.get_active_session(project_id)
        if active is not None:
            return active, False
        try:
            started = self._sessions.start_session(project_id)
            return started, True
        except SessionError as exc:
            logger.warning("Could not start session on open: %s", exc)
            active = self._sessions.get_active_session(project_id)
            if active is not None:
                return active, False
            raise WorkflowLaunchError(str(exc)) from exc


def open_folder_in_explorer(folder: Path) -> None:
    """Open the project root directory in the platform file manager."""
    path = folder.resolve()
    if not path.is_dir():
        raise WorkflowLaunchError(f"Project folder does not exist: {path}")

    try:
        if sys.platform == "win32":
            subprocess.Popen(  # noqa: S603
                ["explorer", str(path)],
                start_new_session=True,
                creationflags=_SUBPROCESS_CREATE_FLAGS,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)], start_new_session=True)  # noqa: S603
        else:
            subprocess.Popen(["xdg-open", str(path)], start_new_session=True)  # noqa: S603
    except OSError as exc:
        raise WorkflowLaunchError(
            f"Could not open folder in the file manager: {exc}"
        ) from exc


def _find_editor_executable(ide: str, *, config: AppConfig | None = None) -> str:
    """Resolve editor CLI or executable on PATH / common install locations."""
    if ide == "custom":
        if config is None:
            raise WorkflowLaunchError("Custom editor path is not configured.")
        custom_path = config.extra.get(CUSTOM_OPENER_PATH_KEY)
        if not custom_path:
            raise WorkflowLaunchError(
                "Custom editor path is empty. Set it under Settings → Open projects with."
            )
        path = Path(str(custom_path)).expanduser()
        if not path.is_file():
            raise WorkflowLaunchError(f"Custom editor not found at {path}")
        return str(path.resolve())

    preset = editor_preset(ide)
    if preset is None or not preset.executables:
        raise WorkflowLaunchError(f"Unsupported editor: {ide}")
    candidates = preset.executables

    for name in candidates:
        found = shutil.which(name)
        if found:
            return found

    label = editor_display_name(ide)
    raise WorkflowLaunchError(
        f"{label} was not found on PATH. Install it or add it to PATH, "
        "or choose Explorer only / Custom Path in Settings."
    )


def launch_editor(ide: str, folder: Path, *, config: AppConfig | None = None) -> int | None:
    """Launch a configured editor on a project folder (detached process)."""
    path = folder.resolve()
    if not path.is_dir():
        raise WorkflowLaunchError(f"Project folder does not exist: {path}")

    executable = _find_editor_executable(ide, config=config)
    try:
        proc = subprocess.Popen(  # noqa: S603
            [executable, str(path)],
            cwd=str(path),
            start_new_session=True,
            creationflags=_SUBPROCESS_CREATE_FLAGS,
        )
    except OSError as exc:
        label = editor_display_name(ide)
        raise WorkflowLaunchError(f"Failed to start {label}: {exc}") from exc

    logger.info("Launched %s for %s (pid=%s)", ide, path, proc.pid)
    return proc.pid
