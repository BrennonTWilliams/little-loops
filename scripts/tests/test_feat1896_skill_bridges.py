"""Bridge wiring tests for FEAT-1896: Decisions Log — Skill Bridges.

Verifies that decide-issue, tradeoff-review-issues, go-no-go, and capture-issue
all contain the expected `ll-issues decisions add` call at the correct phase
boundaries, and that go-no-go frontmatter includes Bash(ll-issues:*).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

GO_NO_GO_SKILL = PROJECT_ROOT / "skills" / "go-no-go" / "SKILL.md"
LL_GO_NO_GO_STUB = PROJECT_ROOT / "skills" / "ll-go-no-go" / "SKILL.md"
DECIDE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "decide-issue" / "SKILL.md"
TRADEOFF_CMD = PROJECT_ROOT / "commands" / "tradeoff-review-issues.md"
CAPTURE_ISSUE_SKILL = PROJECT_ROOT / "skills" / "capture-issue" / "SKILL.md"


def _frontmatter(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[: end + 3]


def _body(path: Path) -> str:
    content = path.read_text()
    end = content.index("---", 3)
    return content[end + 3 :]


class TestGoNoGoFrontmatter:
    """go-no-go primary skill and Codex stub must both declare Bash(ll-issues:*)."""

    def test_go_no_go_skill_has_ll_issues_tool(self) -> None:
        fm = _frontmatter(GO_NO_GO_SKILL)
        assert "Bash(ll-issues:*)" in fm, (
            "skills/go-no-go/SKILL.md must include Bash(ll-issues:*) in allowed-tools (FEAT-1896)"
        )

    def test_ll_go_no_go_stub_has_ll_issues_tool(self) -> None:
        fm = _frontmatter(LL_GO_NO_GO_STUB)
        assert "Bash(ll-issues:*)" in fm, (
            "skills/ll-go-no-go/SKILL.md must include Bash(ll-issues:*) in allowed-tools (FEAT-1896)"
        )


class TestGoNoGoDecisionsBridge:
    """go-no-go Step 3f must call ll-issues decisions add with CHECK_MODE guard."""

    def test_decisions_add_call_present(self) -> None:
        body = _body(GO_NO_GO_SKILL)
        assert "ll-issues decisions add" in body, (
            "skills/go-no-go/SKILL.md must contain ll-issues decisions add call in Step 3f"
        )

    def test_check_mode_guard_present(self) -> None:
        body = _body(GO_NO_GO_SKILL)
        assert 'CHECK_MODE' in body and 'll-issues decisions add' in body, (
            "skills/go-no-go/SKILL.md decisions add call must be guarded by CHECK_MODE"
        )
        # Guard and call must appear in the same section
        step3f_start = body.index("Step 3f")
        decisions_idx = body.index("ll-issues decisions add")
        assert decisions_idx > step3f_start, (
            "ll-issues decisions add must appear after Step 3f heading"
        )

    def test_decisions_yaml_guard_present(self) -> None:
        body = _body(GO_NO_GO_SKILL)
        assert "decisions.yaml" in body, (
            "skills/go-no-go/SKILL.md must guard decisions add call with decisions.yaml existence check"
        )

    def test_category_implementation(self) -> None:
        body = _body(GO_NO_GO_SKILL)
        assert '--category="implementation"' in body, (
            "go-no-go decisions add must use --category=implementation"
        )

    def test_graceful_degradation(self) -> None:
        body = _body(GO_NO_GO_SKILL)
        assert "2>/dev/null || true" in body, (
            "go-no-go decisions add must use 2>/dev/null || true for graceful degradation"
        )


class TestDecideIssueDecisionsBridge:
    """decide-issue must call ll-issues decisions add between Phase 7 and Phase 8."""

    def test_decisions_add_call_present(self) -> None:
        body = _body(DECIDE_ISSUE_SKILL)
        assert "ll-issues decisions add" in body, (
            "skills/decide-issue/SKILL.md must contain ll-issues decisions add call"
        )

    def test_placement_between_phase7_and_phase8(self) -> None:
        body = _body(DECIDE_ISSUE_SKILL)
        phase8_idx = body.index("## Phase 8")
        decisions_idx = body.index("ll-issues decisions add")
        assert decisions_idx < phase8_idx, (
            "ll-issues decisions add must appear before Phase 8 in decide-issue"
        )

    def test_category_architecture(self) -> None:
        body = _body(DECIDE_ISSUE_SKILL)
        assert '--category="architecture"' in body, (
            "decide-issue decisions add must use --category=architecture"
        )

    def test_decisions_yaml_guard_present(self) -> None:
        body = _body(DECIDE_ISSUE_SKILL)
        assert "decisions.yaml" in body, (
            "skills/decide-issue/SKILL.md must guard decisions add call with decisions.yaml existence check"
        )

    def test_graceful_degradation(self) -> None:
        body = _body(DECIDE_ISSUE_SKILL)
        assert "2>/dev/null || true" in body, (
            "decide-issue decisions add must use 2>/dev/null || true for graceful degradation"
        )


class TestTradeoffReviewDecisionsBridge:
    """tradeoff-review-issues Phase 5 must call ll-issues decisions add after each append-log."""

    def test_decisions_add_call_present(self) -> None:
        content = TRADEOFF_CMD.read_text()
        assert "ll-issues decisions add" in content, (
            "commands/tradeoff-review-issues.md must contain ll-issues decisions add call"
        )

    def test_two_bridge_calls_present(self) -> None:
        content = TRADEOFF_CMD.read_text()
        count = content.count("ll-issues decisions add")
        assert count >= 2, (
            f"commands/tradeoff-review-issues.md must have at least 2 decisions add calls (one per outcome), got {count}"
        )

    def test_category_tradeoff(self) -> None:
        content = TRADEOFF_CMD.read_text()
        assert '--category="tradeoff"' in content, (
            "tradeoff-review-issues decisions add must use --category=tradeoff"
        )

    def test_decisions_yaml_guard_present(self) -> None:
        content = TRADEOFF_CMD.read_text()
        assert "decisions.yaml" in content, (
            "commands/tradeoff-review-issues.md must guard decisions add with decisions.yaml existence check"
        )

    def test_graceful_degradation(self) -> None:
        content = TRADEOFF_CMD.read_text()
        assert "2>/dev/null || true" in content, (
            "tradeoff-review-issues decisions add must use 2>/dev/null || true for graceful degradation"
        )

    def test_calls_follow_append_log(self) -> None:
        content = TRADEOFF_CMD.read_text()
        append_log_idx = content.index("ll-issues append-log")
        decisions_idx = content.index("ll-issues decisions add")
        assert decisions_idx > append_log_idx, (
            "decisions add must appear after append-log in tradeoff-review-issues"
        )


class TestCaptureIssueDecisionsBridge:
    """capture-issue Phase 4 step 5 must contain optional decisions add for FEAT/EPIC."""

    def test_decisions_add_call_present(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        assert "ll-issues decisions add" in body, (
            "skills/capture-issue/SKILL.md must contain ll-issues decisions add call (FEAT-1896)"
        )

    def test_bug_type_guard_present(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        assert 'ISSUE_TYPE' in body and 'BUG' in body, (
            "capture-issue decisions add must be gated to skip BUG type"
        )

    def test_category_architecture(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        assert '--category="architecture"' in body, (
            "capture-issue decisions add must use --category=architecture"
        )

    def test_decisions_yaml_guard_present(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        assert "decisions.yaml" in body, (
            "skills/capture-issue/SKILL.md must guard decisions add call with decisions.yaml existence check"
        )

    def test_graceful_degradation(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        assert "2>/dev/null || true" in body, (
            "capture-issue decisions add must use 2>/dev/null || true for graceful degradation"
        )

    def test_placed_before_git_add(self) -> None:
        body = _body(CAPTURE_ISSUE_SKILL)
        decisions_idx = body.index("ll-issues decisions add")
        git_add_idx = body.index('git add "{{config.issues.base_dir}}')
        assert decisions_idx < git_add_idx, (
            "capture-issue decisions add must appear before the git add step"
        )
