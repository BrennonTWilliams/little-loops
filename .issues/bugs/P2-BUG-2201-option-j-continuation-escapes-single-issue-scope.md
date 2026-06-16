---
id: BUG-2201
title: Option J continuation escapes single-issue scope and processes backlog
type: BUG
status: open
priority: P2
captured_at: '2026-06-16T20:52:46Z'
discovered_date: '2026-06-16'
discovered_by: capture-issue
---

# BUG-2201: Option J continuation escapes single-issue scope and processes backlog

## Summary

When an `ll-auto --only {id}` session inside `rn-implement` hits the context limit and triggers the Option J guillotine, the spawned continuation session has no scope constraint. It correctly finishes the interrupted issue but then freely picks up unrelated backlog issues and implements them — bypassing any queued loop that was waiting to process those issues.

## Current Behavior

- `rn-implement` runs `ll-auto --only ENH-2177` for a single issue
- The session exhausts its context window → Option J fires, spawning a fresh Claude session via `guillotine-prompt.md` + `/ll:resume`
- The continuation prompt (`issue_manager.py` run_dir path, ~line 340) adds a `sprint_framing` block only when `sprint_context is not None`
- For non-sprint single-issue runs, no scope constraint is emitted → the continuation is free to do anything
- In the observed incident, the continuation completed ENH-2177, then also implemented ENH-2197–2200 (which were queued in a separate `ll-loop run rn-implement ENH-2197,ENH-2198,ENH-2199,ENH-2200 -q`)

## Steps to Reproduce

1. Start `ll-loop run rn-implement` targeting a single issue (e.g., `ll-loop run rn-implement ENH-2177`)
2. Let the Claude session exhaust its context window — Option J fires and spawns a continuation session via `guillotine-prompt.md` + `/ll:resume`
3. Observe: the continuation session correctly finishes the original issue
4. Observe: the continuation session then picks up and implements additional backlog issues (e.g., ENH-2197–2200) without any scope constraint

## Expected Behavior

- The continuation prompt always includes a single-issue scope constraint when the original session was scoped to one issue
- After completing the interrupted issue, the continuation exits immediately without touching the backlog
- The queued loop wakes up and gracefully skips issues already marked `done`

## Root Cause

**`scripts/little_loops/issue_manager.py`** — `run_with_continuation()`, Option J run_dir path (~line 340):

```python
if sprint_context is not None:
    sprint_framing = (
        f"## Sprint Worker Context\n"
        f"You are a sprint worker. Process exactly ONE issue: "
        f"{sprint_context.issue_id}\n"
        ...
    )
```

The sprint framing (which enforces single-issue scope) is gated on `sprint_context is not None`. When invoked from the FSM loop via `ll-auto --only ENH-2177`, `sprint_context` is `None` even though `issue_path` is provided — so no constraint is emitted.

The same gap exists in **`scripts/little_loops/subprocess_utils.py`** — `assemble_guillotine_prompt()` — for the non-loop (non-run_dir) path, which also accepts `sprint_context` but has no `issue_id` fallback.

## Proposed Solution

Two changes, one issue:

### Fix A — Scope constraint in guillotine prompt (`issue_manager.py` + `subprocess_utils.py`)

**`issue_manager.py` run_dir path (~line 340):**
- When `sprint_context is None` but `issue_path is not None`, extract the issue ID from `issue_path` (parse the `id:` frontmatter field or derive from filename)
- Emit an equivalent scope block:
  ```
  ## Scope Constraint
  Complete exactly ONE issue: {issue_id}
  After completing this issue, exit immediately — do NOT process other issues.
  ```

**`subprocess_utils.py` `assemble_guillotine_prompt()`:**
- Add `issue_id: str | None = None` parameter
- When `sprint_context is None` but `issue_id` is provided, emit the same scope block

### Fix B — Pre-flight status check in `rn-implement.yaml`

Before the state that invokes `ll-auto --only {id}`, add a shell pre-check state:
- Read the issue's `status:` frontmatter via `ll-issues show {id} --field status` (or `grep`)
- If `done` or `cancelled`, route directly to `record_outcome` with outcome `IMPLEMENTED` (or `SKIPPED`)
- This makes the queued loop a true no-op for issues already completed out-of-band, regardless of whether Fix A holds

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` (~line 340): add single-issue scope constraint block when `sprint_context is None` and `issue_path is not None`
- `scripts/little_loops/subprocess_utils.py` — `assemble_guillotine_prompt()`: add `issue_id: str | None = None` parameter and emit scope block when `sprint_context` is absent
- `scripts/little_loops/loops/rn-implement.yaml` — add pre-flight status check state before the `ll-auto --only {id}` invocation

### Dependent Files (Callers/Importers)
- TBD — `grep -r "run_with_continuation\|assemble_guillotine_prompt" scripts/`

### Similar Patterns
- `sprint_framing` block in `issue_manager.py` — the new single-issue scope constraint mirrors this existing pattern

### Tests
- `scripts/tests/` — add test: Option J prompt for a single-issue run contains "Process exactly ONE issue"
- Existing Option J continuation tests must continue to pass

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Update `issue_manager.py` `run_with_continuation()`: when `sprint_context is None` and `issue_path is not None`, extract the issue ID and emit a `## Scope Constraint` block
2. Update `subprocess_utils.py` `assemble_guillotine_prompt()`: add `issue_id: str | None = None` parameter; emit scope block when `sprint_context` is absent but `issue_id` is provided
3. Update `rn-implement.yaml`: insert a pre-flight shell state before the `ll-auto` invocation that reads `status:` via `ll-issues show {id} --field status` and routes `done`/`cancelled` directly to `record_outcome`
4. Add regression test verifying the guillotine prompt for a single-issue run includes "Process exactly ONE issue"
5. Run existing Option J continuation tests to confirm no regressions

## Motivation

In the observed incident, a single continuation session implemented four issues that were reserved for a queued loop, causing the queued loop to become a no-op before it ever ran. Fix A removes the root cause; Fix B adds a cheap defensive guard so future out-of-band completions degrade gracefully.

## Acceptance Criteria

- [ ] Option J continuation for a single-issue `ll-auto --only {id}` run includes the scope constraint in `guillotine-prompt.md`
- [ ] `assemble_guillotine_prompt()` accepts and emits `issue_id` scope when `sprint_context` is absent
- [ ] `rn-implement` skips an issue at the pre-flight state if its status is already `done`/`cancelled`, routing to `record_outcome` without calling `ll-auto`
- [ ] Existing tests for Option J continuation pass
- [ ] New test: Option J prompt for a single-issue run contains "Process exactly ONE issue"

## Impact

- **Priority**: P2 — Continuation sessions can silently process and complete issues reserved for other queued loops, causing those loops to become no-ops and breaking expected execution order
- **Effort**: Small — Two focused additive changes in `issue_manager.py` and `subprocess_utils.py`, plus one new pre-flight state in `rn-implement.yaml`
- **Risk**: Low — Additive-only changes; new scope-constraint block activates only when `sprint_context is None` and `issue_path` is set (the previously uncovered path)
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-06-16T20:56:37 - `34d3fd47-b826-43e9-9c88-3a6f52440424.jsonl`
- `/ll:capture-issue` - 2026-06-16T20:52:46Z
