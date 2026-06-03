"""Doc-wiring regression tests for BUG-1890: init host guard for Codex auto-detection.

Asserts that skills/init/SKILL.md's Codex auto-detect block reads LL_HOST_CLI /
LL_HOOK_HOST before probing for the codex binary, so Claude Code sessions are
not silently given Codex artifacts.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

INIT_SKILL = PROJECT_ROOT / "skills" / "init" / "SKILL.md"


class TestBug1890InitHostGuard:
    """skills/init/SKILL.md must guard the Codex auto-detect block by active host."""

    def test_ll_host_cli_in_autodetect(self) -> None:
        content = INIT_SKILL.read_text()
        assert "LL_HOST_CLI" in content, (
            "skills/init/SKILL.md must check LL_HOST_CLI in the Codex auto-detect "
            "block so Claude Code sessions are not given Codex artifacts"
        )

    def test_ll_hook_host_in_autodetect(self) -> None:
        content = INIT_SKILL.read_text()
        assert "LL_HOOK_HOST" in content, (
            "skills/init/SKILL.md must check LL_HOOK_HOST as fallback in the Codex "
            "auto-detect block (mirrors resolve_host() priority order)"
        )

    def test_claude_code_guard_in_autodetect(self) -> None:
        content = INIT_SKILL.read_text()
        assert "claude-code" in content, (
            "skills/init/SKILL.md must guard against 'claude-code' host in the Codex "
            "auto-detect block so the binary probe is skipped on Claude Code"
        )
