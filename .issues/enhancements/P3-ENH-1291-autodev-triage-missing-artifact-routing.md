---
captured_at: "2026-04-25T19:14:09Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
decision_needed: true
---

# ENH-1291: Autodev `triage_outcome_failure` missing-artifact routing branch

## Summary

`triage_outcome_failure` (ENH-1288) routes issues to `run_decide` when `score_ambiguity ≤ 10` and to `detect_children` otherwise. A third root cause — absent files or unwired components — also lowers `outcome_confidence` but needs routing to `wire-issue`/`refine-issue`, not size-review. This branch is absent and the right signal to detect it is an open design question.

## Current Behavior

After ENH-1288, `triage_outcome_failure` handles two cases:
- `score_ambiguity ≤ 10` → `run_decide` (unresolved design decision)
- Otherwise → `detect_children` (size-review path)

Issues where `outcome_confidence` is low because a referenced file is absent (`ExtensionSection.jsx` absent, unwired component, missing artifact) fall through to `detect_children`. Size-review then scores them as Large due to thorough documentation and proposes decomposition, which is the wrong fix — the actual blocker is a wiring gap, not scope bigness.

## Expected Behavior

`triage_outcome_failure` should have a third branch:
- Artifact/wiring bottleneck → `run_wire` or `run_refine` (whichever is appropriate)

The challenge is the signal. `score_complexity` is ambiguous: low `score_complexity` can mean either "this issue references absent files" or "this issue has narrow scope." Routing to `wire-issue` on a genuinely small-scope issue would be incorrect. A dedicated signal — a field written by `confidence-check` specifically for the artifact case — is needed.

## Motivation

This is the third leg of ENH-1288's own Expected Behavior table:

| Bottleneck | Signal | Right intervention |
|---|---|---|
| Structural bigness | `score_complexity` low (many files, broad scope) | `issue-size-review` |
| Unresolved design | `score_ambiguity` low (≤10) | `decide-issue` |
| **Missing artifacts/wiring** | **?** | **`wire-issue` / `refine-issue`** |

ENH-1288 deliberately scoped this out because `score_complexity` alone cannot distinguish the two artifact-case interpretations. Without this branch, a subset of wiring-blocked issues will continue to reach size-review and risk spurious decomposition (partially mitigated by ENH-1290's guard, but not fully prevented).

## Proposed Solution

TBD — requires a design decision on the signal. Two candidate approaches:

**Option A**: Add a `missing_artifacts: true` field to confidence-check Phase 4.x write-back, set when `outcome_confidence` is low and specific signal phrases indicate absent files or wiring gaps (e.g., "absent", "not yet created", "does not exist", "needs wiring"). `triage_outcome_failure` reads this field directly.

**Option B**: Add a `wire_status: incomplete` field to confidence-check write-back using the existing wiring-gap detection in Phase 4.5. `triage_outcome_failure` checks `wire_status == "incomplete"` before falling through to `detect_children`.

Option A is more explicit and self-documenting in the issue frontmatter. Option B reuses a concept that may already be tracked elsewhere. The decision should consider whether `wire-issue` or `refine-issue` is the right target (they overlap: `wire-issue` is for integration points, `refine-issue` for missing codebase context).

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 4.x write-back: add artifact signal field
- `scripts/little_loops/loops/autodev.yaml` — `triage_outcome_failure` state: add third branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — `run_wire` or `run_refine` state (may need to be added or confirmed present)

### Similar Patterns
- `triage_outcome_failure` in ENH-1288 — exact pattern: read frontmatter field, exit code determines route
- `check_decision_before_size_review` — same shell_exit fragment pattern

### Tests
- Fixture: issue with `outcome_confidence: 64`, `score_ambiguity: 20` (not a decision), `missing_artifacts: true`
- Expected: routes to `run_wire` / `run_refine`, not `run_size_review`

### Documentation
- N/A

### Configuration
- N/A — no new config required; new field written by confidence-check

## Implementation Steps

1. **Decide** (decision_needed): Choose Option A or B for the artifact signal field — see Proposed Solution
2. Add the chosen signal field to `confidence-check` Phase 4.x write-back
3. Add third branch to `triage_outcome_failure` in `autodev.yaml`: read artifact signal, exit 0 if present → `run_wire`/`run_refine`
4. Confirm `run_wire` or `run_refine` state exists in `autodev.yaml`; add if absent
5. Test with artifact-blocked fixture; verify no regression on decision-blocked or scope-big issues

## Impact

- **Priority**: P3 — partial mitigation already provided by ENH-1290's size-review guard; this closes the root-cause gap
- **Effort**: Small-Medium — confidence-check write-back change + one state branch; complexity depends on signal design choice
- **Risk**: Low-Medium — additive routing branch; risk is in the signal accuracy (false positives route to wire-issue unnecessarily)
- **Breaking Change**: No

## Scope Boundaries

- Depends on ENH-1288 landing first (adds `triage_outcome_failure` state)
- Does not change scoring heuristics in `confidence-check` Phase 4.5
- Does not affect interactive mode of `issue-size-review`
- The signal field choice (Option A vs B) is a prerequisite decision, not in-scope for this issue

## Labels

`enhancement`, `autodev`, `confidence-gate`, `decision-needed`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-25T19:14:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d254d7af-8d9d-458c-aec5-e845416d235d.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
