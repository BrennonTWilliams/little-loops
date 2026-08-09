"""ll-mcp: stdio MCP server exposing five coarse read-only tools over the little_loops library.

Implements the 2026-07-28 MCP spec via the official `mcp` SDK (pinned exactly to 2.0.0 — see
the `[project.optional-dependencies].mcp` comment in `scripts/pyproject.toml`). The SDK owns
the protocol: JSON-RPC framing, method routing, `ttlMs`/`cacheScope` attachment, and
`server/discover` are all SDK-provided (FEAT-3135). This package wires the entry point
(`main_mcp`) and the five tool handlers registered in `little_loops.mcp_server.tools`;
`little_loops.mcp_server.server` builds the `Server` instance FEAT-3136 (resources) and
FEAT-3137 (prompts) register their own handlers onto.

No `cli_event_context()` wrapper is used: that convention measures a single CLI invocation's
duration, but a stdio server's process lifetime spans arbitrarily many requests — wrapping the
whole run would be exactly the cross-request session state the 2026-07-28 spec designs away
from (statelessness is the design invariant, not just handshake removal: no request handler
here depends on state established by a prior request). `ll-mcp` also installs no
SIGINT/SIGTERM handlers: it has no in-flight child to kill and no queue to drain. EOF on
stdin (the normal MCP shutdown signal) is handled inside the SDK's transport, and
`anyio.run()` unwinds cleanly on either signal by default.

Blocking library calls inside the five tool handlers (SQLite FTS5, `.issues/` filesystem
parsing) run inline on the event loop thread rather than being offloaded via
`anyio.to_thread.run_sync`: stdio serves exactly one client with no concurrent in-flight
requests, so there is no responsiveness to protect, and offloading would only add a
thread-safety burden on SQLite connections for no benefit. A future HTTP tier (which *would*
need offloading) should revisit this deliberately rather than inherit it.

Exit codes:
    0 - clean EOF/shutdown
    2 - missing the `mcp` extra, or a usage error
"""

from __future__ import annotations

import sys


def main_mcp(argv: list[str] | None = None) -> int:
    """Synchronous entry point for the `ll-mcp` console script.

    This is a protocol server, not a CLI: it parses no meaningful arguments — `argv` exists
    only for console-script signature parity with every other `ll-*` entry point. `mcp` is
    imported lazily here, not at module scope, so a checkout without the `mcp` extra
    installed still imports this module (and every `[project.scripts]` target) cleanly; see
    `test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`.
    """
    del argv

    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "ll-mcp requires the `mcp` extra: pip install 'little-loops[mcp]'",
            file=sys.stderr,
        )
        return 2

    import anyio

    from little_loops.mcp_server.server import run_stdio

    anyio.run(run_stdio)
    return 0


__all__ = ["main_mcp"]
