---
captured_at: "2026-04-25T19:14:09Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
decision_needed: false
blocked_by: [ENH-753, ENH-1290]
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

## Success Metrics

- Artifact-blocked issues (genuine wiring/reference gap) route to `run_wire` or `run_refine`, not `detect_children`
- Decision-blocked issues (`score_ambiguity ≤ 10`) still route to `run_decide` — no regression
- Scope-big issues (genuinely large scope) still route to `detect_children` — no regression
- Chosen signal field set only when genuine artifact absence detected (minimal false positives)

## Proposed Solution

TBD — requires a design decision on the signal. Two candidate approaches:

**Option A**: Add a `missing_artifacts: true` field to confidence-check Phase 4.x write-back, set when `outcome_confidence` is low and specific signal phrases indicate absent files or wiring gaps (e.g., "absent", "not yet created", "does not exist", "needs wiring"). `triage_outcome_failure` reads this field directly.

> **Selected:** Option A (`missing_artifacts: true`) — exact parallel to the existing `decision_needed: true` mechanism in Phase 4.6; all infrastructure (signal-phrase scan → boolean write → `d.get()` read in triage) already exists.

**Option B**: Add a `wire_status: incomplete` field to confidence-check write-back using the existing wiring-gap detection in Phase 4.5. `triage_outcome_failure` checks `wire_status == "incomplete"` before falling through to `detect_children`.

Option A is more explicit and self-documenting in the issue frontmatter. Option B reuses a concept that may already be tracked elsewhere. The decision should consider whether `wire-issue` or `refine-issue` is the right target (they overlap: `wire-issue` is for integration points, `refine-issue` for missing codebase context).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-04-26.

**Selected**: Option A (`missing_artifacts: true`)

**Reasoning**: Option A is a direct clone of the Phase 4.6 `decision_needed` mechanism — scan Outcome Risk Factors for signal phrases, write a boolean frontmatter field, read it in `triage_outcome_failure` via `d.get()`. The entire pattern (signal-phrase list, Edit-tool frontmatter write, `ll-issues show --json` + Python exit-code routing in `autodev.yaml:386-411`) already exists and can be copied verbatim. Option B (`wire_status: incomplete`) has no codebase precedent — the field does not exist anywhere, Phase 4.5 has no dedicated wiring-gap detection, and a string-enum routing check would introduce a new pattern type inconsistent with the boolean-flag convention.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`missing_artifacts: true`) | 3/3 | 3/3 | 3/3 | 3/3 | **12/12** |
| Option B (`wire_status: incomplete`) | 1/3 | 1/3 | 2/3 | 1/3 | **5/12** |

**Key evidence**:
- Option A: `decision_needed: true` set by Phase 4.6 (confidence-check SKILL.md:509-513), read by `triage_outcome_failure` at autodev.yaml:380 — identical pattern ready to reuse. `missing_artifacts: true` already appears in the issue's own test fixture (line 73), confirming author intent.
- Option B: `wire_status` confirmed absent from entire codebase (grep across .md/.yaml/.json/.py); Phase 4.5 writes generic risk factors only — no wiring-specific detection code exists; string-valued field would also risk semantic collision if `wire-issue` later writes the same field.

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

## API/Interface

TBD — pending design decision (see Proposed Solution). New frontmatter field written by `confidence-check` Phase 4.x write-back:

- **Option A**: `missing_artifacts: true` — set when `outcome_confidence` is low + artifact-absence signal phrases detected
- **Option B**: `wire_status: incomplete` — set when Phase 4.5 wiring-gap detection triggers

Read by `triage_outcome_failure` in `autodev.yaml` to route artifact-blocked issues to `run_wire`/`run_refine`.

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
- `/ll:decide-issue` - 2026-04-26T17:24:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42fabf89-9803-43b2-ae07-b91aa0889500.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:format-issue` - 2026-04-26T17:20:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1ca7be1e-da8b-4aa2-922c-a8891aadd970.jsonl`
- `/ll:capture-issue` - 2026-04-25T19:14:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d254d7af-8d9d-458c-aec5-e845416d235d.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
