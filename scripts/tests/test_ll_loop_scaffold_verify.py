"""Tests for ll-loop scaffold-verify (FEAT-2948)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.loop.scaffold_verify import (
    PREPATCH_CHECK_STATE_EXAMPLE,
    scaffold_verify,
)
from little_loops.config import BRConfig
from little_loops.issue_parser import IssueParser


def _make_project(tmp_path: Path) -> None:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    (ll_dir / "ll-config.json").write_text(json.dumps({"project": {"name": "test"}}))
    for sub in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / sub).mkdir(parents=True, exist_ok=True)


def _write_issue(tmp_path: Path, issue_id: str, criteria: list[str] | None = None) -> Path:
    """Write a minimal FEAT issue file with the given Acceptance Criteria bullets."""
    number = issue_id.split("-")[1]
    path = tmp_path / ".issues" / "features" / f"P2-FEAT-{number}-sample-issue.md"
    ac_lines = "\n".join(f"- [ ] {c}" for c in (criteria or []))
    path.write_text(
        f"""---
id: {issue_id}
title: Sample Issue
type: FEAT
priority: P2
status: open
---

# {issue_id}: Sample Issue

## Summary

A sample issue for scaffold tests.

## Acceptance Criteria

{ac_lines}
"""
    )
    return path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestExtractCriteria:
    def test_extracts_top_level_bullets_in_order(self, project: Path) -> None:
        path = _write_issue(project, "FEAT-100", ["First criterion", "Second criterion"])
        parser = IssueParser(BRConfig(project))
        slots = parser.extract_criteria(path)
        assert [s.source_text for s in slots] == ["First criterion", "Second criterion"]
        assert [s.index for s in slots] == [1, 2]
        assert [s.state_name for s in slots] == ["verify-criterion-1", "verify-criterion-2"]

    def test_accepts_checkbox_plain_star_and_numbered_bullets(self, project: Path) -> None:
        number = "101"
        path = project / ".issues" / "features" / f"P2-FEAT-{number}-mixed.md"
        path.write_text(
            "---\nid: FEAT-101\ntitle: Mixed\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
            "# FEAT-101: Mixed\n\n## Acceptance Criteria\n\n"
            "- [ ] checkbox item\n"
            "- [x] done checkbox item\n"
            "- plain dash item\n"
            "* star item\n"
            "1. numbered item\n"
        )
        parser = IssueParser(BRConfig(project))
        slots = parser.extract_criteria(path)
        assert [s.source_text for s in slots] == [
            "checkbox item",
            "done checkbox item",
            "plain dash item",
            "star item",
            "numbered item",
        ]

    def test_skips_indented_sub_bullets(self, project: Path) -> None:
        number = "102"
        path = project / ".issues" / "features" / f"P2-FEAT-{number}-subbullets.md"
        path.write_text(
            "---\nid: FEAT-102\ntitle: Sub\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
            "# FEAT-102: Sub\n\n## Acceptance Criteria\n\n"
            "- Top-level item\n"
            "  - Indented sub-bullet, should be skipped\n"
            "- Another top-level item\n"
        )
        parser = IssueParser(BRConfig(project))
        slots = parser.extract_criteria(path)
        assert [s.source_text for s in slots] == ["Top-level item", "Another top-level item"]

    def test_falls_back_to_expected_behavior_when_ac_empty(self, project: Path) -> None:
        number = "103"
        path = project / ".issues" / "features" / f"P2-FEAT-{number}-fallback.md"
        path.write_text(
            "---\nid: FEAT-103\ntitle: Fallback\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
            "# FEAT-103: Fallback\n\n## Acceptance Criteria\n\n"
            "## Expected Behavior\n\n- Behavior one\n- Behavior two\n"
        )
        parser = IssueParser(BRConfig(project))
        slots = parser.extract_criteria(path)
        assert [s.source_text for s in slots] == ["Behavior one", "Behavior two"]

    def test_no_criteria_sections_returns_empty(self, project: Path) -> None:
        number = "104"
        path = project / ".issues" / "features" / f"P2-FEAT-{number}-none.md"
        path.write_text(
            "---\nid: FEAT-104\ntitle: None\ntype: FEAT\npriority: P2\nstatus: open\n---\n\n"
            "# FEAT-104: None\n\n## Summary\n\nNo criteria here.\n"
        )
        parser = IssueParser(BRConfig(project))
        slots = parser.extract_criteria(path)
        assert slots == []


class TestScaffoldVerifyCriteriaMode:
    def test_single_criterion_chain(self, project: Path) -> None:
        _write_issue(project, "FEAT-200", ["Only criterion"])
        result = scaffold_verify("FEAT-200", adversarial=False)
        assert result.validated is True
        assert "verify-criterion-1" in result.yaml_text
        assert "verify-criterion-2" not in result.yaml_text
        assert "on_yes: done" in result.yaml_text

    def test_n_criteria_chain_correctness(self, project: Path) -> None:
        criteria = [f"Criterion {i}" for i in range(1, 5)]
        _write_issue(project, "FEAT-201", criteria)
        result = scaffold_verify("FEAT-201", adversarial=False)
        assert result.validated is True
        for i in range(1, 4):
            assert f"on_yes: verify-criterion-{i + 1}" in result.yaml_text
        assert result.yaml_text.count("verify-criterion-") >= 4
        assert "failed" in result.yaml_text

    def test_zero_criteria_errors_no_yaml_written(self, project: Path) -> None:
        _write_issue(project, "FEAT-202", [])
        result = scaffold_verify("FEAT-202", adversarial=False)
        assert result.validated is False
        assert result.yaml_text == ""
        assert result.errors

    def test_no_placeholders_in_criteria_mode(self, project: Path) -> None:
        _write_issue(project, "FEAT-203", ["Some criterion"])
        result = scaffold_verify("FEAT-203", adversarial=False)
        assert result.placeholders == []
        assert "<" not in result.yaml_text or "PLACEHOLDER" not in result.yaml_text

    def test_unknown_issue_errors(self, project: Path) -> None:
        result = scaffold_verify("FEAT-999999", adversarial=False)
        assert result.validated is False
        assert result.yaml_text == ""
        assert "not found" in result.errors[0]

    def test_eval_prompt_directs_missing_evidence_to_cannot_judge(self, project: Path) -> None:
        """ENH-3185 AC11.3: the generated eval prompt no longer tells the judge to
        answer NO when evidence is missing/ambiguous — it must answer CANNOT JUDGE."""
        _write_issue(project, "FEAT-204", ["Some criterion"])
        result = scaffold_verify("FEAT-204", adversarial=False)
        assert "evidence is missing/ambiguous" not in result.yaml_text
        assert "CANNOT JUDGE" in result.yaml_text


class TestScaffoldVerifyAdversarialMode:
    def test_emits_fixed_three_probe_template(self, project: Path) -> None:
        _write_issue(project, "FEAT-300", ["Some criterion"])
        result = scaffold_verify("FEAT-300", adversarial=True)
        assert result.validated is True
        for state in ("probe-boundary", "probe-malformed-hostile", "probe-failure-mode"):
            assert state in result.yaml_text
        assert "count_probes" in result.yaml_text
        assert "output_numeric" in result.yaml_text
        assert "target: 3" in result.yaml_text
        assert "failed_too_few" in result.yaml_text
        assert "failed_with_finding" in result.yaml_text
        assert "timeout: 2700" in result.yaml_text

    def test_adversarial_ignores_missing_criteria(self, project: Path) -> None:
        _write_issue(project, "FEAT-301", [])
        result = scaffold_verify("FEAT-301", adversarial=True)
        assert result.validated is True
        assert result.yaml_text != ""

    def test_criteria_mode_timeout_1800(self, project: Path) -> None:
        _write_issue(project, "FEAT-302", ["Criterion"])
        result = scaffold_verify("FEAT-302", adversarial=False)
        assert "timeout: 1800" in result.yaml_text


class TestPrepatchCheckStateExample:
    """ENH-2998: scaffold_verify.py documents the deterministic pre-patch
    check via a state-template example, since it has no generator flag of
    its own (unlike count_probes, a mechanical always-emitted gate)."""

    def test_example_shows_prepatch_check_key_alongside_llm_structured(self) -> None:
        assert "prepatch_check: fail" in PREPATCH_CHECK_STATE_EXAMPLE
        assert "llm_structured" in PREPATCH_CHECK_STATE_EXAMPLE

    def test_example_is_not_emitted_by_either_generated_template(self, project: Path) -> None:
        _write_issue(project, "FEAT-303", ["Criterion"])
        criteria_result = scaffold_verify("FEAT-303", adversarial=False)
        adversarial_result = scaffold_verify("FEAT-303", adversarial=True)
        assert "prepatch_check" not in criteria_result.yaml_text
        assert "prepatch_check" not in adversarial_result.yaml_text
