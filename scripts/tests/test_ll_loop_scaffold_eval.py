"""Tests for ll-loop scaffold-eval (FEAT-2948)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from little_loops.cli.loop.scaffold_eval import scaffold_eval


def _make_project(tmp_path: Path, learning_tests_enabled: bool = True) -> None:
    ll_dir = tmp_path / ".ll"
    ll_dir.mkdir(exist_ok=True)
    config = {
        "project": {"name": "test"},
        "learning_tests": {"enabled": learning_tests_enabled},
    }
    (ll_dir / "ll-config.json").write_text(json.dumps(config))
    for sub in ("bugs", "features", "enhancements", "epics"):
        (tmp_path / ".issues" / sub).mkdir(parents=True, exist_ok=True)


def _write_issue(
    tmp_path: Path,
    issue_id: str,
    title: str = "Sample Issue",
    learning_tests_required: list[str] | None = None,
) -> Path:
    number = issue_id.split("-")[1]
    path = tmp_path / ".issues" / "features" / f"P2-FEAT-{number}-sample.md"
    lt_frontmatter = ""
    if learning_tests_required:
        items = "\n".join(f"- {t}" for t in learning_tests_required)
        lt_frontmatter = f"learning_tests_required:\n{items}\n"
    path.write_text(
        f"""---
id: {issue_id}
title: {title}
type: FEAT
priority: P2
status: open
{lt_frontmatter}---

# {issue_id}: {title}

## Expected Behavior

The user does a thing and observes a result.

## Acceptance Criteria

- [ ] Condition one holds
- [ ] Condition two holds
"""
    )
    return path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestScaffoldEvalVariantA:
    def test_single_issue_variant_a(self, project: Path) -> None:
        _write_issue(project, "FEAT-100")
        result = scaffold_eval(["FEAT-100"], dsl=False)
        assert result.validated is True
        assert "initial: execute" in result.yaml_text
        assert "check_skill" in result.yaml_text
        assert "discover" not in result.yaml_text
        assert result.placeholders == ["<EXECUTE_PROMPT>", "<EVALUATION_CRITERIA_PROMPT>"]
        assert "<EXECUTE_PROMPT>" in result.yaml_text
        assert "<EVALUATION_CRITERIA_PROMPT>" in result.yaml_text

    def test_variant_a_no_proof_states_without_learning_tests(self, project: Path) -> None:
        _write_issue(project, "FEAT-101")
        result = scaffold_eval(["FEAT-101"], dsl=False)
        assert "check_proof_" not in result.yaml_text
        assert "next: check_skill" in result.yaml_text

    def test_variant_a_single_proof_state(self, project: Path) -> None:
        _write_issue(project, "FEAT-102", learning_tests_required=["ruamel.yaml"])
        result = scaffold_eval(["FEAT-102"], dsl=False)
        assert result.validated is True
        assert "check_proof_ruamelyaml" in result.yaml_text
        assert "next: check_proof_ruamelyaml" in result.yaml_text
        assert "ll-learning-tests check --stale-aware" in result.yaml_text

    def test_variant_a_n_proof_states_chained(self, project: Path) -> None:
        _write_issue(project, "FEAT-103", learning_tests_required=["libone", "libtwo", "libthree"])
        result = scaffold_eval(["FEAT-103"], dsl=False)
        assert result.validated is True
        for target in ("libone", "libtwo", "libthree"):
            assert f"check_proof_{target}" in result.yaml_text
        assert "on_yes: check_proof_libtwo" in result.yaml_text
        assert "on_yes: check_proof_libthree" in result.yaml_text
        assert "on_yes: check_skill" in result.yaml_text

    def test_learning_tests_disabled_skips_proof_states(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _make_project(tmp_path, learning_tests_enabled=False)
        monkeypatch.chdir(tmp_path)
        _write_issue(tmp_path, "FEAT-104", learning_tests_required=["somelib"])
        result = scaffold_eval(["FEAT-104"], dsl=False)
        assert "check_proof_" not in result.yaml_text


class TestScaffoldEvalVariantB:
    def test_two_issues_variant_b(self, project: Path) -> None:
        _write_issue(project, "FEAT-200", title="First")
        _write_issue(project, "FEAT-201", title="Second")
        result = scaffold_eval(["FEAT-200", "FEAT-201"], dsl=False)
        assert result.validated is True
        assert "initial: discover" in result.yaml_text
        assert "discover" in result.yaml_text
        assert "advance" in result.yaml_text
        assert "FEAT-200" in result.yaml_text
        assert "FEAT-201" in result.yaml_text

    def test_variant_b_guarded_proof_state(self, project: Path) -> None:
        _write_issue(project, "FEAT-202", learning_tests_required=["onlylib"])
        _write_issue(project, "FEAT-203")
        result = scaffold_eval(["FEAT-202", "FEAT-203"], dsl=False)
        assert result.validated is True
        assert "check_proof_onlylib" in result.yaml_text
        assert 'captured.current_item.output}" = "FEAT-202"' in result.yaml_text


class TestScaffoldEvalErrors:
    def test_dsl_not_implemented(self, project: Path) -> None:
        _write_issue(project, "FEAT-300")
        result = scaffold_eval(["FEAT-300"], dsl=True)
        assert result.validated is False
        assert result.yaml_text == ""
        assert "create-eval-from-issues --dsl" in result.errors[0]

    def test_no_issues_errors(self, project: Path) -> None:
        result = scaffold_eval([], dsl=False)
        assert result.validated is False
        assert result.yaml_text == ""

    def test_unknown_issue_errors(self, project: Path) -> None:
        result = scaffold_eval(["FEAT-999999"], dsl=False)
        assert result.validated is False
        assert "not found" in result.errors[0]
