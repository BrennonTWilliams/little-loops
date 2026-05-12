"""Integration tests for the OpenCode hook adapter (FEAT-1451).

The adapter at ``hooks/adapters/opencode/index.ts`` is a thin transport: it
spawns ``python -m little_loops.hooks <intent>`` and pipes the OpenCode event
payload as JSON to stdin. These tests exercise the adapter end-to-end via the
Bun runtime, asserting the same observable Python-side effects that
``TestHooksMainModule`` asserts for the Claude Code path (config JSON / state
file written under ``cwd``), plus the OpenCode-specific contract that the
adapter sets ``LL_HOOK_HOST=opencode`` on the subprocess.

If Bun is not installed on ``PATH`` the entire module is skipped — TypeScript
runtime testing is opt-in for environments that have it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_BUN = shutil.which("bun")
pytestmark = pytest.mark.skipif(_BUN is None, reason="Bun runtime not available")
# Module-level pytestmark guarantees _BUN is non-None when tests run; assert
# for Pyright/mypy.
BUN: str = _BUN or "bun"

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATH = REPO_ROOT / "hooks" / "adapters" / "opencode" / "index.ts"


def _write_driver(tmp_path: Path, event_name: str, payload: dict) -> Path:
    """Write a Bun driver that imports the adapter and dispatches one event.

    The driver:
      - Imports the adapter's default export (the ``Plugin`` factory).
      - Calls it with a minimal ``ctx`` carrying ``cwd``.
      - Invokes the named event handler with ``payload``.
      - Prints the handler's return value (if any) to stdout as JSON.
      - Propagates handler errors via process.exit(1).
    """
    driver_src = textwrap.dedent(
        f"""
        import plugin from {str(ADAPTER_PATH)!r};

        const ctx = {{ cwd: {str(tmp_path)!r} }};
        const handlers = await (plugin as any)(ctx);
        const handler = handlers[{event_name!r}];
        if (!handler) {{
          console.error("no handler for event " + {event_name!r});
          process.exit(1);
        }}
        try {{
          const result = await handler({json.dumps(payload)});
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


class TestOpenCodeAdapterIntegration:
    """End-to-end adapter tests via Bun + the real Python dispatcher."""

    def test_adapter_files_exist(self) -> None:
        """The adapter directory ships index.ts, package.json, tsconfig.json, README.md."""
        adapter_dir = REPO_ROOT / "hooks" / "adapters" / "opencode"
        assert (adapter_dir / "index.ts").is_file()
        assert (adapter_dir / "package.json").is_file()
        assert (adapter_dir / "tsconfig.json").is_file()
        assert (adapter_dir / "README.md").is_file()

    def test_session_compacted_writes_state_file(self, tmp_path: Path) -> None:
        """session.compacted → pre_compact handler writes .ll/ll-precompact-state.json in cwd."""
        driver = _write_driver(
            tmp_path,
            event_name="session.compacted",
            payload={"transcript_path": str(tmp_path / "fake-transcript.jsonl")},
        )
        result = subprocess.run(
            [BUN, "run", str(driver)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        # pre_compact's stderr surfaces handler feedback; exit 0 (handler success
        # at the Bun layer — adapter does not throw for exit_code in {0, 2}).
        assert result.returncode == 0, (
            f"driver exited {result.returncode}; stderr={result.stderr!r}"
        )
        state_file = tmp_path / ".ll" / "ll-precompact-state.json"
        assert state_file.is_file(), (
            f"expected {state_file} written by pre_compact handler; stderr={result.stderr!r}"
        )

    def test_session_created_runs_session_start(self, tmp_path: Path) -> None:
        """session.created → session_start handler runs; no config in tmp → warning on stderr."""
        driver = _write_driver(tmp_path, event_name="session.created", payload={})
        result = subprocess.run(
            [BUN, "run", str(driver)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
        )
        # Without an ``.ll/ll-config.json`` in cwd, the Python session_start
        # handler emits a "No config found" warning to stderr and exits 0; the
        # adapter forwards stderr via ``console.error``, which lands on
        # ``result.stderr`` for the Bun driver.
        assert result.returncode == 0, (
            f"driver exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert "No config found" in result.stderr

    def test_adapter_sets_ll_hook_host_opencode(self, tmp_path: Path) -> None:
        """The subprocess sees LL_HOOK_HOST=opencode, so LLHookEvent.host == 'opencode'.

        Asserts the contract by stubbing the dispatcher: write a fake
        ``little_loops/hooks/__main__.py`` shim on PYTHONPATH that records the
        env var into a sentinel file, then run the adapter and inspect the
        sentinel. This isolates the env-var propagation from the real handler
        logic (which we already cover separately).
        """
        # Build a minimal Python module tree at fake_pkg/little_loops/hooks
        # that, when invoked as ``python -m little_loops.hooks``, writes the
        # observed LL_HOOK_HOST to a sentinel file.
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
            event_name="session.created",
            payload={},
        )

        env_passthrough = {"PYTHONPATH": str(fake_pkg)}
        # Merge with parent env so PATH (containing python) is preserved.
        import os

        full_env = {**os.environ, **env_passthrough}
        result = subprocess.run(
            [BUN, "run", str(driver)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(tmp_path),
            env=full_env,
        )
        assert result.returncode == 0, (
            f"driver exited {result.returncode}; stderr={result.stderr!r}"
        )
        assert sentinel.is_file(), (
            f"sentinel not written; PYTHONPATH may not have routed to fake "
            f"module. stderr={result.stderr!r}"
        )
        assert sentinel.read_text() == "opencode"
