"""Tests for FEAT-1459: Hook-intent reference doc enrichment.

Verifies that the reference documentation surfaces (hooks-reference.md,
EVENT-SCHEMA.md, API.md, CONFIGURATION.md, TROUBLESHOOTING.md, TESTING.md,
write-a-hook.md) cover the hook-intent abstraction layer per the acceptance
criteria enumerated in FEAT-1459.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

HOOKS_REFERENCE = PROJECT_ROOT / "docs" / "claude-code" / "hooks-reference.md"
EVENT_SCHEMA = PROJECT_ROOT / "docs" / "reference" / "EVENT-SCHEMA.md"
API_DOC = PROJECT_ROOT / "docs" / "reference" / "API.md"
CONFIGURATION_DOC = PROJECT_ROOT / "docs" / "reference" / "CONFIGURATION.md"
TROUBLESHOOTING_DOC = PROJECT_ROOT / "docs" / "development" / "TROUBLESHOOTING.md"
TESTING_DOC = PROJECT_ROOT / "docs" / "development" / "TESTING.md"
WRITE_A_HOOK = PROJECT_ROOT / "docs" / "claude-code" / "write-a-hook.md"


class TestHooksReferenceWiring:
    """hooks-reference.md must include an Intent model & adapters section linking to write-a-hook.md."""

    def test_intent_model_section_present(self) -> None:
        content = HOOKS_REFERENCE.read_text()
        assert "Intent model" in content, (
            "hooks-reference.md must include an 'Intent model & adapters' section near the top"
        )

    def test_links_to_authoring_guide(self) -> None:
        content = HOOKS_REFERENCE.read_text()
        assert "write-a-hook.md" in content, (
            "hooks-reference.md Intent model section must link to write-a-hook.md"
        )

    def test_links_to_event_schema(self) -> None:
        content = HOOKS_REFERENCE.read_text()
        assert "EVENT-SCHEMA.md" in content, (
            "hooks-reference.md Intent model section must link to EVENT-SCHEMA.md"
        )

    def test_mentions_llhookevent_and_result(self) -> None:
        content = HOOKS_REFERENCE.read_text()
        assert "LLHookEvent" in content, (
            "hooks-reference.md Intent model section must name LLHookEvent"
        )
        assert "LLHookResult" in content, (
            "hooks-reference.md Intent model section must name LLHookResult"
        )


class TestEventSchemaWiring:
    """EVENT-SCHEMA.md hook-intents subsection must replace the short blockquote with full field tables."""

    def test_llhookevent_field_table_present(self) -> None:
        content = EVENT_SCHEMA.read_text()
        assert "LLHookEvent" in content
        # Field-table rows: presence of representative fields confirms a table, not just prose
        for token in ("`host`", "`intent`", "`payload`", "`session_id`", "`cwd`"):
            assert token in content, (
                f"EVENT-SCHEMA.md LLHookEvent field table must include {token}"
            )

    def test_llhookresult_field_table_present(self) -> None:
        content = EVENT_SCHEMA.read_text()
        assert "LLHookResult" in content
        for token in ("`exit_code`", "`feedback`", "`decision`", "`data`", "`stdout`"):
            assert token in content, (
                f"EVENT-SCHEMA.md LLHookResult field table must include {token}"
            )

    def test_timestamp_wire_key_documented(self) -> None:
        content = EVENT_SCHEMA.read_text()
        assert "`ts`" in content, (
            "EVENT-SCHEMA.md hook-intent section must mention the `ts` wire key "
            "(LLHookEvent.timestamp serializes as `ts`)"
        )

    def test_wire_format_json_example_present(self) -> None:
        content = EVENT_SCHEMA.read_text()
        # The hook intents subsection must include a JSON code block with intent + payload
        assert '"intent"' in content, (
            "EVENT-SCHEMA.md must include a wire-format JSON example with an 'intent' key"
        )

    def test_per_intent_payload_notes(self) -> None:
        content = EVENT_SCHEMA.read_text()
        for intent in ("pre_compact", "session_start"):
            assert intent in content, (
                f"EVENT-SCHEMA.md must include a per-intent payload note for {intent}"
            )

    def test_cross_links_with_llevent(self) -> None:
        content = EVENT_SCHEMA.read_text()
        assert "LLEvent" in content, (
            "EVENT-SCHEMA.md hook-intent section must cross-link with LLEvent"
        )


class TestApiDocModuleRow:
    """API.md Module Overview table must include a little_loops.hooks row."""

    def test_module_overview_lists_hooks(self) -> None:
        content = API_DOC.read_text()
        assert "`little_loops.hooks`" in content, (
            "API.md Module Overview table must include a `little_loops.hooks` row"
        )


class TestApiDocExtensionApiSections:
    """API.md Extension API must have dedicated LLHookEvent/LLHookResult/LLHookIntentExtension subsections."""

    def test_llhookevent_subsection_present(self) -> None:
        content = API_DOC.read_text()
        assert "### LLHookEvent" in content, (
            "API.md Extension API must have a '### LLHookEvent' subsection"
        )

    def test_llhookresult_subsection_present(self) -> None:
        content = API_DOC.read_text()
        assert "### LLHookResult" in content, (
            "API.md Extension API must have a '### LLHookResult' subsection"
        )

    def test_llhookintentextension_subsection_present(self) -> None:
        content = API_DOC.read_text()
        assert "### LLHookIntentExtension" in content, (
            "API.md Extension API must have a dedicated '### LLHookIntentExtension' subsection "
            "matching the LLExtension Protocol / NoopLoggerExtension shape"
        )

    def test_provided_hook_intents_method_documented(self) -> None:
        content = API_DOC.read_text()
        assert "provided_hook_intents" in content, (
            "API.md LLHookIntentExtension subsection must document the provided_hook_intents method"
        )


class TestConfigurationWiring:
    """CONFIGURATION.md `### extensions` section must note that the entry-point group also dispatches hook-intent providers."""

    def test_extensions_section_mentions_hook_intent_protocol(self) -> None:
        content = CONFIGURATION_DOC.read_text()
        assert "LLHookIntentExtension" in content, (
            "CONFIGURATION.md `### extensions` section must mention LLHookIntentExtension "
            "as a provider type dispatched via the same entry-point group"
        )


class TestTroubleshootingPathAudit:
    """TROUBLESHOOTING.md must keep `hooks/scripts/` paths for non-migrated scripts (no stale renames)."""

    def test_context_monitor_path_intact(self) -> None:
        content = TROUBLESHOOTING_DOC.read_text()
        assert "hooks/scripts/context-monitor.sh" in content, (
            "TROUBLESHOOTING.md must reference hooks/scripts/context-monitor.sh "
            "(context-monitor.sh has not been migrated to hooks/core/)"
        )

    def test_user_prompt_check_path_intact(self) -> None:
        content = TROUBLESHOOTING_DOC.read_text()
        assert "hooks/scripts/user-prompt-check.sh" in content, (
            "TROUBLESHOOTING.md must reference hooks/scripts/user-prompt-check.sh "
            "(user-prompt-check.sh has not been migrated to hooks/core/)"
        )

    def test_check_duplicate_path_intact(self) -> None:
        content = TROUBLESHOOTING_DOC.read_text()
        assert "hooks/scripts/check-duplicate-issue-id.sh" in content, (
            "TROUBLESHOOTING.md must reference hooks/scripts/check-duplicate-issue-id.sh "
            "(check-duplicate-issue-id.sh has not been migrated to hooks/core/)"
        )


class TestTestingDocAdapterFixture:
    """TESTING.md must include an adapter-fixture variant invoking the dispatcher CLI."""

    def test_dispatcher_subprocess_pattern_documented(self) -> None:
        content = TESTING_DOC.read_text()
        assert "little_loops.hooks" in content, (
            "TESTING.md must include an adapter-fixture variant invoking python -m little_loops.hooks"
        )

    def test_subprocess_run_with_python_module(self) -> None:
        content = TESTING_DOC.read_text()
        assert "-m\", \"little_loops.hooks\"" in content or "-m', 'little_loops.hooks'" in content, (
            "TESTING.md adapter-fixture variant must show subprocess.run with -m little_loops.hooks"
        )

    def test_ll_hook_host_env_var_documented(self) -> None:
        content = TESTING_DOC.read_text()
        assert "LL_HOOK_HOST" in content, (
            "TESTING.md adapter-fixture variant must show LL_HOOK_HOST env var "
            "for flipping host identity in tests"
        )


class TestWriteAHookCrossLink:
    """write-a-hook.md `See also` callout must cross-link to EVENT-SCHEMA.md as the canonical wire-format reference."""

    def test_callout_references_event_schema(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "EVENT-SCHEMA.md" in content, (
            "write-a-hook.md must cross-link to EVENT-SCHEMA.md as the canonical "
            "wire-format reference alongside the existing types.py source link"
        )
