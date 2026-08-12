"""ll-mcp: MCP server (stdio, and streamable HTTP per FEAT-3143) exposing five coarse
read-only tools, four guarded mutation tools (FEAT-3149), and a `tasks/get` +
`tasks/cancel` poll surface for `ll-loop` runs (FEAT-3145) over the little_loops library.

Implements the 2026-07-28 MCP spec via the official `mcp` SDK (pinned exactly to 2.0.0 — see
the `[project.optional-dependencies].mcp` comment in `scripts/pyproject.toml`). The SDK owns
the protocol: JSON-RPC framing, method routing, `ttlMs`/`cacheScope` attachment, and
`server/discover` are all SDK-provided (FEAT-3135). This package wires the entry point
(`main_mcp`) and the tool handlers registered in `little_loops.mcp_server.tools`;
`little_loops.mcp_server.server` builds the `Server` instance FEAT-3136 (resources) and
FEAT-3137 (prompts) register their own handlers onto.

The write half of the surface is guarded twice (FEAT-3149). Every mutating tool is
**dry-run by default** — it writes only on an explicit `apply: true`, and treats a missing
or non-`True` value as a refusal to mutate — and every mutating tool can additionally be
refused at the transport layer per deployment, via `mcp.transport_policy` in
`.ll/ll-config.json`. HTTP denies mutations by default (that transport ships without
authentication); stdio, a same-machine channel, allows them. Both guards read the same
`little_loops.mcp_server.policy.MUTATING_TOOLS` registry, so they cannot disagree about
what counts as a write.

`little_loops.mcp_server.tasks` (FEAT-3145) registers `tasks/get`/`tasks/cancel` directly
on the `Server` via `add_request_handler` rather than as tools — polling or stopping a run
does not fit the tools primitive, but is also not read-only, so it gets the same
deny-by-default-on-HTTP transport-policy treatment as mutations, via its own
`mcp.transport_policy.*.allow_tasks` grant (independently expressible from
`allow_mutations` — stopping a running agent and writing an issue file are different
consents). No start path exists here or anywhere in this package: starting a run is
FEAT-3151's territory.

No `cli_event_context()` wrapper is used: that convention measures a single CLI invocation's
duration, but a stdio server's process lifetime spans arbitrarily many requests — wrapping the
whole run would be exactly the cross-request session state the 2026-07-28 spec designs away
from (statelessness is the design invariant, not just handshake removal: no request handler
here depends on state established by a prior request). `ll-mcp` also installs no
SIGINT/SIGTERM handlers: it has no in-flight child to kill and no queue to drain. EOF on
stdin (the normal MCP shutdown signal) is handled inside the SDK's transport, and
`anyio.run()` unwinds cleanly on either signal by default.

Blocking library calls inside the tool handlers (SQLite FTS5, `.issues/` filesystem
parsing) run inline on the event loop thread rather than being offloaded via
`anyio.to_thread.run_sync`. Under stdio this is a non-issue: exactly one client, no
concurrent in-flight requests, so there is no responsiveness to protect. The HTTP transport
(FEAT-3143) reuses this deliberately, not by oversight: it defaults to `stateless=True`,
where each request already runs as its own short-lived `Server.run()` call rather than
sharing a long-lived per-client connection, so the "no concurrent in-flight requests against
shared state" property stdio relies on still holds per request even though multiple HTTP
requests can be in flight at once. Revisit if a non-stateless HTTP mode is ever added.

Exit codes:
    0 - clean EOF/shutdown
    2 - missing the `mcp` extra, or a usage error
"""

from __future__ import annotations

import os
import sys


def main_mcp(argv: list[str] | None = None) -> int:
    """Synchronous entry point for the `ll-mcp` console script.

    This is a protocol server, not a CLI: `argv` exists for console-script signature parity
    with every other `ll-*` entry point, and the only thing read from it is a bare `--http`
    flag (checked directly, not parsed with `argparse` — no help text or subcommands). The
    `LL_MCP_TRANSPORT=http` env var is the fallback for host configs that invoke `ll-mcp`
    with no args (FEAT-3143). Default with neither set is unchanged: stdio. `mcp` is imported
    lazily here, not at module scope, so a checkout without the `mcp` extra installed still
    imports this module (and every `[project.scripts]` target) cleanly; see
    `test_cli_doctor_install_checks.py::test_real_pyproject_all_entry_points_resolve`.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        import mcp  # noqa: F401
    except ImportError:
        print(
            "ll-mcp requires the `mcp` extra: pip install 'little-loops[mcp]'",
            file=sys.stderr,
        )
        return 2

    import anyio

    from little_loops.mcp_server.server import run_http, run_stdio

    if "--http" in argv or os.environ.get("LL_MCP_TRANSPORT") == "http":
        anyio.run(run_http)
    else:
        anyio.run(run_stdio)
    return 0


__all__ = ["main_mcp"]
