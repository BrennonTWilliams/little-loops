"""Tests for config-schema.json structure."""

from __future__ import annotations

import importlib.resources
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

# Resolve via importlib.resources so tests work in both editable installs and
# non-editable wheel installs (the schema now ships inside the package, not at
# the repo root).
CONFIG_SCHEMA = importlib.resources.files("little_loops").joinpath("config-schema.json")


def _load_schema_text() -> str:
    """Read the bundled config-schema.json as text."""
    return CONFIG_SCHEMA.read_text(encoding="utf-8")


class TestConfigSchema:
    """Regression guards for config-schema.json structure."""

    def test_schema_file_exists(self) -> None:
        """config-schema.json must be accessible inside the package."""
        assert CONFIG_SCHEMA.is_file(), f"config-schema.json not found: {CONFIG_SCHEMA}"

    def test_extensions_in_properties(self) -> None:
        """extensions key must be inside the properties block."""
        data = json.loads(_load_schema_text())
        assert "properties" in data, "config-schema.json missing top-level properties block"
        assert "extensions" in data["properties"], (
            "extensions key is outside the properties block — "
            "any config using extensions would trigger additionalProperties violation"
        )

    def test_scratch_pad_properties(self) -> None:
        """scratch_pad block must expose all properties required by the PreToolUse hook."""
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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

    def test_issues_deploy_templates_in_schema(self) -> None:
        """issues.deploy_templates must be declared in config-schema.json.

        issues has additionalProperties: false, so this field must be declared
        or any config using it will be rejected at validation time.
        """
        data = json.loads(_load_schema_text())
        issues_props = data["properties"]["issues"]["properties"]
        assert "deploy_templates" in issues_props, (
            "issues.deploy_templates is not declared in config-schema.json"
        )
        assert issues_props["deploy_templates"]["type"] == "boolean"
        assert issues_props["deploy_templates"].get("default") is False

    def test_commands_recursive_refine_in_schema(self) -> None:
        """commands.recursive_refine must be declared inside the commands block.

        The `commands` object has additionalProperties: false, so any config
        that sets commands.recursive_refine will fail schema validation unless
        the block is declared here.
        """
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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

        # ENH-2487: auto_prove gate for config-driven rn-implement auto-prove
        assert "auto_prove" in lt_props, (
            "learning_tests.auto_prove is missing from config-schema.json; "
            "ENH-2487 requires it so config setting it is not schema-rejected by "
            "additionalProperties: false"
        )
        assert lt_props["auto_prove"]["type"] == "boolean"
        assert lt_props["auto_prove"].get("default") is True

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

    def test_decisions_in_schema(self) -> None:
        """decisions must be declared in config-schema.json.

        The top-level properties block has additionalProperties: false, so a
        config containing decisions will be rejected unless the property
        is declared here.
        """
        data = json.loads(_load_schema_text())
        assert "decisions" in data["properties"], (
            "decisions is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        dec_props = data["properties"]["decisions"]["properties"]
        assert "enabled" in dec_props
        assert dec_props["enabled"]["type"] == "boolean"
        assert dec_props["enabled"].get("default") is False

        assert "log_path" in dec_props
        assert dec_props["log_path"]["type"] == "string"

        assert "auto_generate" in dec_props
        assert dec_props["auto_generate"]["type"] == "array"

        assert data["properties"]["decisions"].get("additionalProperties") is False

    def test_health_url_in_schema(self) -> None:
        """FEAT-2551: project.health_url must be declared in config-schema.json.

        The project block has additionalProperties: false (config-schema.json:61),
        so a config containing project.health_url is rejected unless the
        property is declared here. The code-run-gate oracle's service_health
        state reads this URL to probe service readiness.
        """
        data = json.loads(_load_schema_text())
        project_props = data["properties"]["project"]["properties"]
        assert "health_url" in project_props, (
            "project.health_url is not declared in config-schema.json; configs "
            "using it will be rejected by additionalProperties: false on the "
            "project block (FEAT-2551)"
        )
        assert "null" in project_props["health_url"]["type"], (
            "project.health_url must allow null (type = ['string', 'null'])"
        )
        assert project_props["health_url"].get("default") is None, (
            "project.health_url must default to null"
        )

    def test_design_tokens_in_schema(self) -> None:
        """design_tokens block must be declared in config-schema.json (FEAT-1747).

        The top-level properties block has additionalProperties: false, so a
        config containing 'design_tokens' will be rejected unless the property
        is declared here.
        """
        data = json.loads(_load_schema_text())
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
        assert props["active_theme"]["default"] == "dark"

    def test_artifacts_in_schema(self) -> None:
        """artifacts block must be declared in config-schema.json (FEAT-2390).

        The top-level properties block has additionalProperties: false, so a
        config containing 'artifacts' will be rejected unless the property is
        declared here. The block backs ``BRConfig.artifacts`` / ``ArtifactsConfig``
        which supplies ll-artifact's default output directory.
        """
        data = json.loads(_load_schema_text())
        assert "artifacts" in data["properties"], (
            "artifacts is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        artifacts = data["properties"]["artifacts"]
        assert artifacts["type"] == "object"
        assert artifacts.get("additionalProperties") is False
        props = artifacts["properties"]
        assert props["default_output_dir"]["type"] == "string"
        assert props["default_output_dir"]["default"] == "."

    def test_analytics_in_schema(self) -> None:
        """analytics block must be declared in config-schema.json (FEAT-1624).

        The top-level properties block has additionalProperties: false, so a
        config containing 'analytics' will be rejected unless the property is
        declared here. The block gates the post_tool_use hook's per-tool byte
        tracking (FEAT-1623) consumed by ``ll-ctx-stats``.
        """
        data = json.loads(_load_schema_text())
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

    def test_history_in_schema(self) -> None:
        """history block must be declared in config-schema.json (ENH-1913).

        The top-level properties block has additionalProperties: false, so a
        config containing 'history' will be rejected unless the property is
        declared here. This block is the sole owner of the history.* namespace.
        """
        data = json.loads(_load_schema_text())
        assert "history" in data["properties"], (
            "history is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        history = data["properties"]["history"]
        assert history["type"] == "object"
        assert history.get("additionalProperties") is False
        assert "velocity_window" in history["properties"]
        assert history["properties"]["velocity_window"]["type"] == "integer"
        assert history["properties"]["velocity_window"]["default"] == 10
        assert "max_age_days" in history["properties"]
        assert "null" in history["properties"]["max_age_days"]["type"]
        assert history["properties"]["max_age_days"]["default"] is None
        assert "session_digest" in history["properties"]
        assert history["properties"]["session_digest"]["type"] == "object"
        assert history["properties"]["session_digest"].get("additionalProperties") is False
        assert "evolution" in history["properties"]
        assert history["properties"]["evolution"].get("additionalProperties") is False
        assert "go_no_go" in history["properties"]
        assert "capture_issue" in history["properties"]
        assert "compaction" in history["properties"]

    def test_history_compaction_in_schema(self) -> None:
        """history.compaction must be declared (FEAT-1712); additionalProperties: false rejects it otherwise."""
        data = json.loads(_load_schema_text())
        compaction = data["properties"]["history"]["properties"]["compaction"]
        assert compaction["type"] == "object"
        assert compaction.get("additionalProperties") is False
        assert "enabled" in compaction["properties"]
        assert compaction["properties"]["enabled"]["type"] == "boolean"
        assert compaction["properties"]["enabled"]["default"] is False
        assert "budget_tokens" in compaction["properties"]
        assert compaction["properties"]["budget_tokens"]["default"] == 4096
        assert "model" in compaction["properties"]
        assert "null" in compaction["properties"]["model"]["type"]
        assert "timeout" in compaction["properties"]
        assert "cross_session_enabled" in compaction["properties"], (
            "cross_session_enabled must be declared; additionalProperties: false rejects it otherwise"
        )
        assert compaction["properties"]["cross_session_enabled"]["type"] == "boolean"
        assert compaction["properties"]["cross_session_enabled"]["default"] is True
        assert "max_level" in compaction["properties"], (
            "max_level must be declared; additionalProperties: false rejects it otherwise"
        )
        assert "null" in compaction["properties"]["max_level"]["type"]

    def test_analytics_capture_in_schema(self) -> None:
        """analytics.capture sub-object must be declared so additionalProperties: false
        doesn't silently reject it (ENH-1840)."""
        data = json.loads(_load_schema_text())
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

        assert "correction_patterns" in capture_props
        assert capture_props["correction_patterns"]["type"] == "array"
        assert capture_props["correction_patterns"]["items"]["type"] == "string"
        assert capture_props["correction_patterns"]["default"] == []

    def test_hooks_in_schema(self) -> None:
        """hooks block must be declared in config-schema.json with a host enum.

        The top-level properties block has additionalProperties: false, so a
        config containing 'hooks' will be rejected unless the property is
        declared. FEAT-1448 introduces this block as the foundation of the
        hook-intent abstraction layer (FEAT-1116).
        """
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
        assert "stale_ref_fix" in data["properties"]["hooks"]["properties"], (
            "hooks.stale_ref_fix is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false on the hooks block"
        )
        assert data["properties"]["hooks"]["properties"]["stale_ref_fix"]["type"] == "string"
        assert data["properties"]["hooks"]["properties"]["stale_ref_fix"]["enum"] == [
            "report",
            "auto",
        ]
        assert data["properties"]["hooks"].get("additionalProperties") is False

    def test_events_in_schema(self) -> None:
        """events block must be declared in config-schema.json with a transports array.

        The top-level properties block has additionalProperties: false, so a
        config containing events will be rejected unless the property is declared.
        """
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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
        data = json.loads(_load_schema_text())
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

    def test_orchestration_cluster_in_schema(self) -> None:
        """orchestration.cluster must be declared with its three properties in config-schema.json.

        Follows the test_orchestration_host_cli_in_schema pattern: structural JSON-key
        assertions only, no jsonschema runtime validation.
        """
        data = json.loads(_load_schema_text())
        assert "orchestration" in data["properties"], (
            "orchestration key is not declared in config-schema.json"
        )
        orch = data["properties"]["orchestration"]
        assert "cluster" in orch["properties"], (
            "orchestration.cluster is not declared in config-schema.json"
        )
        cluster = orch["properties"]["cluster"]
        assert cluster["type"] == "object"
        assert "max_batch_size" in cluster["properties"], (
            "orchestration.cluster.max_batch_size is not declared in config-schema.json"
        )
        assert cluster["properties"]["max_batch_size"]["type"] == "integer"
        assert "enable_dedup" in cluster["properties"], (
            "orchestration.cluster.enable_dedup is not declared in config-schema.json"
        )
        assert cluster["properties"]["enable_dedup"]["type"] == "boolean"
        assert "propagate_context" in cluster["properties"], (
            "orchestration.cluster.propagate_context is not declared in config-schema.json"
        )
        assert cluster["properties"]["propagate_context"]["type"] == "boolean"

    def test_epics_removed_from_schema(self) -> None:
        """ENH-2544 (Option B): `epics` must be absent from config-schema.json.

        Decision ARCHITECTURE-096 (2026-06-30) explicitly chose
        `parallel.epic_branches.*` over `epics.*` as a config namespace,
        leaving the `epics.*` schema subtree as an abandoned alternative
        with no in-repo consumer. Per ENH-2544, the schema block is removed
        and any user config setting `epics.*` must now be rejected by the
        root-level `additionalProperties: false`.
        """
        data = json.loads(_load_schema_text())
        root_props = data["properties"]
        assert "epics" not in root_props, (
            "epics is declared in config-schema.json; ENH-2544 Option B "
            "removes the block. configs that set epics.* were already "
            "schema-only / not wired into BRConfig.to_dict()."
        )

    def test_scope_epic_skill_uses_literal_thresholds(self) -> None:
        """ENH-2544 (Option B): scope-epic SKILL.md must use literal 3/8 thresholds.

        Prior to ENH-2544, the skill used `{{config.epics.scope.min_children}}`
        and `{{config.epics.scope.max_children}}` placeholders that resolved
        to an empty string at runtime (no EpicsConfig dataclass). The blockquote
        in CONFIGURATION.md surfaced this gap explicitly. After Option B the
        skill body must hard-code the defaults (3 children min, 8 max).
        """
        skill_path = PROJECT_ROOT / "skills" / "scope-epic" / "SKILL.md"
        assert skill_path.exists(), f"scope-epic SKILL.md not found: {skill_path}"
        body = skill_path.read_text()
        assert "{{config.epics.scope.min_children}}" not in body, (
            "scope-epic SKILL.md still references {{config.epics.scope.min_children}}"
            " — ENH-2544 Option B hard-codes the value (default 3)."
        )
        assert "{{config.epics.scope.max_children}}" not in body, (
            "scope-epic SKILL.md still references {{config.epics.scope.max_children}}"
            " — ENH-2544 Option B hard-codes the value (default 8)."
        )
        # The four substitution sites must now contain literal integers, not placeholders.
        assert "Min children**: `3`" in body or "Min children**: 3" in body, (
            "scope-epic SKILL.md does not contain the literal min-children default (3)."
        )
        assert "Max children**: `8`" in body or "Max children**: 8" in body, (
            "scope-epic SKILL.md does not contain the literal max-children default (8)."
        )
        assert "MIN_CHILDREN = 3" in body, (
            "scope-epic SKILL.md does not contain the literal `MIN_CHILDREN = 3`."
        )
        assert "MAX_CHILDREN = 8" in body, (
            "scope-epic SKILL.md does not contain the literal `MAX_CHILDREN = 8`."
        )

    def test_install_source_in_schema(self) -> None:
        """install_source must be declared in config-schema.json root properties.

        The root properties block has additionalProperties: false, so writing
        install_source to .ll/ll-config.json will be rejected by schema validation
        unless the property is declared here.
        """
        data = json.loads(_load_schema_text())
        assert "install_source" in data["properties"], (
            "install_source is not declared in config-schema.json; writing it to config "
            "would violate additionalProperties: false"
        )
        install_source = data["properties"]["install_source"]
        assert "string" in install_source["type"]
        assert "enum" in install_source, "install_source should have an enum constraint"
        assert "project-claude-code" in install_source["enum"], (
            "project-claude-code missing from install_source enum (BUG-2266)"
        )

    def test_session_capture_in_schema(self) -> None:
        """session_capture block must be declared in config-schema.json (FEAT-1262).

        The top-level properties block has additionalProperties: false, so a
        config containing 'session_capture' will be rejected unless the property
        is declared here. The block gates the session-capture.sh PostToolUse hook
        that appends per-tool event records to .ll/ll-session-events.jsonl.
        """
        data = json.loads(_load_schema_text())
        assert "session_capture" in data["properties"], (
            "session_capture is not declared in config-schema.json; configs using it will be "
            "rejected by additionalProperties: false"
        )
        session_capture = data["properties"]["session_capture"]
        assert session_capture["type"] == "object"
        assert session_capture.get("additionalProperties") is False
        assert "enabled" in session_capture["properties"]
        enabled = session_capture["properties"]["enabled"]
        assert enabled["type"] == "boolean"
        assert enabled["default"] is False

    def test_hooks_pre_compact_rubric_in_schema(self) -> None:
        """hooks.pre_compact.rubric must be declared in config-schema.json (ENH-2341).

        The hooks block has additionalProperties: false, so pre_compact must be
        explicitly declared or any config using it will be rejected by JSON Schema.
        """
        data = json.loads(_load_schema_text())
        hooks_props = data["properties"]["hooks"]["properties"]
        assert "pre_compact" in hooks_props, (
            "hooks.pre_compact is not declared in config-schema.json; configs using "
            "hooks.pre_compact.rubric will be rejected by additionalProperties: false"
        )
        rubric_props = hooks_props["pre_compact"]["properties"]["rubric"]["properties"]
        assert "enabled" in rubric_props
        assert rubric_props["enabled"]["type"] == "boolean"
        assert "hard_ceiling_pct" in rubric_props
        assert rubric_props["hard_ceiling_pct"]["type"] == "number"
        assert "signals" in rubric_props
        signals_props = rubric_props["signals"]["properties"]
        assert "closed_unit_signals" in signals_props
        assert signals_props["closed_unit_signals"]["type"] == "array"
        assert "reducible_signals" in signals_props
        assert "progress_signals" in signals_props
        assert "stuck_signals" in signals_props

    def test_parallel_epic_branches_in_schema(self) -> None:
        """parallel.epic_branches must be declared as a nested object (FEAT-2447).

        The `parallel` block has additionalProperties: false, so epic_branches
        must be explicitly declared or any config setting it will be rejected
        by JSON Schema validation.
        """
        data = json.loads(_load_schema_text())
        parallel = data["properties"]["parallel"]
        assert parallel.get("additionalProperties") is False, (
            "parallel block is expected to have additionalProperties: false"
        )
        assert "epic_branches" in parallel["properties"], (
            "parallel.epic_branches is not declared in config-schema.json; configs "
            "using it will be rejected by additionalProperties: false"
        )
        eb = parallel["properties"]["epic_branches"]
        assert eb["type"] == "object"
        eb_props = eb["properties"]
        assert eb_props["enabled"]["type"] == "boolean"
        assert eb_props["enabled"]["default"] is False
        assert eb_props["prefix"]["type"] == "string"
        assert eb_props["prefix"]["default"] == "epic/"
        assert eb_props["merge_to_base_on_complete"]["type"] == "boolean"
        assert eb_props["merge_to_base_on_complete"]["default"] is True
        assert eb_props["open_pr"]["type"] == "boolean"
        assert eb_props["open_pr"]["default"] is False
