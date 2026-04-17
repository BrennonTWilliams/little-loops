"""Tests for ENH-1146: rate_limit_waiting heartbeat documentation wiring.

Verifies that the `rate_limit_waiting` heartbeat event documentation
added by ENH-1150 (reference files) and ENH-1152 (guide, skill,
changelog) is present across all target doc surfaces so downstream doc
consumers can discover the heartbeat event, its payload fields, and
the updated `LLEvent` type count.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

EVENT_SCHEMA = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
OUTPUT_STYLING = PROJECT_ROOT / "docs" / "reference" / "OUTPUT_STYLING.md"
ANALYZE_LOOP = PROJECT_ROOT / "skills" / "analyze-loop" / "SKILL.md"
API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
COMMANDS = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestEventSchemaWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in EVENT_SCHEMA.read_text(), (
            "docs/reference/EVENT-SCHEMA.md must document rate_limit_waiting heartbeat event"
        )


class TestOutputStylingWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in OUTPUT_STYLING.read_text(), (
            "docs/reference/OUTPUT_STYLING.md must document rate_limit_waiting styling"
        )


class TestAnalyzeLoopSkillWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in ANALYZE_LOOP.read_text(), (
            "skills/analyze-loop/SKILL.md event payload table must include rate_limit_waiting row"
        )


class TestApiReferenceWiring:
    def test_rate_limit_max_wait_seconds_present(self) -> None:
        assert "rate_limit_max_wait_seconds" in API_REFERENCE.read_text(), (
            "docs/reference/API.md must reference rate_limit_max_wait_seconds"
        )

    def test_rate_limit_long_wait_ladder_present(self) -> None:
        assert "rate_limit_long_wait_ladder" in API_REFERENCE.read_text(), (
            "docs/reference/API.md must reference rate_limit_long_wait_ladder"
        )


class TestCliReferenceWiring:
    def test_llevent_type_count_present(self) -> None:
        assert "22 `LLEvent` types" in CLI_REFERENCE.read_text(), (
            "docs/reference/CLI.md must state '22 `LLEvent` types' (updated count after rate_limit_waiting)"
        )


class TestCommandsWiring:
    def test_rate_limit_waiting_present(self) -> None:
        assert "rate_limit_waiting" in COMMANDS.read_text(), (
            "docs/reference/COMMANDS.md must document rate_limit_waiting in analyze-loop heuristics"
        )
