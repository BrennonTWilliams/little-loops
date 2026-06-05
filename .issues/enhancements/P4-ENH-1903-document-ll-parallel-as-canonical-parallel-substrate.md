---
id: ENH-1903
title: Document ll-parallel as canonical parallel substrate
type: ENH
priority: P4
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: [FEAT-1901, FEAT-1902, FEAT-1899]
blocked_by: [FEAT-1902, FEAT-1899]
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

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:47:23 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
