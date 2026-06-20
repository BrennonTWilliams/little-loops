---
id: ENH-2247
title: "rn-remediate overuses --full-rewrite in refine state"
type: ENH
priority: P3
status: open
confidence_score: 0
outcome_confidence: 0
captured_at: "2026-06-20T19:17:49Z"
discovered_date: "2026-06-20"
discovered_by: capture-issue
---

# ENH-2247: rn-remediate overuses --full-rewrite in refine state

## Summary

The `refine` state in `rn-remediate.yaml` hardcodes `--full-rewrite` for every invocation, regardless of whether the route that triggered it actually warrants destroying and rebuilding the issue's content. Only the `diagnose → REFINE` path (a dimensional scoring failure — high ambiguity/complexity/confidence-below-floor) justifies a full rewrite. All other `refine` callers fire `--full-rewrite` even when the issue content is partially correct, wasting work and potentially overwriting valid content.

## Current Behavior

The `refine` state in `rn-remediate.yaml` unconditionally passes `--full-rewrite` to `/ll:refine-issue` for every caller, regardless of why `refine` was triggered:

- `assess → on_no: refine` — first-pass scoring; issue content may be largely correct
- `gate_implement → NEED_REFINE` — marker policy trigger; prose content was not diagnosed as wrong
- `re_assess → on_no: refine` — a full rewrite was already performed this pass; re-applying it overwrites the first pass's improvements
- `wire → on_no: refine` — wiring failure; the issue's prose content was not the problem

## Expected Behavior

Only the `diagnose → REFINE` path (where a dimensional scoring failure is confirmed) passes `--full-rewrite`. All other paths route to appropriately-scoped refine variants:

- `assess → on_no` and `gate_implement → NEED_REFINE` → `refine_first` with `--auto`
- `re_assess → on_no` → `refine_followup` with `--auto --gap-analysis`
- `wire → on_no` → `refine_first` with `--auto`
- `diagnose → REFINE_LIGHT` → unchanged (`refine_light` with `--auto`)

## Motivation

`--full-rewrite` is a destructive operation — it replaces existing issue content. Most paths that trigger `refine` in `rn-remediate` reflect policy requirements or score thresholds that don't imply the content itself is wrong:

- `assess → on_no: refine` — first contact with an unscored issue; content may be largely fine
- `gate_implement → route_gate_refine → refine` — the marker `refined_<ID>.txt` doesn't exist yet; this is a policy trigger, not a content-quality diagnosis
- `re_assess → on_no: refine` — a full rewrite was already done; re-doing it overwrites the first pass's improvements
- `wire → on_no: refine` — wiring failed; the issue's prose content wasn't the problem

The `refine_light` state added in ENH-2223 applied the lighter `--auto` flag but only for the `diagnose → REFINE_LIGHT` catch-all, which is a very narrow band in practice. The broader paths still unconditionally use `--full-rewrite`.

## Implementation Steps

Split the primary `refine` state in `scripts/little_loops/loops/rn-remediate.yaml` into per-path variants (or route each caller to an appropriately-flagged state):

1. **Keep `refine` (with `--full-rewrite`) only for `diagnose → REFINE`**
   - `diagnose` routes: high ambiguity with integration map, high complexity + confidence below floor, outcome below threshold — these are real content-quality failures.

2. **Add `refine_first` state** — `--auto` only (no `--full-rewrite`)
   - Used by: `assess → on_no`, `gate_implement → NEED_REFINE`
   - Rationale: first-pass refinement on an issue that hasn't been scored yet; targeted gap-fill is less destructive.

3. **Change `re_assess → on_no`** to route to a `refine_followup` state — `--auto --gap-analysis`
   - Rationale: a full rewrite was already done this pass; the follow-up should patch remaining gaps, not bulldoze prior work.

4. **Change `wire → on_no`** to route to `refine_first` (or `refine_light`) — `--auto` only
   - Rationale: wire failure is an integration-map problem, not an issue-content problem.

The `mark_refined` marker-gate path is shared; all new refine-variant states should still route through `mark_refined → check_decision_needed_post` on success/partial so the gate logic is unchanged.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update 5 breaking test assertions across 2 test files:
   - `scripts/tests/test_rn_remediate.py:314` — `test_wire_routes_through_mark_wired_on_success`: `wire["on_no"]` → `"refine_first"`
   - `scripts/tests/test_rn_remediate.py:481` — `test_gate_router_cascade_forces_refine_then_wire_then_implement`: `rgr["on_yes"]` → `"refine_first"`
   - `scripts/tests/test_rn_remediate.py:545` — `test_re_assess_has_on_no_route`: `reassess.get("on_no")` → `"refine_followup"`
   - `scripts/tests/test_builtin_loops.py:6971` — `test_assess_on_no_routes_to_refine`: assert target → `"refine_first"`
   - `scripts/tests/test_builtin_loops.py:7010` — `test_wire_on_no_routes_to_refine`: assert target → `"refine_first"`
6. Update `docs/guides/LOOPS_REFERENCE.md` Phase 3 FSM flow block: change `wire → refine` to `wire.on_no → refine_first`; update `refine` state description to note it's now only reached from `diagnose → REFINE`; add `refine_first` and `refine_followup` to the abbreviated state list

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Exact line locations in `rn-remediate.yaml` (callers to update):**
- `assess.on_no: refine` — line ~80; change to `refine_first`
- `route_gate_refine.on_yes: refine` — line ~317; change to `refine_first`
- `wire.on_no: refine` — line ~366; change to `refine_first`
- `re_assess.on_no: refine` — line ~435; change to `refine_followup`
- `diagnose` route table `REFINE: refine` — lines 269–277; keep as-is (this is the justified full-rewrite path)

**State definitions to add (after `refine_light` at line 391):**

```yaml
  refine_first:
    # ENH-2247: lighter refine for first-pass paths (assess on_no, gate_implement NEED_REFINE, wire on_no).
    fragment: with_rate_limit_handling
    action: "/ll:refine-issue ${context.issue_id} --auto"
    action_type: slash_command
    on_yes: mark_refined
    on_no: emit_implement_failed
    on_partial: mark_refined
    on_rate_limit_exhausted: rate_limit_diagnostic

  refine_followup:
    # ENH-2247: additive-only refine for re_assess on_no (a full-rewrite pass already ran this cycle).
    fragment: with_rate_limit_handling
    action: "/ll:refine-issue ${context.issue_id} --auto --gap-analysis"
    action_type: slash_command
    on_yes: mark_refined
    on_no: emit_implement_failed
    on_partial: mark_refined
    on_rate_limit_exhausted: rate_limit_diagnostic
```

**`on_partial` invariant**: Both existing refine states (`refine`, `refine_light`) route `on_partial` to `mark_refined` identically to `on_yes`. New states must do the same — `mark_refined` uses `next:` (unconditional advance to `check_decision_needed_post`), so the marker-gate chain runs regardless of partial vs. full completion.

**Verification command:**
```bash
ll-loop validate rn-remediate && python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_builtin_loops.py -v -k "remediate"
```

### Target file

`scripts/little_loops/loops/rn-remediate.yaml`

### Routing table (before → after)

| Caller | Current | Proposed |
|---|---|---|
| `assess → on_no` | `refine` (`--full-rewrite`) | `refine_first` (`--auto`) |
| `check_wire_needed_outcome → on_no` | `refine` (`--full-rewrite`) | `refine_first` (`--auto`) |
| `check_wire_needed_outcome → on_error` | `refine` (`--full-rewrite`) | `refine_first` (`--auto`) |
| `diagnose → REFINE` | `refine` (`--full-rewrite`) | `refine` (`--full-rewrite`) ✓ keep |
| `gate_implement → NEED_REFINE` | `refine` (`--full-rewrite`) | `refine_first` (`--auto`) |
| `re_assess → on_no` | `refine` (`--full-rewrite`) | `refine_followup` (`--auto --gap-analysis`) |
| `wire → on_no` | `refine` (`--full-rewrite`) | `refine_first` (`--auto`) |
| `diagnose → REFINE_LIGHT` | `refine_light` (`--auto`) | `refine_light` (`--auto`) ✓ unchanged |

> **Audit correction (post-capture):** the original Implementation Steps enumerated 4
> callers to re-route, but `check_wire_needed_outcome` (`rn-remediate.yaml:194-195`,
> reached from `check_outcome → on_yes` on the confidence-gap path) is a 6th/7th route
> into the destructive `refine`. It is a score-threshold trigger, not a content
> diagnosis, so it routes to `refine_first` (`--auto`) for the same reason as the other
> non-`diagnose` callers. After the change the destructive `refine` is reachable **only**
> from `diagnose → REFINE`.

## Scope Boundaries

- **In scope**: Modifying `rn-remediate.yaml` FSM routing to split the `refine` state into per-path variants (`refine`, `refine_first`, `refine_followup`); updating callers to route to the appropriate variant
- **Out of scope**: Changes to `ll-issues refine` CLI itself or its `--full-rewrite`/`--auto` flags; changes to other loops that use `--full-rewrite`; changes to `mark_refined` marker-gate logic; changes to `refine_light` (already correct per ENH-2223)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — add `refine_first` and `refine_followup` states; update routing from `assess`, `gate_implement`, `re_assess`, and `wire` states

### Dependent Files (Callers/Importers)
- N/A — loop YAML is invoked by `ll-loop run`, not imported by Python modules

### Similar Patterns
- `refine_light` state in `rn-remediate.yaml` — existing lighter-weight refine variant using `--auto`; `refine_first` and `refine_followup` should follow the same structural pattern

### Tests
- `ll-loop validate rn-remediate` — structural validation (must pass with no new errors/warnings per Acceptance Criteria)
- `scripts/tests/test_rn_remediate.py` — `TestRemediationActions` (lines 363–385): `test_refine_light_exists_and_omits_full_rewrite()` and `test_refine_light_routes_through_mark_refined()` are the direct templates; add analogous tests for `refine_first` and `refine_followup`
- `scripts/tests/test_rn_remediate.py` — `TestFSMHealth`: validates FSM structure via `load_and_validate` + `validate_fsm`; must still pass after adding new states
- `scripts/tests/test_builtin_loops.py` — `TestRnRemediateAssessRouting` (line 6954): raw-YAML dict fixture pattern; add routing assertions that `assess.on_no`, `re_assess.on_no`, and `wire.on_no` point to the new variants (not `refine`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_remediate.py:314` — `TestRemediationActions.test_wire_routes_through_mark_wired_on_success`: asserts `wire["on_no"] == "refine"` — **will break**; update to `"refine_first"` [Agent 3]
- `scripts/tests/test_rn_remediate.py:481` — `TestMarkerGate.test_gate_router_cascade_forces_refine_then_wire_then_implement`: asserts `rgr["on_yes"] == "refine"` — **will break**; update to `"refine_first"` [Agent 3]
- `scripts/tests/test_rn_remediate.py:545` — `TestReassessAndConvergence.test_re_assess_has_on_no_route`: asserts `reassess.get("on_no") == "refine"` — **will break**; update to `"refine_followup"` [Agent 3]
- `scripts/tests/test_builtin_loops.py:6971` — `TestRnRemediateAssessRouting.test_assess_on_no_routes_to_refine`: asserts `on_no == "refine"` — **will break**; update to `"refine_first"` [Agent 3]
- `scripts/tests/test_builtin_loops.py:7010` — `TestRnRemediateAssessRouting.test_wire_on_no_routes_to_refine`: asserts `on_no == "refine"` — **will break**; update to `"refine_first"` [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "rn-remediate — Iterative Deepening Remediation Sub-Loop" section: Phase 3 FSM flow block (`wire → refine` and `refine (--full-rewrite) → re_assess`) will be stale; update to show `wire.on_no → refine_first` and add `refine_first`/`refine_followup` to the state list; also update the `gate_implement` marker note which says markers are written by `refine` and `wire` (now also written by `refine_first`/`refine_followup` via `mark_refined`) [Agent 2]

### Configuration
- N/A

## Acceptance Criteria

- [x] `diagnose → REFINE` still uses `--full-rewrite`, and is the **only** route into the destructive `refine`
- [x] `assess → on_no`, `gate_implement → NEED_REFINE`, `wire → on_no`, and `check_wire_needed_outcome → on_no`/`on_error` use `--auto` (no `--full-rewrite`)
- [x] `re_assess → on_no` uses `--auto --gap-analysis`
- [x] All new refine-variant states still route through `mark_refined → check_decision_needed_post` on `on_yes` / `on_partial`
- [x] `ll-loop validate rn-remediate` passes with no new errors or warnings

## Impact

- **Priority**: P3 — loop optimization; not blocking but reduces unnecessary destructive rewrites on every non-diagnostic refine trigger
- **Effort**: Small — only modifying state routing in one YAML file; adding 2 new states that mirror the existing `refine_light` pattern
- **Risk**: Low — behavioral change contained to `rn-remediate.yaml`; no external API changes; `mark_refined` gate logic unchanged; worst case is reverting one YAML file
- **Breaking Change**: No — internal FSM routing only

## Labels

`loop`, `fsm`, `rn-remediate`, `enhancement`

## Session Log
- `/ll:wire-issue` - 2026-06-20T19:47:37 - `bc99fa17-1bb8-4be8-ae8b-d96c05dd6c44.jsonl`
- `/ll:refine-issue` - 2026-06-20T19:28:00 - `432269a5-55a7-4866-af30-a20f0f8d9fe1.jsonl`
- `/ll:format-issue` - 2026-06-20T19:21:19 - `9fc17697-29bd-4f28-9400-76fc0d3bd02c.jsonl`
- `/ll:capture-issue` - 2026-06-20T19:17:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e8e922d-6e47-4c38-8faf-cb84b3dd9b5f.jsonl`
