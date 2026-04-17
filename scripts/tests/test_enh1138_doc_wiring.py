"""Tests for ENH-1138: circuit breaker documentation wiring.

Verifies that the rate-limit circuit-breaker documentation added by
ENH-1139 (API.md updates) and ENH-1140 (prose doc updates) is present
in the expected files so downstream doc consumers can discover the
`RateLimitCircuit` surface and the `circuit_breaker_enabled` /
`circuit_breaker_path` configuration fields.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"
LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"
CONFIGURATION = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"


class TestApiReferenceWiring:
    """docs/reference/API.md must document the RateLimitCircuit surface."""

    def test_signal_detector_present(self) -> None:
        content = API_REFERENCE.read_text()
        assert "signal_detector" in content, (
            "docs/reference/API.md must reference `signal_detector`"
        )

    def test_handoff_handler_present(self) -> None:
        content = API_REFERENCE.read_text()
        assert "handoff_handler" in content, (
            "docs/reference/API.md must reference `handoff_handler`"
        )

    def test_loops_dir_present(self) -> None:
        content = API_REFERENCE.read_text()
        assert "loops_dir" in content, "docs/reference/API.md must reference `loops_dir`"

    def test_circuit_parameter_present(self) -> None:
        content = API_REFERENCE.read_text()
        assert "circuit: RateLimitCircuit | None = None" in content, (
            "docs/reference/API.md must document the "
            "`circuit: RateLimitCircuit | None = None` parameter"
        )

    def test_rate_limit_circuit_section_header_present(self) -> None:
        content = API_REFERENCE.read_text()
        assert "### little_loops.fsm.rate_limit_circuit" in content, (
            "docs/reference/API.md must include the H3 section header "
            "`### little_loops.fsm.rate_limit_circuit`"
        )

    def test_rate_limit_circuit_in_quick_import(self) -> None:
        content = API_REFERENCE.read_text()
        assert "RateLimitCircuit," in content, (
            "docs/reference/API.md Quick Import block must list "
            "`RateLimitCircuit,` in the parenthesized `from little_loops.fsm import (…)` grouping"
        )

    def test_rate_limiting_comment_in_quick_import(self) -> None:
        content = API_REFERENCE.read_text()
        assert "# Rate Limiting" in content, (
            "docs/reference/API.md Quick Import block must include the "
            "`# Rate Limiting` comment anchoring the RateLimitCircuit grouping"
        )


class TestLoopsGuideWiring:
    """docs/guides/LOOPS_GUIDE.md must document the circuit-breaker fields."""

    def test_circuit_breaker_enabled_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "circuit_breaker_enabled" in content, (
            "docs/guides/LOOPS_GUIDE.md must document `circuit_breaker_enabled`"
        )

    def test_circuit_breaker_path_present(self) -> None:
        content = LOOPS_GUIDE.read_text()
        assert "circuit_breaker_path" in content, (
            "docs/guides/LOOPS_GUIDE.md must document `circuit_breaker_path`"
        )


class TestConfigurationWiring:
    """docs/reference/CONFIGURATION.md must document the circuit-breaker toggle."""

    def test_circuit_breaker_enabled_present(self) -> None:
        content = CONFIGURATION.read_text()
        assert "circuit_breaker_enabled" in content, (
            "docs/reference/CONFIGURATION.md must document `circuit_breaker_enabled`"
        )
