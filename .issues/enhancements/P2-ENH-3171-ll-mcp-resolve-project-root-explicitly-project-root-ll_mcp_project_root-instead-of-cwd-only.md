---
id: ENH-3171
type: ENH
title: 'll-mcp: resolve project root explicitly (--project-root / LL_MCP_PROJECT_ROOT)
  instead of cwd only'
priority: P2
status: done
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:24:42Z'
completed_at: '2026-08-15T06:54:40Z'
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


## Program Design

### Types

- `project_root: Path | None` — the resolved root, `None` only transiently before
  precedence resolution runs.

### Signatures

- `main_mcp(argv: list[str] | None = None) -> int` — gains a `--project-root PATH` scan
  alongside the existing bare `--http` check, plus `os.environ.get("LL_MCP_PROJECT_ROOT")`
  as fallback, mirroring the existing `LL_MCP_TRANSPORT` env pattern.
- `build_server(transport: str, project_root: Path) -> Server` — new `project_root`
  parameter, replacing the function's own `BRConfig(Path.cwd())` construction.
- `_project_root(explicit: Path | None = None) -> Path` — precedence
  `explicit or env or Path.cwd()`, threaded the same way `transport` already is rather
  than resolved fresh via `Path.cwd()`.
- `check_tool_call(transport: str, method: str, tool_name: str | None, config: BRConfig | None = None) -> PolicyDecision` — signature unchanged; its three callers stop omitting `config` and pass `config=BRConfig(project_root)` explicitly.

### Call Path

- `main_mcp` resolves `project_root` once, then calls `run_http`/`run_stdio` in
  `server.py`, which threads it into `build_server`.
- `build_server` replaces its own `BRConfig(Path.cwd())` call with the passed-in
  `project_root` and threads it into the same factory-closure shape `transport` already
  uses (FEAT-3168) when constructing the tool/task handlers — not a module global, per
  the per-request statelessness invariant.
- `tools._project_root` and `tasks._loops_dir` receive `project_root` through that
  closure instead of calling `Path.cwd()` themselves.
- `check_tool_call`'s three callers — `handle_tasks_get` (inside
  `make_tasks_get_handler`), `handle_tasks_cancel` (inside `make_tasks_cancel_handler`),
  and `handle_call_tool` (inside `make_call_tool_handler`) — pass
  `config=BRConfig(project_root)` instead of omitting `config`, which today falls through
  to `check_tool_call`'s own `BRConfig(Path.cwd())`.

### Deviations

- 2026-08-15: `policy.TransportPolicyMiddleware.__call__` — the ASGI pre-parse gate that
  invokes `check_tool_call` before `handle_call_tool` ever runs on the HTTP path — also
  omitted `config` and fell through to `BRConfig(Path.cwd())`, the same bug class this
  issue fixes, but it wasn't one of the three callers named in the Call Path above (only
  `handle_tasks_get`, `handle_tasks_cancel`, and `handle_call_tool` were). Left unfixed, a
  wrong pre-parse decision (denying what the project's real config allows) would have
  persisted on HTTP even after the three named callers were corrected. Threaded
  `project_root` into `TransportPolicyMiddleware.__init__` (optional, default `None` —
  callers that construct it directly, e.g. tests, keep today's `Path.cwd()` fallback
  behavior) and had `build_http_app` pass the resolved root, so it now builds
  `config=BRConfig(project_root)` the same way the three named callers do.

## Scope Boundaries

- **In scope**: the `--project-root` flag / `LL_MCP_PROJECT_ROOT` env var, threading the
  resolved root through the four call sites above, and the non-project-root startup
  signal described in "Secondary: fail loudly on a non-project root".
- **Out of scope**: BUG-3177's skills-root resolution (`_find_plugin_root()`), which is
  deliberately a separate resolution from the project root and must not be folded in;
  ENH-3173's `--host`/`--port` HTTP transport flags, which this issue only coordinates
  argument-parsing posture with, not implements.

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
- `/ll:manage-issue` - 2026-08-15T06:54:22 - `3b700215-e377-45c6-a681-7712906c616f.jsonl`
- `/ll:ready-issue` - 2026-08-15T06:23:32 - `543bf66e-4713-4227-8003-f6942797c831.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-15T01:18:59 - `6343db1a-2326-4ea0-a5fc-0b0d7d522516.jsonl`
