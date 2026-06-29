---
id: BUG-2375
title: "recursive-refine 'skipped-decision.txt' is misnamed \u2014 decision-needed\
  \ issues are still implemented; rename and document the policy"
type: BUG
status: done
priority: P3
captured_at: '2026-06-28T00:00:00Z'
completed_at: '2026-06-29T03:33:08Z'
discovered_date: '2026-06-28'
discovered_by: audit-loop-run
labels:
- loops
- fsm
- naming
- docs
relates_to:
- BUG-2374
confidence_score: 91
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2375: recursive-refine 'skipped-decision.txt' is misnamed and undocumented

## Summary

`recursive-refine.check_decision_needed` (`recursive-refine.yaml:538-544`) writes
an issue ID to `recursive-refine-skipped-decision.txt` when the issue carries
`decision_needed: true`. The filename implies the issue was **skipped**, but the
write happens *after* the issue already passed confidence and was appended to
`recursive-refine-passed.txt` (lines 260/491). So the issue still flows into
`implement-issue-chain` and gets implemented — the `-skipped-decision.txt` file
is only an informational sidecar, not a skip.

In the `2026-06-28` audit, FEAT-370 appeared in
`recursive-refine-skipped-decision.txt` yet `record_implemented` fired for it.
That is the **expected** behavior (it passed confidence), but the "skipped"
naming makes it read like a bug — a decision-gate miss that was nonetheless
implemented without review.

## Current Behavior

`check_decision_needed` in `recursive-refine.yaml` writes an issue ID to
`recursive-refine-skipped-decision.txt` when the issue carries `decision_needed: true`
and has passed the confidence gate. Despite the "skipped" name, the issue is also
present in `recursive-refine-passed.txt` and flows through to `implement-issue-chain`
where it is implemented normally. The file acts as an informational sidecar, but its
name implies the issue was excluded from implementation.

## Steps to Reproduce

1. Run `ll-loop run recursive-refine` against a backlog containing an issue with
   `decision_needed: true` that passes the confidence gate (score ≥ threshold).
2. After the run completes, open the run-dir sidecar
   `.loops/runs/<run>/recursive-refine-skipped-decision.txt`.
3. Observe the same issue ID also appears in `recursive-refine-passed.txt`.
4. Observe that `record_implemented` fired for the issue — it was implemented, not skipped.
5. Note the contradiction: the "skipped-decision" filename implies exclusion, but the
   issue proceeded to full implementation.

## Root Cause

- **File**: `scripts/little_loops/loops/recursive-refine.yaml`
- **Anchor**: `check_decision_needed` (line ~538); the `decision` sidecar write
- **Cause**: the file is named with a `skipped-` prefix despite recording issues
  that are *not* skipped. The decision gate only short-circuits the **size
  review** step, not implementation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Current code at `check_decision_needed` (lines 538–552)**: exits 1 when
  `decision_needed: true`, routing to `on_no: dequeue_next`. Decision-needed
  issues ARE genuinely skipped (entire issue dequeued), not just "size-review
  skipped." The original bug description ("issues still flow into
  implement-issue-chain") does **not** match current code.
- **`implement-issue-chain.yaml` was deleted by ENH-2389** — this downstream
  concern is no longer relevant.
- **`skipped-decision.txt` naming is therefore accurate** for current behavior:
  issues with `decision_needed: true` are skipped and written to that sidecar.
- **Real inaccuracy**: the comment at line 539 says "Gate: skip size-review if
  the issue has decision_needed: true" — but `dequeue_next` skips the whole
  issue, not just size-review. The comment is misleading even though the
  behavior is correct.
- **`LOOPS_REFERENCE.md` line 1037** already documents this sidecar and policy
  correctly: "issues skipped because `decision_needed: true` was set are
  recorded in `recursive-refine-skipped-decision.txt`…run `/ll:decide-issue`
  on each to resolve the ambiguity, then re-run `recursive-refine`."
- **No tests** assert on the `recursive-refine-skipped-decision.txt` filename.

## Expected Behavior

Either (a) the file is renamed to a non-"skipped" name (e.g.
`recursive-refine-decision-needed.txt`) and the "issues here still proceed to
implementation" policy is documented, or (b) if review-before-implement was the
intent, a guard is added upstream so decision-needed issues are held back. The
audit's analysis points to (a): the issue legitimately passed confidence.

## Integration Map

### Files to Modify (option a — recommended)
- `scripts/little_loops/loops/recursive-refine.yaml` — rename the sidecar file
  and update the comment at `check_decision_needed`.
- `docs/guides/LOOPS_REFERENCE.md` — document that decision-needed issues that
  pass confidence still proceed to implementation; the sidecar is informational.

### Dependent Files (Callers/Importers)
- N/A — the sidecar filename is only written within `recursive-refine.yaml`; no
  external code reads or imports it directly.

### Similar Patterns
- N/A — no other built-in loops use a `-skipped-*` sidecar naming convention.

### Tests
- `scripts/tests/test_builtin_loops.py` — update any assertion referencing
  `recursive-refine-skipped-decision.txt` to the new name.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — already listed under Files to Modify above;
  document the "decision-needed issues that pass confidence proceed to implementation"
  policy.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No rename needed**: `skipped-decision.txt` is accurate — current code
  genuinely skips (dequeues) issues with `decision_needed: true`.
- **`implement-issue-chain.yaml` deleted** (ENH-2389) — remove from any
  references; the downstream "still implemented" scenario cannot occur.
- **`LOOPS_REFERENCE.md:1037` already documents this** sidecar correctly —
  no documentation task remains.
- **No tests assert on `recursive-refine-skipped-decision.txt`** filename —
  the test update listed above is not needed.
- **Narrowed scope**: the only remaining actionable item is fixing the comment
  at `recursive-refine.yaml:539` from "skip size-review" to accurately reflect
  that `dequeue_next` skips the entire issue, not just size-review.

### Configuration
- N/A

## Acceptance Criteria

- [ ] Fix the comment at `recursive-refine.yaml:539` — currently says "skip
      size-review if the issue has decision_needed: true" but `dequeue_next`
      skips the entire issue, not just size-review. One-line comment correction.

_Resolved by refine research: sidecar rename not needed (name is accurate); LOOPS_REFERENCE.md already documents this sidecar at line 1037; no tests assert on the filename._

## Impact

- **Priority**: P3 — naming/clarity issue; no incorrect work is performed today.
- **Effort**: Small — rename + doc, or a small guard.
- **Risk**: Low.
- **Breaking Change**: No.

## Notes

Resolve the intent question first (is decision-needed-but-passed meant to proceed
to implementation?). The audit and the FSM both indicate yes. If so, this is a
pure rename + documentation task.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-29_

**Readiness Score**: 79/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 75/100 → AT threshold

### Concerns
- **Root cause description vs. current YAML**: The issue says decision-needed issues "still flow into `implement-issue-chain`", but in `recursive-refine.yaml:538–552`, `check_decision_needed` exits 1 when `decision_needed: true` → routes to `on_no: dequeue_next` — the issue IS skipped in current code. Verify whether the YAML was already patched (e.g. by BUG-2377 or ENH-2389) before treating this as active misbehavior. If patched, remaining work is purely documentation + optional rename for clarity.
- **Intent question not resolved**: Notes says "Resolve the intent question first" without recording a resolution. The Integration Map labels option (a) "recommended" — treat that as the decision and proceed with rename.

## Session Log
- `/ll:ready-issue` - 2026-06-29T03:25:37 - `acd5c0fa-39aa-4ee0-99de-c8a44a244abd.jsonl`
- `/ll:refine-issue` - 2026-06-29T03:19:40 - `9535fd39-804f-46ad-b629-9ae36fea7ac3.jsonl`
- `/ll:format-issue` - 2026-06-29T03:07:01 - `df10c8d3-ad0a-4b25-b8d2-a795c445864c.jsonl`
- `audit-loop-run` - 2026-06-28 - `.loops/audits/2026-06-28-sprint-refine-and-implement-audit.md`
- `/ll:confidence-check` - 2026-06-29T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-06-28T00:00:00Z - `93bd3ae3-6342-4184-a59f-60566f44aaac.jsonl`

---

## Status

**Open** | Created: 2026-06-28 | Priority: P3
