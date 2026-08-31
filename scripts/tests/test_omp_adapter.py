"""Integration tests for the oh-my-pi (omp) hook adapter (FEAT-2261).

The adapter at ``scripts/little_loops/hooks/adapters/omp/index.ts`` is a thin
transport: it registers native ``HookAPI.on()`` handlers that spawn ``python
-m little_loops.hooks <intent>`` and pipe the omp event payload as JSON to
stdin. These tests exercise the adapter end-to-end via the Bun runtime,
mirroring ``test_opencode_adapter.py`` — the applicable precedent per
FEAT-2261's own Integration Map, since omp is TS/Bun-plugin-shaped like
OpenCode rather than Bash-shim-shaped like Codex/Kimi/Qwen. The one shape
difference: omp hooks register via ``pi.on(event, handler)`` inside a
default-exported function, not OpenCode's ``Plugin`` factory returning an
event-map object.

If Bun is not installed on ``PATH`` the entire module is skipped.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_BUN = shutil.which("bun")
pytestmark = pytest.mark.skipif(_BUN is None, reason="Bun runtime not available")
BUN: str = _BUN or "bun"

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = REPO_ROOT / "scripts" / "little_loops" / "hooks" / "adapters" / "omp"
ADAPTER_PATH = ADAPTER_DIR / "index.ts"
README_PATH = REPO_ROOT / "hooks" / "adapters" / "omp" / "README.md"


def _write_driver(tmp_path: Path, event_name: str, payload: dict) -> Path:
    """Write a Bun driver that imports the adapter and dispatches one event.

    Stubs ``HookAPI`` down to the one method the adapter uses (``on``),
    capturing registered handlers in a plain map keyed by event name — the
    adapter never touches any other ``HookAPI`` surface (pure transport).
    """
    driver_src = textwrap.dedent(
        f"""
        import registerHooks from {str(ADAPTER_PATH)!r};

        const registered: Record<string, Function> = {{}};
        const pi: any = {{
          on: (event: string, handler: Function) => {{ registered[event] = handler; }},
        }};
        registerHooks(pi);

        const ctx: any = {{ cwd: {str(tmp_path)!r}, hasUI: false }};
        const handler = registered[{event_name!r}];
        if (!handler) {{
          console.error("no handler registered for event " + {event_name!r});
          process.exit(1);
        }}
        try {{
          const result = await handler({json.dumps(payload)}, ctx);
          if (result !== undefined) {{
            process.stdout.write(JSON.stringify(result));
          }}
        }} catch (err: any) {{
          console.error("handler threw: " + (err?.message ?? String(err)));
          process.exit(2);
        }}
        """
    ).strip()
    driver = tmp_path / "driver.ts"
    driver.write_text(driver_src)
    return driver


def _run_driver(driver: Path, tmp_path: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BUN, "run", str(driver)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(tmp_path),
        env=env,
    )


class TestOmpAdapterIntegration:
    """End-to-end adapter tests via Bun + the real Python dispatcher."""

    def test_adapter_files_exist(self) -> None:
        """Runnable shims live under scripts/little_loops/ (pip-wheel split, BUG-2275);
        only README.md stays at repo-root hooks/adapters/omp/."""
        assert README_PATH.is_file()
        assert (ADAPTER_DIR / "index.ts").is_file()
        assert (ADAPTER_DIR / "package.json").is_file()
        assert (ADAPTER_DIR / "tsconfig.json").is_file()
        assert not (REPO_ROOT / "hooks" / "adapters" / "omp" / "index.ts").exists()

    def test_session_start_runs_handler(self, tmp_path: Path) -> None:
        """session_start omp event -> session_start ll intent; no config -> stderr warning."""
        driver = _write_driver(tmp_path, event_name="session_start", payload={"type": "session_start"})
        result = _run_driver(driver, tmp_path)
        assert result.returncode == 0, (
            f"driver exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert "No config found" in result.stderr

    def test_tool_result_sets_ll_hook_host_omp(self, tmp_path: Path) -> None:
        """tool_result omp event -> post_tool_use intent; subprocess sees LL_HOOK_HOST=omp.

        Stubs ``little_loops.hooks.__main__`` on PYTHONPATH to record the
        observed env var to a sentinel file, isolating env propagation from
        the real handler (covered separately by the session_start test).
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

        driver = _write_driver(
            tmp_path,
            event_name="tool_result",
            payload={
                "type": "tool_result",
                "toolCallId": "t1",
                "input": {},
                "content": [],
            },
        )
        full_env = {**os.environ, "PYTHONPATH": str(fake_pkg)}
        result = _run_driver(driver, tmp_path, env=full_env)
        assert result.returncode == 0, (
            f"driver exited {result.returncode}; stderr={result.stderr!r}"
        )
        # post_tool_use is fire-and-forget (no await on the spawned Promise per
        # FEAT-1489 precedent); give the detached subprocess a moment to land.
        import time

        for _ in range(50):
            if sentinel.is_file():
                break
            time.sleep(0.1)
        assert sentinel.is_file(), (
            f"sentinel not written; PYTHONPATH may not have routed to fake "
            f"module. stderr={result.stderr!r}"
        )
        assert sentinel.read_text() == "omp"


class TestOmpAdapterTypecheck:
    """Typecheck gate (BUG-2922 precedent): ``tsc --noEmit`` must run and pass."""

    def test_tsc_noemit_passes(self) -> None:
        proc = subprocess.run(
            [BUN, "x", "tsc", "--noEmit", "-p", "tsconfig.json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ADAPTER_DIR),
        )
        assert proc.returncode == 0, (
            f"tsc --noEmit failed (exit {proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )
