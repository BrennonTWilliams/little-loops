"""Captured formatting policy and pure ``is_formatted`` parity (FEAT-3561 phase B)."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from little_loops.issue_parser import _required_sections, is_formatted
from little_loops.issue_template import get_bundled_templates_dir, load_issue_sections
from little_loops.next_arena.inputs import (
    capture_formatting_policy,
    is_formatted_from_state,
)
from little_loops.next_arena.state import ProjectState
from tests.next_arena_support import collect, make_project, record, write_issue

CUTOVER = "2026-07-30"


def _headings(issue_type: str, *, drop: tuple[str, ...] = ()) -> str:
    required = sorted(_required_sections(load_issue_sections(issue_type)))
    return "# Title\n\n" + "".join(f"## {h}\n\ntext\n\n" for h in required if h not in drop)


def _stamp(root: Path, value: str = CUTOVER) -> None:
    (root / ".ll" / "program-design-cutover.json").write_text(
        json.dumps({"date": value}), encoding="utf-8"
    )


def _cases(root: Path) -> dict[str, Path]:
    """A spread of formatted/unformatted/PD-gated issues, keyed by relpath."""
    log = "\n## Session Log\n- `/ll:format-issue` - 2026-10-01T10:00:00 - `a.jsonl`\n"
    specs: dict[str, tuple[dict[str, Any] | None, str]] = {
        "bugs/P3-BUG-001-complete-no-pd.md": (None, _headings("BUG", drop=("Program Design",))),
        "bugs/P3-BUG-002-complete-with-pd.md": (None, _headings("BUG")),
        "bugs/P3-BUG-003-missing-section.md": (None, _headings("BUG", drop=("Summary",))),
        "bugs/P3-BUG-004-format-log.md": (None, "# T\n" + log),
        "features/P3-FEAT-005-new-no-pd.md": (
            {"discovered_date": "2026-09-01"},
            _headings("FEAT", drop=("Program Design",)),
        ),
        "features/P3-FEAT-006-old-no-pd.md": (
            {"discovered_date": "2026-01-01"},
            _headings("FEAT", drop=("Program Design",)),
        ),
        "features/P3-FEAT-007-opt-out.md": (
            {"discovered_date": "2026-09-01", "program_design_not_applicable": "true"},
            _headings("FEAT", drop=("Program Design",)),
        ),
        "features/P3-FEAT-008-refined-after.md": (
            {"discovered_date": "2026-01-01"},
            _headings("FEAT", drop=("Program Design",))
            + "## Session Log\n- `/ll:refine-issue` - 2026-09-15T10:00:00 - `r.jsonl`\n",
        ),
        "features/P3-FEAT-009-refined-before.md": (
            {"discovered_date": "2026-09-01"},
            _headings("FEAT", drop=("Program Design",))
            + "## Session Log\n- `/ll:refine-issue` - 2026-02-15T10:00:00 - `r.jsonl`\n",
        ),
        "enhancements/P3-ENH-010-complete.md": (None, _headings("ENH")),
        "epics/P3-EPIC-011-complete.md": (None, _headings("EPIC")),
        "epics/P3-EPIC-012-incomplete.md": (None, "# T\n\n## Summary\n\nx\n"),
        "bugs/P3-001-no-type.md": (None, _headings("BUG")),
        "completed/P3-BUG-013-legacy-dir.md": ({"status": "done"}, _headings("BUG")),
    }
    return {rel: write_issue(root, rel, fm, body) for rel, (fm, body) in specs.items()}


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    return make_project(tmp_path)


def _assert_parity(root: Path, state: ProjectState, paths: dict[str, Path]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for rel, path in paths.items():
        rec = record(state, rel)
        expected = is_formatted(path)
        assert is_formatted_from_state(rec, state.formatting_policy) is expected, rel
        results[rel] = expected
    return results


def test_parity_without_cutover_stamp(project: Path) -> None:
    paths = _cases(project)
    state = collect(project)
    assert state.formatting_policy.program_design_cutover is None
    results = _assert_parity(project, state, paths)
    # sanity: the fixture spread exercises both outcomes
    assert results["bugs/P3-BUG-001-complete-no-pd.md"] is True
    assert results["bugs/P3-BUG-003-missing-section.md"] is False
    assert results["bugs/P3-BUG-004-format-log.md"] is True
    assert results["bugs/P3-001-no-type.md"] is False
    assert results["epics/P3-EPIC-012-incomplete.md"] is False


def test_parity_with_cutover_stamp_grandfathering_and_opt_out(project: Path) -> None:
    _stamp(project)
    paths = _cases(project)
    state = collect(project)
    assert state.formatting_policy.program_design_cutover == date(2026, 7, 30)
    results = _assert_parity(project, state, paths)
    assert results["bugs/P3-BUG-001-complete-no-pd.md"] is False  # no design date -> gated
    assert results["bugs/P3-BUG-002-complete-with-pd.md"] is True
    assert results["features/P3-FEAT-005-new-no-pd.md"] is False  # discovered after cutover
    assert results["features/P3-FEAT-006-old-no-pd.md"] is True  # grandfathered
    assert results["features/P3-FEAT-007-opt-out.md"] is True  # explicit opt-out
    assert results["features/P3-FEAT-008-refined-after.md"] is False  # refined after cutover
    assert results["features/P3-FEAT-009-refined-before.md"] is True  # refine date wins
    assert results["bugs/P3-BUG-004-format-log.md"] is True  # shortcut beats the gate


def test_parity_when_templates_fail_to_load(
    project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _cases(project)
    empty_plugin_root = tmp_path_factory.mktemp("plugin")
    (empty_plugin_root / "templates").mkdir()  # exists but holds no *-sections.json
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(empty_plugin_root))
    state = collect(project)
    policy = state.formatting_policy
    assert set(policy.load_failures) == {"BUG", "FEAT", "ENH", "EPIC"}
    assert policy.required_sections == {}
    results = _assert_parity(project, state, paths)
    # only the format-log shortcut can still succeed
    assert [rel for rel, ok in results.items() if ok] == ["bugs/P3-BUG-004-format-log.md"]


def test_plugin_root_override_is_honored_at_capture_time(
    project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path_factory.mktemp("plugin")
    templates = plugin_root / "templates"
    shutil.copytree(get_bundled_templates_dir(), templates)
    data = json.loads((templates / "bug-sections.json").read_text(encoding="utf-8"))
    data["common_sections"]["Summary"]["required"] = False
    for section in data["type_sections"].values():
        section["level"] = "optional"
    for name in list(data["common_sections"]):
        data["common_sections"][name]["required"] = name == "Impact"
    (templates / "bug-sections.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))

    write_issue(project, "bugs/P3-BUG-001-x.md", None, "# T\n\n## Impact\n\nx\n")
    state = collect(project)
    assert state.formatting_policy.required_sections["BUG"] == frozenset({"Impact"})
    assert state.formatting_policy.templates_dir == str(templates)
    rec = record(state, "bugs/P3-BUG-001-x.md")
    assert is_formatted_from_state(rec, state.formatting_policy) is True
    assert is_formatted(rec.path) is True


def test_changing_templates_and_cutover_after_capture_does_not_change_results(
    project: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _cases(project)
    state = collect(project)  # no stamp, bundled templates
    before = {
        rel: is_formatted_from_state(record(state, rel), state.formatting_policy) for rel in paths
    }
    legacy_before = {rel: is_formatted(p) for rel, p in paths.items()}
    assert before == legacy_before

    # Change the world after capture: add the stamp and point templates at an empty dir.
    _stamp(project)
    empty = tmp_path_factory.mktemp("plugin")
    (empty / "templates").mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(empty))

    after = {
        rel: is_formatted_from_state(record(state, rel), state.formatting_policy) for rel in paths
    }
    assert after == before  # the captured assessment is immutable
    # ... while the live legacy path demonstrably moved (so the fixture is meaningful)
    legacy_after = {rel: is_formatted(p) for rel, p in paths.items()}
    assert legacy_after != legacy_before

    # Removing the stamp afterwards likewise changes nothing for a stamped capture.
    (project / ".ll" / "program-design-cutover.json").unlink()
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    stamped_state = collect(project)
    assert stamped_state.formatting_policy.program_design_cutover is None


def test_stamped_capture_survives_stamp_removal(project: Path) -> None:
    _stamp(project)
    paths = _cases(project)
    state = collect(project)
    stamped = {
        rel: is_formatted_from_state(record(state, rel), state.formatting_policy) for rel in paths
    }
    (project / ".ll" / "program-design-cutover.json").unlink()
    again = {
        rel: is_formatted_from_state(record(state, rel), state.formatting_policy) for rel in paths
    }
    assert again == stamped
    assert {rel: is_formatted(p) for rel, p in paths.items()} != stamped


def test_assessment_does_not_consult_environment_root_or_stamp_reader(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stamp(project)
    paths = _cases(project)
    state = collect(project)

    import little_loops.issue_template as it
    import little_loops.issues.program_design as pd

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("assessment consulted live state")

    monkeypatch.setattr(pd, "read_cutover_stamp", boom)
    monkeypatch.setattr(pd, "find_project_root", boom)
    monkeypatch.setattr(it, "load_issue_sections", boom)
    monkeypatch.setattr(it, "_default_templates_dir", boom)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: boom())
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/nonexistent/plugin-root")
    for rel in paths:
        is_formatted_from_state(record(state, rel), state.formatting_policy)


def test_capture_formatting_policy_reports_provenance(project: Path) -> None:
    policy = capture_formatting_policy(project)
    assert policy.templates_dir == str(get_bundled_templates_dir())
    assert policy.load_failures == {}
    assert "Program Design" in policy.required_sections["BUG"]
    assert policy.program_design_cutover is None
    _stamp(project, "not-a-date")
    assert capture_formatting_policy(project).program_design_cutover is None
