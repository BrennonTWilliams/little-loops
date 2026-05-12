"""Tests for FEAT-1457: LLHookIntentExtension authoring docs and skills update.

Verifies that the 12 doc/skill/source locations enumerated in FEAT-1457 mention
`LLHookIntentExtension` (or the corresponding hooks/adapters/ path update) so the
new Protocol is discoverable from every authoring surface that already covers
`InterceptorExtension` / `ActionProviderExtension` / `EvaluatorProviderExtension`.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"
CLI_DOC = PROJECT_ROOT / "docs" / "reference" / "CLI.md"
CREATE_EXTENSION_PY = PROJECT_ROOT / "scripts" / "little_loops" / "cli" / "create_extension.py"
WORKFLOW_PROPOSER = PROJECT_ROOT / "skills" / "workflow-automation-proposer" / "SKILL.md"
CONFIGURE_AREAS = PROJECT_ROOT / "skills" / "configure" / "areas.md"
AUDIT_CLAUDE_CONFIG = PROJECT_ROOT / "skills" / "audit-claude-config" / "SKILL.md"
INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"
API_DOC = PROJECT_ROOT / "docs" / "reference" / "API.md"
ARCHITECTURE_DOC = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
TROUBLESHOOTING_DOC = PROJECT_ROOT / "docs" / "development" / "TROUBLESHOOTING.md"
WRITE_A_HOOK = PROJECT_ROOT / "docs" / "claude-code" / "write-a-hook.md"
AUTOMATE_HOOKS = PROJECT_ROOT / "docs" / "claude-code" / "automate-workflows-with-hooks.md"
MKDOCS_YML = PROJECT_ROOT / "mkdocs.yml"
INDEX_MD = PROJECT_ROOT / "docs" / "index.md"


class TestContributingWiring:
    """CONTRIBUTING.md must mention LLHookIntentExtension in Develop and clarify hook event format."""

    def test_develop_section_mentions_protocol(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "LLHookIntentExtension" in content, (
            "CONTRIBUTING.md must mention LLHookIntentExtension as an optional mixin Protocol"
        )

    def test_event_schema_note_mentions_hook_event(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "LLHookEvent" in content, (
            "CONTRIBUTING.md Event Schema Maintenance must clarify LLHookEvent is a "
            "sibling wire format outside the JSON Schema regeneration flow"
        )


class TestCliDocWiring:
    """docs/reference/CLI.md scaffold preview must list LLHookIntentExtension."""

    def test_scaffold_preview_lists_protocol(self) -> None:
        content = CLI_DOC.read_text()
        assert "LLHookIntentExtension" in content, (
            "docs/reference/CLI.md scaffold preview must list LLHookIntentExtension in the "
            "optional mixin Protocols list"
        )


class TestCreateExtensionScaffoldWiring:
    """create_extension.py scaffold docstring must list LLHookIntentExtension."""

    def test_render_extension_docstring_lists_protocol(self) -> None:
        content = CREATE_EXTENSION_PY.read_text()
        assert "LLHookIntentExtension" in content, (
            "create_extension.py scaffold docstring must list LLHookIntentExtension among the "
            "optional mixin Protocols"
        )


class TestWorkflowProposerWiring:
    """workflow-automation-proposer SKILL.md Step 7 must describe the adapter model."""

    def test_hooks_sketch_uses_protocol(self) -> None:
        content = WORKFLOW_PROPOSER.read_text()
        assert "LLHookIntentExtension" in content, (
            "workflow-automation-proposer SKILL.md must reference LLHookIntentExtension "
            "in the 'For hooks' implementation sketch"
        )

    def test_hooks_sketch_references_adapters(self) -> None:
        content = WORKFLOW_PROPOSER.read_text()
        assert "hooks/adapters/" in content, (
            "workflow-automation-proposer SKILL.md must reference hooks/adapters/<host>/ "
            "instead of direct hooks/hooks.json edits"
        )


class TestConfigureAreasWiring:
    """configure/areas.md precompact row must use the adapter path."""

    def test_precompact_row_uses_adapter_path(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        assert "adapters/claude-code/precompact.sh" in content, (
            "configure/areas.md PreCompact row must point at adapters/claude-code/precompact.sh"
        )

    def test_no_bare_precompact_state_path(self) -> None:
        content = CONFIGURE_AREAS.read_text()
        bare_lines = [
            line
            for line in content.splitlines()
            if "precompact-state.sh" in line and "adapters/" not in line
        ]
        assert not bare_lines, (
            "configure/areas.md must not show bare precompact-state.sh paths; "
            f"found: {bare_lines!r}"
        )


class TestAuditClaudeConfigWiring:
    """audit-claude-config SKILL.md audit scope must include hooks/adapters/ and scripts/little_loops/hooks/."""

    def test_audit_scope_includes_adapters(self) -> None:
        content = AUDIT_CLAUDE_CONFIG.read_text()
        assert "hooks/adapters/" in content, (
            "audit-claude-config SKILL.md must include hooks/adapters/ in its audit scope"
        )

    def test_audit_scope_includes_core(self) -> None:
        content = AUDIT_CLAUDE_CONFIG.read_text()
        assert "scripts/little_loops/hooks/" in content, (
            "audit-claude-config SKILL.md must include scripts/little_loops/hooks/ "
            "(host-agnostic Python handlers) in its audit scope"
        )


class TestInitSkillWiring:
    """init SKILL.md Section 9.5 warning must reflect the Python-handler / adapter model."""

    def test_warning_references_adapters(self) -> None:
        content = INIT_SKILL.read_text()
        assert "hooks/adapters/claude-code/" in content, (
            "init SKILL.md hook dependency warning must reference the claude-code adapter path"
        )


class TestClaudeMdWiring:
    """.claude/CLAUDE.md hooks/ entry must show host-agnostic handler location and adapters/ subdirectory."""

    def test_hooks_entry_lists_handlers(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "scripts/little_loops/hooks/" in content, (
            ".claude/CLAUDE.md must list scripts/little_loops/hooks/ "
            "as the host-agnostic Python handler location"
        )

    def test_hooks_entry_lists_adapters(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "adapters/" in content, ".claude/CLAUDE.md hooks/ entry must list hooks/adapters/"


class TestApiDocWiring:
    """docs/reference/API.md wire_extensions description must mention LLHookIntentExtension."""

    def test_wire_extensions_mentions_protocol(self) -> None:
        content = API_DOC.read_text()
        assert "LLHookIntentExtension" in content, (
            "docs/reference/API.md wire_extensions section must mention LLHookIntentExtension"
        )

    def test_wire_extensions_mentions_registry(self) -> None:
        content = API_DOC.read_text()
        assert "_HOOK_INTENT_REGISTRY" in content, (
            "docs/reference/API.md wire_extensions section must mention _HOOK_INTENT_REGISTRY"
        )


class TestArchitectureWiring:
    """docs/ARCHITECTURE.md components table must include an LLHookIntentExtension row."""

    def test_components_table_lists_protocol(self) -> None:
        content = ARCHITECTURE_DOC.read_text()
        assert "LLHookIntentExtension" in content, (
            "docs/ARCHITECTURE.md components table must include an LLHookIntentExtension row"
        )

    def test_components_row_references_registry(self) -> None:
        content = ARCHITECTURE_DOC.read_text()
        assert "_HOOK_INTENT_REGISTRY" in content, (
            "docs/ARCHITECTURE.md LLHookIntentExtension row must reference _HOOK_INTENT_REGISTRY"
        )


class TestTroubleshootingWiring:
    """docs/development/TROUBLESHOOTING.md must not retain the stale precompact-state.sh path."""

    def test_chmod_block_uses_adapter_path(self) -> None:
        content = TROUBLESHOOTING_DOC.read_text()
        assert "hooks/adapters/claude-code/precompact.sh" in content, (
            "TROUBLESHOOTING.md chmod block must list the adapter path for precompact"
        )

    def test_no_stale_hooks_scripts_precompact_state_path(self) -> None:
        content = TROUBLESHOOTING_DOC.read_text()
        assert "hooks/scripts/precompact-state.sh" not in content, (
            "TROUBLESHOOTING.md must not retain the stale hooks/scripts/precompact-state.sh path"
        )


class TestWriteAHookWiring:
    """docs/claude-code/write-a-hook.md must exist and reference the intent-model surface."""

    def test_guide_file_exists(self) -> None:
        assert WRITE_A_HOOK.exists(), (
            "FEAT-1458 authoring guide must exist at docs/claude-code/write-a-hook.md"
        )

    def test_guide_mentions_llhookevent(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "LLHookEvent" in content, (
            "write-a-hook.md must document LLHookEvent as the handler input type"
        )

    def test_guide_mentions_llhookresult(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "LLHookResult" in content, (
            "write-a-hook.md must document LLHookResult as the handler return type"
        )

    def test_guide_mentions_llhookintentextension(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "LLHookIntentExtension" in content, (
            "write-a-hook.md must reference the LLHookIntentExtension Protocol"
        )

    def test_guide_mentions_provided_hook_intents(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "provided_hook_intents" in content, (
            "write-a-hook.md must describe the provided_hook_intents extension method"
        )

    def test_guide_cross_references_ll_create_extension(self) -> None:
        content = WRITE_A_HOOK.read_text()
        assert "ll-create-extension" in content, (
            "write-a-hook.md must cross-reference the ll-create-extension scaffolding CLI"
        )


class TestAutomateHooksWiring:
    """docs/claude-code/automate-workflows-with-hooks.md must include the little-loops adapter-flow diagram."""

    def test_automate_hooks_has_adapter_diagram(self) -> None:
        content = AUTOMATE_HOOKS.read_text()
        assert "flowchart LR" in content, (
            "automate-workflows-with-hooks.md must include a mermaid flowchart LR block "
            "showing the host event → adapter → python dispatcher → handler → result flow"
        )

    def test_automate_hooks_links_to_write_a_hook(self) -> None:
        content = AUTOMATE_HOOKS.read_text()
        assert "write-a-hook.md" in content, (
            "automate-workflows-with-hooks.md must cross-link to the authoring guide"
        )


class TestMkdocsNavWiring:
    """mkdocs.yml nav must expose the Claude Code authoring docs."""

    def test_nav_has_claude_code_group(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "Claude Code:" in content, (
            "mkdocs.yml nav must declare a 'Claude Code:' group for the claude-code/ docs"
        )

    def test_nav_lists_write_a_hook(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "claude-code/write-a-hook.md" in content, (
            "mkdocs.yml nav must include claude-code/write-a-hook.md so the authoring "
            "guide is discoverable from the site nav"
        )

    def test_nav_lists_hooks_reference(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "claude-code/hooks-reference.md" in content, (
            "mkdocs.yml nav must include claude-code/hooks-reference.md"
        )

    def test_nav_lists_automate_workflows_with_hooks(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "claude-code/automate-workflows-with-hooks.md" in content, (
            "mkdocs.yml nav must include claude-code/automate-workflows-with-hooks.md"
        )


class TestIndexMdWiring:
    """docs/index.md must surface the write-a-hook guide and mention hook intent types."""

    def test_index_links_to_write_a_hook(self) -> None:
        content = INDEX_MD.read_text()
        assert "claude-code/write-a-hook.md" in content, (
            "docs/index.md must link to claude-code/write-a-hook.md so the authoring "
            "guide is discoverable from the documentation index"
        )

    def test_event_schema_entry_mentions_hook_intent_types(self) -> None:
        content = INDEX_MD.read_text()
        # The EVENT-SCHEMA entry was broadened to mention hook intent types now that
        # FEAT-1459 added LLHookEvent / LLHookResult coverage to that reference doc.
        event_schema_line = next(
            (line for line in content.splitlines() if "EVENT-SCHEMA.md" in line),
            None,
        )
        assert event_schema_line is not None, (
            "docs/index.md must contain an EVENT-SCHEMA.md entry"
        )
        assert "LLHookEvent" in event_schema_line or "LLHookResult" in event_schema_line, (
            "docs/index.md EVENT-SCHEMA.md description must mention LLHookEvent or "
            "LLHookResult now that the reference doc covers hook intent types"
        )
