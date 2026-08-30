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

    def test_hooks_json_registers_drift_check_under_session_start(self) -> None:
        """The doc-drift check (drift-check.sh) must be registered under SessionStart (ENH-2888)."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in data["hooks"], "hooks.json is missing SessionStart key"
        ss_cmds = [
            h["command"]
            for group in data["hooks"]["SessionStart"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("drift-check.sh" in cmd for cmd in ss_cmds), (
            f"expected drift-check.sh in a SessionStart command; got {ss_cmds!r}"
        )

    def test_hooks_json_registers_scratch_cleanup_under_session_start(self) -> None:
        """scratch-cleanup.sh (BUG-2420) must be registered under SessionStart.

        BUG-3363: SessionEnd hooks are killed under a hard ~1.5s ceiling on
        any exit path (Ctrl+C, Ctrl+D, /exit), regardless of configured
        ``timeout`` (anthropics/claude-code#32712, #41577) — the same
        upstream bug test_hooks_json_registers_sweep_under_session_start
        documents for session-end.sh. scratch-cleanup.sh's own runtime
        (~0.07s) is nowhere near that ceiling, but it was still being
        intermittently cancelled — consistent with the ceiling depending on
        exit-path teardown timing, not purely the hook's own cost. Re-homed
        to SessionStart, mirroring session-end.sh's BUG-2483 fix.
        """
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionStart" in data["hooks"], "hooks.json is missing SessionStart key"
        ss_cmds = [
            h["command"]
            for group in data["hooks"]["SessionStart"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("scratch-cleanup.sh" in cmd for cmd in ss_cmds), (
            f"expected scratch-cleanup.sh in a SessionStart command; got {ss_cmds!r}"
        )

    def test_hooks_json_has_no_session_end_key(self) -> None:
        """SessionEnd must have zero registered hooks after BUG-3363.

        Both prior SessionEnd handlers (session-end.sh, re-homed by
        BUG-2483; scratch-cleanup.sh, re-homed by BUG-3363) now live under
        SessionStart. Per BUG-3363's wiring decision the SessionEnd key is
        dropped entirely rather than left as an empty array — an absent key
        also trivially covers the two prior regression checks this test
        replaces (session-end.sh absence, orphan-worker-sweep.sh absence;
        the latter guards a local-only hook documented at
        .claude/plans/make-it-a-local-only-groovy-stallman.md that must
        never ship via hooks/hooks.json).
        """
        data = json.loads(HOOKS_JSON.read_text())
        assert "SessionEnd" not in data["hooks"], (
            f"hooks.json must not have a SessionEnd key; got "
            f"{data['hooks'].get('SessionEnd')!r}"
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

    def test_stop_adapter_exists_and_executable(self) -> None:
        """hooks/adapters/claude-code/stop.sh must exist and be executable (FEAT-3118)."""
        adapter = ADAPTER_DIR / "stop.sh"
        assert adapter.is_file(), f"{adapter} does not exist"
        assert os.access(adapter, os.X_OK), f"{adapter} is not executable"

    def test_hooks_json_has_pre_done_stop_entry(self) -> None:
        """hooks/hooks.json must have a Stop entry pointing to stop.sh (FEAT-3118)."""
        data = json.loads(HOOKS_JSON.read_text())
        assert "Stop" in data["hooks"], "hooks.json is missing Stop key"
        cmds = [
            h["command"]
            for group in data["hooks"]["Stop"]
            for h in group.get("hooks", [])
            if h.get("type") == "command"
        ]
        assert any("stop.sh" in cmd for cmd in cmds), (
            f"expected stop.sh in a Stop command; got {cmds!r}"
        )

    def test_hooks_json_pre_done_timeout_covers_advisor_default(self) -> None:
        """The Stop/stop.sh timeout must be >= AdvisorConfig().timeout_seconds' default.

        A killed hook has already spent budget (record_consult reserves before the
        host call), so this coupling must not drift silently (FEAT-3118 AC #8).
        """
        from little_loops.config.orchestration import AdvisorConfig

        data = json.loads(HOOKS_JSON.read_text())
        entry = next(
            group
            for group in data["hooks"]["Stop"]
            for h in group.get("hooks", [])
            if h.get("type") == "command" and "stop.sh" in h["command"]
        )
        timeout = entry["hooks"][0]["timeout"]
        assert timeout >= AdvisorConfig().timeout_seconds, (
            f"Stop/stop.sh timeout ({timeout}) must be >= "
            f"AdvisorConfig().timeout_seconds ({AdvisorConfig().timeout_seconds})"
        )

    def test_stop_adapter_round_trip(self, tmp_path: Path) -> None:
        """stop.sh pipes stdin through the Python dispatcher and exits 0 outside a git repo."""
        adapter = ADAPTER_DIR / "stop.sh"
        payload = json.dumps({"session_id": "session-1", "hook_event_name": "Stop"})
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
