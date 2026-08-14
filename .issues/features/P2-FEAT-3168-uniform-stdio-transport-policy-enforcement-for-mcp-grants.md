---
id: FEAT-3168
type: FEAT
title: "ll-mcp: enforce stdio transport policy for both grants across all three guarded surfaces"
priority: P2
status: open
discovered_by: issue-review
discovered_date: '2026-08-14'
captured_at: '2026-08-14T22:40:00Z'
parent: EPIC-3127
labels:
- multi-host
- mcp
- security
relates_to:
- FEAT-3145
- FEAT-3149
- FEAT-3151
size: Medium
testable: true
---

# FEAT-3168: ll-mcp — enforce stdio transport policy for both grants

## Summary

`mcp.transport_policy.stdio.*` is **advisory today: setting any of its knobs to `false`
has no effect.** The policy decision function is only ever called from the HTTP
transport's ASGI middleware, so over stdio nothing consults it. An operator who
deliberately locks down stdio gets silent non-enforcement.

This issue plumbs transport identity into the handler layer so the same
`check_tool_call` decision applies on both transports.

(Two config grants — `allow_mutations` and `allow_tasks` — covering three guarded
surfaces: the mutation tools, `tasks/*`, and `loop_start`.)

## Current Behavior

`policy.check_tool_call` (`scripts/little_loops/mcp_server/policy.py`) encodes all three
grants correctly. It has exactly **one call site** in the package:
`TransportPolicyMiddleware`, which is HTTP-only (`server.py::build_http_app` wraps the
ASGI app; `run_stdio` has no equivalent). The handlers themselves
(`tools.py::handle_call_tool`, `tasks.py::handle_tasks_get`/`handle_tasks_cancel`) never
invoke the policy.

Consequences over stdio:

- `stdio.allow_mutations: false` does not stop FEAT-3149's four mutation tools.
- `stdio.allow_tasks: false` does not stop FEAT-3145's `tasks/get` / `tasks/cancel`.
- `stdio.allow_tasks: false` does not stop FEAT-3151's `loop_start` — which spawns an
  agent with the project's full tool permissions.

The gap predates FEAT-3151; that issue's Decision 8 recorded it explicitly, accepted it
rather than half-fixing it for one tool, and owed this follow-up. `MCP_SERVER_GUIDE.md`
already documents the knobs as advisory, so this is a known gap, not a silent one.

## Expected Behavior

`check_tool_call` reaches its decision on **both** transports. A denied call over stdio
returns the same `-32001` JSON-RPC error the HTTP path returns (minus the HTTP 403, which
has no stdio analogue), for both grants and all three guarded surfaces uniformly.

## Motivation

The default posture is unaffected — stdio defaults open, and it is a same-machine,
same-user channel, so this is not a live exposure. What is wrong is that a **setting the
config schema advertises does nothing**. An operator hardening a shared or automation-run
workstation sets `stdio.allow_tasks: false`, reads no warning, and believes run control is
off when it is not. A knob that silently no-ops is worse than an absent one.

`loop_start` raises the stakes enough to be worth doing now rather than deferring
indefinitely: it is the only MCP surface that spawns an agent.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_server/server.py` — `build_server()` currently takes no
  parameters and is transport-agnostic. Handlers need to know which transport they are
  serving. Note `test_build_server_signature_unchanged`
  (`test_feat_3143_mcp_http_transport.py:67-69`) pins the zero-parameter signature — see
  Open Questions.
- `scripts/little_loops/mcp_server/tools.py` — `handle_call_tool` gains the policy check
  (guard 0, ahead of FEAT-3149's dry-run guard 1).
- `scripts/little_loops/mcp_server/tasks.py` — `handle_tasks_get` / `handle_tasks_cancel`
  likewise.
- `scripts/little_loops/mcp_server/policy.py` — `check_tool_call` itself should not need
  to change; it already takes `transport` as a parameter.

### Similar Patterns
- `TransportPolicyMiddleware` (`policy.py`) is the model for the denial shape (`-32001`,
  the reason string).

### Tests
- New module `test_feat_3168_stdio_policy_enforcement.py`, modeled on
  `test_feat_3149_transport_policy.py` but driving the stdio server. Note BUG-3167's
  fix to the stdio test harness (do not close stdin early) applies here.
- Assert all three guarded surfaces deny over stdio when their grant is set to `false`,
  and that the default-open
  posture is unchanged when unset.

### Documentation
- `docs/guides/MCP_SERVER_GUIDE.md` — remove the "stdio knobs are currently advisory"
  paragraph once this lands. It is currently accurate and must not be removed before.
- `docs/reference/CLI.md` — `### ll-mcp` transport policy notes.

## Open Questions

1. **How does transport identity reach the handlers?** Options: (a) parameterize
   `build_server(transport=...)` and close over it in the handler factories — simplest,
   but breaks `test_build_server_signature_unchanged`, which would need a sanctioned
   edit; (b) a context variable set by `run_stdio`/`build_http_app`; (c) read it off the
   `ServerRequestContext` if the SDK exposes anything usable. (a) is the obvious default
   unless (c) turns out to be free.
2. **Should the HTTP middleware stay?** If handlers enforce uniformly, the middleware
   becomes a redundant early-out. Keeping it is still worthwhile: it denies *before* the
   JSON-RPC body is parsed, which is the property FEAT-3149 wanted. Recommend keeping
   both and asserting they agree.

## Acceptance Criteria

1. With `mcp.transport_policy.stdio.allow_mutations: false`, a `tools/call` naming a
   `MUTATING_TOOLS` member over stdio is denied with `-32001`.
2. With `mcp.transport_policy.stdio.allow_tasks: false`, `tasks/get` and `tasks/cancel`
   over stdio are denied with `-32001`.
3. With `mcp.transport_policy.stdio.allow_tasks: false`, `loop_start` over stdio is
   denied with `-32001` and **no process is spawned**.
4. With the knobs unset, stdio behavior is unchanged from today (default open) — no
   existing test in `test_mcp_server.py` needs modifying to accommodate this.
5. HTTP enforcement is unchanged; `test_feat_3149_transport_policy.py` passes unmodified.
6. The "advisory" paragraph is removed from `MCP_SERVER_GUIDE.md` in the same change.
7. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 — not a live exposure (stdio is same-machine/same-user and defaults
  open), but a config knob that silently does nothing is a correctness and trust defect,
  and it now guards a run-spawning tool.
- **Effort**: Medium — the decision logic already exists and is already parameterized by
  transport; the work is plumbing identity into the handler layer plus a new test module.
- **Risk**: Low-Medium — touches the dispatch path of every tool. The default-open
  posture (AC 4) is what keeps it from breaking existing users.
- **Breaking Change**: No for anyone on defaults. For an operator who *had* set a stdio
  knob to `false`, behavior changes from "silently ignored" to "enforced" — which is the
  point, and should be called out in the changelog.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.

## Related Key Documentation

- [`docs/guides/MCP_SERVER_GUIDE.md`](../../docs/guides/MCP_SERVER_GUIDE.md)

## Status

**Open** — filed as FEAT-3151's owed Decision 8 follow-up | Created: 2026-08-14 | Priority: P2
