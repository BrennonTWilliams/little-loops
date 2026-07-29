"""Integration tests for the Kimi Code hook adapter (FEAT-2915, EPIC-2910).

The adapter at ``scripts/little_loops/hooks/adapters/kimi/*.sh`` is a thin
Bash transport: each script reads the host JSON payload from stdin, exports
``LL_HOOK_HOST=kimi-code`` on the subprocess environment, and pipes the
payload to ``python -m little_loops.hooks <intent>``. These tests assert the
sentinel files exist, the shims carry the host export + intent names, the
``hooks.toml`` install template carries the ``{{LL_PLUGIN_ROOT}}`` /
``{{LL_GEN_VERSION}}`` placeholders, and the adapter works end-to-end via
``bash`` with kimi-shaped payloads (verified shapes from
``thoughts/research/kimi-cli-surface.md``, kimi 0.30.0).

If ``bash`` is not on ``PATH`` the entire module is skipped — should be
rare on macOS / Linux CI, but the guard keeps Windows-without-WSL green.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
import tomllib
from pathlib import Path

import pytest

_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available on PATH")
BASH: str = _BASH or "bash"

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO_ROOT / "scripts" / "little_loops" / "hooks" / "adapters" / "kimi"
HOOKS_TOML = ADAPTER_DIR / "hooks.toml"

# Kimi event name → (shim filename, ll intent)
EXPECTED_SHIMS: dict[str, tuple[str, str]] = {
    "SessionStart": ("session-start.sh", "session_start"),
    "PreCompact": ("pre-compact.sh", "pre_compact"),
    "UserPromptSubmit": ("user-prompt-submit.sh", "user_prompt_submit"),
    "PreToolUse": ("pre-tool-use.sh", "pre_tool_use"),
    "PostToolUse": ("post-tool-use.sh", "post_tool_use"),
    "SessionEnd": ("session-end.sh", "session_end"),
    "SubagentStart": ("subagent-start.sh", "subagent_start"),
    "SubagentStop": ("subagent-stop.sh", "subagent_stop"),
}


def _rendered_hooks_toml() -> dict:
    """Return the hooks.toml template with install-time substitutions applied."""
    raw = HOOKS_TOML.read_text(encoding="utf-8")
    rendered = raw.replace("{{LL_PLUGIN_ROOT}}", "/tmp/pkg").replace(
        "{{LL_GEN_VERSION}}", "0.0.0-test"
    )
    return tomllib.loads(rendered)


class TestKimiAdapterSentinels:
    """Sentinel-file and template-content assertions (no subprocess)."""

    def test_adapter_files_exist(self) -> None:
        """The package ships all eight shims + hooks.toml; README.md stays at repo-root hooks/adapters/kimi/."""
        for shim, _intent in EXPECTED_SHIMS.values():
            assert (ADAPTER_DIR / shim).is_file(), f"missing shim {shim}"
        assert HOOKS_TOML.is_file()
        assert (REPO_ROOT / "hooks" / "adapters" / "kimi" / "README.md").is_file()

    def test_adapter_scripts_are_executable(self) -> None:
        """Bash adapter scripts must be marked executable so Kimi can `bash` them."""
        for shim, _intent in EXPECTED_SHIMS.values():
            path = ADAPTER_DIR / shim
            assert os.access(path, os.X_OK), f"{path} is not executable; chmod +x required"

    def test_shims_export_ll_hook_host_and_intent(self) -> None:
        """Every shim exports LL_HOOK_HOST=kimi-code and dispatches its intent."""
        for shim, intent in EXPECTED_SHIMS.values():
            body = (ADAPTER_DIR / shim).read_text(encoding="utf-8")
            assert "export LL_HOOK_HOST=kimi-code" in body, f"{shim} missing host export"
            assert f"python -m little_loops.hooks {intent}" in body, (
                f"{shim} must dispatch the {intent} intent"
            )

    def test_hooks_toml_references_placeholders(self) -> None:
        """Template must carry {{LL_PLUGIN_ROOT}} / {{LL_GEN_VERSION}} for install-time substitution."""
        raw = HOOKS_TOML.read_text(encoding="utf-8")
        assert "{{LL_PLUGIN_ROOT}}" in raw
        assert "{{LL_GEN_VERSION}}" in raw
        # Staleness detection reads this marker line out of the managed block.
        assert "# ll-gen-version: {{LL_GEN_VERSION}}" in raw

    def test_hooks_toml_renders_valid_toml_with_all_events(self) -> None:
        """Rendered template parses as TOML and maps every kimi event to its shim."""
        data = _rendered_hooks_toml()
        entries = data["hooks"]
        assert len(entries) == len(EXPECTED_SHIMS)
        by_event = {entry["event"]: entry for entry in entries}
        for event, (shim, _intent) in EXPECTED_SHIMS.items():
            assert event in by_event, f"hooks.toml missing {event} entry"
            entry = by_event[event]
            assert entry["command"] == f"bash /tmp/pkg/hooks/adapters/kimi/{shim}"
            assert entry["timeout"] == 30
        # Matchers per adapter policy: SessionStart restricted to startup,
        # PreCompact to manual|auto, tool events unscoped (all tools).
        assert by_event["SessionStart"]["matcher"] == "startup"
        assert by_event["PreCompact"]["matcher"] == "manual|auto"
        assert "matcher" not in by_event["PreToolUse"]
        assert "matcher" not in by_event["PostToolUse"]


class TestKimiAdapterIntegration:
    """End-to-end adapter tests via bash + the real Python dispatcher."""

    def test_session_start_runs_without_config(self, tmp_path: Path) -> None:
        """session-start.sh with a kimi-shaped payload (no transcript_path) → "No config found" on stderr."""
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "test-session",
            "cwd": str(tmp_path),
            "source": "startup",
        }
        result = subprocess.run(
            [BASH, str(ADAPTER_DIR / "session-start.sh")],
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

    def test_pre_compact_writes_state_file(self, tmp_path: Path) -> None:
        """pre-compact.sh with a base-fields-only kimi payload writes .ll/ll-precompact-state.json."""
        payload = {
            "hook_event_name": "PreCompact",
            "session_id": "test-session",
            "cwd": str(tmp_path),
        }
        result = subprocess.run(
            [BASH, str(ADAPTER_DIR / "pre-compact.sh")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        # pre_compact's success path is exit_code in {0, 2} with stderr feedback;
        # both indicate the handler ran. Kimi ignores PreCompact return values.
        assert result.returncode in (0, 2), (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        assert state_file.is_file(), (
            f"expected {state_file} written by pre_compact handler; stderr={result.stderr!r}"
        )

    def _assert_shim_sets_host(self, shim: str, payload: dict, tmp_path: Path) -> None:
        """Run *shim* against a stub dispatcher and assert LL_HOOK_HOST=kimi-code.

        Same sentinel-file pattern as test_codex_adapter.py: a fake
        ``little_loops/hooks/__main__.py`` on PYTHONPATH records the env var,
        isolating env propagation from real handler logic.
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

        full_env = {**os.environ, "PYTHONPATH": str(fake_pkg)}
        # Wipe any inherited LL_HOOK_HOST so we're sure the adapter sets it.
        full_env.pop("LL_HOOK_HOST", None)

        result = subprocess.run(
            [BASH, str(ADAPTER_DIR / shim)],
            input=json.dumps(payload),
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
        assert sentinel.read_text() == "kimi-code"

    def test_session_start_sets_ll_hook_host_kimi(self, tmp_path: Path) -> None:
        """session-start.sh sets LL_HOOK_HOST=kimi-code in the Python subprocess."""
        self._assert_shim_sets_host(
            "session-start.sh",
            {"hook_event_name": "SessionStart", "source": "startup"},
            tmp_path,
        )

    def test_user_prompt_submit_sets_ll_hook_host_kimi(self, tmp_path: Path) -> None:
        """user-prompt-submit.sh sets LL_HOOK_HOST=kimi-code (kimi block-array prompt shape)."""
        self._assert_shim_sets_host(
            "user-prompt-submit.sh",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": [{"type": "text", "text": "test prompt"}],
            },
            tmp_path,
        )

    def test_post_tool_use_sets_ll_hook_host_kimi(self, tmp_path: Path) -> None:
        """post-tool-use.sh sets LL_HOOK_HOST=kimi-code (kimi tool_output shape)."""
        self._assert_shim_sets_host(
            "post-tool-use.sh",
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "tool_call_id": "Bash_0",
                "tool_output": "total 0",
            },
            tmp_path,
        )
