"""Doc-wiring regression tests for ENH-1639: timeout-budget guidance for MCP-heavy prompts.

Asserts that:
1. skills/create-loop/loop-types.md contains timeout: 1500 on the execute state
2. docs/generalized-fsm-loop.md Timeouts section includes MCP guidance text
3. docs/guides/AUTOMATIC_HARNESSING_GUIDE.md Tips section includes MCP guidance text
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

LOOP_TYPES = PROJECT_ROOT / "skills" / "create-loop" / "loop-types.md"
FSM_DOC = PROJECT_ROOT / "docs" / "generalized-fsm-loop.md"
HARNESS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "AUTOMATIC_HARNESSING_GUIDE.md"


class TestLoopTypesTimeout:
    """skills/create-loop/loop-types.md must default execute state to timeout: 1500."""

    def test_timeout_1500_present(self) -> None:
        content = LOOP_TYPES.read_text()
        assert "timeout: 1500" in content, (
            "skills/create-loop/loop-types.md must contain 'timeout: 1500' on the execute "
            "state scaffold so new loops default to an MCP-safe timeout"
        )

    def test_mcp_calls_rationale_comment_present(self) -> None:
        content = LOOP_TYPES.read_text()
        assert "MCP calls" in content or "MCP call" in content, (
            "skills/create-loop/loop-types.md must include a comment explaining the timeout "
            "budget for MCP-heavy prompts near the timeout: 1500 field"
        )


class TestFsmDocTimeoutsSection:
    """docs/generalized-fsm-loop.md Timeouts section must include MCP-heavy prompt guidance."""

    def test_mcp_heavy_guidance_present(self) -> None:
        content = FSM_DOC.read_text()
        assert "MCP tool calls" in content, (
            "docs/generalized-fsm-loop.md ## Timeouts section must mention 'MCP tool calls' "
            "in guidance about timeout budgeting for MCP-heavy prompts"
        )

    def test_1500_budget_mentioned(self) -> None:
        content = FSM_DOC.read_text()
        assert "1500" in content, (
            "docs/generalized-fsm-loop.md ## Timeouts section must recommend 1500s as the "
            "minimum timeout for MCP-heavy prompt states"
        )

    def test_default_timeout_bypass_explained(self) -> None:
        content = FSM_DOC.read_text()
        assert "default_timeout" in content, (
            "docs/generalized-fsm-loop.md ## Timeouts section must explain that loop-level "
            "default_timeout: bypasses the 3600s executor fallback"
        )


class TestHarnessGuideTips:
    """docs/guides/AUTOMATIC_HARNESSING_GUIDE.md Tips section must include MCP timeout note."""

    def test_mcp_heavy_tip_present(self) -> None:
        content = HARNESS_GUIDE.read_text()
        assert "MCP" in content, (
            "docs/guides/AUTOMATIC_HARNESSING_GUIDE.md Tips section must mention MCP-heavy "
            "execute states and their timeout requirements"
        )

    def test_1500_budget_mentioned(self) -> None:
        content = HARNESS_GUIDE.read_text()
        assert "1500" in content, (
            "docs/guides/AUTOMATIC_HARNESSING_GUIDE.md Tips section must recommend timeout: "
            "1500 for MCP-heavy prompt states"
        )
