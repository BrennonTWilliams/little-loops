---
id: 3145
title: 'll-mcp: tasks/* run-dispatch surface via Server.add_request_handler (tier-3,
  evidence-gated)'
type: FEAT
priority: P3
status: open
discovered_date: '2026-08-10'
discovered_by: learning-test
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp extension mechanism
depends_on:
- FEAT-3143
- ENH-3144
relates_to:
- FEAT-3143
confidence_score: 53
outcome_confidence: 43
score_complexity: 13
score_test_coverage: 10
score_ambiguity: 5
score_change_surface: 15
missing_artifacts: true
---

# FEAT-3145: ll-mcp: tasks/* run-dispatch surface via Server.add_request_handler

## ⚠ Gated — do not implement before the tier-3 evidence gate opens

EPIC-3127 holds the job tier behind an explicit gate: long-running orchestration
is "built only if real usage of the first two tiers shows hosts wanting to
*drive* runs rather than plan them." That evidence does not exist yet. This issue
is captured so the proven mechanism and the design shape are not lost, **not**
because the gate has opened. Anything that spawns an agent or runs for minutes
stays off the tool surface until it has.

## Summary

Expose long-running little-loops work (`ll-loop run`, `ll-queue` entries) over
MCP as a `tasks/*` request surface — start, poll, cancel, retrieve result —
registered through `Server.add_request_handler` on the existing lowlevel server,
and shaped to match SEP-2663 so it can be replaced by the official
`io.modelcontextprotocol/tasks` extension when an SDK ships one.

## Current Behavior

`ll-mcp` serves five read-only tools. Orchestration (`ll-auto`, `ll-parallel`,
`ll-loop`, `ll-action invoke`) is deliberately absent from the tool surface —
correctly, since a tool call that runs for minutes does not fit the tools
primitive. There is no other way to reach a run from an MCP host.

## Expected Behavior

A small set of custom methods — shaped as `tasks/get`, `tasks/cancel`, and a
start path — dispatch to the existing run machinery, so a host can begin a run,
poll it, and collect its result without the call itself being long-running.
Progress rides `subscriptions/listen` rather than a bespoke notification channel.

## Proven by learning test

`.ll/learning-tests/mcp-extension-mechanism.md` (`proven`, mcp 2.0.0, 6/6):

- **The mechanism works today.** `Server.add_request_handler("tasks/get",
  TasksGetParams, handler)` on the unmodified `build_server()` server dispatched
  over streamable HTTP and returned the handler's result, with wire params
  validated through the camelCase alias (`taskId`). No `MCPServer` migration
  required.
- The formal `Extension` API is *not* the path: it attaches via
  `MCPServer(extensions=[...])`, and the lowlevel `Server` has no `extensions`
  parameter.
- `MethodBinding` enforces additive-only naming (a spec method such as
  `tools/list` raises `ValueError`), which is the same boundary a custom
  `tasks/*` surface should respect.
- `MethodBinding.protocol_versions` gates a method by wire version; an empty
  frozenset raises at construction.
- MRTR is available for any step needing human input mid-flight:
  `INPUT_REQUIRED_METHODS` covers `prompts/get`, `resources/read`, and
  `tools/call`, with `is_input_required` as the TypeGuard.

## Design constraint: imitate SEP-2663, do not diverge from it

The value of matching the spec's shape is that swapping to the official
extension later becomes a registration change rather than a client-visible
protocol change. Method names, params, and result shapes should track SEP-2663
even though nothing enforces that today.

## Dependencies

- **FEAT-3143** — the surface is most useful over HTTP; stdio-only dispatch has
  little reason to exist.
- **ENH-3144** — the epic's guidance must be corrected first, or this issue reads
  as contradicting its own parent.

## Anti-goals

- Do not advertise `io.modelcontextprotocol/tasks` in the capabilities response.
  The server would be claiming an extension it implements privately. This is
  EPIC-3127 open question 4 and it stays closed until an SDK ships the extension.
- Do not turn `ll-auto` / `ll-parallel` into tools as a side effect.

## Acceptance Criteria

*(To be settled when the gate opens — captured now only as intent.)*

- A run can be started, polled, and cancelled from an MCP host without any
  request being long-running.
- Method and result shapes are traceable line-by-line to SEP-2663.
- The capabilities response does not claim the official extension.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.
Tier 3 (job API), evidence-gated.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-10_

**Readiness Score**: 53/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 43/100 → LOW

### Concerns
- The issue itself states it is gated: "do not implement before the tier-3 evidence gate opens." The tier-3 evidence trigger (hosts wanting to *drive* runs, not just plan them) has not been observed yet, per EPIC-3127.
- `depends_on: FEAT-3143` is still `open` — the HTTP transport this surface is "most useful over" per the Dependencies section does not exist yet.
- Acceptance Criteria are explicitly marked "(To be settled when the gate opens — captured now only as intent.)" — not testable as written.

### Gaps to Address
- `## Program Design` section is missing entirely (Program Design gate fails: `ll-issues check-design FEAT-3145` exits 1). Populate it with concrete types/signatures/call path once the gate opens, or set `program_design_not_applicable: true` if this stays a captured-intent placeholder until then.
- Resolve `FEAT-3143` (HTTP transport) before implementation — it is the more load-bearing of the two `depends_on` entries.
- Acceptance Criteria need to be settled with real, testable statements once the tier-3 evidence gate opens.

### Outcome Risk Factors
- High ambiguity: method/result shapes must track SEP-2663 "even though nothing enforces that today" — no automated check ties the implementation to the spec.
- No test coverage yet for the `tasks/*` handlers themselves (only the underlying mechanism is covered, via the proven learning test).

## Status

**Open (gated)** | Created: 2026-08-10 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-10T21:19:52 - `c399e98c-b001-4568-9896-227421406281.jsonl`
