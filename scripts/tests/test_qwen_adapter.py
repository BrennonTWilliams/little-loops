"""Integration tests for the Qwen Code hook adapter (FEAT-3158, EPIC-3154).

The adapter at ``scripts/little_loops/hooks/adapters/qwen/*.sh`` is a thin
Bash transport: each script reads the host JSON payload from stdin, exports
``LL_HOOK_HOST=qwen`` on the subprocess environment, and pipes the payload
to ``python -m little_loops.hooks <intent>``. These tests assert the
sentinel files exist, the shims carry the host export + intent names, the
``settings-block.json`` install template carries the ``{{LL_PLUGIN_ROOT}}``
/ ``{{LL_GEN_VERSION}}`` placeholders, and the adapter works end-to-end via
``bash`` with qwen-shaped payloads (verified shapes from
``thoughts/research/qwen-code-surface.md``, qwen 0.21.6).

Also covers ``install_qwen_adapter`` — the ARCHITECTURE-046 Option A
structured JSON merge into ``.qwen/settings.json``.

If ``bash`` is not on ``PATH`` the subprocess tests are skipped — should be
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
ADAPTER_DIR = REPO_ROOT / "scripts" / "little_loops" / "hooks" / "adapters" / "qwen"
SETTINGS_BLOCK = ADAPTER_DIR / "settings-block.json"

# Qwen event name → (shim filename, ll intent). Stop has no intent in the
# dispatch table — it resolves the legacy Claude-plugin scripts directly.
EXPECTED_SHIMS: dict[str, tuple[str, str]] = {
    "SessionStart": ("session-start.sh", "session_start"),
    "PreCompact": ("pre-compact.sh", "pre_compact"),
    "UserPromptSubmit": ("prompt-submit.sh", "user_prompt_submit"),
    "PreToolUse": ("pre-tool-use.sh", "pre_tool_use"),
    "PostToolUse": ("post-tool-use.sh", "post_tool_use"),
    "SessionEnd": ("session-end.sh", "session_end"),
    "SubagentStart": ("subagent-start.sh", "subagent_start"),
    "SubagentStop": ("subagent-stop.sh", "subagent_stop"),
}
EXTRA_SHIMS = {
    "drift-check.sh": "drift_check",
    "precompact-handoff.sh": "pre_compact_handoff",
    "edit-batch-nudge.sh": "edit_batch_nudge",
}


def _rendered_settings_block() -> dict:
    """Return settings-block.json with install-time substitutions applied."""
    raw = SETTINGS_BLOCK.read_text(encoding="utf-8")
    rendered = raw.replace("{{LL_PLUGIN_ROOT}}", "/tmp/pkg").replace(
        "{{LL_GEN_VERSION}}", "0.0.0-test"
    )
    return json.loads(rendered)


class TestQwenAdapterSentinels:
    """Sentinel-file and template-content assertions (no subprocess)."""

    def test_adapter_files_exist(self) -> None:
        """The package ships all shims + settings-block.json; README.md at repo-root hooks/adapters/qwen/."""
        for shim, _intent in EXPECTED_SHIMS.values():
            assert (ADAPTER_DIR / shim).is_file(), f"missing shim {shim}"
        for shim in EXTRA_SHIMS:
            assert (ADAPTER_DIR / shim).is_file(), f"missing shim {shim}"
        assert (ADAPTER_DIR / "stop.sh").is_file()
        assert SETTINGS_BLOCK.is_file()
        assert (REPO_ROOT / "hooks" / "adapters" / "qwen" / "README.md").is_file()

    def test_adapter_scripts_are_executable(self) -> None:
        """Bash adapter scripts must be marked executable so Qwen can `bash` them."""
        for shim, _intent in EXPECTED_SHIMS.values():
            path = ADAPTER_DIR / shim
            assert os.access(path, os.X_OK), f"{path} is not executable; chmod +x required"
        for shim in [*EXTRA_SHIMS, "stop.sh"]:
            path = ADAPTER_DIR / shim
            assert os.access(path, os.X_OK), f"{path} is not executable; chmod +x required"

    def test_shims_export_ll_hook_host_and_intent(self) -> None:
        """Every intent shim exports LL_HOOK_HOST=qwen and dispatches its intent."""
        expected = dict(EXPECTED_SHIMS.values())
        expected.update(EXTRA_SHIMS)
        for shim, intent in expected.items():
            body = (ADAPTER_DIR / shim).read_text(encoding="utf-8")
            assert "export LL_HOOK_HOST=qwen" in body, f"{shim} missing host export"
            # BUG-2921 hardening: shims resolve the interpreter via
            # LL_PYTHON/probe rather than a bare `python`.
            assert "LL_PYTHON" in body, f"{shim} missing LL_PYTHON interpreter resolution"
            assert f'"$PY" -m little_loops.hooks {intent}' in body, (
                f"{shim} must dispatch the {intent} intent"
            )

    def test_stop_shim_resolves_legacy_scripts(self) -> None:
        """stop.sh prefers $CLAUDE_PLUGIN_ROOT legacy scripts and never fails."""
        body = (ADAPTER_DIR / "stop.sh").read_text(encoding="utf-8")
        assert "context-handoff-sentinel.sh" in body
        assert "session-cleanup.sh" in body
        assert body.rstrip().endswith("exit 0")

    def test_settings_block_references_placeholders(self) -> None:
        """Template must carry {{LL_PLUGIN_ROOT}} / {{LL_GEN_VERSION}} for install-time substitution."""
        raw = SETTINGS_BLOCK.read_text(encoding="utf-8")
        assert "{{LL_PLUGIN_ROOT}}" in raw
        assert "{{LL_GEN_VERSION}}" in raw
        # The gen-version stamp lives in the description (JSON has no comments).
        assert "(ll-gen:{{LL_GEN_VERSION}})" in raw

    def test_settings_block_renders_valid_json_with_all_events(self) -> None:
        """Rendered template parses as JSON and maps every qwen event to its shim(s)."""
        data = _rendered_settings_block()
        hooks = data
        for event, (shim, _intent) in EXPECTED_SHIMS.items():
            assert event in hooks, f"settings-block.json missing {event}"
            commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
            assert any(c == f"bash /tmp/pkg/hooks/adapters/qwen/{shim}" for c in commands), (
                f"{event} does not reference {shim}"
            )
        # Extra intents wired to their events.
        session_start_cmds = [
            h["command"] for group in hooks["SessionStart"] for h in group["hooks"]
        ]
        assert any("drift-check.sh" in c for c in session_start_cmds)
        precompact_cmds = [h["command"] for group in hooks["PreCompact"] for h in group["hooks"]]
        assert any("precompact-handoff.sh" in c for c in precompact_cmds)
        post_tool_cmds = [h["command"] for group in hooks["PostToolUse"] for h in group["hooks"]]
        assert any("edit-batch-nudge.sh" in c for c in post_tool_cmds)
        assert "Stop" in hooks and any(
            "stop.sh" in h["command"] for group in hooks["Stop"] for h in group["hooks"]
        )

    def test_settings_block_matchers_use_qwen_runtime_tool_ids(self) -> None:
        """FEAT-3155: Claude display names (Write|Edit) never match on Qwen."""
        data = _rendered_settings_block()
        raw = json.dumps(data)
        assert '"Write' not in raw and '"Bash"' not in raw and "MultiEdit" not in raw
        matchers = [
            group.get("matcher")
            for groups in data.values()
            for group in groups
            if isinstance(group, dict) and "matcher" in group
        ]
        assert "write_file|edit" in matchers
        assert "manual|auto" in matchers

    def test_managed_entries_carry_ll_name_prefix(self) -> None:
        """install_qwen_adapter identifies managed entries by the ll: name prefix."""
        data = _rendered_settings_block()
        for groups in data.values():
            for group in groups:
                for entry in group["hooks"]:
                    assert entry["name"].startswith("ll:"), entry
                    assert isinstance(entry["timeout"], int) and entry["timeout"] >= 5000


class TestQwenAdapterIntegration:
    """End-to-end adapter tests via bash + the real Python dispatcher."""

    def test_session_start_runs_without_config(self, tmp_path: Path) -> None:
        """session-start.sh with a qwen-shaped payload (no config) → "No config found" on stderr."""
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "test-session",
            "transcript_path": str(tmp_path / "chats" / "test-session.jsonl"),
            "cwd": str(tmp_path),
            "timestamp": "2026-08-13T00:00:00.000Z",
            "permission_mode": "yolo",
            "source": "startup",
            "model": "qwen3.8-max-preview",
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
        """pre-compact.sh with a base-fields-only qwen payload writes .ll/ll-precompact-state.json."""
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
        assert result.returncode in (0, 2), (
            f"adapter exited {result.returncode}; stderr={result.stderr!r}"
        )
        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        assert state_file.is_file(), (
            f"expected {state_file} written by pre_compact handler; stderr={result.stderr!r}"
        )

    def _assert_shim_sets_host(self, shim: str, payload: dict, tmp_path: Path) -> None:
        """Run *shim* against a stub dispatcher and assert LL_HOOK_HOST=qwen.

        Same sentinel-file pattern as test_kimi_adapter.py: a fake
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
        assert sentinel.read_text() == "qwen"

    def test_session_start_sets_ll_hook_host_qwen(self, tmp_path: Path) -> None:
        self._assert_shim_sets_host(
            "session-start.sh",
            {"hook_event_name": "SessionStart", "source": "startup"},
            tmp_path,
        )

    def test_prompt_submit_sets_ll_hook_host_qwen(self, tmp_path: Path) -> None:
        """prompt-submit.sh sets LL_HOOK_HOST=qwen (qwen string prompt shape)."""
        self._assert_shim_sets_host(
            "prompt-submit.sh",
            {"hook_event_name": "UserPromptSubmit", "prompt": "test prompt"},
            tmp_path,
        )

    def test_pre_tool_use_sets_ll_hook_host_qwen(self, tmp_path: Path) -> None:
        """pre-tool-use.sh sets LL_HOOK_HOST=qwen (qwen runtime tool-id shape)."""
        self._assert_shim_sets_host(
            "pre-tool-use.sh",
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "write_file",
                "tool_input": {"file_path": "/tmp/x.txt", "content": "hi"},
                "tool_use_id": "toolu_test",
                "tool_call_id": "call_test",
            },
            tmp_path,
        )

    def test_shim_cd_into_payload_cwd(self, tmp_path: Path) -> None:
        """BUG-2921 hardening: shims cd into the payload's project dir before dispatching."""
        proj_dir = tmp_path / "proj"
        proj_dir.mkdir()
        fake_pkg = tmp_path / "fake_pkg"
        ll_dir = fake_pkg / "little_loops" / "hooks"
        ll_dir.mkdir(parents=True)
        (fake_pkg / "little_loops" / "__init__.py").write_text("")
        (ll_dir / "__init__.py").write_text("")
        sentinel = tmp_path / "cwd-sentinel.txt"
        (ll_dir / "__main__.py").write_text(
            textwrap.dedent(
                f"""
                import os, sys
                with open({str(sentinel)!r}, "w") as f:
                    f.write(os.getcwd())
                sys.exit(0)
                """
            ).strip()
        )

        full_env = {**os.environ, "PYTHONPATH": str(fake_pkg)}
        full_env.pop("LL_HOOK_HOST", None)
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "test-cd",
            "cwd": str(proj_dir),
            "source": "startup",
        }
        result = subprocess.run(
            [BASH, str(ADAPTER_DIR / "session-start.sh")],
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
        assert sentinel.is_file(), f"sentinel not written; stderr={result.stderr!r}"
        assert sentinel.read_text() == str(proj_dir)

    def test_stop_shim_noops_without_plugin_root(self, tmp_path: Path) -> None:
        """stop.sh exits 0 silently when CLAUDE_PLUGIN_ROOT/LL_PLUGIN_ROOT are unset."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "test-stop",
            "cwd": str(tmp_path),
            "stop_hook_active": True,
        }
        env = {
            k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "LL_PLUGIN_ROOT")
        }
        result = subprocess.run(
            [BASH, str(ADAPTER_DIR / "stop.sh")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
            env=env,
        )
        assert result.returncode == 0, f"stop.sh must never fail; stderr={result.stderr!r}"


class TestInstallQwenAdapter:
    """install_qwen_adapter: structured JSON merge into .qwen/settings.json."""

    def _install(self, tmp_path: Path, **kwargs):
        from little_loops.init.writers import install_qwen_adapter

        return install_qwen_adapter(tmp_path, tmp_path, **kwargs)

    def test_fresh_install_creates_settings_json(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        dest = tmp_path / ".qwen" / "settings.json"
        assert dest.is_file()
        data = json.loads(dest.read_text(encoding="utf-8"))
        hooks = data["hooks"]
        assert set(hooks) == {
            "SessionStart",
            "PreCompact",
            "UserPromptSubmit",
            "PreToolUse",
            "PostToolUse",
            "Stop",
            "SessionEnd",
            "SubagentStart",
            "SubagentStop",
        }
        # Placeholders substituted — no {{ }} survives.
        assert "{{" not in dest.read_text(encoding="utf-8")

    def test_merge_preserves_other_settings_keys(self, tmp_path: Path) -> None:
        dest = tmp_path / ".qwen"
        dest.mkdir()
        (dest / "settings.json").write_text(
            json.dumps({"theme": "dark", "model": {"name": "qwen3"}}),
            encoding="utf-8",
        )
        assert self._install(tmp_path) is True
        data = json.loads((dest / "settings.json").read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["model"] == {"name": "qwen3"}
        assert "hooks" in data

    def test_merge_preserves_third_party_hooks(self, tmp_path: Path) -> None:
        """Non-ll hook entries survive the merge untouched."""
        dest = tmp_path / ".qwen"
        dest.mkdir()
        existing_hooks = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "run_shell_command",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash /opt/vendor/guard.sh",
                                "name": "vendor:guard",
                            }
                        ],
                    }
                ]
            }
        }
        (dest / "settings.json").write_text(json.dumps(existing_hooks), encoding="utf-8")
        assert self._install(tmp_path) is True
        data = json.loads((dest / "settings.json").read_text(encoding="utf-8"))
        groups = data["hooks"]["PreToolUse"]
        vendor = [g for g in groups if any(h.get("name") == "vendor:guard" for h in g["hooks"])]
        assert len(vendor) == 1
        ll_groups = [
            g for g in groups if any(str(h.get("name", "")).startswith("ll:") for h in g["hooks"])
        ]
        assert ll_groups

    def test_idempotent_at_same_gen_version(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        before = (tmp_path / ".qwen" / "settings.json").read_text(encoding="utf-8")
        assert self._install(tmp_path) is False  # same stamp → skipped
        assert (tmp_path / ".qwen" / "settings.json").read_text(encoding="utf-8") == before

    def test_force_reinstalls(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        assert self._install(tmp_path, force=True) is True

    def test_reinstall_replaces_managed_entries_without_duplicates(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        assert self._install(tmp_path, force=True) is True
        data = json.loads((tmp_path / ".qwen" / "settings.json").read_text(encoding="utf-8"))
        names = [
            h.get("name")
            for groups in data["hooks"].values()
            for group in groups
            for h in group["hooks"]
        ]
        assert len(names) == len(set(names)), f"duplicate managed entries: {names}"

    def test_corrupt_settings_returns_none(self, tmp_path: Path) -> None:
        dest = tmp_path / ".qwen"
        dest.mkdir()
        (dest / "settings.json").write_text("{not json", encoding="utf-8")
        assert self._install(tmp_path) is None
        # Corrupted file left untouched.
        assert (dest / "settings.json").read_text(encoding="utf-8") == "{not json"

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        assert self._install(tmp_path, dry_run=True) is True
        assert not (tmp_path / ".qwen" / "settings.json").exists()
