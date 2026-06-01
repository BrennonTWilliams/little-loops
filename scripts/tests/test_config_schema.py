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

    def test_issues_auto_commit_in_schema(self) -> None:
        """issues.auto_commit and auto_commit_prefix must be declared in config-schema.json.

        issues has additionalProperties: false, so these fields must be declared
        or any config using them will be rejected at validation time.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        issues_props = data["properties"]["issues"]["properties"]
        assert "auto_commit" in issues_props, (
            "issues.auto_commit is not declared in config-schema.json"
        )
        assert issues_props["auto_commit"]["type"] == "boolean"
        assert issues_props["auto_commit"].get("default") is False

        assert "auto_commit_prefix" in issues_props, (
            "issues.auto_commit_prefix is not declared in config-schema.json"
        )
        assert issues_props["auto_commit_prefix"]["type"] == "string"

    def test_commands_recursive_refine_in_schema(self) -> None:
        """commands.recursive_refine must be declared inside the commands block.

        The `commands` object has additionalProperties: false, so any config
        that sets commands.recursive_refine will fail schema validation unless
        the block is declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        commands = data["properties"]["commands"]
        assert commands.get("additionalProperties") is False, (
            "commands block is expected to have additionalProperties: false"
        )
        assert "recursive_refine" in commands["properties"], (
            "commands.recursive_refine is not declared; configs using it will be "
            "rejected by additionalProperties: false"
        )
        rr = commands["properties"]["recursive_refine"]
        assert rr["type"] == "object"
        rr_props = rr["properties"]
        assert rr_props["max_depth"]["type"] == "integer"
        assert rr_props["max_depth"]["minimum"] == 1
        assert rr_props["max_depth"]["default"] == 3

    def test_commands_review_epic_in_schema(self) -> None:
        """commands.review_epic must be declared inside the commands block.

        The `commands` object has additionalProperties: false, so any config
        that sets commands.review_epic will fail schema validation unless
        the block is declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        commands = data["properties"]["commands"]
        assert commands.get("additionalProperties") is False, (
            "commands block is expected to have additionalProperties: false"
        )
        assert "review_epic" in commands["properties"], (
            "commands.review_epic is not declared; configs using it will be "
            "rejected by additionalProperties: false"
        )
        re_ = commands["properties"]["review_epic"]
        assert re_["type"] == "object"
        re_props = re_["properties"]
        assert re_props["stale_days"]["type"] == "integer"
        assert re_props["stale_days"]["minimum"] == 1
        assert re_props["stale_days"]["default"] == 14
        assert re_props["enable_scope_drift_check"]["type"] == "boolean"
        assert re_props["enable_scope_drift_check"]["default"] is True

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

    def test_loops_glyphs_parallel_in_schema(self) -> None:
        """loops.glyphs.parallel must be declared so ll-config.json can set it.

        The `loops.glyphs` block has additionalProperties: false, so configs
        that set loops.glyphs.parallel will be rejected unless the property is
        declared here alongside the other glyph keys.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        glyph_props = data["properties"]["loops"]["properties"]["glyphs"]["properties"]
        assert "parallel" in glyph_props, (
            "loops.glyphs.parallel is not declared; configs using it will be "
            "rejected by additionalProperties: false"
        )
        assert glyph_props["parallel"]["type"] == "string"

    def test_learning_tests_in_schema(self) -> None:
        """learning_tests must be declared in config-schema.json.

        The top-level properties block has additionalProperties: false, so a
        config containing learning_tests will be rejected unless the property
        is declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "learning_tests" in data["properties"], (
            "learning_tests is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        lt_props = data["properties"]["learning_tests"]["properties"]
        assert "stale_after_days" in lt_props
        assert lt_props["stale_after_days"]["type"] == "integer"

        # FEAT-1743: enabled master switch
        assert "enabled" in lt_props, (
            "learning_tests.enabled is missing from config-schema.json; "
            "FEAT-1743 requires a boolean master switch"
        )
        assert lt_props["enabled"]["type"] == "boolean"
        assert lt_props["enabled"].get("default") is False

        # FEAT-1743: discoverability sub-object
        assert "discoverability" in lt_props, (
            "learning_tests.discoverability is missing from config-schema.json; "
            "FEAT-1743 requires discoverability settings"
        )
        disc_props = lt_props["discoverability"]["properties"]
        assert "mode" in disc_props
        assert disc_props["mode"]["type"] == "string"
        assert "skip_packages" in disc_props
        assert disc_props["skip_packages"]["type"] == "array"

    def test_design_tokens_in_schema(self) -> None:
        """design_tokens block must be declared in config-schema.json (FEAT-1747).

        The top-level properties block has additionalProperties: false, so a
        config containing 'design_tokens' will be rejected unless the property
        is declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "design_tokens" in data["properties"], (
            "design_tokens is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        dt = data["properties"]["design_tokens"]
        assert dt["type"] == "object"
        assert dt.get("additionalProperties") is False
        props = dt["properties"]
        assert props["enabled"]["type"] == "boolean"
        assert props["enabled"]["default"] is True
        assert props["path"]["type"] == "string"
        assert props["path"]["default"] == ".ll/design-tokens"
        assert props["primitives_file"]["type"] == "string"
        assert props["primitives_file"]["default"] == "primitives.json"
        assert props["semantic_file"]["type"] == "string"
        assert props["semantic_file"]["default"] == "semantic.json"
        assert props["themes_dir"]["type"] == "string"
        assert props["themes_dir"]["default"] == "themes"
        assert props["active_theme"]["type"] == "string"
        assert props["active_theme"]["default"] == "light"

    def test_analytics_in_schema(self) -> None:
        """analytics block must be declared in config-schema.json (FEAT-1624).

        The top-level properties block has additionalProperties: false, so a
        config containing 'analytics' will be rejected unless the property is
        declared here. The block gates the post_tool_use hook's per-tool byte
        tracking (FEAT-1623) consumed by ``ll-ctx-stats``.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "analytics" in data["properties"], (
            "analytics is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        analytics = data["properties"]["analytics"]
        assert analytics["type"] == "object"
        assert analytics.get("additionalProperties") is False
        assert "enabled" in analytics["properties"]
        enabled = analytics["properties"]["enabled"]
        assert enabled["type"] == "boolean"
        assert enabled["default"] is False

    def test_analytics_capture_in_schema(self) -> None:
        """analytics.capture sub-object must be declared so additionalProperties: false
        doesn't silently reject it (ENH-1840)."""
        data = json.loads(CONFIG_SCHEMA.read_text())
        analytics = data["properties"]["analytics"]
        assert analytics.get("additionalProperties") is False

        assert "capture" in analytics["properties"], (
            "analytics.capture is not declared; configs using it will be "
            "rejected by additionalProperties: false on the analytics block"
        )
        capture = analytics["properties"]["capture"]
        assert capture["type"] == "object"
        assert capture.get("additionalProperties") is False

        capture_props = capture["properties"]
        assert "skills" in capture_props
        assert capture_props["skills"]["type"] == "array"
        assert capture_props["skills"]["items"]["type"] == "string"
        assert capture_props["skills"]["default"] == ["*"]

        assert "cli_commands" in capture_props
        assert capture_props["cli_commands"]["type"] == "array"
        assert capture_props["cli_commands"]["default"] == ["*"]

        assert "corrections" in capture_props
        assert capture_props["corrections"]["type"] == "boolean"
        assert capture_props["corrections"]["default"] is True

        assert "file_events" in capture_props
        assert capture_props["file_events"]["type"] == "boolean"
        assert capture_props["file_events"]["default"] is True

    def test_hooks_in_schema(self) -> None:
        """hooks block must be declared in config-schema.json with a host enum.

        The top-level properties block has additionalProperties: false, so a
        config containing 'hooks' will be rejected unless the property is
        declared. FEAT-1448 introduces this block as the foundation of the
        hook-intent abstraction layer (FEAT-1116).
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "hooks" in data["properties"], (
            "hooks is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        hooks_block = data["properties"]["hooks"]
        assert hooks_block["type"] == "object"
        assert hooks_block.get("additionalProperties") is False
        assert "host" in hooks_block["properties"]
        host = hooks_block["properties"]["host"]
        assert host["type"] == "string"
        assert host["enum"] == ["claude-code", "opencode", "codex"]

    def test_stale_ref_fix_in_schema(self) -> None:
        """hooks.stale_ref_fix must be declared in config-schema.json (FEAT-1680).

        The hooks block has additionalProperties: false, so a config containing
        hooks.stale_ref_fix will be rejected unless the property is declared here.
        The value must be a string enum restricted to "report" or "auto".
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "stale_ref_fix" in data["properties"]["hooks"]["properties"], (
            "hooks.stale_ref_fix is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false on the hooks block"
        )
        assert data["properties"]["hooks"]["properties"]["stale_ref_fix"]["type"] == "string"
        assert data["properties"]["hooks"]["properties"]["stale_ref_fix"]["enum"] == ["report", "auto"]
        assert data["properties"]["hooks"].get("additionalProperties") is False

    def test_events_in_schema(self) -> None:
        """events block must be declared in config-schema.json with a transports array.

        The top-level properties block has additionalProperties: false, so a
        config containing events will be rejected unless the property is declared.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "events" in data["properties"], (
            "events is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        events_props = data["properties"]["events"]["properties"]
        assert "transports" in events_props
        assert events_props["transports"]["type"] == "array"
        assert events_props["transports"]["items"]["type"] == "string"

        assert "socket" in events_props, (
            "events.socket is not declared; configs using events.socket will be "
            "rejected by additionalProperties: false on the events block"
        )
        socket_block = events_props["socket"]
        assert socket_block["type"] == "object"
        assert socket_block.get("additionalProperties") is False
        socket_props = socket_block["properties"]
        assert socket_props["path"]["type"] == "string"
        assert socket_props["path"]["default"] == ".ll/events.sock"
        assert socket_props["max_clients"]["type"] == "integer"
        assert socket_props["max_clients"]["default"] == 8

        assert "otel" in events_props, (
            "events.otel is not declared; configs using events.otel will be "
            "rejected by additionalProperties: false on the events block"
        )
        otel_block = events_props["otel"]
        assert otel_block["type"] == "object"
        assert otel_block.get("additionalProperties") is False
        otel_props = otel_block["properties"]
        assert otel_props["endpoint"]["type"] == "string"
        assert otel_props["endpoint"]["default"] == "http://localhost:4317"
        assert otel_props["service_name"]["type"] == "string"
        assert otel_props["service_name"]["default"] == "little-loops"

        assert "webhook" in events_props, (
            "events.webhook is not declared; configs using events.webhook will be "
            "rejected by additionalProperties: false on the events block"
        )
        webhook_block = events_props["webhook"]
        assert webhook_block["type"] == "object"
        assert webhook_block.get("additionalProperties") is False
        webhook_props = webhook_block["properties"]
        assert webhook_props["url"]["default"] is None
        assert webhook_props["batch_ms"]["type"] == "integer"
        assert webhook_props["batch_ms"]["default"] == 1000
        assert webhook_props["headers"]["type"] == "object"

        assert "sqlite" in events_props, (
            "events.sqlite is not declared; configs using events.sqlite will be "
            "rejected by additionalProperties: false on the events block"
        )
        sqlite_block = events_props["sqlite"]
        assert sqlite_block["type"] == "object"
        assert sqlite_block.get("additionalProperties") is False
        assert sqlite_block["properties"]["path"]["default"] == ".ll/history.db"

    def test_issues_relationship_fields_in_schema(self) -> None:
        """Relationship fields must be declared inside issues.properties.

        The issues block has additionalProperties: false, so any config that
        sets parent/blocked_by/depends_on/relates_to/duplicate_of will be
        rejected unless they are declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        issues = data["properties"]["issues"]
        assert issues.get("additionalProperties") is False, (
            "issues block is expected to have additionalProperties: false — "
            "if that changes, this test's rationale no longer holds"
        )
        issue_props = issues["properties"]

        # Single-value string fields
        for field in ("parent", "duplicate_of"):
            assert field in issue_props, (
                f"issues.{field} is not declared; configs using it will be "
                "rejected by additionalProperties: false"
            )
            assert issue_props[field]["type"] == "string"

        # Array-of-strings fields
        for field in ("blocked_by", "depends_on", "relates_to"):
            assert field in issue_props, (
                f"issues.{field} is not declared; configs using it will be "
                "rejected by additionalProperties: false"
            )
            assert issue_props[field]["type"] == "array"
            assert issue_props[field]["items"] == {"type": "string"}

    def test_orchestration_host_cli_in_schema(self) -> None:
        """orchestration.host_cli must be declared as a string enum in config-schema.json.

        Follows the test_hooks_in_schema pattern: structural JSON-key assertions only,
        no jsonschema runtime validation.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "orchestration" in data["properties"], (
            "orchestration key is not declared in config-schema.json"
        )
        orch = data["properties"]["orchestration"]
        assert orch["type"] == "object"
        assert "host_cli" in orch["properties"], (
            "orchestration.host_cli is not declared in config-schema.json"
        )
        host_cli = orch["properties"]["host_cli"]
        assert host_cli["type"] == "string"
        assert "enum" in host_cli
        assert "claude-code" in host_cli["enum"]
        assert "codex" in host_cli["enum"]

    def test_epics_scope_in_schema(self) -> None:
        """epics.scope must be declared as a top-level property in config-schema.json.

        The root properties block has additionalProperties: false, so any config
        that sets epics.scope.* will fail schema validation unless the epics
        property and its scope sub-properties are declared here.
        """
        data = json.loads(CONFIG_SCHEMA.read_text())
        root_props = data["properties"]
        assert "epics" in root_props, (
            "epics is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        epics = root_props["epics"]
        assert epics["type"] == "object"
        assert "scope" in epics["properties"], (
            "epics.scope is not declared in config-schema.json"
        )
        scope = epics["properties"]["scope"]
        assert scope["type"] == "object"
        scope_props = scope["properties"]
        assert scope_props["min_children"]["type"] == "integer"
        assert scope_props["min_children"]["minimum"] == 1
        assert scope_props["min_children"]["default"] == 3
        assert scope_props["max_children"]["type"] == "integer"
        assert scope_props["max_children"]["minimum"] == 1
        assert scope_props["max_children"]["default"] == 8
