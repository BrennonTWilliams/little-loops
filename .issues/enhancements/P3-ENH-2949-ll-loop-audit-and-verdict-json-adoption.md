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

Two related offloads: (a) `skills/audit-loop-run/SKILL.md` (480 lines) asks the LLM to count events and do arithmetic by hand; (b) `cli/action.py`'s `VERDICT_JSON:` / `REVIEW_JSON:` structured-output contract is only *partially* adopted — the `REVIEW_JSON` half has two emitters, the `VERDICT_JSON` half has none — so verifier telemetry still degrades to coarse exit codes.

## Current Behavior

- audit-loop-run: `ls -d .loops/.history/*-<loop>/ | sort | tail -1` run resolution (L45), `wc -l | awk` event counting (L128), "Count the number of `action_complete` events" (L210), aux-mutation tallies (L218–229), budget-utilization arithmetic (Step 5.6), fixed verdict table (Step 6b). Steps 7–9 (rubric-vs-description audit, sub-loop verdict-laundering detection, ranked improvement proposals) are genuine analysis.
- **Adoption state (verified 2026-07-31, corrects this issue's original "zero skills emit" premise):**
  - `REVIEW_JSON:` **is** emitted by `skills/audit-loop-run/SKILL.md:103,440` and `commands/audit-architecture.md:165`.
  - `VERDICT_JSON:` has **no** emitter — so `_record_verdict` falls back to exit-code-only readings for all 9 `_VERIFIER_SKILLS`.
  - The docstrings at `cli/action.py:74` and `:118` both still assert "No skill currently emits …" — **stale**, and the misinformation that produced this issue's original framing.

## Expected Behavior

- `ll-loop audit <run|--latest LOOP> --json` — resolves the run dir, computes all counters (events by type, per-state tallies, aux mutations, durations, budget utilization) and the deterministic verdict-table inputs; the skill consumes the stats blob and keeps only Steps 7–9 interpretation. **Lives under `ll-loop`, not `ll-logs`**: loop-run artifacts are in `.loops/` history dirs already read by `ll-loop history`/`audit-meta`, while `ll-logs` operates on host session logs. No new entry point (FEAT-2940 stays the epic's only one).
- At least one `_VERIFIER_SKILLS` member touched by EPIC-2938 (confidence-check is the natural first adopter, already slimmed by ENH-2946) emits a final `VERDICT_JSON: {...}` line per the `cli/action.py` contract (`verdict`, `severity_counts`, `findings_count`, `confidence`, `target_id`, `target_kind`), so `_record_verdict` stops degrading to exit codes.
- The stale docstrings at `cli/action.py:74` and `:118` are corrected to state the real adoption position (which skills emit which tag), so the next reader doesn't repeat this issue's original error.

## Proposed Solution

Counters reuse the event-stream access patterns of `ll-loop history`/`audit-meta`; contract shapes come from `output_parsing.extract_tagged_json` and `action.py`'s `_VERIFIER_SKILLS`/`_REVIEWER_SKILLS` field expectations.

## Implementation Steps

1. `ll-loop audit` + tests (fixture run dirs; counter parity with the skill's current formulas).
2. Slim `skills/audit-loop-run/SKILL.md` to invocation + Steps 7–9.
3. Add the `VERDICT_JSON` trailer to confidence-check (and any other `_VERIFIER_SKILLS` member this epic already touches); verify `ll-action invoke` records structured verdicts (test via `_record_verdict` path). `REVIEW_JSON` needs no new emitters unless a reviewer skill this epic slims lacks one — check `audit-loop-run` retains its trailer after step 2's rewrite.
4. Correct the `cli/action.py:74` / `:118` docstrings to name the actual emitters.

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

- In scope: `ll-loop audit` counters + JSON; slimming audit-loop-run to Steps 7–9 **without dropping its existing `REVIEW_JSON` trailer**; the first `VERDICT_JSON` emitter (confidence-check); correcting the stale `action.py` docstrings.
- Out of scope: new entry points, `ll-logs` (host-session logs — different corpus), retrofitting the trailer to all 16 verifier/reviewer skills (follow-up if >3 skills needed).

## Impact

- **Priority**: P3 - Observability/telemetry quality; nothing else in the epic blocks on it
- **Effort**: Medium - Counters straightforward; trailer adoption spans a few skills
- **Risk**: Low - Read-only audit; trailer is additive to skill output

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] `ll-loop audit --json` reproduces every counter the skill currently computes
- [ ] audit-loop-run contains no counting/arithmetic instructions, and still emits its `REVIEW_JSON` trailer after slimming
- [ ] At least one `_VERIFIER_SKILLS` member emits `VERDICT_JSON:` and `_record_verdict` captures the structured fields (test asserts non-exit-code-derived values land in the DB)
- [ ] `cli/action.py:74` / `:118` docstrings state the real adoption position
- [ ] pytest coverage in `scripts/tests/`

## Notes

(a) and (b) are separable — split if VERDICT adoption touches more than ~3 skills. Soft-dep: land after ENH-2946 so confidence-check is already slimmed.

Review correction (2026-07-31): this issue originally claimed zero skills emit either tag. `REVIEW_JSON` had two emitters at scoping time; only the `VERDICT_JSON` half was genuinely unadopted.
