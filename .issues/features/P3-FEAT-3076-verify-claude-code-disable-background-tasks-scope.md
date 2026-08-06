---
id: FEAT-3076
title: Verify actual scope of CLAUDE_CODE_DISABLE_BACKGROUND_TASKS via a real host invocation
type: FEAT
priority: P3
status: open
testable: true
parent: FEAT-3060
labels:
- automation
- headless
- host-runner
---

# FEAT-3076: Verify actual scope of CLAUDE_CODE_DISABLE_BACKGROUND_TASKS via a real host invocation

## Summary

Determine, empirically, what `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` actually
disables when set in a real `claude` child process: only the `Bash`
`run_in_background` parameter, or also the synchronous-agent paths
`ll-parallel` relies on (subagent tool backgrounding). The vendored docs
(`docs/claude-code/settings.md:772`) describe the flag as disabling "all
background task functionality, including the `run_in_background` parameter on
Bash and subagent tools, auto-backgrounding" — but no test in this codebase
exercises a real subprocess to confirm this, and every existing test
(`test_fsm*.py`, `test_issue_manager.py`, `test_subprocess_utils.py`) mocks
`Popen`/`resolve_host`.

## Parent Issue

Decomposed from FEAT-3060: Hard-disable background tasks in headless
automation instead of instructing against them. Resolves that issue's
Acceptance Criterion 6 and its "open question worth answering before
implementing."

## Motivation

FEAT-3077 (carve-out decision) and FEAT-3078 (main implementation) both need
this answer before they can proceed correctly:

- If the flag also disables subagent-tool backgrounding, it would break the
  two known carve-outs (`manage-issue` smoke tests, `go-no-go`'s concurrent
  agent launch) more broadly than a Bash-only reading suggests, changing the
  carve-out decision in FEAT-3077.
- The implementation in FEAT-3078 should not ship AC1/AC2 as "done" against a
  reading of the docs alone when a five-minute manual check can confirm it
  directly.

## Expected Behavior

A documented, evidence-backed answer to: does
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in a `claude` child process's
environment reject only `Bash run_in_background: true` calls, or does it also
prevent the agent from launching background subagents (the mechanism
`ll-parallel` depends on)?

## Proposed Solution

Manually invoke the `claude` CLI (or a minimal harness script) with
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` set in its environment, and:

1. Attempt a `Bash` call with `run_in_background: true` — confirm it is
   rejected or behaves differently than without the flag.
2. Attempt to launch a subagent expected to run in the background (mirroring
   how `ll-parallel` invokes concurrent agents) — confirm whether it is also
   rejected or unaffected.
3. Record the findings (which calls are blocked, any error message/behavior
   observed) in this issue's Session Log / a Resolution note, in a form
   FEAT-3077 and FEAT-3078 can cite directly (e.g. "Bash `run_in_background`
   only; subagent launches unaffected" or the reverse).

This is a manual, out-of-suite verification step — no new automated test
harness exists for real subprocess execution, and building one is out of
scope here (this issue is the investigation, not new test infrastructure).

## Acceptance Criteria

1. The flag's actual scope is confirmed via a real host invocation (not
   inferred from documentation alone).
2. The finding — which call paths are blocked and which are not — is recorded
   in this issue in a form other issues can cite as evidence.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/claude-code/settings.md:772` | The only existing description of the flag's scope |
| `skills/manage-issue/SKILL.md:376-400` | Carve-out that depends on this answer (see FEAT-3077) |
| `skills/go-no-go/SKILL.md:174,274,278` | Second carve-out that depends on this answer (see FEAT-3077) |


## Session Log
- `/ll:issue-size-review` - 2026-08-06T05:11:26 - `c21cd57e-cb03-41ae-b233-cd39e3e2a29a.jsonl`
