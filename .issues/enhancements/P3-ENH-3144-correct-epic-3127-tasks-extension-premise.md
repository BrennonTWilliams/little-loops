---
id: ENH-3144
title: 'Correct EPIC-3127''s Tasks-extension premise: SDK 2.0.0 ships no io.modelcontextprotocol/tasks'
type: ENH
priority: P3
status: done
discovered_date: '2026-08-10'
discovered_by: learning-test
labels:
- multi-host
- mcp
parent: EPIC-3127
learning_tests_required:
- mcp extension mechanism
relates_to:
- FEAT-3145
program_design_not_applicable: true
testable: false
---

# ENH-3144: Correct EPIC-3127's Tasks-extension premise

## Summary

EPIC-3127 instructs the job tier to "wrap the Tasks extension, not invent a
protocol." That instruction rests on a premise that is false for the SDK the
project pins: `mcp==2.0.0` ships no `io.modelcontextprotocol/tasks`
implementation. Correct the epic body so the job tier is not planned against an
API that does not exist.

## Current Behavior

`.issues/epics/P3-EPIC-3127-*.md` lines 112–118 state that `job_start` /
`job_status` / `job_cancel` "maps 1:1 onto `tasks/get` / `tasks/cancel` plus
final-result retrieval from the formalized `io.modelcontextprotocol/tasks`
extension (SEP-2663)", and that inventing a parallel job primitive "would put
`ll-mcp` out of step with every other 2026-07-28-compatible server."

Open question 4 likewise asks whether `ll-mcp` should "advertise the Tasks
extension in its capabilities response."

Both read as though the extension is available to depend on.

## Expected Behavior

The epic states what is actually true of the pinned SDK: the extension is
specified but not implemented in `mcp==2.0.0`, so the job tier must build its own
`tasks/*` surface via the mechanism that does exist, shaped to SEP-2663 so it can
be swapped later at low cost. Open question 4 is reframed accordingly — it cannot
be answered by declaring an extension the SDK does not provide.

## Proven by learning test

`.ll/learning-tests/mcp-extension-mechanism.md` (`proven`, mcp 2.0.0, 6/6):

- No `io.modelcontextprotocol/tasks` extension ships. The only `EXTENSION_ID`
  defined anywhere in the installed package is `io.modelcontextprotocol/ui`
  (`mcp/server/apps.py:43`). No `tasks/*` method appears in
  `SPEC_CLIENT_METHODS`, and no module in the package has "task" in its name.
  `mcp/server/extension.py:59` names `tasks/get` only as a docstring example.
- The formal `Extension` API attaches via `MCPServer(extensions=[...])`; the
  lowlevel `Server` that `build_server()` uses has no `extensions` parameter. So
  even the extension mechanism as such is not reachable from `ll-mcp` as built.
- `Server.add_request_handler` *is* reachable and does dispatch a custom
  `tasks/get` over streamable HTTP — that is the real path, and it is what the
  corrected text should point at.

## Impact

Small edit, but it prevents the job tier from being scoped against a
non-existent dependency, and it removes a "just wrap the standard thing"
framing that would make the tier look cheaper than it is.

## Scope

- Rewrite the third bullet of EPIC-3127's "Spec target: MCP 2026-07-28" section.
- Reframe open question 4.
- Cite the learning test so the claim is checkable rather than asserted.

## Scope Boundaries

The same incorrect premise appears in a design document maintained outside this
repository. Correcting it there is a separate follow-up and is not part of this
issue.

## Acceptance Criteria

- EPIC-3127 no longer instructs the job tier to wrap an extension the pinned SDK
  does not implement.
- The corrected text names `Server.add_request_handler` as the available path and
  SEP-2663 as the shape to imitate.
- The learning-test record is cited by target name.

## Parent Issue

EPIC-3127 — `ll-mcp`: MCP server as little-loops' host-agnostic serving layer.

## Status

**Done** | Created: 2026-08-10 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-08-10T21:12:31 - `d5144cd9-13fc-478c-b6f8-d6862bb7b2e6.jsonl`
