"""Tests for ENH-1115: progressive throttling documentation wiring.

Verifies that the throttle event types, ThrottleConfig, and configuration
documentation added by ENH-1115 are present in the expected doc surfaces
so downstream consumers can discover the throttle feature surface.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

EVENT_SCHEMA = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
CONFIGURATION = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"
API_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "API.md"
CLI_REFERENCE = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
COMMANDS = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestEventSchemaWiring:
    def test_throttle_warn_present(self) -> None:
        assert "throttle_warn" in EVENT_SCHEMA.read_text(), (
            "docs/reference/EVENT-SCHEMA.md must document throttle_warn event"
        )

    def test_throttle_hard_present(self) -> None:
        assert "throttle_hard" in EVENT_SCHEMA.read_text(), (
            "docs/reference/EVENT-SCHEMA.md must document throttle_hard event"
        )

    def test_throttle_stop_present(self) -> None:
        assert "throttle_stop" in EVENT_SCHEMA.read_text(), (
            "docs/reference/EVENT-SCHEMA.md must document throttle_stop event"
        )


class TestConfigurationWiring:
    def test_throttle_config_present(self) -> None:
        assert "throttle" in CONFIGURATION.read_text(), (
            "docs/reference/CONFIGURATION.md must document throttle config block"
        )


class TestApiReferenceWiring:
    def test_throttle_config_in_quick_import(self) -> None:
        assert "ThrottleConfig" in API_REFERENCE.read_text(), (
            "docs/reference/API.md must reference ThrottleConfig"
        )

    def test_throttle_warn_event_present(self) -> None:
        assert "THROTTLE_WARN_EVENT" in API_REFERENCE.read_text(), (
            "docs/reference/API.md must reference THROTTLE_WARN_EVENT"
        )


class TestCliReferenceWiring:
    def test_llevent_type_count_updated(self) -> None:
        assert "37 `LLEvent` types" in CLI_REFERENCE.read_text(), (
            "docs/reference/CLI.md must state '37 `LLEvent` types' (current count)"
        )


class TestCommandsWiring:
    def test_throttle_event_in_analyze_loop_heuristics(self) -> None:
        assert "throttle" in COMMANDS.read_text(), (
            "docs/reference/COMMANDS.md must document throttle event classification in debug-loop-run"
        )
