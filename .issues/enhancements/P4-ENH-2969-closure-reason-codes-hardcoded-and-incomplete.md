---
id: ENH-2969
title: Closure reason codes are a hardcoded set; invalid_ref is documented but rejected
type: ENH
priority: P4
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2870
- ENH-2664
- BUG-2956
testable: true
labels:
- issues
- cli
---

# ENH-2969: Closure reason codes are a hardcoded set; `invalid_ref` is documented but rejected

## Summary

`_CLOSED_REASON_CODES` (`cli/issues/set_status.py:17`) is a hardcoded literal
set of two values. Three docstrings advertise a third code the CLI rejects,
and there is no code for the common "closed because it never reproduced"
case. The sibling deferral set one line above was already migrated off exactly
this shape.

## Current Behavior

```python
# ENH-2870: derived from DeferReason so the two can't drift out of lockstep
# (previously a hardcoded literal set duplicating the enum).
_DEFERRAL_REASON_CODES = frozenset(r.value for r in DeferReason)
_CLOSED_REASON_CODES = frozenset({"already_fixed", "superseded"})
```

Two concrete defects follow:

**1. A documented code is rejected.** `invalid_ref` appears as an example
closure reason in three docstrings — `output_parsing.py:263`
(*"close_reason: str|None (e.g., 'already_fixed', 'invalid_ref')"*),
`issue_lifecycle.py:285`, and `issue_lifecycle.py:670` — but:

```
$ ll-issues set-status BUG-2956 cancelled --reason invalid_ref
error: argument --reason: invalid choice: 'invalid_ref'
  (choose from already_fixed, blocked_by_unmet, decision_unresolved,
   design_gate_failed, gate_blocked, low_readiness, oversized_atomic,
   readiness_stagnated, remediation_stalled, superseded)
```

**2. No code fits "not reproducible."** Closing BUG-2956 on 2026-08-01 —
an issue whose own research established the described defect *never existed*
(the code was never written the way the report claimed) — required
`--reason already_fixed`, which asserts something false: nothing was fixed.
The frontmatter now carries a closure reason that misdescribes the closure.
`ll-history` and any consumer of closure codes inherit that inaccuracy.

Note also that `--reason`'s choice list mixes deferral and closure codes in
one flat enum, so the error message offers `low_readiness` for a `cancelled`
transition where only two of the ten are valid.

## Expected Behavior

- Closure codes derive from an enum, mirroring `DeferReason`, so the CLI
  surface and the code cannot drift.
- `invalid_ref` either becomes valid or stops appearing in docstrings.
- A code exists for "investigated, did not reproduce / defect never existed" —
  distinct from `already_fixed` ("was real, since fixed").
- Ideally `--reason` validates against the subset legal for the target status
  rather than the union.

## Motivation

Closure codes are machine-readable metadata; their value is entirely in being
accurate enough to aggregate. Two of the three problems actively corrupt that:
a rejected-but-documented code sends callers down a dead end, and forcing
`already_fixed` onto non-reproducible closures inflates the "was a real bug"
population with issues that never were.

The rate matters here. BUG-2956 was closed as not-reproducible today, and its
own confidence-check recommended exactly that outcome — meaning the tooling
*routinely produces* this closure class while having no code for it. This is
not a hypothetical gap.

The fix is also unusually well-specified: `_DEFERRAL_REASON_CODES` sits one
line above, already migrated from a hardcoded literal to an enum derivation
under ENH-2870, with a comment explaining why. This issue applies the same
change to its neighbor.

## Proposed Solution

Mirror `DeferReason` exactly:

1. Add `ClosureReason(Enum)` beside `DeferReason` (`issue_lifecycle.py:58`),
   with the existing `ALREADY_FIXED`/`SUPERSEDED` plus a not-reproducible
   member. Name it deliberately — `NOT_REPRODUCIBLE` covers "could not
   reproduce"; the BUG-2956 case is stronger (the defect provably never
   existed). One member with a docstring distinguishing it from
   `already_fixed` is probably right; two feels like over-modeling until a
   second instance appears.
2. `_CLOSED_REASON_CODES = frozenset(r.value for r in ClosureReason)`.
3. Resolve `invalid_ref`: it reads like a real closure class (issue references
   a symbol/file that no longer exists). Either add it as a member or strike
   it from the three docstrings. Adding is preferable — the docstrings suggest
   someone intended it.
4. Optionally scope `--reason`'s `choices` to the target status. This is the
   only part that changes CLI behavior for existing callers, so it can land
   separately if it risks breaking automation that passes a now-invalid pair.

## Program Design

### Types

- `ClosureReason(Enum)` — new, in `issue_lifecycle.py` beside `DeferReason`
  (`L58`), same shape: `str`-valued members with a per-member comment.
  Members: `ALREADY_FIXED = "already_fixed"`,
  `SUPERSEDED = "superseded"`, `NOT_REPRODUCIBLE = "not_reproducible"`, and
  `INVALID_REF = "invalid_ref"` if step 3 resolves toward adding it.

### Signatures

No function signatures change. The affected bindings are module-level:

- `_CLOSED_REASON_CODES` (`cli/issues/set_status.py:17`) — becomes
  `frozenset(r.value for r in ClosureReason)`.
- `cmd_set_status` (`cli/issues/set_status.py:19`) already writes
  `updates["closed_reason"] = reason` at `L72`/`L76`; unchanged.
- The `--reason` argparse `choices` list (`cli/issues/__init__.py:803`
  region) — currently the union; becomes the union of both derived enums, or
  status-scoped under step 4.

### Call Path

`cmd_set_status` → validate against `_CLOSED_REASON_CODES` (now
enum-derived) → `updates["closed_reason"]` → frontmatter write

Unchanged except for where the valid set comes from.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `ClosureReason` beside
  `DeferReason` (`L58`); the two example docstrings at `L285`, `L670`.
- `scripts/little_loops/cli/issues/set_status.py` — `L17`.
- `scripts/little_loops/cli/issues/__init__.py` — the `--reason` help text
  (`~L803`) already describes the deferral/closure split in prose; update it
  to match whatever step 4 decides.
- `scripts/little_loops/output_parsing.py` — the `L263` docstring example.

### Dependent Files
- `scripts/little_loops/parallel/types.py:69` — documents `close_reason` with
  the same `already_fixed` example; check whether it constrains values.
- `.claude/CLAUDE.md` § Issue File Format — documents the deferral reason
  codes (ENH-2664) in detail but not the closure codes; adding them keeps the
  two symmetric. (See ENH-2970 — CLAUDE.md accuracy is being gated.)

### Similar Patterns
- `DeferReason` (`issue_lifecycle.py:58`) and its ENH-2870 migration — the
  exact change this issue repeats, including the explanatory comment about
  why the literal set was replaced.

## Implementation Steps

1. Add `ClosureReason` with the existing two members; derive
   `_CLOSED_REASON_CODES` from it. No behavior change yet.
2. Add the not-reproducible member; document how it differs from
   `already_fixed` in its comment.
3. Resolve `invalid_ref` — add as a member, or strike from all three
   docstrings. Do not leave it half-documented.
4. Optionally scope `--reason` choices per target status; land separately if
   it risks existing automation.
5. Re-close BUG-2956 with the accurate code once one exists (it currently
   carries `closed_reason: already_fixed` as a documented approximation).
6. Tests: per-member round-trip through `set-status`, and a test asserting
   every `ClosureReason` member is accepted by the CLI — the drift guard the
   enum derivation is for.

## Scope Boundaries

**In scope:**
- `ClosureReason` enum + derived `_CLOSED_REASON_CODES`.
- The `invalid_ref` documentation/validation mismatch.
- A not-reproducible closure code.

**Out of scope:**
- Deferral codes and `DeferReason` — already correct.
- Changing what `already_fixed` or `superseded` mean, or re-coding
  historical closures beyond BUG-2956 (step 5).
- The supersession graph model (ENH-2829) — `superseded` as a *closure code*
  is distinct from the `supersedes:` edge, and this issue does not touch the
  latter.

## Impact

- **Priority**: P4 — metadata accuracy, no functional breakage. Raised from
  P5 by the documented-but-rejected `invalid_ref`, which is a straightforward
  defect rather than a modeling preference.
- **Effort**: Small — one enum, one derivation, a few docstrings.
- **Risk**: Low, except step 4 (status-scoped `choices`), which could reject
  argument pairs existing automation passes today. Landing it separately
  contains that.
- **Breaking Change**: No — additive to the accepted set. Step 4 alone would
  be narrowing, hence its separation.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T16:20:52 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P4
