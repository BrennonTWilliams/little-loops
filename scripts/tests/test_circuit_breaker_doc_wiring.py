"""Tests for ENH-1143: circuit breaker skills & API doc wiring.

Verifies that the rate-limit circuit-breaker configuration (added by ENH-1134)
is surfaced in authoritative user-facing documentation and skills so users can
discover and configure `circuit_breaker_enabled` and `circuit_breaker_path`.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"
SHOW_OUTPUT = PROJECT_ROOT / "skills" / "configure" / "show-output.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
CREATE_LOOP_REFERENCE = PROJECT_ROOT / "skills" / "create-loop" / "reference.md"
CREATE_LOOP_TYPES = PROJECT_ROOT / "skills" / "create-loop" / "loop-types.md"


class TestApiReferenceWiring:
    """docs/reference/API.md must list rate_limits on the CommandsConfig row."""

    def test_commands_config_includes_rate_limits(self) -> None:
        content = API_REFERENCE.read_text()
        assert "rate_limits: RateLimitsConfig" in content, (
            "docs/reference/API.md CommandsConfig row must include "
            "`rate_limits: RateLimitsConfig` in its inline attribute list"
        )


class TestShowOutputWiring:
    """skills/configure/show-output.md must render rate_limits in `commands --show`."""

    def test_rate_limits_block_present(self) -> None:
        content = SHOW_OUTPUT.read_text()
        assert "rate_limits:" in content, (
            "skills/configure/show-output.md commands --show block must include rate_limits"
        )

    def test_circuit_breaker_enabled_present(self) -> None:
        content = SHOW_OUTPUT.read_text()
        assert "circuit_breaker_enabled" in content, (
            "skills/configure/show-output.md must display circuit_breaker_enabled"
        )

    def test_circuit_breaker_path_present(self) -> None:
        content = SHOW_OUTPUT.read_text()
        assert "circuit_breaker_path" in content, (
            "skills/configure/show-output.md must display circuit_breaker_path"
        )


class TestConfigureAreasWiring:
    """skills/configure/areas.md must expose circuit-breaker knobs in the commands flow."""

    def test_circuit_breaker_enabled_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "circuit_breaker_enabled" in content, (
            "skills/configure/areas.md commands flow must include circuit_breaker_enabled"
        )

    def test_circuit_breaker_path_present(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "circuit_breaker_path" in content, (
            "skills/configure/areas.md commands flow must include circuit_breaker_path"
        )


class TestCreateLoopReferenceWiring:
    """skills/create-loop/reference.md must document both circuit-breaker fields."""

    def test_circuit_breaker_enabled_documented(self) -> None:
        content = CREATE_LOOP_REFERENCE.read_text()
        assert "circuit_breaker_enabled" in content, (
            "skills/create-loop/reference.md rate-limit fields section must "
            "document circuit_breaker_enabled"
        )

    def test_circuit_breaker_path_documented(self) -> None:
        content = CREATE_LOOP_REFERENCE.read_text()
        assert "circuit_breaker_path" in content, (
            "skills/create-loop/reference.md rate-limit fields section must "
            "document circuit_breaker_path"
        )


class TestCreateLoopTypesWiring:
    """skills/create-loop/loop-types.md YAML example must surface circuit-breaker fields."""

    def test_circuit_breaker_enabled_in_yaml(self) -> None:
        content = CREATE_LOOP_TYPES.read_text()
        assert "circuit_breaker_enabled" in content, (
            "skills/create-loop/loop-types.md rate-limit YAML example must "
            "include circuit_breaker_enabled"
        )

    def test_circuit_breaker_path_in_yaml(self) -> None:
        content = CREATE_LOOP_TYPES.read_text()
        assert "circuit_breaker_path" in content, (
            "skills/create-loop/loop-types.md rate-limit YAML example must "
            "include circuit_breaker_path"
        )
