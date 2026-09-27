---
id: ENH-3625
type: ENH
title: State the first-gate Program Design rule
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:48:55Z'
parent: EPIC-3565
relates_to:
- ENH-3623
- ENH-3621
---

# ENH-3625: State the first-gate Program Design rule

## Summary

Decide the Program Design rule for autodev's first post-refine gate, and write it down.
Today the first gate (`check_passed`) ignores the Program Design verdict, while every
later gate in the ladder hard-ANDs it. The ENH-3621 spike found this asymmetry as quirk
Q3 (report `thoughts/spikes/preparation-policy-spike.md`, § "H2 — first gate skips
check-design" and § Quirks). It is probably intentional, but no comment, doc or test
states it as a rule. ENH-3623's `decide()` has to encode one rule or the other.

## Current Behavior

- `check_passed` (`scripts/little_loops/loops/autodev.yaml`, state at `:726`) runs only
  `ll-issues check-readiness … --honor-waiver`. It does not run `ll-issues
  check-design`. `on_yes` goes on toward implementation.
- `recheck_scores` (`:1890`), `regate_after_atomic_remediation` (`:2277`) and
  `recheck_after_size_review` (`:2589`) each run `ll-issues check-design` and require it
  to pass, together with the readiness/outcome gate.
- As a result, an issue whose scores pass right after the inner `refine-to-ready-issue`
  run is implemented even when its Program Design gate fails. An issue that goes through
  any second-pass remedy cannot pass with a failing design gate. The spike pinned this
  with the differential scenario `h2_first_gate_skips_design` and
  `test_h2_first_gate_ignores_design_and_files_no_marker`.
- The inner loop has a tier-1 `DESIGN` obligation (`refine-to-ready-issue.yaml`,
  `select_obligation` → `DESIGN: check_gate_refine_limit`, BUG-3551), so an inner `done`
  normally implies the design gate was handled. The inner loop also has a selector call
  that skips `DESIGN` (`--skip … DESIGN …`), and the refine budget is shared. Whether an
  inner `done` *guarantees* a passing design gate has not been shown.

## Expected Behavior

One stated rule, applied the same way in the YAML (until ENH-3623 lands) and in
`decide()` (after it lands). Choose one:

- **A. The first gate runs check-design too.** `check_passed` hard-ANDs `ll-issues
  check-design`, the same as the later gates. A design failure goes to the second-pass
  ladder (design remedy, then `design_gate_failed`), not to implementation.
- **B. The inner loop owns the design gate at the first gate.** Keep `check_passed`
  readiness-only. Document that the inner loop's tier-1 DESIGN obligation owns the
  Program Design gate on the first pass. Add a test showing that an inner `done` with
  a failing design gate cannot happen, or that it is the accepted exception.

## Motivation

The spike could only keep parity with the asymmetry. It could not say whether the
asymmetry is intended. `decide()` makes the rule explicit in one table row, so the
choice should be made on purpose before the port, not inherited.

## Proposed Solution

1. Trace whether an inner `refine-to-ready-issue` `done` can leave `ll-issues
   check-design` failing. Check the `--skip DESIGN` selector call and the shared
   refine-limit exhaustion path.
2. If it can, choose A. If it cannot (or only through a documented budget exhaustion
   that ends `failed`), choose B.
3. Record the rule:
   - a comment on `check_passed`;
   - a line in `docs/guides/LOOPS_REFERENCE.md` (autodev section);
   - a structural test pinning the chosen gate shape;
   - a row in ENH-3623's `decide()` table tests.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml`: `check_passed` (comment, or a gate
  change under A)
- `docs/guides/LOOPS_REFERENCE.md`: state the rule

### Tests

- `scripts/tests/test_autodev_characterization.py`: re-pin `h2`-shaped behavior under A
- `scripts/tests/test_autodev_loop.py` or `test_autodev_scores_freshness.py`: a
  structural pin of the first gate

### Documentation

- `docs/guides/LOOPS_REFERENCE.md`

## Program Design

### Types

- N/A — no new types; the rule is a gate shape in `autodev.yaml` and one row in ENH-3623's `decide()` table

### Signatures

- `cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int` — the existing Program Design gate; exit 0 passes. Under option A, `check_passed` calls it; unchanged either way
- `decide(snapshot: IssueSnapshot, facts: Facts) -> Step` — ENH-3623's pure policy; gains one first-gate row encoding the chosen rule

### Call Path

`autodev.yaml:check_passed` -> `ll-issues check-readiness` -> `cmd_check_readiness`; under option A, then `ll-issues check-design` -> `cmd_check_design`

## Impact

- **Priority**: P4. Probably intended behavior; this issue makes it explicit before the
  policy port.
- **Effort**: Small
- **Risk**: Low under B (docs and tests only). Low-Medium under A (more issues take the
  design remedy path).
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the decision, the comment/doc/test, and, under option A, the
  `check_passed` change and its characterization re-pin.
- **Out of scope**: changing the later gates, and changing `check-design` itself.

## Acceptance Criteria

- [ ] The rule (A or B) is chosen, with the trace evidence recorded in this issue
- [ ] `check_passed` carries a comment stating the rule
- [ ] A test pins the chosen first-gate shape
- [ ] ENH-3623's `decide()` table tests include the rule

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-27T02:13:31 - `eab069d8-1487-4826-8057-122a54e92dfd.jsonl`
