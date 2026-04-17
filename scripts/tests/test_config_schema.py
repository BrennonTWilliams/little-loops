"""Tests for config-schema.json structure."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_SCHEMA = PROJECT_ROOT / "config-schema.json"


class TestConfigSchema:
    """Regression guards for config-schema.json structure."""

    def test_schema_file_exists(self) -> None:
        """config-schema.json must exist at project root."""
        assert CONFIG_SCHEMA.exists(), f"config-schema.json not found: {CONFIG_SCHEMA}"

    def test_extensions_in_properties(self) -> None:
        """extensions key must be inside the properties block."""
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "properties" in data, "config-schema.json missing top-level properties block"
        assert "extensions" in data["properties"], (
            "extensions key is outside the properties block — "
            "any config using extensions would trigger additionalProperties violation"
        )

    def test_scratch_pad_properties(self) -> None:
        """scratch_pad block must expose all properties required by the PreToolUse hook."""
        data = json.loads(CONFIG_SCHEMA.read_text())
        props = data["properties"]["scratch_pad"]["properties"]
        assert props["automation_contexts_only"]["default"] is True
        assert props["tail_lines"]["default"] == 20
        assert props["tail_lines"]["minimum"] == 5
        assert props["tail_lines"]["maximum"] == 200
        assert "cat" in props["command_allowlist"]["default"]
        assert ".py" in props["file_extension_filters"]["default"]

    def test_issues_next_issue_in_schema(self) -> None:
        """issues.next_issue block must declare strategy enum with the two known presets.

        Uses structural JSON-key assertions only; jsonschema is not a dependency,
        so this acts as a sentinel guard rather than runtime validation.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        issues_props = data["properties"]["issues"]["properties"]
        assert "next_issue" in issues_props, (
            "issues.next_issue is not declared in config-schema.json"
        )
        strategy = issues_props["next_issue"]["properties"]["strategy"]
        assert "enum" in strategy
        assert "confidence_first" in strategy["enum"]
        assert "priority_first" in strategy["enum"]
        assert "bogus" not in strategy["enum"]  # sentinel guard, not real validation

    def test_commands_rate_limits_block(self) -> None:
        """commands.rate_limits must be declared inside the commands block.

        The `commands` object has additionalProperties: false, so any config
        that sets commands.rate_limits will fail schema validation unless the
        block is declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        commands = data["properties"]["commands"]
        assert commands.get("additionalProperties") is False, (
            "commands block is expected to have additionalProperties: false — "
            "if that changes, this test's rationale no longer holds"
        )
        assert "rate_limits" in commands["properties"], (
            "commands.rate_limits is not declared; configs using it will be "
            "rejected by additionalProperties: false"
        )
        rate_limits = commands["properties"]["rate_limits"]
        assert rate_limits["type"] == "object"
        assert rate_limits.get("additionalProperties") is False
        rl_props = rate_limits["properties"]
        assert rl_props["max_wait_seconds"]["default"] == 21600
        assert rl_props["long_wait_ladder"]["default"] == [300, 900, 1800, 3600]
        assert rl_props["circuit_breaker_enabled"]["default"] is True
        assert rl_props["circuit_breaker_path"]["default"] == ".loops/tmp/rate-limit-circuit.json"
