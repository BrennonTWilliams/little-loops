---
id: ENH-2967
title: autodev.yaml re-derives the DESIGN_FAIL predicate in three inline blocks
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2852
- ENH-2870
- BUG-2956
testable: true
labels:
- loops
- issues
- autodev
---

# ENH-2967: `autodev.yaml` re-derives the `DESIGN_FAIL` predicate in three inline blocks

## Summary

Three independent inline-Python blocks in `autodev.yaml` each shell out to
`ll-issues format-check --format json` and re-derive the same
"Program Design gate failed" boolean by hand. `issue_parser.py` already
computes that predicate once. Expose it as a CLI verdict and have the loop
consume it instead of reimplementing it three times.

## Current Behavior

`scripts/little_loops/loops/autodev.yaml` at `L1095`, `L1594`, and `L1758`
each contain a near-identical block:

```bash
DESIGN_JSON=$(ll-issues format-check "$ID" --format json 2>/dev/null || echo '{}')
DESIGN_FAIL=$(printf '%s' "$DESIGN_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
nonspecific = d.get('program_design_nonspecific') or []
missing = d.get('missing') or []
empty = d.get('empty') or []
fail = bool(nonspecific) or ('Program Design' in missing) or ('Program Design' in empty)
print('true' if fail else 'false')
" 2>/dev/null || echo "false")
```

The same OR-of-three-gap-classes appears a fourth time as prose in
`commands/ready-issue.md` (`L233-237`), documented there as a deliberately
surface-only, non-blocking check.

## Expected Behavior

One place computes "did the Program Design gate fail for this issue," and
every consumer asks it. The loop's shell blocks reduce to an exit-code or
single-field check with no inline JSON parsing.

## Motivation

The duplication is currently *benign but fragile*, and it is worth being
precise about which:

- **Semantic changes propagate correctly today.** All three blocks read the
  same JSON fields, so a change to what `program_design_nonspecific` *means*
  reaches them automatically. This is not an active correctness bug.
- **Shape changes break all three silently.** Rename a gap class, nest the
  gap set under a wrapper key, or split `missing` — and every block falls
  through its `except Exception` / `|| echo "false"` path to
  `DESIGN_FAIL=false`. The gate does not error; it silently stops gating, and
  design-less issues sail into implementation. That is the same
  fail-quiet-on-parse-error shape MR-10 exists to flag in loop YAML.
- The blocks are also invisible to the Python test suite — nothing imports
  them, so a refactor of `FormatGaps` gets no failing test from this
  direction.

BUG-2956 accumulated this finding during its wiring pass; that issue was
closed as not-reproducible on 2026-08-01, and the finding was explicitly
carried forward here rather than dying with it.

## Proposed Solution

Add a first-class verdict to the CLI so the predicate has one owner.

**Option A (preferred): a dedicated exit-code check.** Extend the existing
`ll-issues check-*` family (`check-flag`, `check-readiness`,
`check-decidable`, `check-open-questions`) with `check-design <id>` — exit 0
when the gate passes, 1 when it fails. The loop blocks become:

```bash
if ! ll-issues check-design "$ID"; then
  touch ${context.run_dir}/autodev-design-gate-failed-$ID
fi
```

This matches how `check-readiness` is already consumed three lines below the
first duplicated block, so the loop gains no new idiom.

**Option B: a derived field on the JSON payload.** Add
`design_gate_failed: bool` to `FormatGaps.to_dict()`. Cheaper, but leaves the
loop parsing JSON inline and keeps the fail-quiet `except` path.

Option A is preferred because it removes the inline Python entirely, which is
the part that fails silently.

Whichever is chosen, the predicate itself must live next to the gap
computation in `issue_parser.py` / `issues/program_design.py`, not in the CLI
layer, so `is_formatted()` and any future consumer share it.

## Program Design

### Types

**No new types.** The predicate is a `bool` derived from the existing
`FormatGaps` (`issue_parser.py:232`).

### Signatures

- `design_gate_failed(gaps: FormatGaps) -> bool` — new, in `issue_parser.py`
  beside `FormatGaps`; returns
  `bool(gaps.program_design_nonspecific) or "Program Design" in gaps.missing
  or "Program Design" in gaps.empty`. Single owner of the OR.
- `cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int` —
  Option A's subcommand, modeled on `cmd_check_readiness`; calls
  `check_format_gaps()` then `design_gate_failed()`.

Note `FormatGaps.to_dict()` (`issue_parser.py:268`) must gain the field under
Option B — and per the `testable` regression, any new category surfaced there
also needs its text-mode rendering path, though a derived `bool` is a
different shape from a gap list and may not belong in `_print_gaps` at all.

### Call Path

`cmd_check_design` → `check_format_gaps` → `design_gate_failed` → exit code

`autodev.yaml` (three sites) → `ll-issues check-design` → exit code, replacing
the inline `python3 -c` blocks entirely.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `design_gate_failed()` beside
  `FormatGaps`.
- `scripts/little_loops/cli/issues/` — the `check-design` subcommand
  (Option A), registered in `cli/issues/__init__.py` alongside the other
  `check-*` entries.
- `scripts/little_loops/loops/autodev.yaml` — the three blocks at `L1095`,
  `L1594`, `L1758`.

### Dependent Files
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` gate
  (`L114`) invokes `ll-issues format-check "$ID"` directly. Different check
  (whole-format, not design-specific), so likely unaffected — confirm during
  implementation rather than assuming.
- `commands/ready-issue.md` (`L233-237`) — documents the same OR as a
  surface-only check, explicitly to avoid "two gates enforcing the same
  requirement with different remedies." If the predicate gains a CLI home,
  this prose should point at it rather than restate it. Note its
  non-blocking framing is deliberate and must survive.
- `skills/confidence-check/SKILL.md` — Phase 1.6 consumes the gate as a hard
  override; check whether it too restates the OR.

### Similar Patterns
- `ll-issues check-readiness` — consumed by `autodev.yaml` immediately after
  the first duplicated block (`L1111-1113`); the exact idiom Option A adopts.
- `ll-verify-skill-prose` (ENH-2951) — exists precisely to catch prose
  reimplementations of logic that lives in `scripts/little_loops/`. Inline
  loop-YAML Python is the same failure class in a corpus that linter does not
  currently scan; worth noting whether its marker table could extend to
  `loops/*.yaml`.

## Implementation Steps

1. Add `design_gate_failed()` to `issue_parser.py`; unit-test it against each
   of the three gap-class inputs and their combinations.
2. Add `ll-issues check-design` (Option A) with exit-code semantics matching
   `check-readiness`.
3. Replace the three `autodev.yaml` blocks; confirm each retains its distinct
   surrounding behavior (`L1095`'s block also gates
   `autodev-staged.txt` via a chained `&&`, which the others do not).
4. Grep for any fourth restatement of the OR in skills/commands and point it
   at the new check.
5. Add a loop-level test asserting the gate still blocks a design-less issue —
   the coverage that does not exist today.

## Scope Boundaries

**In scope:**
- One owner for the design-gate predicate; the three `autodev.yaml` call
  sites; a `check-*` subcommand.

**Out of scope:**
- Changing what the Program Design gate *means* or when it fires — this is a
  refactor of who computes it, not a semantics change (ENH-2852 owns the
  semantics).
- `rn-remediate.yaml`'s `ensure_formatted` whole-format gate.
- Other inline-Python blocks in `autodev.yaml` unrelated to this predicate.

## Impact

- **Priority**: P3 — no active defect; a fail-quiet fragility plus
  three-way duplication. Not P2 because the current behavior is correct and
  the failure requires someone to change `FormatGaps`' shape.
- **Effort**: Small — one function, one subcommand, three YAML edits.
- **Risk**: Low-Medium — the risk is in the YAML edits, not the Python.
  Each of the three blocks sits in different surrounding control flow
  (`L1095` chains into `autodev-staged.txt`; the other two branch twice on
  `DESIGN_FAIL`), so a mechanical find-replace would be wrong.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T16:20:51 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
