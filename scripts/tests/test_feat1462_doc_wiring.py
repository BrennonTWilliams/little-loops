"""Tests for FEAT-1462: Host CLI abstraction doc sweep.

Verifies that the reference documentation surfaces (API.md, ARCHITECTURE.md,
HOST_COMPATIBILITY.md, TROUBLESHOOTING.md, .claude/CLAUDE.md) cover the
``host_runner`` abstraction layer per the acceptance criteria enumerated in
FEAT-1462 (split out as FEAT-1473).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

API_DOC = PROJECT_ROOT / "docs" / "reference" / "API.md"
ARCHITECTURE = PROJECT_ROOT / "docs" / "ARCHITECTURE.md"
HOST_COMPAT = PROJECT_ROOT / "docs" / "reference" / "HOST_COMPATIBILITY.md"
TROUBLESHOOTING = PROJECT_ROOT / "docs" / "development" / "TROUBLESHOOTING.md"
CLAUDE_MD = PROJECT_ROOT / ".claude" / "CLAUDE.md"


class TestApiMdWiring:
    """API.md must document the host_runner public surface."""

    def test_host_runner_module_listed(self) -> None:
        content = API_DOC.read_text()
        assert "host_runner" in content, "API.md must reference the little_loops.host_runner module"

    def test_resolve_host_documented(self) -> None:
        content = API_DOC.read_text()
        assert "resolve_host" in content, (
            "API.md must document the resolve_host() discovery entry point"
        )

    def test_host_invocation_documented(self) -> None:
        content = API_DOC.read_text()
        assert "HostInvocation" in content, "API.md must document the HostInvocation dataclass"

    def test_host_not_configured_documented(self) -> None:
        content = API_DOC.read_text()
        assert "HostNotConfigured" in content, (
            "API.md must document the HostNotConfigured exception"
        )

    def test_capability_not_supported_documented(self) -> None:
        content = API_DOC.read_text()
        assert "CapabilityNotSupported" in content, (
            "API.md must document the CapabilityNotSupported warning"
        )

    def test_capability_report_documented(self) -> None:
        content = API_DOC.read_text()
        assert "CapabilityReport" in content, "API.md must document the CapabilityReport dataclass"

    def test_capability_entry_documented(self) -> None:
        content = API_DOC.read_text()
        assert "CapabilityEntry" in content, "API.md must document the CapabilityEntry dataclass"

    def test_hook_entry_documented(self) -> None:
        content = API_DOC.read_text()
        assert "HookEntry" in content, "API.md must document the HookEntry dataclass"

    def test_describe_capabilities_documented(self) -> None:
        content = API_DOC.read_text()
        assert "describe_capabilities" in content, (
            "API.md must document the describe_capabilities() Protocol method"
        )


class TestArchitectureMdWiring:
    """ARCHITECTURE.md must include host_runner in the layering diagram."""

    def test_host_runner_in_layering(self) -> None:
        content = ARCHITECTURE.read_text()
        assert "host_runner" in content, (
            "ARCHITECTURE.md must reference host_runner in the layering description"
        )


class TestHostCompatibilityWiring:
    """HOST_COMPATIBILITY.md must have an orchestration row with all four hosts."""

    def test_orchestration_row_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "Orchestration" in content, (
            "HOST_COMPATIBILITY.md must include the Orchestration CLI section"
        )

    def test_pi_column_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "Pi" in content, (
            "HOST_COMPATIBILITY.md must include a Pi column in the orchestration table"
        )

    def test_codex_skills_path_present(self) -> None:
        content = HOST_COMPAT.read_text()
        assert "codex/skills" in content, (
            "HOST_COMPATIBILITY.md must reference ~/.codex/skills/ after FEAT-1483 research "
            "(replaces the now-invalid .codex/prompts/ reference)"
        )


class TestTroubleshootingWiring:
    """TROUBLESHOOTING.md must have a HostNotConfigured entry."""

    def test_host_not_configured_entry(self) -> None:
        content = TROUBLESHOOTING.read_text()
        assert "HostNotConfigured" in content, (
            "TROUBLESHOOTING.md must include a HostNotConfigured entry"
        )

    def test_ll_host_cli_remediation(self) -> None:
        content = TROUBLESHOOTING.read_text()
        assert "LL_HOST_CLI" in content, (
            "TROUBLESHOOTING.md HostNotConfigured entry must mention LL_HOST_CLI remediation"
        )


class TestClaudeMdWiring:
    """CLAUDE.md must reference host_runner or LL_HOST_CLI."""

    def test_host_runner_note_present(self) -> None:
        content = CLAUDE_MD.read_text()
        assert "host_runner" in content or "LL_HOST_CLI" in content, (
            "CLAUDE.md must direct contributors to route host-CLI calls through "
            "resolve_host() / LL_HOST_CLI"
        )
