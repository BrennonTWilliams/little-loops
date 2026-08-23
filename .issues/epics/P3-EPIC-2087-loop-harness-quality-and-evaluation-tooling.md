---
id: EPIC-2087
title: Loop Harness Quality & Evaluation Tooling
type: EPIC
priority: P3
status: open
verify_verdict: VALID
captured_at: '2026-06-10T18:37:38Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
relates_to:
- ENH-2079
- ENH-2080
- ENH-2081
- ENH-2082
- ENH-2084
- ENH-2086
- BUG-2482
---

# EPIC-2087: Loop Harness Quality & Evaluation Tooling

## Motivation

Loops are authored and iterated subjectively — authors assess quality via spot checks and self-evaluation, both of which are unreliable. This epic closes the gap between loop authoring and empirical harness quality by shipping: better static validation (new MR rules), richer runtime measurement (Wilson CI, cross-host baselines), automated eval task generation from existing ll config formats, and a failure-mode detector for shallow iteration. Together they make loops *measurably* correct rather than subjectively reviewed.

## Scope

### In Scope
- Static validation rules that catch authoring anti-patterns before runtime
- Statistical rigor in baseline comparison output
- Automated generation of eval tasks from ll's own YAML/config artifacts
- Failure-mode detection for loops that iterate without meaningful progress
- Cross-host baseline validation

### Out of Scope
- UI or dashboard for loop quality metrics
- Changes to the FSM executor core
- Loop authoring wizard changes (covered by separate issues)

## Children

- **ENH-2079** — Enforce generator-fix discipline in meta-loop validation (MR-6)
- **ENH-2080** — Add retry-budget calibration guide tied to evaluator health
- **ENH-2081** — Generate DSL-native eval tasks from ll's own config formats
- **ENH-2082** — Add shallow-iteration failure mode detector to loop audit
- **ENH-2084** — Add Wilson CI reporting to ll-loop run --baseline
- **ENH-2086** — Add cross-host validation option to ll-loop run --baseline

- **BUG-2482** — Shallow-iteration heuristic blind for gitignored run dirs *(parented 2026-07-05 as a defect in ENH-2082's shipped detector)*

- **ENH-3298** — Baseline verdicts ignore the Wilson CIs they print — **open**; completes ENH-2084's half-landed statistical rigor, whose ACs asked only that the CI be *displayed*

**Re-parented out 2026-08-23** to EPIC-3299 (artifact templates), which describes
what they actually deliver: FEAT-2301, FEAT-3036, ENH-3035. All three had landed
here by automated sweep rather than a scoping decision, and two of them
(FEAT-2301's authoring UI, the dashboards FEAT-3036 anticipates) fall under this
epic's own Out-of-Scope list.

## Implementation Notes

Delivery order suggestion:
1. ENH-2084 (Wilson CI) — pure formula addition, no coupling
2. ENH-2079 (MR-6) — extends existing validate rule registry
3. ENH-2082 (shallow-iteration detector) — extends loop audit
4. ENH-2086 (cross-host baseline) — depends on baseline infra from ENH-2084
5. ENH-2081 (DSL-native eval tasks) — standalone generation utility
6. ENH-2080 (retry-budget guide) — documentation, can land any time

## Acceptance Criteria

- [x] All seven original child issues are resolved (ENH-2079/2080/2081/2082/2084/2086, BUG-2482)
- [x] `ll-loop validate` enforces MR-6 with suppression flag — `_validate_generator_fix_discipline` in `scripts/little_loops/fsm/validation/meta_rules.py:358`, suppressed by top-level `generator_fix_ok: true`
- [x] `ll-loop run --baseline` reports Wilson 95% CI alongside point estimates
- [ ] Baseline **conclusions** are CI-aware, not just the display — ENH-3298
- [x] `ll-loop run --baseline` supports `--cross-host` validation
- [x] Shallow-iteration failure mode detection — originally delivered by ENH-2082 as a step in the `/ll:audit-loop-run` skill (fixture `assess-shallow-iteration.yaml` + skill step). **Superseded 2026-08-01 by ENH-2949** (under EPIC-2938), which landed exactly the `ll-loop audit --json` subcommand this line previously said would not be built; `skills/audit-loop-run/SKILL.md:206` now calls it for deterministic `tool_call_count` / `aux_mutation_count` / `diff_stall_present` counters. Treat the earlier "not as a CLI subcommand" wording as historical, not as a design constraint.
- [x] DSL-native eval task generation is available for ll config formats — `ll-loop scaffold-eval`
- [x] Retry-budget calibration guidance is documented — `ll-loop calibrate-budget` + `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`

## Verification Notes

- 2026-08-10: Verified 2026-08-10: original 6-item AC checklist (ENH-2079/80/81/82/84/86, BUG-2482) is fully done but checkboxes remained unchecked in the AC section — checked off. Two later children (FEAT-3036, ENH-3035, added 2026-08-04) are legitimately still open, so the epic correctly stays open pending those.

- 2026-08-23: Re-reviewed against the epic's stated goal. All seven original
  deliverables verified present in the tree, not merely marked done — MR-6
  (`fsm/validation/meta_rules.py:358`), `stats.wilson_ci` wired into both the A/B
  summary and `diagnose-evaluators`, `--cross-host` (`_run_cross_host_validation`),
  `ll-loop scaffold-eval`, `ll-loop calibrate-budget`, and `ll-loop audit --json`.

  Two corrections to this file: (1) the shallow-iteration AC's "not as an
  `ll-loop audit` CLI subcommand" clause went stale when ENH-2949 built that
  subcommand on 2026-08-01 — annotated above so it is not honored as a
  constraint; (2) FEAT-2301 / FEAT-3036 / ENH-3035 re-parented to EPIC-3299.

  One genuine gap found and filed as **ENH-3298**: ENH-2084 added Wilson CIs to
  the *display* but nothing consumes them. `_print_ab_summary`
  (`cli/loop/_helpers.py:2074`) picks its verdict from `results.delta > 0`, and
  `_print_cross_host_table` (`:2213`) gates its ordering-reversal warning the
  same way — so a one-item delta at n=5 is reported as confidently as a decisive
  one. `grep -rnE 'overlap|significan|inconclusive'` over `cli/loop/`,
  `stats.py`, and `ab_writer.py` returns nothing.

  With ENH-3298 closed, this epic has no remaining work under its stated scope.

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:04:16 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:08 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
<!-- ll-private-ok: repo-relative project slug for the local session-store path, not a private absolute path -->
- `/ll:capture-issue` - 2026-06-10T18:37:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef92cf80-1078-41c4-8aca-bc4d37e1afbb.jsonl`

---

## Status

open
