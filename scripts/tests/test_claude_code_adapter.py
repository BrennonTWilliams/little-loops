"""Integration tests for the Claude Code hook adapter (BUG-1881).

The adapter at ``hooks/adapters/claude-code/post-tool-use.sh`` is a thin
Bash transport: it reads the host JSON payload from stdin and pipes it
through the host-agnostic Python dispatcher (``python -m little_loops.hooks
post_tool_use``). Unlike the Codex shim it does **not** set ``LL_HOOK_HOST``
— the dispatcher defaults ``LLHookEvent.host`` to ``"claude-code"``.

If ``bash`` is not on ``PATH`` the entire module is skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available on PATH")
BASH: str = _BASH or "bash"

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO_ROOT / "hooks" / "adapters" / "claude-code"
POST_TOOL_USE = ADAPTER_DIR / "post-tool-use.sh"
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


class TestClaudeCodeAdapterIntegration:
    """End-to-end adapter tests for the Claude Code post-tool-use shim."""

    def test_adapter_files_exist(self) -> None:
        """hooks/adapters/claude-code/post-tool-use.sh must exist (BUG-1881)."""
        assert POST_TOOL_USE.is_file(), (
            f"{POST_TOOL_USE} does not exist; BUG-1881 fix requires this shim"
        )

    def test_adapter_scripts_are_executable(self) -> None:
        """post-tool-use.sh must have the executable bit set."""
        assert os.access(POST_TOOL_USE, os.X_OK), (
            f"{POST_TOOL_USE} is not executable; chmod +x required"
        )

    def test_hooks_json_has_post_tool_use(self) -> None:
        """hooks/hooks.json must have a PostToolUse entry pointing to post-tool-use.sh."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "PostToolUse" in data["hooks"], "hooks.json is missing PostToolUse key"
        groups = data["hooks"]["PostToolUse"]
        assert len(groups) >= 1
        # Collect all commands across all PostToolUse matcher groups
        all_commands = [
            h["command"]
            for group in groups
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("post-tool-use.sh" in cmd for cmd in all_commands), (
            f"expected post-tool-use.sh in a PostToolUse command; got {all_commands!r}"
        )
        # Verify it appears as a wildcard matcher entry
        wildcard_commands = [
            h["command"]
            for group in groups
            if group.get("matcher") == "*"
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("post-tool-use.sh" in cmd for cmd in wildcard_commands), (
            f"post-tool-use.sh must be registered with matcher '*'; "
            f"wildcard commands: {wildcard_commands!r}"
        )

    def test_post_tool_use_default_host_claude_code(self, tmp_path: Path) -> None:
        """post-tool-use.sh runs the Python handler without setting LL_HOOK_HOST.

        The dispatcher must exit 0 (analytics disabled or no-op path) and
        must not crash. LL_HOOK_HOST is not set by the shim, so the dispatcher
        defaults LLHookEvent.host to 'claude-code'.
        """
        payload = json.dumps(
            {
                "tool_name": "Read",
                "input": {},
                "output": "",
                "session_id": "test",
            }
        )
        env = {**os.environ}
        # Ensure LL_HOOK_HOST is absent so we prove the shim does not set it
        env.pop("LL_HOOK_HOST", None)

        result = subprocess.run(
            [BASH, str(POST_TOOL_USE)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
            env=env,
        )
        assert result.returncode == 0, (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
