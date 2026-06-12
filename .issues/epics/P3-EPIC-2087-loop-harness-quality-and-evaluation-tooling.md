---
id: EPIC-2087
title: Loop Harness Quality & Evaluation Tooling
type: EPIC
priority: P3
status: done
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

## Implementation Notes

Delivery order suggestion:
1. ENH-2084 (Wilson CI) — pure formula addition, no coupling
2. ENH-2079 (MR-6) — extends existing validate rule registry
3. ENH-2082 (shallow-iteration detector) — extends loop audit
4. ENH-2086 (cross-host baseline) — depends on baseline infra from ENH-2084
5. ENH-2081 (DSL-native eval tasks) — standalone generation utility
6. ENH-2080 (retry-budget guide) — documentation, can land any time

## Acceptance Criteria

- [ ] All six child issues are resolved
- [ ] `ll-loop validate` enforces MR-6 with suppression flag
- [ ] `ll-loop run --baseline` reports Wilson 95% CI alongside point estimates
- [ ] `ll-loop run --baseline` supports `--cross-host` validation
- [x] Shallow-iteration failure mode detection — delivered by ENH-2082 as a step in the `/ll:audit-loop-run` skill (fixture `assess-shallow-iteration.yaml` + skill step), not as an `ll-loop audit` CLI subcommand; AC wording updated 2026-06-12 to match the shipped surface
- [ ] DSL-native eval task generation is available for ll config formats
- [ ] Retry-budget calibration guidance is documented

## Session Log
- `/ll:capture-issue` - 2026-06-10T18:37:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ef92cf80-1078-41c4-8aca-bc4d37e1afbb.jsonl`

---

## Status

open
