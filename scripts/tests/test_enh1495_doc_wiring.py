"""Doc-wiring tests for ENH-1495: Add docs/codex/ user-facing onboarding walkthrough.

Asserts that all three new docs/codex/ files exist, that navigation and index files
reference them, and that HOST_COMPATIBILITY.md cross-links to the new user docs.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

CODEX_README = PROJECT_ROOT / "docs" / "codex" / "README.md"
CODEX_GETTING_STARTED = PROJECT_ROOT / "docs" / "codex" / "getting-started.md"
CODEX_USAGE = PROJECT_ROOT / "docs" / "codex" / "usage.md"
HOST_COMPAT = PROJECT_ROOT / "docs" / "reference" / "HOST_COMPATIBILITY.md"
README = PROJECT_ROOT / "README.md"
MKDOCS_YML = PROJECT_ROOT / "mkdocs.yml"
INDEX_MD = PROJECT_ROOT / "docs" / "index.md"
CONTRIBUTING = PROJECT_ROOT / "CONTRIBUTING.md"


class TestCodexDocsExist:
    """All three docs/codex/ files must exist."""

    def test_codex_readme_exists(self) -> None:
        assert CODEX_README.exists(), "docs/codex/README.md must exist (ENH-1495)"

    def test_codex_getting_started_exists(self) -> None:
        assert CODEX_GETTING_STARTED.exists(), "docs/codex/getting-started.md must exist (ENH-1495)"

    def test_codex_usage_exists(self) -> None:
        assert CODEX_USAGE.exists(), "docs/codex/usage.md must exist (ENH-1495)"


class TestCodexReadmeContent:
    """docs/codex/README.md must cover the expected landing-page topics."""

    def test_mentions_hook_intents(self) -> None:
        content = CODEX_README.read_text()
        assert "session_start" in content, (
            "docs/codex/README.md must document the session_start hook intent"
        )

    def test_mentions_orchestration_clis(self) -> None:
        content = CODEX_README.read_text()
        assert "ll-auto" in content or "ll-parallel" in content, (
            "docs/codex/README.md must mention orchestration CLIs (ll-auto or ll-parallel)"
        )

    def test_mentions_skill_discovery(self) -> None:
        content = CODEX_README.read_text()
        assert "ll-adapt-skills-for-codex" in content, (
            "docs/codex/README.md must mention ll-adapt-skills-for-codex for skill discovery"
        )

    def test_links_to_getting_started(self) -> None:
        content = CODEX_README.read_text()
        assert "getting-started" in content, (
            "docs/codex/README.md must link to getting-started.md"
        )

    def test_links_to_usage(self) -> None:
        content = CODEX_README.read_text()
        assert "usage" in content, "docs/codex/README.md must link to usage.md"

    def test_mentions_deferred_intents(self) -> None:
        content = CODEX_README.read_text()
        assert "deferred" in content, (
            "docs/codex/README.md must mention deferred hook intents"
        )


class TestCodexGettingStartedContent:
    """docs/codex/getting-started.md must cover install, trust, config, and skill discovery."""

    def test_mentions_init_codex(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert "--codex" in content, (
            "docs/codex/getting-started.md must document the /ll:init --codex install step"
        )

    def test_mentions_trust_prompt(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert "trust" in content.lower(), (
            "docs/codex/getting-started.md must cover the Codex hook-trust prompt"
        )

    def test_mentions_trust_all(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert "Trust All" in content, (
            "docs/codex/getting-started.md must describe the 'Trust All and Continue' dialog option"
        )

    def test_mentions_config_file(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert ".codex/ll-config.json" in content, (
            "docs/codex/getting-started.md must document .codex/ll-config.json config probe"
        )

    def test_mentions_skill_discovery(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert "ll-adapt-skills-for-codex" in content, (
            "docs/codex/getting-started.md must document ll-adapt-skills-for-codex --apply"
        )

    def test_mentions_codex_hooks_json(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert ".codex/hooks.json" in content, (
            "docs/codex/getting-started.md must reference .codex/hooks.json"
        )

    def test_trust_key_format_present(self) -> None:
        content = CODEX_GETTING_STARTED.read_text()
        assert "session_start:0:0" in content, (
            "docs/codex/getting-started.md must show the trust key format with :0:0 suffix"
        )


class TestCodexUsageContent:
    """docs/codex/usage.md must cover orchestration, skills, opt-in pre_tool_use, and limitations."""

    def test_mentions_ll_host_cli(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "LL_HOST_CLI=codex" in content, (
            "docs/codex/usage.md must show LL_HOST_CLI=codex usage"
        )

    def test_mentions_pre_tool_use_opt_in(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "pre_tool_use" in content or "PreToolUse" in content, (
            "docs/codex/usage.md must document the opt-in pre_tool_use configuration"
        )

    def test_mentions_current_limitations(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "Current Limitations" in content or "Limitations" in content, (
            "docs/codex/usage.md must have a Current Limitations section"
        )

    def test_mentions_agent_flag_limitation(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "--agent" in content, (
            "docs/codex/usage.md must document the --agent flag limitation"
        )

    def test_mentions_capability_not_supported(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "CapabilityNotSupported" in content, (
            "docs/codex/usage.md must mention CapabilityNotSupported for unsupported flags"
        )

    def test_mentions_ll_auto(self) -> None:
        content = CODEX_USAGE.read_text()
        assert "ll-auto" in content, (
            "docs/codex/usage.md must show ll-auto as an orchestration CLI example"
        )


class TestHostCompatibilityWiring:
    """HOST_COMPATIBILITY.md must cross-link to the new Codex user docs."""

    def test_references_codex_readme(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "codex/README" in content or "docs/codex" in content, (
            "HOST_COMPATIBILITY.md must cross-link to docs/codex/ user docs"
        )

    def test_references_getting_started(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "getting-started" in content, (
            "HOST_COMPATIBILITY.md must cross-link to docs/codex/getting-started.md"
        )


class TestReadmeCodexReference:
    """README.md must reference Codex CLI install path."""

    def test_readme_mentions_codex(self) -> None:
        content = README.read_text()
        assert "codex" in content.lower(), (
            "README.md must mention Codex CLI in the install section"
        )

    def test_readme_links_to_codex_getting_started(self) -> None:
        content = README.read_text()
        assert "docs/codex/getting-started.md" in content or "docs/codex/" in content, (
            "README.md must link to docs/codex/ getting-started"
        )


class TestMkdocsNavWiring:
    """mkdocs.yml nav must include a Codex CLI group with all three pages."""

    def test_nav_has_codex_group(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "Codex CLI:" in content or "Codex:" in content, (
            "mkdocs.yml nav must declare a Codex CLI group for the codex/ docs"
        )

    def test_nav_lists_codex_readme(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "codex/README.md" in content, (
            "mkdocs.yml nav must include codex/README.md"
        )

    def test_nav_lists_codex_getting_started(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "codex/getting-started.md" in content, (
            "mkdocs.yml nav must include codex/getting-started.md"
        )

    def test_nav_lists_codex_usage(self) -> None:
        content = MKDOCS_YML.read_text()
        assert "codex/usage.md" in content, (
            "mkdocs.yml nav must include codex/usage.md"
        )


class TestIndexMdWiring:
    """docs/index.md must reference the Codex CLI docs in the User Documentation section."""

    def test_index_links_to_codex_readme(self) -> None:
        content = INDEX_MD.read_text()
        assert "codex/README.md" in content or "codex/" in content, (
            "docs/index.md must link to the codex/ user docs in the User Documentation section"
        )

    def test_index_links_to_codex_getting_started(self) -> None:
        content = INDEX_MD.read_text()
        assert "codex/getting-started.md" in content, (
            "docs/index.md must link to codex/getting-started.md"
        )

    def test_index_links_to_codex_usage(self) -> None:
        content = INDEX_MD.read_text()
        assert "codex/usage.md" in content, (
            "docs/index.md must link to codex/usage.md"
        )


class TestContributingWiring:
    """CONTRIBUTING.md project structure tree must include docs/codex/."""

    def test_project_tree_mentions_codex_dir(self) -> None:
        content = CONTRIBUTING.read_text()
        assert "codex/" in content, (
            "CONTRIBUTING.md project structure tree must include a docs/codex/ entry"
        )
