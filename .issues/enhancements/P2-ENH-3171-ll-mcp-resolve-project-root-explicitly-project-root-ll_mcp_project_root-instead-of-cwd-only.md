---
id: ENH-3171
type: ENH
title: 'll-mcp: resolve project root explicitly (--project-root / LL_MCP_PROJECT_ROOT)
  instead of cwd only'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:24:42Z'
parent: EPIC-3127
labels:
- mcp
- multi-host
relates_to:
- BUG-3177
- ENH-3173
---

# ENH-3171: ll-mcp: resolve project root explicitly (--project-root / LL_MCP_PROJECT_ROOT) instead of cwd only

## Summary

`ll-mcp` resolves the project root as the process's current working directory and
nothing else — `tools.py::_project_root()` returns `Path.cwd()`, `tasks.py::_loops_dir()`
builds `BRConfig(Path.cwd())`, `server.py::build_server()` does the same for the
resource index, and `policy.py::check_tool_call()` does the same when its `config`
parameter is omitted (`policy.py:130`) — which every production caller does
(`tools.py:876`, `tasks.py:125`, `tasks.py:187`). There is no `--project-root` flag, no
config key, and no upward search for a `.ll/` marker.

The failure this produces is silent and total. An MCP host that spawns its servers from
`$HOME` (Claude Desktop and several GUI clients do) starts `ll-mcp` against `$HOME`, and
every surface then answers *truthfully about a project that does not exist there*:
`issues_query` returns `[]`, `deps_check` reports a clean graph, `resources/list` is
empty, `history_search` finds nothing. (`prompts/list` is the one surface *not* affected:
the prompt index resolves against the plugin root via `_find_plugin_root()`, not cwd —
its failure modes are install-source-dependent and belong to BUG-3177, which deliberately
keeps the skills root a separate resolution from the project root. Do not fold the two
together.) No tool errors, no warning on startup — the server looks healthy and is
useless.

The policy site is the security-relevant one: the transport-policy grants
(`mcp.transport_policy` → `allow_mutations` / `allow_tasks`) are read from whatever
directory the host spawned from. Spawned from `$HOME`, `check_tool_call` evaluates
mutation and task policy against a nonexistent config — falling back to schema defaults —
instead of the project's actual `.ll/ll-config.json`. The resolved root must reach this
path too, or this issue ships with the same class of bug it fixes.

`docs/guides/MCP_SERVER_GUIDE.md`
already calls this "the single most common cause of a 'working but useless' `ll-mcp`" and
documents two workarounds (a client `cwd` field, or `sh -c 'cd … && exec ll-mcp'`), which
is an admission that the server should accept the root itself.

## Proposed change

Accept an explicit project root, in precedence order: a `--project-root PATH` argument
parsed in `main_mcp`, then `LL_MCP_PROJECT_ROOT`, then `Path.cwd()` as today. The resolved
root must reach *every* call site — the **four** named above (`tools._project_root`,
`tasks._loops_dir`, `server.build_server`'s `BRConfig` line, and
`policy.check_tool_call`'s omitted-`config` fallback) are the full set, and the
per-request statelessness invariant means it cannot simply be cached at module scope; it
should be threaded through the same factory-closure shape `transport` already uses
(FEAT-3168) rather than becoming a module global. For the policy site, the natural shape
is passing an explicit `config` (or root) from the three callers that currently omit it,
rather than teaching `check_tool_call` a new resolution path.

Note `main_mcp` today is deliberately not an `argparse` CLI (it checks a bare `--http`
literal). Adding one flag does not require changing that posture, but a second flag is the
point where a real parser starts paying for itself — decide that explicitly rather than
accreting literals. **Coordinate with ENH-3173** (`--host` / `--port` for the HTTP
transport): whichever of the two lands first should make the argparse call once, and the
second builds on it instead of accreting another bare-literal check or independently
introducing a parser.

## Secondary: fail loudly on a non-project root

Independently of the flag, a resolved root with no `.ll/` directory and no `.issues/`
directory should be reported — a stderr line at startup, or a `capabilities` field. The
silence is what makes the misconfiguration expensive; a client that swallows stderr still
gets the signal through `capabilities`, which is the one tool a user runs first when
verifying the server.


## Current Behavior

`ll-mcp` (and `ll-mcp --http`) always operates on `Path.cwd()`. Pointing it at a specific
project requires the host to control the spawn cwd, or a shell wrapper
(`sh -c 'cd /abs/path && exec ll-mcp'`). Against a non-project directory every surface
returns empty successfully.

## Expected Behavior

- `ll-mcp --project-root /abs/path` serves that project regardless of spawn cwd.
- `LL_MCP_PROJECT_ROOT=/abs/path ll-mcp` does the same, for hosts whose config exposes
  `env` but not `args`.
- With neither set, behavior is unchanged (`Path.cwd()`).
- A resolved root containing neither `.ll/` nor `.issues/` produces a visible signal
  rather than silently-empty results.

## Impact

- **Priority**: P2 - Documented as the most common `ll-mcp` misconfiguration, and it
  fails silently rather than loudly. It gates usable adoption on every GUI host.
- **Effort**: Small - Four call sites (`tools._project_root`, `tasks._loops_dir`,
  `server.build_server`, and the omitted-`config` fallback in `policy.check_tool_call` —
  fixed at its three callers) plus `main_mcp` argument handling; the factory-closure
  threading pattern already exists from FEAT-3168.
- **Risk**: Low - Purely additive; the no-flag path keeps today's semantics.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-15T01:18:59 - `6343db1a-2326-4ea0-a5fc-0b0d7d522516.jsonl`
