---
id: ENH-1903
title: Document ll-parallel as canonical parallel substrate
type: ENH
priority: P4
status: open
captured_at: 2026-06-03 19:12:39+00:00
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to:
- FEAT-1901
- FEAT-1902
- FEAT-1899
blocked_by:
- FEAT-1899
confidence_score: 70
outcome_confidence: 86
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1903: Document ll-parallel as canonical parallel substrate

## Summary

Update architecture documentation to formalize `ll-parallel` as the canonical
parallel substrate for EPIC-1867's layered architecture. No code changes.

Deliverables:
- `CLAUDE.md` CLI Tools section: add note that `ll-parallel` is the canonical
  parallel substrate used by `ll-sprint` multi-issue waves; explicitly document
  that `ll-parallel` is kept as Python (no FSM equivalent — no concurrency primitive).
- `docs/ARCHITECTURE.md`: add/update orchestration layer diagram showing
  Layer 0 (internal library + CLI subcommands), Layer 1 (FSM + `ll-auto` shim),
  Layer 2 (wave driver + `ll-sprint` shim), and Layer 3 (`ll-parallel`, unchanged).
- Reference `docs/research/ll-orchestrator-decomposition-plan-v0.2.md` from
  `docs/ARCHITECTURE.md` for the full decomposition rationale.

Should be written last, after FEAT-1902 and FEAT-1899 are merged, so the docs
reflect the final implementation.

## Impact

- **Priority**: P4 — docs only; no code changes
- **Effort**: Small — documentation edits in 2–3 files
- **Risk**: Low
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-03 | Priority: P4


## Verification Notes

**Verdict**: VALID — 2026-06-09T00:00:00

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- FEAT-1902 (now **done**) removed from `blocked_by`; still blocked by FEAT-1899 (open)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-07_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- FEAT-1899 (`ll-sprint` FSM wave driver and shim) is still open; the issue explicitly states implementation should occur after both FEAT-1902 and FEAT-1899 are merged. The Layer 2 content of the architecture diagram cannot be accurately documented until FEAT-1899 delivers the wave driver.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The CLAUDE.md CLI Tools section note added by this issue and the CLAUDE.md Loop Authoring compaction by ENH-2023 target overlapping sections of `.claude/CLAUDE.md`. If ENH-2023 lands before this issue, ENH-2023's compaction pass must explicitly include the `ll-parallel` canonical substrate note, or the note will be lost in the collapse. Coordinate: either sequence this issue's CLAUDE.md commit before ENH-2023, or confirm ENH-2023's diff includes the `ll-parallel` addition in its revised § Loop Authoring table.

## Session Log
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:02 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `2b586685-5335-49af-953f-8e65bba5e334.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:47:23 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
