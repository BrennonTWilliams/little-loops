---
id: ENH-2969
title: Closure reason codes are a hardcoded set; invalid_ref is documented but rejected
type: ENH
priority: P4
status: done
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
confidence_score: 95
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
completed_at: '2026-08-03T19:18:28Z'
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

> ⚠ **Codebase Research Findings**: the two `issue_lifecycle.py` line
> numbers above are stale against the current tree. Line 285 is inside
> `classify_failure()`'s tool-cancellation branch and line 670 is inside
> `_commit_issue_completion()`'s `_resolve_line` helper — neither mentions
> `invalid_ref`. The actual current occurrences are `output_parsing.py:263`
> (`parse_ready_issue_output()` Returns docstring), `issue_lifecycle.py:312`
> (`_build_closure_resolution()` Args docstring), and
> `issue_lifecycle.py:912` (`close_issue()` Args docstring). All three still
> need the same resolution described in step 3 below.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- `DeferReason(Enum)` actually starts at `issue_lifecycle.py:65` (through
  `L88`) — `L58` (cited above and in Implementation Steps step 1) is the
  preceding `DeferBy(Enum)` (`L58-62`), a different two-member enum. Place
  `ClosureReason` beside `DeferReason` at its real anchor, `L65`, not `L58`.
- A sibling `CompletionResult` enum in the same file documents in its own
  docstring why these enums use plain `Enum` with string-valued members
  rather than `StrEnum` — "a repo-wide grep found zero `StrEnum` usages in
  `scripts/little_loops/`." `ClosureReason` should follow the same plain-`Enum`
  convention for consistency, not introduce the first `StrEnum` usage.
- `cmd_set_status`'s `updates["closed_reason"] = reason` writes are inside a
  nested `_status_updates()` (starts `L49`), at `L76` (status `done`) and
  `L80` (status `cancelled`) — not `L72`/`L76` as stated above.
- A second, independent validation block exists at `set_status.py:104-121`,
  inside `cmd_set_status` itself: it checks `reason in _DEFERRAL_REASON_CODES`
  against `args.status not in ("deferred",)` and `reason in
  _CLOSED_REASON_CODES` against `args.status not in ("done", "cancelled")`,
  erroring and exiting 1 on mismatch. This runs after the argparse `choices=`
  gate and is a second consumer of `_CLOSED_REASON_CODES` the Call Path above
  did not name — deriving it from `ClosureReason` automatically keeps this
  check in lockstep too, but an implementer tracing the call path needs both
  consumers, not just the argparse one.
- Repo-wide grep confirms `frozenset(r.value for r in EnumName)` is used in
  exactly two places today: `set_status.py:20` (the `_DEFERRAL_REASON_CODES`
  definition) and `test_issue_lifecycle.py:1992` (the test assertion
  reproducing the same expression). It is a single precedent being extended
  to a second case here, not an established codebase-wide idiom.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `ClosureReason` beside
  `DeferReason` (`L58`); the two example docstrings, currently at `L312`
  (`_build_closure_resolution()`) and `L912` (`close_issue()`) — see the
  Codebase Research Findings note under Current Behavior for why the
  originally-cited `L285`/`L670` are stale.
- `scripts/little_loops/cli/issues/set_status.py` — `L17`.
- `scripts/little_loops/cli/issues/__init__.py` — the `--reason` help text
  (`~L803`) already describes the deferral/closure split in prose; update it
  to match whatever step 4 decides.
- `scripts/little_loops/output_parsing.py` — the `L263` docstring example.
- `docs/reference/CLI.md:1886` — the `--reason` flag's closure-code list in
  the `set-status` reference table; keep in sync with the new enum members.

### Dependent Files
- `scripts/little_loops/parallel/types.py:69` — documents `close_reason` with
  the same `already_fixed` example; check whether it constrains values.
- `.claude/CLAUDE.md` § Issue File Format — documents the deferral reason
  codes (ENH-2664) in detail but not the closure codes; adding them keeps the
  two symmetric. (See ENH-2970 — CLAUDE.md accuracy is being gated.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_manager.py:773` (`process_issue_inplace`)
  already special-cases `close_reason == "invalid_ref"` to skip file
  operations for a stale/nonexistent reference. This is a live consumer that
  already assumes `invalid_ref` is a valid closure code — it currently only
  becomes reachable through non-CLI callers of `close_issue()`, since the
  `set-status` CLI's argparse `choices=` rejects the value first. Adding
  `invalid_ref` as a `ClosureReason` member (step 3) makes this existing
  branch reachable via the CLI too, rather than introducing new behavior.
- `docs/reference/CLI.md:1886` documents the `--reason` flag's closure codes
  explicitly (`already_fixed`, `superseded`; ENH-2749/BUG-2844) alongside the
  deferral codes — not previously listed as a doc site to update; add it to
  the Files to Modify list alongside `.claude/CLAUDE.md`.
- Multiple tests already exercise `invalid_ref` as a valid `close_reason`
  through `parse_ready_issue_output()`/`close_issue()` (not the `set-status`
  CLI, so the argparse gap has never surfaced there):
  `test_output_parsing.py`, `test_issue_manager.py`,
  `test_issue_lifecycle.py:136`, `test_issue_history_advanced_analytics.py`.
- Existing closure-reason coverage in `test_set_status_cli.py` to extend
  (step 6): `test_set_status_done_stamps_closed_reason` (`:431`),
  `test_set_status_cancelled_superseded_stamps_closed_reason` (`:468`),
  `test_set_status_cancelled_without_reason_omits_closed_reason` (`:505`),
  `test_set_status_invalid_reason_rejected` (`:563`),
  `test_set_status_deferral_reason_rejected_on_done` (`:594`),
  `test_set_status_closed_reason_rejected_on_deferred` (`:630`). None of
  these currently exercise a closure code beyond `already_fixed`/`superseded`.
- The drift-guard test shape to model the new `ClosureReason` tests after
  already exists for `DeferReason` in two complementary forms:
  `TestDeferReasonEnum` (`test_issue_lifecycle.py:1977-1993`) asserts set
  equality (`_DEFERRAL_REASON_CODES == frozenset(r.value for r in
  DeferReason)`) as a pure drift guard, and
  `test_set_status_deferred_stamps_autodev_reason_codes`
  (`test_set_status_cli.py:336-390`, parametrized over `DeferReason` values)
  round-trips each literal through `main_issues()` end-to-end (argv →
  frontmatter write). Step 6 should add both forms for `ClosureReason`.

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- `docs/reference/CLI.md` — the `--reason` flag documentation has moved to
  `~L2101` (examples at `L2111-2112`); the `L1886` anchor recorded above is
  now stale.
- `scripts/little_loops/cli/issues/__init__.py` — the `--reason` argparse
  `choices=` assembly (`choices=sorted(_DEFERRAL_REASON_CODES |
  _CLOSED_REASON_CODES)`) is now at `L832-845` (union at `L837`), preceded by
  a comment already asserting both constants are enum-derived — currently
  inaccurate for `_CLOSED_REASON_CODES`. The `~L803` anchor recorded in
  Program Design → Signatures is now stale.
- `scripts/little_loops/issue_manager.py` — the `invalid_ref` special-case
  conditional (`if close_reason == "invalid_ref":`) is now at `L931`, inside
  `process_issue_inplace()` (starts `L642`); the `close_reason` value is read
  at `L926-928`. The `:908` anchor in this issue's own Verification Notes is
  now stale — line numbers here have drifted twice since capture.

_Added by `/ll:refine-issue` — 2026-08-03 — based on codebase analysis:_

- The parametrized round-trip test this issue models step 6's tests after
  (`test_set_status_deferred_stamps_autodev_reason_codes`,
  `test_set_status_cli.py:336-390`) hardcodes its reason codes as a literal
  `@pytest.mark.parametrize` list — it does not derive them from
  `DeferReason`. Only the separate `TestDeferReasonEnum` class
  (`test_issue_lifecycle.py:1977-1993`) does the derived-equality check. A
  `ClosureReason` equivalent of the parametrized test will need its own
  literal list of closure codes maintained alongside the enum, same as the
  deferral precedent — not something the enum derivation makes automatic.
- A second sibling pattern disagrees with the enum-derivation approach:
  `VALID_PRIORITIES` (`cli_args.py:391`) is a `frozenset[str]` of CLI choices
  with no backing enum at all — there is no repo convention that every
  `choices=`-backing frozenset must be enum-derived, only that this specific
  one (`_DEFERRAL_REASON_CODES`) already made that choice under ENH-2870.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `commands/ready-issue.md` — the Closure Conditions table (`~L296-309`) and
  the `## CLOSE_REASON` output template (`~L391-398`) instruct the
  `/ll:ready-issue` model to emit `Reason:
  already_fixed|invalid_ref|stale|too_vague|duplicate|wont_do` — a wider
  vocabulary than the planned `ClosureReason` enum (which omits `stale`,
  `too_vague`, `duplicate`, `wont_do`), and it never mentions `superseded` or
  `not_reproducible` at all. This is static prompt text, not code that reads
  `ClosureReason`/`_CLOSED_REASON_CODES` — widening the enum in Python will
  not keep this table in sync automatically. [Agent 2 finding]
- `.gemini/commands/ready-issue.toml` (`~L286-292`, `~L377`) — verbatim
  mirror of the same table and `Reason:` line. [Agent 2 finding]
- `.kimi-code/skills/ll-ready-issue/SKILL.md` (`~L303-309`, `~L394`) —
  verbatim mirror of the same table and `Reason:` line, a third copy.
  [Agent 2 finding]
- `docs/reference/API.md` — `close_issue()` param doc (`L2685`),
  `parse_ready_issue_output()` return-dict doc (`L3373-3374`), and the
  CLOSE-handling comparison table row (`L3428`, documents the
  `issue_manager.py` `invalid_ref` special-case) all give `close_reason`
  examples that should stay in sync with the new enum members.
  [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — the `issue.closed` event field table
  (`~L826-847`) lists example `close_reason` values including `duplicate`
  and `unknown`, which are outside the planned enum; confirms the wider
  vocabulary above already leaks into a third surface. [Agent 2 finding]

_No action needed (confirmed opaque/unconstrained, listed for completeness):_
- `docs/reference/schemas/issue_closed.json` and
  `scripts/little_loops/generate_schemas.py:501-503` — `close_reason` is
  already a plain `"type": "string"` with no `enum` constraint; no schema
  change required for the enum widening. [Agent 2 finding]
- `scripts/little_loops/cli/issues/show.py:231,368-370,427` — reads
  `closed_reason` from frontmatter and displays it opaquely with no set
  validation; will surface new enum values without any change needed.
  [Agent 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Reconcile the wider closure-reason vocabulary hardcoded in
  `commands/ready-issue.md`'s Closure Conditions table and `## CLOSE_REASON`
  template (`stale`, `too_vague`, `duplicate`, `wont_do` — none in the
  planned `ClosureReason` enum; `superseded`/`not_reproducible` absent from
  its table) against the new enum. Decide: widen `ClosureReason` to match, or
  treat `/ll:ready-issue`'s prompt vocabulary as a distinct, only
  partially-overlapping superset understood not to round-trip through
  `--reason` today. Either decision needs to be explicit, not left implicit.
- If reconciled, update the two verbatim mirrors of that table:
  `.gemini/commands/ready-issue.toml` and
  `.kimi-code/skills/ll-ready-issue/SKILL.md`.
- Update `docs/reference/API.md` (`L2685`, `L3373-3374`, `L3428`) and
  `docs/reference/EVENT-SCHEMA.md` (`~L826-847`) closure-reason examples to
  reflect the final enum membership.

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

## Verification Notes

_Added by `/ll:verify-issues`:_ Core defect still accurate —
`_CLOSED_REASON_CODES = frozenset({"already_fixed", "superseded"})` remains
hardcoded, and `invalid_ref` is still documented but rejected. Line-number
citations have drifted: `_CLOSED_REASON_CODES` is now at
`set_status.py:21` (was `L17`); the three `invalid_ref` docstrings are at
`output_parsing.py:263`, `issue_lifecycle.py:312`, and `issue_lifecycle.py:912`
(the issue's own corrected findings — matches current code); the
`issue_manager.py` `close_reason == "invalid_ref"` special-case is now at
`:908` (was cited `:773`).

## Session Log
- `ll-auto` - 2026-08-03T19:18:28 - `16ff1256-0c08-4583-9e86-ff5dd7213d83.jsonl`
- `/ll:ready-issue` - 2026-08-03T19:10:47 - `b3d1c6b5-1365-4814-857b-9e9e12e1cbe2.jsonl`
- `/ll:confidence-check` - 2026-08-03T19:09:05 - `6e0d6193-586c-4055-a583-e7830c8701a8.jsonl`
- `/ll:wire-issue` - 2026-08-03T19:06:38 - `cf52f1b5-069a-44a6-af25-83df7b26af35.jsonl`
- `/ll:refine-issue` - 2026-08-03T19:00:12 - `242c41d1-1c8c-4a92-a4b7-02660b097acc.jsonl`
- `/ll:verify-issues` - 2026-08-03T04:54:47 - `d03f8e53-9873-4f8d-8cfd-bbc50704a66b.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:23:46 - `1f45db6d-28e7-4a99-8a50-d33fd51d2130.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:20:52 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P4


---

## Resolution

- **Action**: improve
- **Completed**: 2026-08-03
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
