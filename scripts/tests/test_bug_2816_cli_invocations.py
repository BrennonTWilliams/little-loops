"""Regression tests for BUG-2816: broken CLI/skill invocations in built-in loops.

Each test asserts a specific broken string is gone and/or the corrected form is
present, following the content-assertion idiom in test_brainstorm.py and
test_loop_router.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"


def _text(rel_path: str) -> str:
    return (BUILTIN_LOOPS_DIR / rel_path).read_text()


class TestApplyResearchFix:
    """apply-research.yaml:63 — `--format table` doesn't exist on `ll-issues list`,
    and the `2>/dev/null | head -30 || echo` fallback never fires without pipefail."""

    def test_no_format_flag(self) -> None:
        assert "--format table" not in _text("apply-research.yaml")

    def test_uses_flat_and_limit(self) -> None:
        action = yaml.safe_load(_text("apply-research.yaml"))["states"]["load_context"]["action"]
        assert "ll-issues list --status open --flat --limit 30" in action

    def test_pipefail_set(self) -> None:
        action = yaml.safe_load(_text("apply-research.yaml"))["states"]["load_context"]["action"]
        assert "set -o pipefail" in action


class TestLibCliFix:
    """lib/cli.yaml:94 — `ll-deps check` doesn't exist; `ll-deps validate` does."""

    def test_ll_deps_validate(self) -> None:
        text = (BUILTIN_LOOPS_DIR / "lib" / "cli.yaml").read_text()
        assert "ll-deps check" not in text
        assert "ll-deps validate" in text


class TestBrainstormSetFlagFix:
    """brainstorm.yaml:373 — `ll-issues set-flag` doesn't exist."""

    def test_no_set_flag(self) -> None:
        assert "set-flag" not in _text("brainstorm.yaml")

    def test_edit_tool_instruction_present(self) -> None:
        action = yaml.safe_load(_text("brainstorm.yaml"))["states"]["sink_decision"]["action"]
        assert "decision_needed: true" in action
        assert "Edit tool" in action


class TestAdoptThirdPartyApiFix:
    """adopt-third-party-api.yaml:21 — `/ll:scrape-docs` doesn't resolve for a
    repo-local (unpackaged) project skill; the prefix-free form does."""

    def test_no_ll_prefix(self) -> None:
        assert "/ll:scrape-docs" not in _text("adopt-third-party-api.yaml")

    def test_prefix_free_scrape_docs(self) -> None:
        state = yaml.safe_load(_text("adopt-third-party-api.yaml"))["states"]["scrape"]
        assert state["action"] == "/scrape-docs ${context.input}"


class TestAutoFlagDropped:
    """sprint-build-and-validate.yaml:45, backlog-flow-optimizer.yaml:94 — neither
    create-sprint nor tradeoff-review-issues declares --auto."""

    def test_create_sprint_no_auto(self) -> None:
        assert "create-sprint --auto" not in _text("sprint-build-and-validate.yaml")
        assert "/ll:create-sprint`" in _text("sprint-build-and-validate.yaml")

    def test_tradeoff_review_no_auto(self) -> None:
        assert "tradeoff-review-issues --auto" not in _text("backlog-flow-optimizer.yaml")
        assert "/ll:tradeoff-review-issues`" in _text("backlog-flow-optimizer.yaml")


class TestPromptAcrossIssuesQuickFix:
    """prompt-across-issues.yaml:19 — normalize-issues has no --quick flag."""

    def test_no_quick_flag(self) -> None:
        assert "--quick" not in _text("prompt-across-issues.yaml")

    def test_auto_flag_used(self) -> None:
        assert "/ll:normalize-issues {issue_id} --auto" in _text("prompt-across-issues.yaml")


class TestRlCodingAgentCommentFix:
    """rl-coding-agent.yaml:22,27 — `ll-manage-issue` is not a CLI entry point;
    it's the /ll:manage-issue skill."""

    def test_no_bare_ll_manage_issue_cli_reference(self) -> None:
        text = _text("rl-coding-agent.yaml")
        assert "ll-manage-issue" not in text


class TestLoopInputFlagSweep:
    """No `--input` flag exists on `ll-loop run`; input is positional
    (cli/loop/__init__.py). Sweep across loop YAMLs enumerated in BUG-2816."""

    SITES = [
        "adversarial-redesign.yaml",
        "sprint-refine-and-implement.yaml",
        "cli-anything-bootstrap.yaml",
        "loop-router.yaml",
        "loop-composer.yaml",
        "loop-composer-adaptive.yaml",
        "README.md",
    ]

    def test_no_dashdash_input_remains(self) -> None:
        offenders = []
        for site in self.SITES:
            text = (BUILTIN_LOOPS_DIR / site).read_text()
            if "--input" in text:
                offenders.append(site)
        assert not offenders, f"--input still present in: {offenders}"

    def test_cli_anything_bootstrap_operator_output_fixed(self) -> None:
        action = yaml.safe_load(_text("cli-anything-bootstrap.yaml"))["states"]["finalize_done"][
            "action"
        ]
        assert 'll-loop run <target_name>-task "<their goal in natural language>"' in action
