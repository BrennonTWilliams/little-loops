---
id: BUG-3005
title: ll-auto's run summary reports attempted-and-failed issues as "filtered out",
  contradicting its own log
type: BUG
priority: P4
captured_at: '2026-08-02T18:59:27Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- ll-auto
- issue-manager
- diagnostics
relates_to:
- BUG-3004
status: open
testable: true
---

# BUG-3005: ll-auto reports attempted-and-failed issues as "filtered out"

## Summary

When `ll-auto --only <ID>` attempts an issue and the attempt fails, the exit
summary re-derives an eligibility reason from the dependency graph rather than
reporting what actually happened. Because the issue is still open, unblocked, and
acyclic, it falls through every modeled branch to the catch-all `"filtered out"`
— directly contradicting the line logged seconds earlier.

Observed on `ll-auto --only BUG-3002` (2026-08-02):

```
[13:47:27] Issue BUG-3002 was attempted but verification failed
...
[13:47:27]   BUG-3002: filtered out
```

"Filtered out" sends the operator hunting for a selection-filter bug that does
not exist.

## Steps to Reproduce

1. Pick an open, unblocked issue that `ll-auto` will attempt but fail to complete
   (e.g. any issue whose Phase 2 exits without code changes — see BUG-3004 for a
   reliable trigger).
2. Run `ll-auto --only <ISSUE-ID>`.
3. Observe the log emits `Issue <ID> was attempted but verification failed`.
4. Observe: the `PROCESSING SUMMARY` block that follows reports
   `<ID>: filtered out`.

## Current Behavior

`AutoManager._unreachable_reason()` in `scripts/little_loops/issue_manager.py`
builds the exit-1 message by recomputing eligibility from scratch against
`self.dep_graph`. It models four cases: `not_found`, `already_<status>`, `in a
dependency cycle`, and `blocked by: <ids>`. An issue that was selected, attempted,
and failed matches none of them — it is still `open`, has no blockers, and is not
in a cycle — so it reaches the final `else` branch and is labeled `filtered out`.

The function has no knowledge of what happened during the run; it is a pure
re-derivation from graph state, called after processing has already concluded.

## Expected Behavior

The summary should report the outcome that actually occurred. An issue that was
attempted should never be described in terms of eligibility filtering.

Expected for the observed run:

```
[13:47:27]   BUG-3002: attempted, verification failed
```

More generally: `_unreachable_reason()` should first consult what the run
actually did with the ID, and only fall back to graph re-derivation for IDs that
were never selected. The `filtered out` catch-all should remain reachable only
for genuinely unexplained non-selection, and — since it is by construction a
"reason unknown" label — should say so rather than implying a filter matched.

## Motivation

This is a diagnostics defect, and its whole cost is misdirected engineering time.
Investigating the BUG-3002 run, the contradiction between "attempted but
verification failed" and "filtered out" invited a search for a nonexistent
selection filter before the real cause (the confidence gate, BUG-3004) surfaced.

The summary block is the artifact an operator reads first after an unattended
run — often the only thing they read. It is the one place a wrong answer costs
the most.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in method AutoManager._unreachable_reason()`
- **Cause**: The method is called after processing but derives its answer purely
  from pre-run graph state (`self.dep_graph`, `self.state_manager.state.completed_issues`),
  which cannot distinguish "never selected" from "selected, attempted, failed".
  Attempted-and-failed is not a modeled case, so it silently lands in the final
  `else: reasons.append(f"{issue_id}: filtered out")` branch. The per-issue
  outcome is known at that point — `AutoManager._process_issue()` returns it and
  the "attempted but verification failed" line is emitted from the same run — but
  it is never recorded anywhere `_unreachable_reason()` can see.

## Proposed Solution

Record per-issue outcomes during the run and consult them before falling back to
graph re-derivation.

1. **Track attempts.** Add an instance attribute to `AutoManager.__init__`:

   ```python
   self._attempted: dict[str, str] = {}   # issue_id -> short outcome reason
   ```

   Populate it in `_process_issue()` on every terminal path, reusing the
   `failure_reason` already carried on `IssueProcessingResult` so the summary
   inherits whatever detail the phase produced (including BUG-3004's
   `below_readiness_threshold (80 < 85)`).

2. **Consult it first** in `_unreachable_reason()`, before the cycle and blocker
   checks:

   ```python
   for issue_id in matches:
       if issue_id in self._attempted:
           reasons.append(f"{issue_id}: attempted, {self._attempted[issue_id]}")
           continue
       ...
   ```

3. **Make the catch-all honest.** Replace the bare `filtered out` with something
   that names its own uncertainty — e.g. `not selected (no filter matched)` — so
   a future occurrence reads as "we don't know" rather than as a positive claim
   that a filter excluded it.

Keep `_unreachable_reason()` free of I/O; it should read only in-memory run
state, as it does today.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `AutoManager.__init__`
  (new `_attempted` dict), `AutoManager._process_issue` (record outcomes),
  `AutoManager._unreachable_reason` (consult first, reword catch-all)

### Dependent Files (Callers/Importers)
- `AutoManager.run()` — sole caller of `_unreachable_reason()`; verify the exit-1
  path and return-code semantics are untouched (this is a message-only change)

### Similar Patterns
- `AutoManager._log_blocked_issues()` — the other summary-reporting method;
  check whether it has the same "re-derive rather than report" shape

### Tests
- `scripts/tests/` — new test: an attempted-and-failed `--only` issue yields a
  summary reason containing `attempted`, not `filtered out`
- New test: a genuinely blocked / cycled / not-found `--only` issue still
  produces its existing reason string (no regression in the four modeled cases)
- Verify no existing test asserts on the literal string `"filtered out"` before
  rewording the catch-all

### Documentation
- None expected — log-message wording only

### Configuration
- N/A

## Program Design

### Types

- `AutoManager._attempted: dict[str, str]` — issue_id -> short outcome reason,
  populated during the run

### Signatures

- `_unreachable_reason(self, requested_id: str) -> str`
- `_process_issue(self, info: IssueInfo) -> bool`

Both signatures are unchanged. `_unreachable_reason` gains a
`self._attempted` lookup ahead of graph re-derivation; `_process_issue` now
writes `self._attempted[info.issue_id]` on every terminal path.

### Call Path

`AutoManager.run` -> `AutoManager._process_issue` -> writes `self._attempted`;
later `AutoManager.run` -> `AutoManager._unreachable_reason` -> reads
`self._attempted`, falling back to `self.dep_graph.get_blocking_issues` /
`detect_cycles` only for IDs never attempted.

## Implementation Steps

1. Add `self._attempted` to `AutoManager.__init__` and populate it from
   `IssueProcessingResult.failure_reason` on every terminal path in
   `_process_issue()`.
2. Consult `self._attempted` at the top of the per-ID loop in
   `_unreachable_reason()`.
3. Reword the catch-all to name its own uncertainty; grep the test suite for the
   old literal first.
4. Add tests for attempted-and-failed plus the four existing reason cases; run
   `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P4 - Cosmetic in mechanism, but it actively misdirects diagnosis
  of real failures. No functional effect: exit codes and processing behavior are
  unchanged. Worth fixing alongside BUG-3004, whose failures surface through this
  exact path.
- **Effort**: Small - One dict, one lookup, one string change, plus tests. No new
  dependencies, no I/O, no signature changes.
- **Risk**: Low - Message-only change confined to one class. The only regression
  surface is a test asserting on the old literal string, which step 3 checks for
  explicitly.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance | Why |
|----------|-----------|-----|
| `docs/reference/API.md` | Medium | Documents `little_loops.issue_manager`, where `AutoManager` gains the `_attempted` outcome map |

## Labels

`bug`, `captured`, `ll-auto`, `diagnostics`

## Session Log
- `/ll:capture-issue` - 2026-08-02T19:02:30 - `97be14aa-df1e-4353-ae1f-24a9a6e1da2f.jsonl`

---

## Status

**Open** | Created: 2026-08-02 | Priority: P4
