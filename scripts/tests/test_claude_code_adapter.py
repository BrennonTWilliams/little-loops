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

    def test_hooks_json_has_precompact_handoff(self) -> None:
        """hooks/hooks.json must have a second PreCompact entry pointing to precompact-handoff.sh."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "PreCompact" in data["hooks"], "hooks.json is missing PreCompact key"
        groups = data["hooks"]["PreCompact"]
        assert len(groups) >= 2, f"Expected ≥2 PreCompact groups, got {len(groups)}"
        all_commands = [
            h["command"]
            for group in groups
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("precompact-handoff.sh" in cmd for cmd in all_commands), (
            f"expected precompact-handoff.sh in a PreCompact command; got {all_commands!r}"
        )

    def test_hooks_json_registers_sweep_under_session_start(self) -> None:
        """The stale-ref sweep (session-end.sh) must be registered under SessionStart.

        Claude Code enforces a hard ~1.5s ceiling on SessionEnd hooks before
        killing them on any exit path (Ctrl+C, Ctrl+D, /exit), regardless of the
        configured ``timeout`` — a confirmed, unfixed upstream bug
        (anthropics/claude-code#32712, #41577). The sweep's full-tree issue scan
        exceeds that ceiling on repos with a few thousand issue files, so it was
        being killed (and printing "Hook cancelled") on nearly every exit. Re-homed
        to SessionStart — it now runs once at the start of the *next* session
        instead of racing session teardown, with the same detection value.
        """
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in data["hooks"], "hooks.json is missing SessionStart key"
        ss_cmds = [
            h["command"]
            for group in data["hooks"]["SessionStart"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("session-end.sh" in cmd for cmd in ss_cmds), (
            f"expected session-end.sh in a SessionStart command; got {ss_cmds!r}"
        )

    def test_hooks_json_session_end_no_longer_references_sweep(self) -> None:
        """The SessionEnd array must no longer reference session-end.sh (regression).

        After re-homing to SessionStart, the sweep must not race session
        teardown. The other SessionEnd handler (scratch-cleanup.sh) remains
        untouched.
        """
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionEnd" in data["hooks"], "hooks.json is missing SessionEnd key"
        se_cmds = [
            h["command"]
            for group in data["hooks"]["SessionEnd"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert not any("session-end.sh" in cmd for cmd in se_cmds), (
            f"session-end.sh must be removed from the SessionEnd array; got {se_cmds!r}"
        )

    def test_hooks_json_session_end_no_longer_references_orphan_worker_sweep(self) -> None:
        """The SessionEnd array must no longer reference orphan-worker-sweep.sh.

        The orphan xdist sweep is a local-only hook (registered in
        .claude/settings.local.json, gitignored) — it is NOT a built-in plugin
        hook and must not ship via hooks/hooks.json. See the design discussion
        recorded at .claude/plans/make-it-a-local-only-groovy-stallman.md.
        """
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionEnd" in data["hooks"], "hooks.json is missing SessionEnd key"
        se_cmds = [
            h["command"]
            for group in data["hooks"]["SessionEnd"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert not any("orphan-worker-sweep" in cmd for cmd in se_cmds), (
            f"orphan-worker-sweep.sh must not be in SessionEnd (it is a "
            f"local-only hook, not a built-in); got {se_cmds!r}"
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

    def test_subagent_start_adapter_exists_and_executable(self) -> None:
        """hooks/adapters/claude-code/subagent-start.sh must exist and be executable (ENH-2505)."""
        adapter = ADAPTER_DIR / "subagent-start.sh"
        assert adapter.is_file(), f"{adapter} does not exist"
        assert os.access(adapter, os.X_OK), f"{adapter} is not executable"

    def test_subagent_stop_adapter_exists_and_executable(self) -> None:
        """hooks/adapters/claude-code/subagent-stop.sh must exist and be executable (ENH-2505)."""
        adapter = ADAPTER_DIR / "subagent-stop.sh"
        assert adapter.is_file(), f"{adapter} does not exist"
        assert os.access(adapter, os.X_OK), f"{adapter} is not executable"

    def test_hooks_json_has_subagent_start(self) -> None:
        """hooks/hooks.json must have a SubagentStart entry pointing to subagent-start.sh."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "SubagentStart" in data["hooks"], "hooks.json is missing SubagentStart key"
        cmds = [
            h["command"]
            for group in data["hooks"]["SubagentStart"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("subagent-start.sh" in cmd for cmd in cmds), (
            f"expected subagent-start.sh in a SubagentStart command; got {cmds!r}"
        )

    def test_hooks_json_has_subagent_stop(self) -> None:
        """hooks/hooks.json must have a SubagentStop entry pointing to subagent-stop.sh."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "SubagentStop" in data["hooks"], "hooks.json is missing SubagentStop key"
        cmds = [
            h["command"]
            for group in data["hooks"]["SubagentStop"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("subagent-stop.sh" in cmd for cmd in cmds), (
            f"expected subagent-stop.sh in a SubagentStop command; got {cmds!r}"
        )

    def test_subagent_start_adapter_round_trip(self, tmp_path: Path) -> None:
        """subagent-start.sh pipes stdin through the Python dispatcher and exits 0."""
        adapter = ADAPTER_DIR / "subagent-start.sh"
        payload = json.dumps(
            {
                "session_id": "parent-1",
                "agent_id": "agent-abc",
                "agent_type": "Explore",
                "hook_event_name": "SubagentStart",
            }
        )
        result = subprocess.run(
            [BASH, str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )

    def test_subagent_stop_adapter_round_trip(self, tmp_path: Path) -> None:
        """subagent-stop.sh pipes stdin through the Python dispatcher and exits 0."""
        adapter = ADAPTER_DIR / "subagent-stop.sh"
        payload = json.dumps(
            {
                "session_id": "parent-1",
                "agent_id": "agent-abc",
                "agent_type": "Explore",
                "agent_transcript_path": "/tmp/parent-1/subagents/agent-abc.jsonl",
                "hook_event_name": "SubagentStop",
            }
        )
        result = subprocess.run(
            [BASH, str(adapter)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
