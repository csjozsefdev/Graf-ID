"""GrafiTalk handoff: builder, renderers, validator, and the contract regression.

The expected shapes below encode GrafiTalk's own documented importer
(Grafitalk/docs/GRAF_ID_EXPORT_SCHEMA.md). If one of these tests has to change,
GrafiTalk's import contract has changed too and must be coordinated.
"""

from __future__ import annotations

import json

import pytest

from grafid.handoff.builder import build_flat, build_handoff, git_summary_line, serialized_size
from grafid.handoff.render import render_json, render_markdown, render_text
from grafid.handoff.schema import EXTENSION_KEY, GRAFITALK_MAX_BYTES
from grafid.handoff.validate import (
    HandoffValidationError,
    parse_handoff_bytes,
    validate_handoff,
)
from grafid.tests.grafitalk_contract import check_grafitalk_compatibility
from grafid.resume.project_context import (
    CommitRef,
    Continuity,
    ContextNotes,
    GitContext,
    ProjectContext,
    ProjectIdentity,
    WorkflowFileRef,
)

EXPORTED_AT = "2026-09-20T10:00:00+00:00"


def make_context(**over) -> ProjectContext:
    return ProjectContext(
        identity=ProjectIdentity(
            name="Mesencsi webshop",
            category="Client Work",
            status="active",
            last_opened_at="2026-09-19T08:00:00+00:00",
            has_open_session=False,
        ),
        continuity=over.pop(
            "continuity",
            Continuity(
                current_focus="Checkout flow is finished; receipt page in progress.",
                where_you_left_off=("Checkout flow is finished.",),
                suggested_next_step="Wire the receipt page to the API",
                blockers=("Barion production key / merchant approval",),
                open_issues=("Barion production key / merchant approval", "Refund flow"),
                last_completed="Manual QA completed.",
                recent_fixes=("Pin release runtime to Python 3.12.10",),
                recent_improvements=("Add integration flow tracing",),
                confidence="high",
                sources=("exit note", "handoff"),
            ),
        ),
        git=over.pop(
            "git",
            GitContext(
                is_repo=True,
                branch="main",
                state="dirty",
                modified_files=("src/checkout.rs", "README.md"),
                staged_files=("src/receipt.rs",),
                recent_commits=(
                    CommitRef("fix: pin release runtime", "2026-09-14T10:00:00+02:00", "a1b2c3d4"),
                ),
            ),
        ),
        context=over.pop(
            "context",
            ContextNotes(
                notes="Client prefers weekly summaries.",
                workflow_files=(WorkflowFileRef("docs/HANDOVER.md", "handoff"),),
            ),
        ),
    )


# ------------------------------------------------------------------ flat contract


def test_flat_handoff_is_exactly_the_grafitalk_v01_contract() -> None:
    """Snapshot: key set, key order, values."""
    payload = build_flat(make_context())
    assert list(payload) == [
        "source", "schema_version", "project_name", "current_status",
        "changes", "blockers", "next_steps", "notes", "files",
    ]
    assert payload == {
        "source": "graf-id",
        "schema_version": "0.1",
        "project_name": "Mesencsi webshop",
        "current_status": "Checkout flow is finished; receipt page in progress.",
        "changes": [
            "Manual QA completed.",
            "Pin release runtime to Python 3.12.10",
            "Add integration flow tracing",
        ],
        "blockers": ["Barion production key / merchant approval"],
        "next_steps": ["Wire the receipt page to the API"],
        "notes": "Client prefers weekly summaries.\nGit: uncommitted changes on main, 3 changed files.",
        "files": ["src/checkout.rs", "README.md", "src/receipt.rs"],
    }
    assert check_grafitalk_compatibility(payload) == []


def test_lean_handoff_has_no_extension_and_no_absolute_paths_or_ids() -> None:
    text = json.dumps(build_handoff(make_context(), include_extension=False))
    assert EXTENSION_KEY not in text
    assert "C:\\" not in text and "/Users/" not in text and '"id"' not in text


def test_missing_optional_fields_are_omitted_not_null() -> None:
    bare = ProjectContext(identity=ProjectIdentity(name="Bare"))
    payload = build_handoff(bare, include_extension=False)
    assert payload == {"source": "graf-id", "schema_version": "0.1", "project_name": "Bare"}
    assert check_grafitalk_compatibility(payload) == []
    full = build_handoff(bare, include_extension=True, exported_at=EXPORTED_AT)
    assert "null" not in json.dumps(full)
    assert full[EXTENSION_KEY]["project"] == {"name": "Bare", "has_open_session": False}


def test_project_without_blocker_has_no_blockers_key_and_with_blocker_has_it() -> None:
    no_blocker = make_context(continuity=Continuity(current_focus="x y z", blockers=()))
    assert "blockers" not in build_flat(no_blocker)
    assert build_flat(make_context())["blockers"] == ["Barion production key / merchant approval"]


@pytest.mark.parametrize(
    ("git", "expected"),
    [
        (GitContext(is_repo=True, branch="main", state="clean"), "Git: working tree clean on main."),
        (GitContext(is_repo=True, branch="dev", state="dirty", modified_files=("a.py",)),
         "Git: uncommitted changes on dev, 1 changed file."),
        (GitContext(is_repo=True, branch="main", state="unknown"), None),
        (GitContext(is_repo=False), None),
    ],
)
def test_git_summary_lines(git, expected) -> None:
    assert git_summary_line(make_context(git=git)) == expected


def test_clean_repo_lists_no_files_and_dirty_repo_lists_changed_files() -> None:
    clean = build_flat(make_context(git=GitContext(is_repo=True, branch="main", state="clean")))
    assert "files" not in clean and "clean" in clean["notes"]
    dirty = build_flat(make_context())
    assert dirty["files"][0] == "src/checkout.rs"


def test_unicode_survives_every_format() -> None:
    ctx = make_context(
        continuity=Continuity(current_focus="Kosár és pénztár — árvíztűrő tükörfúrógép 日本語"),
        context=ContextNotes(notes="Jegyzet: ő ű á é — ✓"),
    )
    ctx = ProjectContext(identity=ProjectIdentity(name="Projekt Ő"), continuity=ctx.continuity,
                         git=ctx.git, context=ctx.context)
    payload = build_handoff(ctx, include_extension=True, exported_at=EXPORTED_AT)
    for rendered in (render_json(payload), render_markdown(payload), render_text(payload)):
        assert "árvíztűrő tükörfúrógép 日本語" in rendered and "Projekt Ő" in rendered
    assert json.loads(render_json(payload))["project_name"] == "Projekt Ő"


def test_large_notes_keep_the_file_under_the_grafitalk_limit() -> None:
    ctx = make_context(context=ContextNotes(notes="N" * 5000))
    payload = build_handoff(ctx, include_extension=True, exported_at=EXPORTED_AT)
    assert serialized_size(payload) < GRAFITALK_MAX_BYTES
    assert check_grafitalk_compatibility(payload) == []


def test_oversized_extension_is_shed_before_the_contract_fields() -> None:
    from grafid.handoff.builder import enforce_size_limit

    payload = build_handoff(make_context(), include_extension=True, exported_at=EXPORTED_AT)
    payload[EXTENSION_KEY]["git"]["recent_commits"] = [{"subject": "x" * 500}] * 900
    shrunk = enforce_size_limit(payload, limit=60_000)
    assert serialized_size(shrunk) <= 60_000
    assert shrunk["project_name"] == "Mesencsi webshop" and shrunk["next_steps"]


def test_output_is_deterministic() -> None:
    a = build_handoff(make_context(), include_extension=True, exported_at=EXPORTED_AT)
    b = build_handoff(make_context(), include_extension=True, exported_at=EXPORTED_AT)
    assert render_json(a) == render_json(b)


# -------------------------------------------------------------- full JSON extension


def test_full_json_is_flat_contract_plus_additive_graf_id_block() -> None:
    payload = build_handoff(make_context(), include_extension=True, exported_at=EXPORTED_AT)
    flat = build_flat(make_context())
    assert {k: payload[k] for k in flat} == flat
    ext = payload[EXTENSION_KEY]
    assert ext["extension_version"] == 1 and ext["exported_at"] == EXPORTED_AT
    assert ext["app_version"] == "1.0.0"
    assert set(ext) == {"extension_version", "exported_at", "app_version", "project",
                        "continuity", "git", "context"}
    assert ext["project"] == {"name": "Mesencsi webshop", "category": "Client Work",
                              "status": "active", "last_opened_at": "2026-09-19T08:00:00+00:00",
                              "has_open_session": False}
    assert ext["git"]["recent_commits"] == [
        {"subject": "fix: pin release runtime", "committed_at": "2026-09-14T10:00:00+02:00",
         "short_hash": "a1b2c3d4"}
    ]
    assert ext["context"]["workflow_files"] == [{"path": "docs/HANDOVER.md", "kind": "handoff"}]
    assert check_grafitalk_compatibility(payload) == []  # GrafiTalk ignores the unknown key


def test_full_json_requires_an_export_timestamp() -> None:
    with pytest.raises(ValueError):
        build_handoff(make_context(), include_extension=True)


def test_json_round_trip_through_the_validator() -> None:
    payload = build_handoff(make_context(), include_extension=True, exported_at=EXPORTED_AT)
    result = parse_handoff_bytes(render_json(payload).encode("utf-8"))
    assert result.data == build_flat(make_context())
    assert result.extension == payload[EXTENSION_KEY]
    assert result.ignored_keys == () and result.warnings == ()


# ------------------------------------------------------------- Markdown / TXT


def test_markdown_and_text_use_the_labels_grafitalk_imports() -> None:
    payload = build_flat(make_context())
    md = render_markdown(payload)
    assert md.startswith("# Project\nMesencsi webshop\n")
    for heading in ("## Current status", "## What changed", "## Current blocker",
                    "## Next step", "## Notes", "## Files updated"):
        assert heading in md
    txt = render_text(payload)
    assert txt.startswith("Project:\nMesencsi webshop\n")
    for label in ("Current status:", "What changed:", "Current blocker:", "Next step:",
                  "Notes:", "Files updated:"):
        assert label in txt
    assert "- Manual QA completed." in txt


def test_markdown_and_text_skip_empty_sections() -> None:
    payload = build_flat(ProjectContext(identity=ProjectIdentity(name="Bare")))
    assert render_text(payload) == "Project:\nBare\n"
    assert render_markdown(payload) == "# Project\nBare\n"


# ------------------------------------------------------------------- validator


def valid() -> dict:
    return {"source": "graf-id", "schema_version": "0.1", "project_name": "Demo"}


def test_minimal_valid_handoff_is_accepted() -> None:
    assert validate_handoff(valid()).data == valid()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.pop("source"), "source"),
        (lambda d: d.update(source="grafitalk"), "Unsupported source"),
        (lambda d: d.pop("schema_version"), "schema_version"),
        (lambda d: d.update(schema_version="0.2"), "Unsupported schema_version"),
        (lambda d: d.update(schema_version="1"), "Unsupported schema_version"),
        (lambda d: d.update(schema_version=True), "schema_version"),
        (lambda d: d.pop("project_name"), "project_name"),
        (lambda d: d.update(project_name="   "), "project_name"),
        (lambda d: d.update(project_name=["x"]), "project_name"),
        (lambda d: d.update(changes="not a list"), "changes"),
        (lambda d: d.update(blockers=[1, {"a": 1}]), "blockers"),
        (lambda d: d.update(notes={"a": 1}), "notes"),
        (lambda d: d.update(files=["f"] * 101), "too many"),
        (lambda d: d.update(notes="x" * 20_001), "too long"),
    ],
)
def test_malformed_or_unsupported_schema_is_rejected_with_a_reason(mutate, message) -> None:
    data = valid()
    mutate(data)
    with pytest.raises(HandoffValidationError, match=message):
        validate_handoff(data)


def test_numeric_schema_version_is_coerced_like_grafitalk_does() -> None:
    data = valid()
    data["schema_version"] = 0.1
    assert validate_handoff(data).data["schema_version"] == "0.1"


@pytest.mark.parametrize("raw", [b"", b"   \n", b"\xff\xfe\x00garbage", b"{not json", b"[1, 2]", b'"str"', b"null"])
def test_corrupted_input_is_rejected_cleanly(raw: bytes) -> None:
    with pytest.raises(HandoffValidationError):
        parse_handoff_bytes(raw)


def test_oversized_payload_is_rejected_before_parsing() -> None:
    big = json.dumps({**valid(), "notes": "x" * (GRAFITALK_MAX_BYTES + 10)}).encode()
    with pytest.raises(HandoffValidationError, match="too large"):
        parse_handoff_bytes(big)


def test_utf8_bom_is_accepted() -> None:
    assert parse_handoff_bytes(b"\xef\xbb\xbf" + json.dumps(valid()).encode()).data == valid()


def test_unknown_optional_fields_are_ignored_and_reported() -> None:
    data = {**valid(), "future_field": 1, "estimated_time": "2 days"}
    result = validate_handoff(data)
    assert result.ignored_keys == ("future_field",)
    assert result.data["estimated_time"] == "2 days" and "future_field" not in result.data


def test_control_characters_are_stripped() -> None:
    result = validate_handoff({**valid(), "notes": "a\x00b"})
    assert result.data["notes"] == "ab"


@pytest.mark.parametrize(
    "extension",
    ["nope", {"no_version": 1}, {"extension_version": "1"}, {"extension_version": 99}],
)
def test_bad_or_newer_extension_is_dropped_but_never_fails_the_flat_part(extension) -> None:
    result = validate_handoff({**valid(), EXTENSION_KEY: extension})
    assert result.extension is None and result.warnings
    assert result.data["project_name"] == "Demo"


def test_grafitalk_compatibility_checker_flags_real_incompatibilities() -> None:
    bad = {"source": "graf-id", "schema_version": 0.1, "project_name": "",
           "changes": "x", "notes": 3}
    problems = " ".join(check_grafitalk_compatibility(bad))
    for needle in ("schema_version", "project_name", "changes", "notes"):
        assert needle in problems
    assert check_grafitalk_compatibility({**valid(), "notes": "x" * GRAFITALK_MAX_BYTES})


def test_package_version_matches_pyproject() -> None:
    """The export embeds app_version; it must not drift from the released version."""
    import re
    from pathlib import Path

    import grafid

    pyproject = (Path(grafid.__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    assert declared and declared.group(1) == grafid.__version__


def test_status_is_omitted_when_there_is_no_reliable_focus_but_wylo_stays_in_the_extension() -> None:
    ctx = make_context(continuity=Continuity(
        current_focus=None, where_you_left_off=("Last known focus: React 19 + TypeScript stack",)))
    assert "current_status" not in build_flat(ctx)
    ext = build_handoff(ctx, include_extension=True, exported_at=EXPORTED_AT)[EXTENSION_KEY]
    assert ext["continuity"]["where_you_left_off"] == ["Last known focus: React 19 + TypeScript stack"]
