"""Integration tests for the Codex CLI hook adapter (FEAT-957).

The adapter at ``hooks/adapters/codex/{session-start,pre-compact}.sh`` is a
thin Bash transport: each script reads the host JSON payload from stdin,
exports ``LL_HOOK_HOST=codex`` on the subprocess environment, and pipes the
payload to ``python -m little_loops.hooks <intent>``. These tests exercise
the adapter end-to-end via ``bash``, asserting the same observable
Python-side effects that ``TestHooksMainModule`` asserts for the Claude
Code path (config JSON / state file written under ``cwd``), plus the
Codex-specific contract that the adapter sets ``LL_HOOK_HOST=codex``.

If ``bash`` is not on ``PATH`` the entire module is skipped — should be
rare on macOS / Linux CI, but the guard keeps Windows-without-WSL green.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available on PATH")
BASH: str = _BASH or "bash"

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO_ROOT / "hooks" / "adapters" / "codex"
SESSION_START = ADAPTER_DIR / "session-start.sh"
PRE_COMPACT = ADAPTER_DIR / "pre-compact.sh"


class TestCodexAdapterIntegration:
    """End-to-end adapter tests via bash + the real Python dispatcher."""

    def test_adapter_files_exist(self) -> None:
        """The adapter directory ships session-start.sh, pre-compact.sh, hooks.json, README.md."""
        assert SESSION_START.is_file()
        assert PRE_COMPACT.is_file()
        assert (ADAPTER_DIR / "hooks.json").is_file()
        assert (ADAPTER_DIR / "README.md").is_file()

    def test_adapter_scripts_are_executable(self) -> None:
        """Bash adapter scripts must be marked executable so Codex can `bash` them."""
        assert os.access(SESSION_START, os.X_OK), (
            f"{SESSION_START} is not executable; chmod +x required"
        )
        assert os.access(PRE_COMPACT, os.X_OK), (
            f"{PRE_COMPACT} is not executable; chmod +x required"
        )

    def test_hooks_json_uses_matcher_startup(self) -> None:
        """SessionStart MatcherGroup must restrict to ``"matcher": "startup"`` per FEAT-957 policy.

        Firing on ``resume`` or ``clear`` would re-emit identifiers for an
        already-running session; restricting to ``startup`` matches the
        semantics the Claude Code adapter already relies on.
        """
        data = json.loads((ADAPTER_DIR / "hooks.json").read_text())
        session_start_groups = data["hooks"]["SessionStart"]
        assert len(session_start_groups) >= 1
        assert session_start_groups[0]["matcher"] == "startup"

    def test_hooks_json_references_plugin_root_placeholder(self) -> None:
        """Template must use ``{{LL_PLUGIN_ROOT}}`` for ``ll:init --codex`` to substitute at install time."""
        raw = (ADAPTER_DIR / "hooks.json").read_text()
        assert "{{LL_PLUGIN_ROOT}}" in raw, (
            "hooks.json template must reference {{LL_PLUGIN_ROOT}} so the "
            "absolute plugin path is filled in at install time"
        )

    def test_pre_compact_writes_state_file(self, tmp_path: Path) -> None:
        """pre-compact.sh → pre_compact handler writes .ll/ll-precompact-state.json in cwd."""
        payload = {
            "hook_event_name": "PreCompact",
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "model": "gpt-4o",
            "trigger": "manual",
            "transcript_path": str(tmp_path / "fake-transcript.jsonl"),
        }
        result = subprocess.run(
            [BASH, str(PRE_COMPACT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        # pre_compact's success path is exit_code in {0, 2} with stderr feedback;
        # both indicate the handler ran. The adapter passes the Python exit code
        # through verbatim — both are acceptable here.
        assert result.returncode in (0, 2), (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        assert state_file.is_file(), (
            f"expected {state_file} written by pre_compact handler; stderr={result.stderr!r}"
        )

    def test_session_start_runs_without_config(self, tmp_path: Path) -> None:
        """session-start.sh runs the handler; no config in tmp → "No config found" on stderr."""
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "model": "gpt-4o",
            "source": "startup",
            "transcript_path": str(tmp_path / "fake-transcript.jsonl"),
        }
        result = subprocess.run(
            [BASH, str(SESSION_START)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0, (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert "No config found" in result.stderr

    def test_adapter_sets_ll_hook_host_codex(self, tmp_path: Path) -> None:
        """The Python subprocess sees ``LL_HOOK_HOST=codex``.

        Asserts the contract by stubbing the dispatcher: write a fake
        ``little_loops/hooks/__main__.py`` shim on ``PYTHONPATH`` that
        records the env var into a sentinel file, then run the adapter and
        inspect the sentinel. Isolates env-var propagation from the real
        handler logic (which we already cover separately).
        """
        fake_pkg = tmp_path / "fake_pkg"
        ll_dir = fake_pkg / "little_loops" / "hooks"
        ll_dir.mkdir(parents=True)
        (fake_pkg / "little_loops" / "__init__.py").write_text("")
        (ll_dir / "__init__.py").write_text("")
        sentinel = tmp_path / "sentinel.txt"
        (ll_dir / "__main__.py").write_text(
            textwrap.dedent(
                f"""
                import os, sys
                with open({str(sentinel)!r}, "w") as f:
                    f.write(os.environ.get("LL_HOOK_HOST", "<unset>"))
                sys.exit(0)
                """
            ).strip()
        )

        env_passthrough = {"PYTHONPATH": str(fake_pkg)}
        full_env = {**os.environ, **env_passthrough}
        # Wipe any inherited LL_HOOK_HOST so we're sure the adapter sets it.
        full_env.pop("LL_HOOK_HOST", None)

        result = subprocess.run(
            [BASH, str(SESSION_START)],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
            env=full_env,
        )
        assert result.returncode == 0, (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert sentinel.is_file(), (
            f"sentinel not written; PYTHONPATH may not have routed to fake "
            f"module. stderr={result.stderr!r}"
        )
        assert sentinel.read_text() == "codex"
