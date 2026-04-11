---
discovered_date: 2026-04-11
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 90
---

# ENH-1033: `refine-to-ready-issue`: skip retry refine when only outcome confidence fails

## Summary

When `check_scores` fails in `refine-to-ready-issue`, the FSM unconditionally retries `/ll:refine-issue` regardless of which metric failed. `/ll:refine-issue` improves technical readiness (codebase research, implementation wiring). When only outcome confidence is below threshold — a measure of business value certainty — the retry is unlikely to close the gap and wastes roughly 11 minutes per attempt.

## Current Behavior

`check_scores` at `scripts/little_loops/loops/refine-to-ready-issue.yaml:110` evaluates both `confidence` (readiness) and `outcome` in a single boolean. Any failure routes to `check_refine_limit → refine_issue`. There is no distinction between:
- Readiness failed (technical gaps — `/ll:refine-issue` can fix this)
- Outcome confidence failed (business value uncertainty — `/ll:refine-issue` cannot reliably fix this)

Observed in practice: FEAT-095 scored 93/100 readiness (above threshold) but 64/100 outcome (below 75 threshold). The FSM retried `/ll:refine-issue`, which ran for ~11 minutes and is unlikely to raise outcome confidence by 11 points since the uncertainty is inherent to the feature's business case, not missing technical detail.

## Expected Behavior

When readiness passes but only outcome confidence fails, the FSM should route directly to `breakdown_issue` (or `failed` with a diagnostic) rather than retrying refinement. Optionally, it could invoke a different skill targeted at outcome uncertainty (e.g., prompting for use-case clarification or scope reduction).

## Motivation

Outcome confidence measures whether the feature's benefit is well-understood and realistically achievable. Low outcome confidence signals a problem with the feature's definition, not the implementation plan. Re-researching the codebase won't resolve "we're not sure this feature will have the expected impact." The retry wastes time and token budget without addressing the actual gap.

## Success Metrics

- **Time saved**: ~11 min per issue where readiness passes but outcome confidence fails (no unnecessary refinement retry)
- **Routing accuracy**: Outcome-only-fails path routes to `breakdown_issue` without retrying `/ll:refine-issue`
- **Test coverage**: New test case in `scripts/tests/test_builtin_loops.py` passes for outcome-only-fails scenario

## Proposed Solution

Split `check_scores` into two sequential checks:
1. **`check_readiness`** — if readiness < threshold, route to retry path (refine is appropriate)
2. **`check_outcome`** — if outcome < threshold (after readiness passes), route directly to `breakdown_issue` (scope reduction is the right intervention, not more refinement)

Alternatively, add a separate `check_scores_by_metric` state that exits with distinct codes for "readiness failed", "outcome failed", or "both failed", and route accordingly.

## Implementation Steps

1. In `scripts/little_loops/loops/refine-to-ready-issue.yaml:108` — update `confidence_check.next: check_scores` → `next: check_readiness`
2. In `scripts/little_loops/loops/refine-to-ready-issue.yaml:110–141` — replace `check_scores` state with two sequential states:
   - `check_readiness`: Python inline reads only `confidence` vs `readiness_threshold`; `on_yes: check_outcome`; `on_no: check_refine_limit`; `on_error: check_scores_from_file`
   - `check_outcome`: Python inline reads only `outcome` vs `outcome_threshold`; `on_yes: done`; `on_no: breakdown_issue`; `on_error: failed`
3. In `scripts/little_loops/loops/refine-to-ready-issue.yaml:162–189` — update `check_scores_from_file`: change `on_no: failed` → `on_no: breakdown_issue` (minimal fix; full two-state split is optional)
4. Verify `recursive-refine.yaml` — `check_passed` re-reads frontmatter independently, no changes needed; confirm `run_refine` sub-loop still terminates at `done`
5. Update `scripts/tests/test_builtin_loops.py` (`TestRefineToReadyIssueSubLoop`, lines 490–661):
   - Remove/update tests asserting `check_scores` state fields (those state names no longer exist)
   - Update any `confidence_check.next == "check_scores"` assertion to `"check_readiness"`
   - Add: `test_check_readiness_on_yes_routes_to_check_outcome` — asserts `check_readiness.on_yes == "check_outcome"`
   - Add: `test_check_readiness_on_no_routes_to_check_refine_limit` — asserts `check_readiness.on_no == "check_refine_limit"`
   - Add: `test_check_outcome_on_yes_routes_to_done` — asserts `check_outcome.on_yes == "done"`
   - Add: `test_check_outcome_on_no_routes_to_breakdown_issue` — asserts `check_outcome.on_no == "breakdown_issue"`
6. Update loop description/comments in `refine-to-ready-issue.yaml:1–10` to reflect new two-state routing logic

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Verify `scripts/little_loops/loops/issue-refinement.yaml:29` — confirms delegation to `refine-to-ready-issue` is by loop name only (no state-name references); no code change expected, just verify
8. Update `scripts/tests/test_builtin_loops.py:535–540` — rename `test_check_scores_from_file_routes_to_failed_on_no` to `test_check_scores_from_file_routes_to_breakdown_issue_on_no` and update assertion from `"failed"` to `"breakdown_issue"`
9. Update `docs/guides/LOOPS_GUIDE.md:271` — revise "otherwise it routes to `failed`" to reflect `check_scores_from_file.on_no: breakdown_issue`

## Scope Boundaries

- **In scope**: Routing logic change in `refine-to-ready-issue.yaml`; corresponding test coverage
- **Out of scope**: Changing the thresholds themselves; adding new skills to address outcome uncertainty

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:110–159` — split `check_scores` into `check_readiness` + `check_outcome`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — references `check_passed` from `refine-to-ready-issue.yaml`; verify `check_passed` logic is unaffected by state split

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/issue-refinement.yaml:29` — delegates to `refine-to-ready-issue` as a `loop:` sub-loop target; verify no state-name dependencies before implementing [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — has similar scoring/check structure; verify consistency with new two-state approach

### Tests
- `scripts/tests/test_builtin_loops.py` — add test case for outcome-only-fails path (readiness passes, outcome fails → routes to `breakdown_issue`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:535–540` — `test_check_scores_from_file_routes_to_failed_on_no`: asserts `on_no == "failed"` — **will break** when step 3 changes `on_no: failed` → `on_no: breakdown_issue`; update assertion to `"breakdown_issue"` [Agent 2 & 3 finding]
- `scripts/tests/test_fsm_fragments.py:837` — `TestBuiltinLoopMigration.test_builtin_loops_load_after_migration`: loads and validates `refine-to-ready-issue.yaml` structurally; passes automatically after the split as long as the YAML remains schema-valid — no action needed, free regression guard [Agent 2 finding]

### Documentation
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1–10` — update loop description/comments to reflect new routing logic

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:271` — documents `check_scores_from_file` fallback with "otherwise it routes to `failed`"; this sentence becomes inaccurate when step 3 changes `check_scores_from_file.on_no` from `failed` → `breakdown_issue`; update to reflect new routing [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical missed change — `confidence_check` upstream connection:**
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:108` — `confidence_check` state has `next: check_scores`; this must change to `next: check_readiness` after the split. Not changing this leaves the new states unreachable.

**Exact routing for the two new states (confirmed via FSM engine analysis):**
- `check_readiness`: `on_yes: check_outcome` | `on_no: check_refine_limit` | `on_error: check_scores_from_file` (preserves existing error fallback)
- `check_outcome`: `on_yes: done` | `on_no: breakdown_issue` | `on_error: failed`

**`check_scores_from_file` at line 162 — minimal update path:**
- This is the error-recovery fallback (reached when `check_scores`/`check_readiness` subprocess fails). It uses the same combined `and` boolean and currently routes `on_no: failed`. The minimal fix for this path: change `on_no: failed` to `on_no: breakdown_issue` so outcome-only failures here also avoid the retry loop. Full two-state split of this fallback is optional.

**Sequential chaining pattern to follow:**
- `scripts/little_loops/loops/backlog-flow-optimizer.yaml:63–86` — canonical example of sequential `on_no` chaining: state N's `on_no` names state N+1; state N's `on_yes` routes to the action branch. Mirror this: `check_readiness.on_no: check_refine_limit`, `check_readiness.on_yes: check_outcome`, `check_outcome.on_no: breakdown_issue`, `check_outcome.on_yes: done`.

**`recursive-refine.yaml` verification (no changes needed):**
- `check_passed` state (`recursive-refine.yaml:99–140`) re-reads frontmatter independently via its own `ll-issues show --json` call. It does not reference `check_scores` by name. No changes needed there.

**Existing tests that must be updated/removed** (in `TestRefineToReadyIssueSubLoop`, `test_builtin_loops.py:490–661`):
- `test_check_scores_routes_to_done` — remove or rename to `test_check_outcome_routes_to_done`
- `test_check_scores_on_error_is_check_scores_from_file` — remove or rename to `test_check_readiness_on_error_is_check_scores_from_file`
- Any assertion that `confidence_check.next == "check_scores"` — update to `"check_readiness"`
- Existing `test_check_refine_limit_on_no_routes_to_breakdown_issue` can remain unchanged

## Impact

- **Priority**: P3 — Saves ~11 min per issue with inherently low outcome confidence
- **Effort**: Low — routing change + 1-2 new states
- **Risk**: Low — change is additive; existing paths unaffected when both metrics fail or when readiness fails
- **Breaking Change**: No

## Blocked By

_None — BUG-1032 (direct breakdown path fix) is completed; ENH-1033 is unblocked._

## Labels

`enhancement`, `loops`, `fsm`, `refine-to-ready-issue`, `performance`

## Resolution

**Completed** | 2026-04-11

Split `check_scores` into two sequential states in `refine-to-ready-issue.yaml`:
- `check_readiness`: checks only `confidence_score` vs `readiness_threshold`; `on_no` routes to `check_refine_limit` (retry refinement)
- `check_outcome`: checks only `outcome_confidence` vs `outcome_threshold`; `on_no` routes to `breakdown_issue` (scope reduction)

Updated `confidence_check.next` from `check_scores` → `check_readiness`. Updated `check_scores_from_file.on_no` from `failed` → `breakdown_issue`. Updated tests and LOOPS_GUIDE docs.

## Status

**Completed** | Created: 2026-04-11 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-04-11T17:02:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1dc5b7fe-1bf2-4be6-ac9e-ea464991f7ca.jsonl`
- `/ll:confidence-check` - 2026-04-11T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bab1e73-bdcf-4ff6-9eb3-8a7dca3a0202.jsonl`
- `/ll:wire-issue` - 2026-04-11T16:58:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4d91bb8-3a33-4482-ba55-6f11c0e0c72d.jsonl`
- `/ll:refine-issue` - 2026-04-11T16:54:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc5911d7-0392-43a1-9e13-6e488a7951cb.jsonl`
- `/ll:format-issue` - 2026-04-11T16:49:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20e57717-455c-4ff2-a806-8a83232025d2.jsonl`
- `/ll:verify-issues` - 2026-04-11T16:33:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe163fab-25f0-47a9-b5d3-57cef164c232.jsonl`
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05d0324c-611c-469d-8af1-b4e42644c47d.jsonl`
- `/ll:manage-issue` - 2026-04-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
