---
id: ENH-2949
title: "ll-loop audit <run> --json and VERDICT_JSON adoption in judgment skills"
type: ENH
priority: P3
status: open
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- ENH-2946
labels:
- cli
- loops
- observability
---

# ENH-2949: `ll-loop audit` + VERDICT_JSON structured-output adoption

## Summary

Two related offloads: (a) `skills/audit-loop-run/SKILL.md` (480 lines) asks the LLM to count events and do arithmetic by hand; (b) `cli/action.py` defines and parses a `VERDICT_JSON:` / `REVIEW_JSON:` structured-output contract that **zero skills emit** (per the docstrings at `action.py:74` and `action.py:118`), so verdict telemetry degrades to coarse exit codes.

## Current Behavior

- audit-loop-run: `ls -d .loops/.history/*-<loop>/ | sort | tail -1` run resolution (L45), `wc -l | awk` event counting (L128), "Count the number of `action_complete` events" (L210), aux-mutation tallies (L218–229), budget-utilization arithmetic (Step 5.6), fixed verdict table (Step 6b). Steps 7–9 (rubric-vs-description audit, sub-loop verdict-laundering detection, ranked improvement proposals) are genuine analysis.
- `ll-action`'s `_record_verdict`/`_record_review` fall back to exit-code-only readings for the 9 verifier and 7 reviewer skills because no skill emits the tagged JSON line.

## Expected Behavior

- `ll-loop audit <run|--latest LOOP> --json` — resolves the run dir, computes all counters (events by type, per-state tallies, aux mutations, durations, budget utilization) and the deterministic verdict-table inputs; the skill consumes the stats blob and keeps only Steps 7–9 interpretation. **Lives under `ll-loop`, not `ll-logs`**: loop-run artifacts are in `.loops/` history dirs already read by `ll-loop history`/`audit-meta`, while `ll-logs` operates on host session logs. No new entry point (FEAT-2940 stays the epic's only one).
- The judgment skills touched by EPIC-2938 (confidence-check, audit-loop-run, and go-no-go-adjacent flows) emit a final `VERDICT_JSON: {...}` / `REVIEW_JSON: {...}` line per the `cli/action.py` contract (`verdict`, `severity_counts`, `findings_count`, `confidence`, `target_id`, `target_kind`) so `ll-action` telemetry stops degrading to exit codes.

## Proposed Solution

Counters reuse the event-stream access patterns of `ll-loop history`/`audit-meta`; contract shapes come from `output_parsing.extract_tagged_json` and `action.py`'s `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` field expectations.

## Implementation Steps

1. `ll-loop audit` + tests (fixture run dirs; counter parity with the skill's current formulas).
2. Slim `skills/audit-loop-run/SKILL.md` to invocation + Steps 7–9.
3. Add the VERDICT_JSON/REVIEW_JSON trailer to the touched judgment skills; verify `ll-action invoke` records structured verdicts (test via `_record_verdict` path).

## Program Design

### Types

- `RunAuditStats: dataclass`
  - `run_id: str`
  - `loop: str`
  - `events_total: int`
  - `events_by_type: dict[str, int]`
  - `per_state: dict[str, StateStats]`
  - `aux_mutation_count: int`
  - `budget_utilization: float`
  - `verdict_inputs: dict[str, Any]`
- `StateStats: dataclass`
  - `entries: int`
  - `actions_complete: int`
  - `duration_s: float`

### Signatures

- `resolve_run(run_or_loop: str, latest: bool) -> Path` — `.loops/.history/` resolution now done via `ls | sort | tail`
- `audit_run(run_dir: Path) -> RunAuditStats` — reuses event-stream access from `ll-loop history`/`audit-meta`
- Skill-side contract: final stdout line `VERDICT_JSON: {"verdict": ..., "confidence": ..., "target_id": ..., "target_kind": ...}` / `REVIEW_JSON: {...}` per `cli/action.py` `_record_verdict`/`_record_review` field expectations (parsed by `output_parsing.extract_tagged_json`)

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `resolve_run()` -> `audit_run()`
- `ll-action` invoke path -> `extract_tagged_json()` (existing, `output_parsing.py`) — consumes the new trailers

## Scope Boundaries

- In scope: `ll-loop audit` counters + JSON; slimming audit-loop-run to Steps 7–9; VERDICT_JSON/REVIEW_JSON trailers in confidence-check, audit-loop-run, and go-no-go-adjacent flows touched by this epic.
- Out of scope: new entry points, `ll-logs` (host-session logs — different corpus), retrofitting the trailer to all 16 verifier/reviewer skills (follow-up if >3 skills needed).

## Impact

- **Priority**: P3 - Observability/telemetry quality; nothing else in the epic blocks on it
- **Effort**: Medium - Counters straightforward; trailer adoption spans a few skills
- **Risk**: Low - Read-only audit; trailer is additive to skill output

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] `ll-loop audit --json` reproduces every counter the skill currently computes
- [ ] audit-loop-run contains no counting/arithmetic instructions
- [ ] At least confidence-check and audit-loop-run emit the tagged JSON line, and `ll-action` telemetry captures structured verdicts for them
- [ ] pytest coverage in `scripts/tests/`

## Notes

(a) and (b) are separable — split if VERDICT adoption touches more than ~3 skills. Soft-dep: land after ENH-2946 so confidence-check is already slimmed.
