---
discovered_date: 2026-03-16
discovered_by: scan-codebase
source_loop: issue-refinement
source_state: check_commit
confidence_score: 100
outcome_confidence: 75
---

# ENH-775: analyze-loop conflates intentional state cycling with stuck retries

## Summary

The `analyze-loop` skill's "ENH — Retry flood" heuristic triggers whenever the same state appears in `state_enter` events 5 or more times, regardless of whether those re-entries are intentional design or actual retry failures. In the `issue-refinement` loop this produced two false positive signals: `check_commit` flagged as "retried 8x" and `route_format` flagged as "retried 9x". Neither state uses a retry counter — both use normal `on_no` routing as part of their designed control flow. True retries (which increment a retry counter and eventually hit `on_retry_exhausted`) are fundamentally different from intentional cycling via `on_yes`/`on_no` routing.

## Current Behavior

`analyze-loop` flags any state that appears in `state_enter` events 5 or more times as a "retry flood" signal, regardless of whether the re-entries are intentional (via `on_no`/`on_yes` routing) or actual retries (via `on_retry`). This produces false positive signals for states that use normal cycling as their designed control flow. Example: `check_commit` visited 8x (expected for 8 completed prompt actions) and `route_format` visited 9x (expected for 9 evaluated issues) were both flagged as problems.

## Expected Behavior

`analyze-loop` distinguishes true retries (states with `on_retry`/`max_retries` configured) from intentional cycling (states re-entered via `on_no`/`on_yes`). Only true retry states trigger the "retry flood" signal. Intentional cycling states are noted informally in analysis output without generating issue signals, unless >20 consecutive re-entries with no intervening state occur (indicating a genuinely stuck loop).

## Motivation

False positive signals in `analyze-loop` output erode trust in the tool — when users investigate false positives and find they're expected behavior, they start treating all signals as noise. The `issue-refinement` loop generated 2 false positives (`check_commit` and `route_format`) that could mislead an agent into "fixing" correctly functioning states. Accurate signal generation is critical for `analyze-loop` to remain a reliable diagnostic tool rather than a source of implementation noise.

## Root Cause

- **File**: `skills/analyze-loop/SKILL.md` — Signal Rules, "ENH — Retry flood" section
- **Cause**: The heuristic counts raw `state_enter` events without distinguishing how the state was re-entered. States with `on_no` routing that cycle back through the FSM as a designed pattern look identical in the event log to states that are genuinely stuck retrying. The signal title even uses the word "retried", which is inaccurate for cycling states.

## False Signals Generated

**Signal 3** — `check_commit` "retried 8x":
- `check_commit` outputs `COMMIT` only when `N % 5 == 0`, otherwise outputs `SKIP`
- `on_no: evaluate` when SKIP — this is the designed looping behavior
- 8 visits is expected for 8 completed prompt actions over the session
- No retry counter involved; this is pure `on_no` cycling

**Signal 4** — `route_format` "retried 9x":
- `route_format` is a pure routing state with no action, only `evaluate: type: output_contains`
- When the current issue doesn't need formatting, `on_no: route_score` proceeds down the pipeline
- When it does need formatting, `on_yes: format_issues` processes it
- 9 visits means 9 issues were evaluated — entirely correct behavior

## Distinction: True Retries vs. Intentional Cycling

| Property | True retry | Intentional cycling |
|----------|-----------|---------------------|
| Re-entry mechanism | `on_retry` transition | `on_no` or `on_yes` routing |
| Counter incremented | Yes (`retry_count`) | No |
| Has `max_retries` limit | Usually | No |
| Has `on_retry_exhausted` | Usually | No |
| Progress indicator | Same state, no progress | Different state visited between cycles |

## Proposed Solution

Update `skills/analyze-loop/SKILL.md`, Signal Rules, "ENH — Retry flood" section to distinguish true retries from intentional cycling:

**True retry detection** (existing behavior, refined):
- State re-entered via `on_retry` transition (retry counter incremented)
- Flag when retry count is approaching `max_retries` (>= 80% of limit) or has hit `on_retry_exhausted`
- Priority: P3

**Intentional cycling detection** (new, non-alarming):
- State re-entered via `on_no`/`on_yes` routing with no retry counter
- Note the frequency in analysis output, but do **not** generate an issue signal
- Only escalate to a signal if the same state is visited **>20x** with no other states visited in between (true stuck-in-place loop with no progress)
- If escalated: Priority P4, title: `"<state> cycling without progress (>20 consecutive re-entries) in <loop_name> loop"`

**How to detect**: Check whether the state configuration has `on_retry:` or `max_retries:` fields. If absent, any re-entry is cycling, not retrying.

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md:124-128` — update "ENH — Retry flood" signal rule to distinguish true retries (via `on_retry`) from intentional cycling (via `on_no`/`on_yes`)
- `skills/analyze-loop/SKILL.md:84-92` — add `retry_exhausted` event type to the event parsing table (currently missing; the event exists in the executor but the skill doesn't document or use it)
- `docs/reference/COMMANDS.md:380` — update the summary line "Same state entered 5+ times (retry flood) → ENH P3" to reflect the new disambiguation logic

### Dependent Files (Callers/Importers)
- `skills/analyze-loop/` — no Python callers; skill is invoked directly by users via `/ll:analyze-loop`
- `.issues/` — any analyze-loop-generated issue files may reference old signal terminology

### Similar Patterns
- Other signal rules in `skills/analyze-loop/SKILL.md` (SIGKILL, performance anomalies) — check for similar raw-count-based heuristics that could have the same conflation problem

### Tests
- N/A — analyze-loop is a pure SKILL.md with no Python module or test files

### Documentation
- `docs/reference/COMMANDS.md:380` — references the signal rule summary; must be updated to reflect new logic
- `thoughts/shared/plans/2026-03-13-FEAT-719-management.md:37` — historical plan doc; update is optional (thought file, not user-facing)

### Configuration
- N/A — no configuration files affected

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Event stream structure** (`scripts/little_loops/fsm/executor.py:496-502`):
- `state_enter` is emitted identically for every mode of re-entry: `on_no` cycling, `on_yes` cycling, and true `max_retries` retries. No field in the event indicates how the state was entered.

**`retry_exhausted` event** (`executor.py:468-493`):
- Emitted when `retry_count > state_config.max_retries` — the ONLY event that unambiguously identifies true retry behavior
- Fields: `state`, `retries`, `next`
- Fires instead of `state_enter` once limit is exceeded
- NOT currently in the skill's event parsing table (`SKILL.md:76-83`)
- No live loop history currently contains this event (no loop YAML uses `max_retries` yet)

**`route` event** (`executor.py:529-535`):
- Fields: `from` (str), `to` (str) — no field for which transition key was used
- Available in the event stream; can be used to detect consecutive same-state routing (`from == to`)

**Consecutive vs. total re-entry** — the executor's `_retry_counts` (`executor.py:392-447`):
- Only increments on CONSECUTIVE same-state entries (when `current_state == _prev_state`)
- Resets when ANY different state is visited
- `check_commit` (on_no: evaluate) and `route_format` (on_no: route_verify) NEVER produce consecutive entries because they always route to different states
- The skill does NOT have access to this counter — it is never written to events

**Implementation choice (critical)**: The proposed solution says "check whether the state configuration has `on_retry:` or `max_retries:` fields" — this requires loading the loop YAML, which the skill currently does NOT do. Two valid approaches:
1. **YAML-loading approach** (authoritative): Add a step to load `ll-loop show <loop_name>` or read the YAML, then check each flagged state for `max_retries` presence before emitting the signal
2. **Event-stream-only approach** (simpler): Use `route` events — if `from == to` (state routes to itself), that's a true consecutive cycling pattern. Combine with `retry_exhausted` event presence. States like `check_commit` (on_no: evaluate, `to != from`) are correctly excluded.

## Implementation Steps

1. Read `skills/analyze-loop/SKILL.md:124-128` (retry flood signal rule) and `SKILL.md:84-92` (event parsing table)
2. Choose detection approach (see Integration Map research findings for trade-offs):
   - **Recommended**: Event-stream-only — use `route` events to check if `from == to` (state routes to itself consecutively); also check for `retry_exhausted` events. Avoids adding a YAML-loading step.
   - **Alternative**: Load YAML via `ll-loop show <loop_name>` and check each flagged state for `max_retries` field presence
3. Update `SKILL.md:111-115` "ENH — Retry flood" to split into two cases:
   - True retry flood: only trigger when consecutive same-state re-entries detected (route from == to, or retry_exhausted present)
   - Intentional cycling: note in output but do NOT generate an issue signal; only escalate if >20 consecutive same-state entries with no intervening different state
4. Add `retry_exhausted` event type to the event parsing table at `SKILL.md:76-83`
5. Update signal title from "retried Nx" to "retry flood" (only for true retry states)
6. Update `docs/reference/COMMANDS.md:380` summary line to reflect the new disambiguation
7. Verify by re-running `ll-loop history issue-refinement --json` and confirming the updated skill does NOT flag `check_commit` or `route_format` — both use `on_no` routing to different states (never route to themselves)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Reference `loops/issue-refinement.yaml:107-121` to see `check_commit` state (on_no: evaluate → routes to different state → never consecutive)
- Reference `loops/issue-refinement.yaml:57-64` to see `route_format` state (on_no: route_verify → routes to different state → never consecutive)
- Reference `scripts/tests/test_fsm_executor.py:2968-3138` (`TestPerStateRetryLimits`) for how `retry_exhausted` event is structured and when it fires — useful for understanding the event to add to the skill's parsing table
- Reference `scripts/little_loops/fsm/executor.py:529-535` for the `route` event structure (`from`, `to` fields — no transition key label)

## Scope Boundaries

- Out of scope: Changes to FSM execution engine or loop YAML format
- Out of scope: Changes to other signal rules (SIGKILL, performance anomalies, etc.)
- Out of scope: Changing how loop history is stored or parsed
- Out of scope: Updating existing loop configurations to remove cycling patterns

## Acceptance Criteria

- [ ] `analyze-loop` does not flag states that use `on_no` cycling as "retry floods" when they have no `on_retry`/`max_retries` configuration
- [ ] `analyze-loop` still correctly flags states with `on_retry` that are approaching `max_retries`
- [ ] `analyze-loop` flags cycling states only if >20 consecutive re-entries with no intervening state (true stuck loop)
- [ ] Re-running `analyze-loop` over `issue-refinement` history does not produce false positive signals on `check_commit` or `route_format`
- [ ] Analysis output notes high-frequency cycling states as informational (not as issues)

## Impact

- **Priority**: P3 — Quality improvement; does not block functionality but degrades tool reliability when false positives appear
- **Effort**: Small — Single SKILL.md heuristic update with a clear, well-specified change
- **Risk**: Low — Detection logic change only; no FSM execution, YAML format, or API changes
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `analyze-loop`, `captured`

## Resolution

**Completed**: 2026-03-17

### Changes Made

1. **`skills/analyze-loop/SKILL.md`** — Added `retry_exhausted` event type to the event parsing table (fields: `state`, `retries`, `next`).
2. **`skills/analyze-loop/SKILL.md`** — Replaced "ENH — Retry flood" signal rule with two distinct rules:
   - **ENH — Retry flood (true retries only)**: Only fires when the state config (from loop YAML already loaded in Step 2) has `on_retry` or `max_retries` fields, OR a `retry_exhausted` event is present. Title updated from "retried Nx" to "retry flood".
   - **NOTE — Intentional cycling (informational only)**: States without retry config that appear 5+ times are noted in output without generating an issue signal. Exception: 20+ consecutive re-entries with no intervening state → ENH P4 "cycling without progress" signal.
3. **`docs/reference/COMMANDS.md`** — Updated signal detection summary line to reflect the retry vs. cycling disambiguation.

### Acceptance Criteria Verification

- [x] `analyze-loop` does not flag states that use `on_no` cycling as "retry floods" when they have no `on_retry`/`max_retries` configuration — cycling states are now informational only
- [x] `analyze-loop` still correctly flags states with `on_retry` that are approaching `max_retries` — true retry flood rule preserved
- [x] `analyze-loop` flags cycling states only if >20 consecutive re-entries with no intervening state — stuck-loop escalation added
- [x] Re-running `analyze-loop` over `issue-refinement` history would not produce false positive signals on `check_commit` or `route_format` — neither state has `on_retry`/`max_retries` config, so both are classified as intentional cycling
- [x] Analysis output notes high-frequency cycling states as informational — NOTE rule adds `"<state> cycled <N>x (intentional on_no/on_yes routing — no issue signal)"`

## Status

**Completed** | Created: 2026-03-16 | Completed: 2026-03-17 | Priority: P3


## Verification Notes

Verified 2026-03-16. Core bug claims confirmed accurate:
- `skills/analyze-loop/SKILL.md:124-128` — "ENH — Retry flood" heuristic triggers on raw 5+ `state_enter` count with no retry vs. cycling distinction ✓
- `skills/analyze-loop/SKILL.md:84-91` — event parsing table confirmed; `retry_exhausted` event is absent ✓
- `docs/reference/COMMANDS.md:380` — retry flood summary line confirmed accurate ✓

**Line reference corrections in Implementation Steps** (Integration Map references are correct; steps have wrong line numbers):
- Step 3 says `SKILL.md:111-115` → actual location is **124-128** (matches Integration Map)
- Step 4 says event table at `SKILL.md:76-83` → actual location is **84-91** (matches Integration Map)

## Session Log
- `/ll:manage-issue` - 2026-03-17T00:00:00 - improve ENH-775
- `/ll:ready-issue` - 2026-03-17T05:23:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/264c7eb5-eeca-4747-b693-1c7447fa1867.jsonl`
- `/ll:verify-issues` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6845dcb9-5d3d-4e87-aaff-4382e49ef209.jsonl`
- `/ll:refine-issue` - 2026-03-17T03:54:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f5188477-e8ba-44da-8d95-f92aeaf36e0b.jsonl`
- `/ll:refine-issue` - 2026-03-16T23:41:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0364dd7-6557-4614-a167-51d913f25bbc.jsonl`
- `/ll:verify-issues` - 2026-03-16T19:31:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:30:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
