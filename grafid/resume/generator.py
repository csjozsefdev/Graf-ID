"""Deterministic resume summary builder."""

from __future__ import annotations

from grafid.models.snapshot import PersistedFindingRecord
from grafid.resume.models import ResumeBundle, ResumeMode, ResumeSection, ResumeSummary
from grafid.resume.quality import (
    SummaryPurpose,
    compact_section_title,
    normalize_note,
    truncate_scroll_content,
)

# Display limits (noise reduction)
SHORT_LIMITS = {"findings": 5, "modified": 5, "staged": 3, "active_files": 5, "commits": 2}
DETAILED_LIMITS = {"findings": 15, "modified": 10, "staged": 6, "active_files": 10, "commits": 3}

MARKER_ORDER = ("FIXME", "BUG", "HACK", "TODO", "NEXT")
SECTION_PRIORITY = {
    "exit_note": 1,
    "handoff": 2,
    "next_step": 3,
    "workflow_next": 4,
    "workflow_session": 5,
    "workflow_exit_note": 6,
    "workflow_notes": 7,
    "workflow_todo": 8,
    "workflow_readme": 9,
    "workflow_changelog": 10,
    "blocker": 11,
    "modified_files": 12,
    "staged_files": 13,
    "unfinished_tasks": 14,
    "last_active_files": 15,
    "metadata": 99,
}

WORKFLOW_SECTION_TITLES = {
    "handoff": "Handoff document",
    "next": "Next steps",
    "session": "Session notes",
    "exit_note": "Exit note file",
    "notes": "Project notes",
    "todo": "Task list",
    "readme": "Readme",
    "changelog": "Changelog",
}


class ResumeSummaryGenerator:
    """Build explainable resume text from a ResumeBundle."""

    def generate(
        self,
        bundle: ResumeBundle,
        *,
        mode: ResumeMode = "short",
        purpose: SummaryPurpose = "resume",
    ) -> ResumeSummary:
        limits = SHORT_LIMITS if mode == "short" else DETAILED_LIMITS
        if purpose == "startup":
            limits = {
                "findings": min(3, limits["findings"]),
                "modified": min(3, limits["modified"]),
                "staged": 0,
                "active_files": min(3, limits["active_files"]),
                "commits": 1,
            }
        sections: list[ResumeSection] = []

        exit_note = (
            normalize_note(bundle.session.exit_note) if bundle.session else None
        )
        blocker = normalize_note(bundle.session.blocker) if bundle.session else None
        next_step = normalize_note(bundle.session.next_step) if bundle.session else None

        if exit_note:
            sections.append(
                _section(
                    "exit_note",
                    "Last session note (done)",
                    [exit_note],
                    purpose=purpose,
                )
            )

        if next_step:
            sections.append(
                _section("next_step", "Next step", [next_step], purpose=purpose)
            )

        for artifact in bundle.workflow_artifacts:
            section_key = (
                "handoff"
                if artifact.kind == "handoff"
                else f"workflow_{artifact.kind}"
            )
            title = WORKFLOW_SECTION_TITLES.get(artifact.kind, "Workflow file")
            artifact_lines: list[str] = []
            if artifact.title:
                artifact_lines.append(artifact.title)
            if artifact.focus_area:
                artifact_lines.append(f"Focus area: {artifact.focus_area}")
            if artifact.next_step_line:
                artifact_lines.append(f"Next step: {artifact.next_step_line}")
            artifact_lines.extend(artifact.preview_lines)
            if artifact_lines:
                sections.append(
                    _section(section_key, title, artifact_lines, purpose=purpose)
                )

        if blocker:
            sections.append(
                _section("blocker", "Current blocker", [blocker], purpose=purpose)
            )

        modified, staged = _git_file_lists(bundle)
        if modified:
            lines = [f"- {path}" for path in modified[: limits["modified"]]]
            sections.append(_section("modified_files", "Modified files", lines))

        if staged and mode == "detailed":
            lines = [f"- {path}" for path in staged[: limits["staged"]]]
            sections.append(_section("staged_files", "Staged files", lines))

        task_lines = _format_findings(bundle.findings, limits["findings"])
        if task_lines:
            sections.append(_section("unfinished_tasks", "Unfinished task markers", task_lines))

        active_files = _active_files(bundle.findings, limits["active_files"])
        if active_files:
            lines = [f"- {path}" for path in active_files]
            sections.append(_section("last_active_files", "Last active files", lines))

        if purpose != "startup":
            meta_lines = _metadata_lines(bundle, limits)
            if meta_lines:
                sections.append(_section("metadata", "Context", meta_lines))

        if not sections:
            sections.append(
                _section(
                    "metadata",
                    "Context",
                    [
                        "No session notes or scan data stored yet.",
                        "Add a project scan and work session to capture where you stopped.",
                    ],
                )
            )

        sections.sort(key=lambda item: item.priority)
        ordered = tuple(sections)
        body = _render_body(bundle.project_name, mode, ordered, bundle, purpose=purpose)
        body = truncate_scroll_content(body, purpose=purpose)

        return ResumeSummary(
            project_name=bundle.project_name,
            mode=mode,
            sections=ordered,
            body=body,
            snapshot_id=bundle.snapshot.id if bundle.snapshot else None,
            session_id=bundle.session.id if bundle.session else None,
        )


def _section(
    key: str,
    title: str,
    lines: list[str],
    *,
    purpose: SummaryPurpose = "resume",
) -> ResumeSection:
    cleaned = tuple(line for line in lines if line and line.strip())
    display_title = compact_section_title(title) if purpose == "startup" else title
    priority = SECTION_PRIORITY.get(key, SECTION_PRIORITY["metadata"])
    return ResumeSection(
        priority=priority, title=display_title, lines=cleaned
    )


def _git_file_lists(bundle: ResumeBundle) -> tuple[list[str], list[str]]:
    if bundle.git is None or not bundle.git.is_git_repo:
        return [], []
    return list(bundle.git.modified_files), list(bundle.git.staged_files)


def _dedupe_findings(
    findings: tuple[PersistedFindingRecord, ...],
) -> list[PersistedFindingRecord]:
    seen: set[tuple[str, int, str, str]] = set()
    unique: list[PersistedFindingRecord] = []
    for item in findings:
        text_key = " ".join(item.text.lower().split())
        key = (item.file_path, item.line_number, item.marker, text_key)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _format_findings(
    findings: tuple[PersistedFindingRecord, ...], limit: int
) -> list[str]:
    deduped = _dedupe_findings(findings)
    deduped.sort(
        key=lambda item: (
            MARKER_ORDER.index(item.marker) if item.marker in MARKER_ORDER else 99,
            item.file_path,
            item.line_number,
        )
    )
    lines: list[str] = []
    for item in deduped[:limit]:
        text = item.text.strip() or "(no description)"
        lines.append(f"- {item.marker} {item.file_path}:{item.line_number} {text}")
    return lines


def _active_files(
    findings: tuple[PersistedFindingRecord, ...], limit: int
) -> list[str]:
    paths = sorted({item.file_path for item in findings})
    return paths[:limit]


def _metadata_lines(bundle: ResumeBundle, limits: dict[str, int]) -> list[str]:
    lines: list[str] = []

    if bundle.session:
        if bundle.using_active_session:
            lines.append("You have an active session for this project.")
        else:
            lines.append("Your last session has ended.")
        lines.append(f"Session started: {bundle.session.started_at}")
        if bundle.session.ended_at:
            lines.append(f"Session ended: {bundle.session.ended_at}")
    else:
        lines.append("No work session has been recorded yet.")

    if bundle.snapshot:
        lines.append(
            f"Latest scan: {bundle.snapshot.scanned_at} "
            f"({bundle.snapshot.findings_count} task marker(s) found)."
        )
    else:
        lines.append("No scan has been run for this project yet.")

    if bundle.git and bundle.git.is_git_repo:
        dirty = "has uncommitted changes" if bundle.git.is_dirty else "is clean"
        branch = bundle.git.current_branch or "unknown"
        lines.append(f"Git branch {branch} {dirty}.")
        for commit in bundle.git.latest_commits[: limits["commits"]]:
            short_hash = commit.get("commit_hash", "")[:8]
            subject = commit.get("subject", "")
            lines.append(f"  Recent commit {short_hash}: {subject}")
    elif bundle.git is not None:
        lines.append("Not a git repository at last scan.")
    else:
        lines.append("No git information from the latest scan.")

    return lines


def _render_body(
    project_name: str,
    mode: ResumeMode,
    sections: tuple[ResumeSection, ...],
    bundle: ResumeBundle,
    *,
    purpose: SummaryPurpose = "resume",
) -> str:
    if purpose == "startup":
        header = [
            f"Where you left off — {project_name}",
            "",
        ]
    else:
        header = [
            "Where you left off",
            "",
        ]
    parts = list(header)
    for section in sections:
        parts.append(section.title + ":")
        if section.lines:
            parts.extend(section.lines)
        else:
            parts.append("- (none)")
        parts.append("")

    if bundle.using_active_session:
        parts.append(
            "Active session in progress. End the session with an Exit Note when you finish."
        )
    return "\n".join(parts).rstrip() + "\n"


def count_open_tasks(findings: tuple[PersistedFindingRecord, ...]) -> int:
    """Count deduplicated task markers for headlines."""
    return len(_dedupe_findings(findings))
