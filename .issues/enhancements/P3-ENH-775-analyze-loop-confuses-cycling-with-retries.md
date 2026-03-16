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
- `skills/analyze-loop/SKILL.md` — update "ENH — Retry flood" signal rule to distinguish true retries (via `on_retry`) from intentional cycling (via `on_no`/`on_yes`)

### Dependent Files (Callers/Importers)
- `skills/analyze-loop/` — no Python callers; skill is invoked directly by users via `/ll:analyze-loop`
- `.issues/` — any analyze-loop-generated issue files may reference old signal terminology

### Similar Patterns
- Other signal rules in `skills/analyze-loop/SKILL.md` (SIGKILL, performance anomalies) — check for similar raw-count-based heuristics that could have the same conflation problem

### Tests
- N/A — analyze-loop is a pure SKILL.md with no Python module or test files

### Documentation
- N/A — no external docs reference analyze-loop signal rules

### Configuration
- N/A — no configuration files affected

## Implementation Steps

1. Read `skills/analyze-loop/SKILL.md` retry flood signal rule to understand current detection logic
2. Update "ENH — Retry flood" detection to check for `on_retry`/`max_retries` presence in state config before classifying re-entries as retries
3. Add intentional cycling detection rule: note high-frequency cycling states in analysis output; escalate only when >20 consecutive re-entries with no intervening state
4. Update signal title/description to accurately distinguish "retry flood" (true retries) from "cycling without progress" (stuck loops)
5. Verify by re-running analyze-loop over `issue-refinement` loop history — confirm no false positives on `check_commit` or `route_format`

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

## Status

**Open** | Created: 2026-03-16 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-03-16T19:31:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:format-issue` - 2026-03-16T19:30:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cb5b34b-15fc-4f5c-b73a-5ce3439be412.jsonl`
