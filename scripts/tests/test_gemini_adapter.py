"""Integration tests for the Gemini CLI hook adapter (FEAT-2186, EPIC-2178).

The adapter at ``scripts/little_loops/hooks/adapters/gemini/*.sh`` is a thin
Bash transport: each script reads the host JSON payload from stdin, exports
``LL_HOOK_HOST=gemini`` on the subprocess environment, and pipes the payload
to ``python -m little_loops.hooks <intent>``. These tests assert the
sentinel files exist, the shims carry the host export + intent names, the
``hooks.json`` install template carries the ``{{LL_PLUGIN_ROOT}}`` /
``{{LL_GEN_VERSION}}`` placeholders, and the adapter works end-to-end via
``bash`` with gemini-shaped payloads (verified shapes from
``thoughts/research/gemini-cli-surface.md``, gemini-cli 0.46.0).

Also covers ``install_gemini_adapter`` — the ARCHITECTURE-046 Option A
structured JSON merge into ``.gemini/settings.json``.

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
ADAPTER_DIR = REPO_ROOT / "scripts" / "little_loops" / "hooks" / "adapters" / "gemini"
HOOKS_TEMPLATE = ADAPTER_DIR / "hooks.json"

# Gemini event name → (shim filename, ll intent).
EXPECTED_SHIMS: dict[str, tuple[str, str]] = {
    "SessionStart": ("session-start.sh", "session_start"),
    "PreCompress": ("pre-compact.sh", "pre_compact"),
    "BeforeAgent": ("prompt-submit.sh", "user_prompt_submit"),
    "BeforeTool": ("pre-tool-use.sh", "pre_tool_use"),
    "AfterTool": ("post-tool-use.sh", "post_tool_use"),
    "SessionEnd": ("session-end.sh", "session_end"),
}


def _rendered_hooks_template() -> dict:
    """Return hooks.json with install-time substitutions applied."""
    raw = HOOKS_TEMPLATE.read_text(encoding="utf-8")
    rendered = raw.replace("{{LL_PLUGIN_ROOT}}", "/tmp/pkg").replace(
        "{{LL_GEN_VERSION}}", "0.0.0-test"
    )
    return json.loads(rendered)


class TestGeminiAdapterSentinels:
    """Sentinel-file and template-content assertions (no subprocess)."""

    def test_adapter_files_exist(self) -> None:
        """The package ships all shims + hooks.json; README.md at repo-root hooks/adapters/gemini/."""
        for shim, _intent in EXPECTED_SHIMS.values():
            assert (ADAPTER_DIR / shim).is_file(), f"missing shim {shim}"
        assert HOOKS_TEMPLATE.is_file()
        assert (REPO_ROOT / "hooks" / "adapters" / "gemini" / "README.md").is_file()

    def test_adapter_scripts_are_executable(self) -> None:
        """Bash adapter scripts must be marked executable so Gemini can `bash` them."""
        for shim, _intent in EXPECTED_SHIMS.values():
            path = ADAPTER_DIR / shim
            assert os.access(path, os.X_OK), f"{path} is not executable; chmod +x required"

    def test_shims_export_ll_hook_host_and_intent(self) -> None:
        """Every intent shim exports LL_HOOK_HOST=gemini and dispatches its intent."""
        for shim, intent in EXPECTED_SHIMS.values():
            body = (ADAPTER_DIR / shim).read_text(encoding="utf-8")
            assert "export LL_HOOK_HOST=gemini" in body, f"{shim} missing host export"
            assert "LL_PYTHON" in body, f"{shim} missing LL_PYTHON interpreter resolution"
            assert f'"$PY" -m little_loops.hooks {intent}' in body, (
                f"{shim} must dispatch the {intent} intent"
            )

    def test_hooks_template_references_placeholders(self) -> None:
        """Template must carry {{LL_PLUGIN_ROOT}} / {{LL_GEN_VERSION}} for install-time substitution."""
        raw = HOOKS_TEMPLATE.read_text(encoding="utf-8")
        assert "{{LL_PLUGIN_ROOT}}" in raw
        assert "{{LL_GEN_VERSION}}" in raw
        # The gen-version stamp lives in the description (JSON has no comments).
        assert "(ll-gen:{{LL_GEN_VERSION}})" in raw

    def test_hooks_template_renders_valid_json_with_all_events(self) -> None:
        """Rendered template parses as JSON and maps every gemini event to its shim."""
        hooks = _rendered_hooks_template()
        for event, (shim, _intent) in EXPECTED_SHIMS.items():
            assert event in hooks, f"hooks.json missing {event}"
            commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
            assert any(c == f"bash /tmp/pkg/hooks/adapters/gemini/{shim}" for c in commands), (
                f"{event} does not reference {shim}"
            )

    def test_hooks_template_matchers_use_lifecycle_and_regex_semantics(self) -> None:
        """SessionStart matcher is exact-string `startup`; tool events use regex `.*`."""
        hooks = _rendered_hooks_template()
        session_start_matchers = [
            group.get("matcher") for group in hooks["SessionStart"] if "matcher" in group
        ]
        assert "startup" in session_start_matchers
        for event in ("BeforeTool", "AfterTool"):
            matchers = [group.get("matcher") for group in hooks[event] if "matcher" in group]
            assert ".*" in matchers

    def test_managed_entries_carry_ll_name_prefix(self) -> None:
        """install_gemini_adapter identifies managed entries by the ll: name prefix."""
        hooks = _rendered_hooks_template()
        for groups in hooks.values():
            for group in groups:
                for entry in group["hooks"]:
                    assert entry["name"].startswith("ll:"), entry
                    assert isinstance(entry["timeout"], int) and entry["timeout"] >= 5000


class TestGeminiAdapterIntegration:
    """End-to-end adapter tests via bash + the real Python dispatcher."""

    def test_session_start_runs_without_config(self, tmp_path: Path) -> None:
        """session-start.sh with a gemini-shaped payload (no config) → "No config found" on stderr."""
        payload = {
            "hook_event_name": "SessionStart",
            "session_id": "test-session",
            "transcript_path": str(tmp_path / "chats" / "test-session.jsonl"),
            "cwd": str(tmp_path),
            "timestamp": "2026-09-02T00:00:00.000Z",
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
        """pre-compact.sh with a base-fields-only gemini payload writes .ll/ll-precompact-state.json."""
        payload = {
            "hook_event_name": "PreCompress",
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
        """Run *shim* against a stub dispatcher and assert LL_HOOK_HOST=gemini.

        Same sentinel-file pattern as test_qwen_adapter.py: a fake
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
        assert sentinel.read_text() == "gemini"

    def test_session_start_sets_ll_hook_host_gemini(self, tmp_path: Path) -> None:
        self._assert_shim_sets_host(
            "session-start.sh",
            {"hook_event_name": "SessionStart", "source": "startup"},
            tmp_path,
        )

    def test_prompt_submit_sets_ll_hook_host_gemini(self, tmp_path: Path) -> None:
        """prompt-submit.sh sets LL_HOOK_HOST=gemini (BeforeAgent string prompt shape)."""
        self._assert_shim_sets_host(
            "prompt-submit.sh",
            {"hook_event_name": "BeforeAgent", "prompt": "test prompt"},
            tmp_path,
        )

    def test_pre_tool_use_sets_ll_hook_host_gemini(self, tmp_path: Path) -> None:
        """pre-tool-use.sh sets LL_HOOK_HOST=gemini (BeforeTool payload shape)."""
        self._assert_shim_sets_host(
            "pre-tool-use.sh",
            {
                "hook_event_name": "BeforeTool",
                "tool_name": "write_file",
                "tool_input": {"file_path": "/tmp/x.txt", "content": "hi"},
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


class TestInstallGeminiAdapter:
    """install_gemini_adapter: structured JSON merge into .gemini/settings.json."""

    def _install(self, tmp_path: Path, **kwargs):
        from little_loops.init.writers import install_gemini_adapter

        return install_gemini_adapter(tmp_path, tmp_path, **kwargs)

    def test_fresh_install_creates_settings_json(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        dest = tmp_path / ".gemini" / "settings.json"
        assert dest.is_file()
        data = json.loads(dest.read_text(encoding="utf-8"))
        hooks = data["hooks"]
        assert set(hooks) == {
            "SessionStart",
            "PreCompress",
            "BeforeAgent",
            "BeforeTool",
            "AfterTool",
            "SessionEnd",
        }
        # Placeholders substituted — no {{ }} survives.
        assert "{{" not in dest.read_text(encoding="utf-8")

    def test_merge_preserves_other_settings_keys(self, tmp_path: Path) -> None:
        dest = tmp_path / ".gemini"
        dest.mkdir()
        (dest / "settings.json").write_text(
            json.dumps({"theme": "dark", "model": {"name": "gemini-2.5-pro"}}),
            encoding="utf-8",
        )
        assert self._install(tmp_path) is True
        data = json.loads((dest / "settings.json").read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["model"] == {"name": "gemini-2.5-pro"}
        assert "hooks" in data

    def test_merge_preserves_third_party_hooks(self, tmp_path: Path) -> None:
        """Non-ll hook entries survive the merge untouched."""
        dest = tmp_path / ".gemini"
        dest.mkdir()
        existing_hooks = {
            "hooks": {
                "BeforeTool": [
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
        groups = data["hooks"]["BeforeTool"]
        vendor = [g for g in groups if any(h.get("name") == "vendor:guard" for h in g["hooks"])]
        assert len(vendor) == 1
        ll_groups = [
            g for g in groups if any(str(h.get("name", "")).startswith("ll:") for h in g["hooks"])
        ]
        assert ll_groups

    def test_idempotent_at_same_gen_version(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        before = (tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8")
        assert self._install(tmp_path) is False  # same stamp → skipped
        assert (tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8") == before

    def test_force_reinstalls(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        assert self._install(tmp_path, force=True) is True

    def test_reinstall_replaces_managed_entries_without_duplicates(self, tmp_path: Path) -> None:
        assert self._install(tmp_path) is True
        assert self._install(tmp_path, force=True) is True
        data = json.loads((tmp_path / ".gemini" / "settings.json").read_text(encoding="utf-8"))
        names = [
            h.get("name")
            for groups in data["hooks"].values()
            for group in groups
            for h in group["hooks"]
        ]
        assert len(names) == len(set(names)), f"duplicate managed entries: {names}"

    def test_corrupt_settings_returns_none(self, tmp_path: Path) -> None:
        dest = tmp_path / ".gemini"
        dest.mkdir()
        (dest / "settings.json").write_text("{not json", encoding="utf-8")
        assert self._install(tmp_path) is None
        # Corrupted file left untouched.
        assert (dest / "settings.json").read_text(encoding="utf-8") == "{not json"

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        assert self._install(tmp_path, dry_run=True) is True
        assert not (tmp_path / ".gemini" / "settings.json").exists()
