---
id: FEAT-3118
title: Wire pre_done consult trigger into the Stop hook
type: FEAT
parent: FEAT-3038
priority: P3
status: open
testable: true
verify_verdict: VALID
discovered_date: 2026-08-08
depends_on:
- FEAT-3116
- FEAT-3120
labels:
- planning-hub
---

# FEAT-3118: Wire pre_done consult trigger into the Stop hook

## Summary

Child 3 of 3 decomposed from FEAT-3038 (Advisor signal-gated auto-consults and
per-task budget). Adds the `pre_done` signal: a new `Stop` hook entry that
dispatches to a host-agnostic handler, calling `should_consult`/
`consult_for_trigger` on the final diff before a task is declared done.
Depends on FEAT-3116 for `should_consult` and `consult_for_trigger`.

## Parent Issue

Decomposed from FEAT-3038: Advisor signal-gated auto-consults and per-task
budget. See that issue's "Proposed Solution" → "Trigger dispatch" →
`pre_done` subsection and its codebase research on the contested `Stop`-hook
shape and hook-intent registration sites.

## Current Behavior

`hooks/hooks.json:199-230` — the `Stop` event runs three shell scripts
(context-handoff-sentinel, session-cleanup, record-hook-event); none dispatch
through `python -m little_loops.hooks`.
<!-- ll-prose-ok: pre_done does not exist yet — this sentence documents its absence, the reason this feature is being proposed -->
No `pre_done` intent exists in
`hooks/__init__.py`'s `_INTENT_EVENT_NAME`, `_USAGE`, or `_dispatch_table()`.

**Contested convention to resolve**: existing `Stop` entries have no
`"matcher"` key and route through bash-only scripts under `hooks/scripts/`.
The only other Python-dispatched adapters (`SubagentStart`/`SubagentStop`,
`hooks/hooks.json:277-302`) use `"matcher": "*"` and route through
`hooks/adapters/claude-code/*.sh` (two-line `INPUT=$(cat) | python3 -m
little_loops.hooks <intent>` shape, e.g.
`hooks/adapters/claude-code/precompact.sh`). This issue follows the
`SubagentStart`/`SubagentStop` shape (`"matcher": "*"` +
`hooks/adapters/claude-code/`) since it is the only demonstrated pattern for a
Python-dispatched hook — the pre_done entry is the first `Stop` entry to use
it.

## Expected Behavior

The `Stop` hook, on the final diff, auto-consults with signal `pre_done`
before a task is declared done, when `pre_done` is listed in
`advisor.triggers`. An unlisted trigger or `advisor.enabled: false` fires no
consult. A failed or timed-out consult never blocks session end — the hook
completes normally with a logged warning.

**"Final diff" specification (settled 2026-08-23; previously undefined)**:
the consult context is the output of `git diff HEAD` (staged + unstaged
changes vs `HEAD`) run from the project root at Stop time, plus
`git status --porcelain` for untracked files, truncated to a fixed cap
(~400 lines with an explicit truncation marker) before being passed as
`context`. **Empty-diff no-op**: the `Stop` event fires on *every* session
stop, not only when a task is being declared done — if `git diff HEAD` is
empty and there are no untracked files (or the CWD is not a git work tree),
the handler exits 0 without consulting and without spending budget. This is
what keeps an enabled `pre_done` trigger from consulting on every
conversational session end.

## Proposed Solution

- Add a `pre_done` intent across all three dispatch sites in
  `hooks/__init__.py`, kept consistent by
  `test_hook_intents.py::test_dispatch_table_intent_event_name_usage_stay_consistent`
  (`:827-855`): `_INTENT_EVENT_NAME` (`:68-80`), `_USAGE` (`:111-116`),
  `_dispatch_table()` (`:134-165`).
- New handler `scripts/little_loops/hooks/pre_done.py`, following the
  existing handler layout (`pre_compact.py`, `drift_check.py`): wraps its body
  in try/except returning exit 0 regardless of outcome (the same fail-soft
  contract documented at `hooks/__init__.py:40-43`). Assembles the final
  diff per the specification above (`git diff HEAD` + `git status
  --porcelain`, capped, empty-diff → exit 0 no-op). Calls
  `should_consult("pre_done", config)` (from FEAT-3116); if `True`, calls
  `consult_for_trigger("pre_done", question=..., context=<the capped diff>)`.
  `LLHookEvent.session_id` (`main_hooks()`, `hooks/__init__.py:203`) feeds
  `resolve_task_key()`'s session-ID fallback tier.
- New adapter `hooks/adapters/claude-code/stop.sh` (or extend the existing
  `Stop` entry set), copying the two-line
  `INPUT=$(cat) | python3 -m little_loops.hooks pre_done` shape from
  `hooks/adapters/claude-code/precompact.sh`.
- New `Stop` entry in `hooks/hooks.json:199-230` with `"matcher": "*"`,
  alongside (not replacing) the existing three shell scripts.

## Acceptance Criteria

1. The `Stop` hook triggers exactly one consult with signal `pre_done` when
   `pre_done` is listed in `advisor.triggers` (FEAT-3038 AC #2).
2. `pre_done` absent from `advisor.triggers` fires no consult on this path;
   `advisor.enabled: false` fires none either (FEAT-3038 AC #3, pre_done
   half).
3. A `Stop` event with an empty `git diff HEAD` and no untracked files (or a
   non-git CWD) fires no consult and spends no budget — the handler exits 0
   silently (the empty-diff no-op above).
4. A failed or timed-out consult never blocks session end — the `Stop` hook
   completes normally (exit 0) with a logged warning (FEAT-3038 AC #7,
   pre_done half).
5. `_INTENT_EVENT_NAME`, `_USAGE`, and `_dispatch_table()` stay in sync per
   `test_dispatch_table_intent_event_name_usage_stay_consistent`.
6. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.

## Tests

- `scripts/tests/test_hook_intents.py` — `pre_done` added to
  `test_dispatch_table_intent_event_name_usage_stay_consistent`; a
  `TestHooksMainModule` happy-path subprocess smoke test (per
  `test_dispatch_subagent_start_happy_path:520-533`) and a malformed-payload
  variant (per `test_dispatch_subagent_start_malformed_payload:534-544`);
  trigger-unlisted no-op case; empty-diff/non-git-CWD no-op case (AC #3).
- `scripts/tests/test_advisor.py` (or a new `test_pre_done_hook.py`) — mocked
  `consult()` failure leaves the hook's exit code at 0 and logs a warning.

## Documentation

- `.claude/CLAUDE.md` — hooks section.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — the new `pre_done` intent.
- `docs/reference/CLI.md`, `docs/reference/API.md` — if the new handler
  introduces any CLI-visible or importable surface beyond the dispatch table.

## Impact

- **Priority**: P3 — matches parent FEAT-3038.
- **Effort**: Small-Medium — new hook intent plumbing across three dispatch
  sites, but the budget/identity work is already available from FEAT-3116.
- **Risk**: Medium — adds a synchronous network call to the `Stop` hook, a hot
  path; mitigated by fail-soft semantics and off-by-default triggers
  (unchanged from parent's risk assessment).
- **Breaking Change**: No — inert unless `advisor.triggers` lists `pre_done`.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1 (pair LLM judgment with a
  non-LLM signal).

## Status

**Open** | Created: 2026-08-08 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:56 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:51:42 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:issue-size-review` - 2026-08-08T21:18:50 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
