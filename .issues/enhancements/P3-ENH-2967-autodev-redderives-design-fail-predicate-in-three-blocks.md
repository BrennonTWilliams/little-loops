---
id: ENH-2967
title: autodev.yaml re-derives the DESIGN_FAIL predicate in three inline blocks
type: ENH
priority: P3
status: done
captured_at: '2026-08-01T16:02:14Z'
completed_at: '2026-08-03T18:54:51Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- ENH-2852
- ENH-2870
- BUG-2956
testable: true
decision_needed: false
labels:
- loops
- issues
- autodev
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-2967: `autodev.yaml` re-derives the `DESIGN_FAIL` predicate in three inline blocks

## Summary

Three independent inline-Python blocks in `autodev.yaml` each shell out to
`ll-issues format-check --format json` and re-derive the same
"Program Design gate failed" boolean by hand. `issue_parser.py` already
computes that predicate once. Expose it as a CLI verdict and have the loop
consume it instead of reimplementing it three times.

## Current Behavior

`scripts/little_loops/loops/autodev.yaml` at `L1195`, `L1737`, and `L1974`
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Undercounted duplication**: `skills/confidence-check/SKILL.md` Phase 1.6
  (`L135-140`) does not restate the OR as one prose line — it re-derives the
  predicate via **two separate** `ll-issues format-check ... | python -c ...`
  shellouts (`PD_GAP` from `program_design_nonspecific`, `PD_MISSING` from
  `"Program Design" in missing + empty`), each its own inline JSON parse. That
  makes **five** total re-derivation sites, not four: the three `autodev.yaml`
  blocks, `commands/ready-issue.md`'s prose, and these two SKILL.md shellouts.
- Phase 3 of that same SKILL.md (`L303`) then ORs `PD_GAP`/`PD_MISSING` into a
  **hard blocking override** ("Program Design Hard Override (ENH-2852)") —
  the opposite framing from `ready-issue.md`'s explicit "surface only, never
  block." The two docs are internally consistent (ready-issue.md's own text
  defers the blocking decision to confidence-check), but both independently
  re-derive the predicate from raw JSON rather than calling a shared boolean.
  Any consolidation should give `check-design`/`design_gate_failed()` a
  return shape SKILL.md can also consume (it currently needs the *reason
  string* from `PD_GAP` for its "Gaps to Address" output, not just a
  boolean — an exit-code-only `check-design` would need to keep `format-check
  --format json` around for that detail, or `check-design` could optionally
  print the reason to stdout on failure).

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

**Option A (preferred): a dedicated exit-code check.**

> **Selected:** Option A — matches the codebase's established `check-readiness`/`check-decidable` CLI pattern exactly (thin `cmd_check_<name>`, three-point `__init__.py` wiring, ready test template) and removes the fail-quiet JSON-parsing scaffolding at its root; Option B only shrinks the OR-computation while leaving that scaffolding intact, and its `FormatGaps.to_dict()` placement contradicts the explicit ENH-2992 design decision against widening that contract.

Extend the existing
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

### Decision Rationale

_Added by `/ll:decide-issue`:_

**Selected: Option A (dedicated `check-design` exit-code subcommand).**

Codebase evidence for both options was gathered via parallel
`codebase-pattern-finder` agents before scoring:

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 0 |
| Simplicity | 2 | 1 |
| Testability | 3 | 1 |
| Risk | 2 | 1 |
| **Total** | **10/12** | **3/12** |

**Option A evidence**: `cmd_check_readiness` (`check_readiness.py:99-125`) and
`cmd_check_decidable` (`check_decidable.py:19-52`) are thin `cmd_check_<name>(config,
args) -> int` functions with no new abstractions — the same shape Option A adopts. The
three/four-point wiring pattern (`__init__.py` import, subparser, dispatch) is real and
consistently applied across `check-flag`/`check-decidable`/`check-open-questions`/
`check-readiness`. `test_ll_issues_check_decidable.py` is a direct, working template for
`test_ll_issues_check_design.py`. No downstream consumer of the `DESIGN_FAIL` boolean
needs anything beyond the exit code — the reason-string consumers
(`ready-issue.md`, `confidence-check/SKILL.md`) already read the raw gap-class list
fields directly and never touch a boolean, so Option A's exit-code-only shape loses
nothing they need.

**Option B evidence against**: `format_check.py:323-336` (ENH-2992) contains an explicit,
recent design decision *against* widening `FormatGaps.to_dict()`'s `dict[str, list[str]]`
contract with a derived boolean — Option B as proposed directly contradicts that
rationale. More importantly, Option B doesn't address the mechanism the issue itself
identifies as the real problem: all three `autodev.yaml` blocks would still shell out to
`python3 -c "..."` wrapped in `try/except Exception: d = {}` and `2>/dev/null || echo
"false"` — that fail-quiet scaffolding exists because the blocks parse JSON in bash at
all, not because they compute a three-way OR, so it survives unchanged under Option B.
`test_every_format_gaps_field_is_rendered` (`test_ll_issues_format_check.py:1555-1577`)
would also need a carve-out since it assumes every `FormatGaps` field is a `list[str]`.

## Program Design

### Types

**No new types.** The predicate is a `bool` derived from the existing
`FormatGaps` (`issue_parser.py:232`, confirmed 11 fields: `missing`,
`renamed`, `empty`, `boilerplate`, `malformed_id`, `prose_dep_drift`,
`stale_prose_dep`, `program_design_nonspecific`, `deprecated_key`,
`multi_frontmatter`, `testable` — all `list[str]`). `FormatGaps` already has
a same-shaped precedent for a derived boolean: `has_gaps` (property,
`issue_parser.py:251`) ORs all eleven fields together. `design_gate_failed()`
is the identical derivation pattern scoped to three of the eleven, so it
belongs beside `has_gaps` as a free function (not a `@property`, since it
doesn't cover the whole dataclass) rather than as new surface area.

### Signatures

- `design_gate_failed(gaps: FormatGaps) -> bool` — new, in `issue_parser.py`
  beside `FormatGaps`; returns
  `bool(gaps.program_design_nonspecific) or "Program Design" in gaps.missing
  or "Program Design" in gaps.empty`. Single owner of the OR.
- `check_format_gaps(issue_path: Path, templates_dir: Path | None = None,
  issue_statuses: dict[str, str] | None = None) -> FormatGaps` — already
  exists (`issue_parser.py:308`); `cmd_check_design` calls this, not a new
  function. Fails open (returns an empty `FormatGaps`) on unreadable file,
  undetermined issue type, or unloadable template — `design_gate_failed()`
  inherits that fail-open behavior for free rather than needing its own
  `except`. The `program_design_nonspecific` gap itself is populated only
  when `## Program Design` is present, non-boilerplate, and
  `grade_issue_section()` (`issues/program_design.py`) judges it non-specific
  (`issue_parser.py:446-451`), gated by `_gate_program_design()`
  (`issue_parser.py:411`) so the whole predicate is inert on projects that
  haven't armed the gate — this is the existing fail-quiet-when-off behavior,
  distinct from the *shape-change* fail-quiet risk this issue targets.
- `cmd_check_design(config: BRConfig, args: argparse.Namespace) -> int` —
  Option A's subcommand, modeled on `cmd_check_readiness`
  (`cli/issues/check_readiness.py`): resolves the issue path via
  `_resolve_issue_id` (`cli/issues/show.py`), treats "not found" as failure
  (`return 1`, error to stderr), else calls `check_format_gaps()` then
  `design_gate_failed()` and returns `0`/`1`. No JSON output — pure
  exit-code gate, matching the `check-*` family's convention.

Note `FormatGaps.to_dict()` (`issue_parser.py:268`) must gain the field under
Option B — and per the `testable` regression, any new category surfaced there
also needs its text-mode rendering path, though a derived `bool` is a
different shape from a gap list and may not belong in `_print_gaps` at all.

### Call Path

`cmd_check_design` → `check_format_gaps` → `design_gate_failed` → exit code

`autodev.yaml` (three sites) → `ll-issues check-design` → exit code, replacing
the inline `python3 -c` blocks entirely.

`check-readiness` wiring (the model to mirror) touches three separate points
in `cli/issues/__init__.py`, by hand — there's no shared registration helper
to hook into: the import (`L30`), the subparser block (`L682-703`: positional
`issue_id`, `add_config_arg(cr)`), and the dispatch `if` branch (`L951-952`).
`check-open-questions` instead factors its subparser into a standalone
`add_check_open_questions_parser(subs)` called once from `__init__.py:680` —
either wiring shape is precedented; `check-readiness`'s inline shape is the
closer model since Option A explicitly adopts that command's idiom.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `design_gate_failed()` beside
  `FormatGaps`.
- `scripts/little_loops/cli/issues/` — the `check-design` subcommand
  (Option A), registered in `cli/issues/__init__.py` alongside the other
  `check-*` entries.
- `scripts/little_loops/loops/autodev.yaml` — the three blocks at `L1195`,
  `L1737`, `L1974`.

### Dependent Files
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` gate is
  at **`L98`**, not `L114` as originally noted (stale anchor, corrected by
  research). It invokes `ll-issues format-check "$ID"` directly for a
  whole-format check, not the design-specific OR — unaffected by this issue,
  confirmed rather than assumed.
- `commands/ready-issue.md` (`L233-241`) — confirmed: documents the same
  three JSON fields as an explicitly surface-only, non-blocking check
  ("Do **not** set the verdict to BLOCKED or NOT_READY on this... two gates
  enforcing the same requirement with different remedies is how an issue
  gets stuck between them"). If the predicate gains a CLI home, this prose
  should point at it rather than restate the three field names.
- `skills/confidence-check/SKILL.md` Phase 1.6 (`L135-140`) and Phase 3
  (`L303`) — confirmed to restate the OR, and as **two** separate inline
  shellouts (`PD_GAP`, `PD_MISSING`), not one prose line. Phase 3 uses these
  as a **hard blocking override**, the opposite framing from
  `ready-issue.md`'s "surface only, never block" — the two docs are
  internally consistent with each other (ready-issue.md defers the blocking
  decision to confidence-check) but neither calls a shared boolean today.
  See Proposed Solution → Codebase Research Findings for the return-shape
  implication (SKILL.md needs the reason string, not just a bool).

### Conventions in Force
- Every `check-*` subcommand lives in its own module under
  `cli/issues/check_*.py`, exports one `cmd_check_<name>(config, args) -> int`
  function, treats "issue not found" as failure, and returns `0` (pass) /
  `1` (fail) with no stdout payload — evidence: `check_readiness.py`,
  `check_flag.py`, `check_decidable.py`, `check_open_questions.py`.
- `check-*` subcommands are tested with a subprocess-level integration file
  named `test_ll_issues_check_<name>.py`, using shared `_cli()` /
  `temp_project_dir` / `_write_issue()` / `_invoke()` helpers, plus a
  `TestCliRegistration` class asserting the subcommand name appears in
  `--help` output — evidence: `test_ll_issues_check_decidable.py`.
- `FormatGaps`/`QuestionGaps` (`issue_parser.py:232`, `:285`) are the
  established shape for "list-of-gap-category fields + one derived boolean +
  `to_dict()`"; `QuestionGaps`'s own docstring calls itself a "Mirror of
  `FormatGaps`" — `design_gate_failed()` extends this same shape rather than
  introducing a new one.
- `autodev.yaml` already consumes `ll-issues check-readiness` via
  `if ! ll-issues check-X "$ID"; then ... fi` / `&&`-chained-on-exit-code
  idiom at three sites (`L493`, `L667`, `L1110`) — including one directly
  chained against the not-yet-consolidated `DESIGN_FAIL` block
  (`L1092-1115`). This is the idiom Option A's replacement blocks adopt.

### Tests
- `scripts/tests/test_issue_parser.py` — existing `FormatGaps` coverage;
  add `design_gate_failed()` cases here.
- `scripts/tests/test_ll_issues_check_decidable.py` (or
  `test_ll_issues_check_open_questions.py`) — structural template for a new
  `test_ll_issues_check_design.py`.
- `scripts/tests/test_autodev_loop.py` — existing `autodev.yaml` loop test
  coverage; Implementation Step 5's new loop-level assertion belongs here.
- `scripts/tests/test_ll_issues_format_check.py` — existing `format-check`
  CLI coverage, confirms `FormatGaps.to_dict()` → JSON key names
  (`missing`, `empty`, `program_design_nonspecific`) the three inline blocks
  parse today.

### Similar Patterns
- `ll-issues check-readiness` — consumed by `autodev.yaml` immediately after
  the first duplicated block (`L1111-1113`); the exact idiom Option A adopts.
  Wiring for a new `check-*` command touches three hand-maintained points in
  `cli/issues/__init__.py`: import (`L30`), subparser (`L682-703`), dispatch
  (`L951-952`) — no shared registration helper exists for this family.
- `ll-verify-skill-prose` (ENH-2951) — exists precisely to catch prose
  reimplementations of logic that lives in `scripts/little_loops/`. Inline
  loop-YAML Python is the same failure class in a corpus that linter does not
  currently scan; worth noting whether its marker table could extend to
  `loops/*.yaml`.

## Implementation Steps

1. Add `design_gate_failed()` to `issue_parser.py`; unit-test it against each
   of the three gap-class inputs and their combinations.
2. Add `ll-issues check-design` (Option A) with exit-code semantics matching
   `check-readiness`; wire it at the same three points `check-readiness` uses
   in `cli/issues/__init__.py` (import, subparser, dispatch — see
   Integration Map → Similar Patterns for exact line references).
3. Replace the three `autodev.yaml` blocks by state name — `recheck_scores`
   (`L1092-1115`, chains into `autodev-staged.txt` via `&&`, single implicit
   branch on the compound exit code), `regate_after_atomic_remediation`
   (`L1591-1638+`, explicitly force-fails a separately computed `GATE`
   variable when `DESIGN_FAIL` is true — a second, explicit branch),
   `recheck_after_size_review` (`L1755-1787+`, same double-branch shape as
   `regate_after_atomic_remediation`). Confirm each retains its distinct
   surrounding behavior; a mechanical find-replace across all three would be
   wrong given the shape difference between block 1 and blocks 2/3.
4. `commands/ready-issue.md` (`L233-241`) is a fourth restatement (prose,
   already confirmed non-blocking — point it at the new check without
   changing its non-blocking framing). `skills/confidence-check/SKILL.md`
   Phase 1.6/Phase 3 (`L135-140`, `L303`) is a fifth and sixth — two separate
   `PD_GAP`/`PD_MISSING` shellouts feeding a hard override, not one line;
   decide there whether `check-design`'s exit code alone suffices or whether
   Phase 1.6 still needs the `PD_GAP` reason string for its "Gaps to
   Address" output (see Proposed Solution → Codebase Research Findings).
5. Add a loop-level test asserting the gate still blocks a design-less issue —
   the coverage that does not exist today; `test_autodev_loop.py` is the
   existing home for `autodev.yaml` loop-level assertions.

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
  (`L1195` chains into `autodev-staged.txt`; the other two branch twice on
  `DESIGN_FAIL`), so a mechanical find-replace would be wrong.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues`:_ The three inline `DESIGN_FAIL` Python blocks
in `autodev.yaml` still exist verbatim (same shape, same fail-quiet
`except`/`|| echo "false"` pattern) and the core premise (three-way
duplication, no shared predicate) is still fully accurate. Line-number
citations have drifted with the file's growth: the blocks are now at
`autodev.yaml:1195`, `:1737`, `:1974` (originally cited `L1095`, `L1594`,
`L1758`).

## Resolution

Implemented Option A exactly as decided:

- Added `design_gate_failed(gaps: FormatGaps) -> bool` beside `FormatGaps` in
  `issue_parser.py` — single owner of the three-way OR.
- Added `ll-issues check-design <id>` (`cli/issues/check_design.py`), wired at
  the three `check-readiness`-mirrored points in `cli/issues/__init__.py`
  (import, subparser, dispatch), plus help text.
- Replaced all three `autodev.yaml` inline `python3 -c "..."` `DESIGN_FAIL`
  blocks (`recheck_scores`, `regate_after_atomic_remediation`,
  `recheck_after_size_review`) with `ll-issues check-design "$ID"` calls,
  preserving each state's distinct surrounding control flow (compound
  `&&`-chain vs. explicit `GATE` override) as flagged in the Program Design.
- Pointed `commands/ready-issue.md` and `skills/confidence-check/SKILL.md`
  Phase 1.6/Phase 3 at the new predicate (`PD_FAIL` via `check-design`),
  keeping the raw `format-check` shellout only where the reason string
  (`PD_GAP`) is still needed for display.
- Tests: `TestDesignGateFailed` (unit, `test_issue_parser.py`),
  `test_ll_issues_check_design.py` (subprocess CLI contract, mirrors
  `test_ll_issues_check_decidable.py`), updated
  `TestDesignGateStep0Detection` (static YAML assertions now assert the
  consolidated form and the *absence* of the old inline-JSON scaffolding),
  and a new `TestRecheckScoresDesignGateEndToEnd` (real subprocess
  `ll-issues` calls against a real project tree — the loop-level coverage
  Implementation Step 5 called out as missing).

Full suite: `python -m pytest scripts/tests/` — 18138 passed, 42 skipped, 4
pre-existing failures unrelated to this change (`test_logo.py`,
`test_des_audit.py` — logo asset content / design-tokens audit tree, no
relation to `FormatGaps`/`check-design`/`autodev.yaml`).

## Session Log
- `/ll:manage-issue` - 2026-08-03T18:54:45 - `db8fe1b2-96e0-465a-9850-cf44c91814b2.jsonl`
- `/ll:ready-issue` - 2026-08-03T18:31:57 - `ad926e93-54c3-4b1d-b4d2-67d13f7853e7.jsonl`
- `/ll:confidence-check` - 2026-08-03T18:29:53 - `a23e1705-9059-4fbe-b846-9d41d7d516e0.jsonl`
- `/ll:decide-issue` - 2026-08-03T18:28:16 - `e741de04-992f-48cc-9f92-560488af7cc3.jsonl`
- `/ll:verify-issues` - 2026-08-03T04:54:47 - `d03f8e53-9873-4f8d-8cfd-bbc50704a66b.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:03:56 - `610a6707-96a5-4407-9a1a-bc051890c79f.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:20:51 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
