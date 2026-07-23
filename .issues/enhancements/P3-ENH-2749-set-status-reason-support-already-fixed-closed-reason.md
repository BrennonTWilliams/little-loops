---
id: ENH-2749
status: open
captured_at: '2026-07-23T18:23:57Z'
discovered_date: 2026-07-23
discovered_by: capture-issue
decision_needed: false
confidence_score: 95
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2749: `set-status --reason` can't express `already_fixed` for `done` transitions

## Summary

`ll-issues set-status ISSUE_ID done --reason already_fixed` is structurally
unsupported. The `--reason` flag's `choices=` list (`set_status.py`) is
`blocked_by_unmet`, `remediation_stalled`, `low_readiness`, `gate_blocked`,
`decision_unresolved`, `oversized_atomic` — all deferral reason codes — and
`_status_updates()` only consumes `args.reason` inside the `status ==
"deferred"` branch. Passing `--reason` on a `done` transition is silently
ignored (argparse rejects `already_fixed` outright since it's not in
`choices`, so the call fails before reaching that branch at all).

The `already_fixed` value the user actually wants to record lives in the
frontmatter's `closed_reason` field (introduced by ENH-2535 for closure-context
display in `ll-issues show`), which `set-status` has no flag for at all.

## Current Behavior

- `ll-issues set-status BUG-042 done --reason already_fixed` → argparse error:
  `invalid choice: 'already_fixed'` (not in the deferred-only `choices` list).
- Even if the choices list were relaxed, `_status_updates()` only branches on
  `status == "deferred"` to write a reason — a `done` transition never writes
  anything from `args.reason`.
- There is no CLI path to set `closed_reason` on a `done`/`cancelled`
  transition; it must be hand-edited into frontmatter.

## Expected Behavior

`set-status` should let the caller record *why* an issue was closed the same
way it already records *why* an issue was deferred:

- Add a `done`/`cancelled`-scoped reason mechanism (e.g. reuse `--reason` with
  a status-appropriate choices set, or add a distinct `--closed-reason` flag)
  that writes `closed_reason` into frontmatter on `done`/`cancelled`
  transitions, mirroring how `deferred_reason` is written on `deferred`
  transitions.
- `already_fixed` should be a valid value for that closed-reason mechanism.

## Motivation

Automation and humans currently have no way to distinguish "closed because
already fixed elsewhere" from any other `done` closure via `set-status` — the
only way to set `closed_reason` today is a manual frontmatter edit, which
automation paths (autodev, sprint runners) can't do safely mid-flow.

## Proposed Solution

In `scripts/little_loops/cli/issues/set_status.py`:

1. Split `--reason`'s single deferral-only `choices=` list into a
   status-conditional validation: keep the existing deferral codes for
   `status == "deferred"`, and accept a separate closed-reason enum (starting
   with `already_fixed`, extensible later) for `status in ("done",
   "cancelled")`. Validate the combination in `cmd_set_status` (or via
   argparse `choices` per status if the parser structure allows) rather than
   one flat list.
2. In `_status_updates()`, add a branch alongside the existing `deferred`
   branch: `elif status in ("done", "cancelled"): if reason: updates["closed_reason"] = reason`.
3. Update the `--reason` help text to reflect that it's now valid for both
   deferral and closure transitions.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Step 1 above ("validate the combination in `cmd_set_status` … or via argparse
`choices=` per status if the parser structure allows") leaves the validation
mechanism open. Research confirms argparse `choices=` is a static, flat list
tied to one argument — it has no built-in way to make one flag's valid values
conditional on another flag's value (`status` and `--reason` are separate
`add_argument()` calls on the same subparser with no cross-reference). So the
"per status" argparse option isn't actually available; validation has to
happen in Python after `parse_args()`, inside `cmd_set_status()`. Two
conventions already coexist in this codebase for that shape of check:

**Option A**: Raise via `parser.error(...)` immediately after parsing (matches the existing static `choices=` rejection: `SystemExit(2)`, stderr message). Precedent: `scripts/little_loops/cli/history_context.py:204-208`, `scripts/little_loops/cli/auto.py:81-89`, `scripts/little_loops/cli/parallel.py:233-238`.

**Option B**: Check in the handler body and `return 1` with a stderr message — no `SystemExit`. Precedent: `set_status.py`'s own existing `--cascade` guard at lines 70-78 (`if args.status not in _TERMINAL_STATUSES: print(..., file=sys.stderr); return 1`), and `scripts/little_loops/cli/messages.py:224-228`.

> **Selected:** Option B — matches `set_status.py`'s own established post-parse validation convention exactly; Option A would require a structural signature change and a mismatched exit code.

**Recommended**: Option B — `set_status.py` already establishes this exact convention locally for a status-conditional flag guard (the `--cascade` check), so a `--reason`-on-`done`/`cancelled` validation should match it for consistency within the same function, rather than introducing a second, differently-shaped rejection path (`SystemExit(2)` vs `return 1`) in the same file. This also matches the existing test pattern for the `--cascade` guard (`test_cascade_rejected_for_non_closing_status` — asserts `result == 1` and stderr content, not `pytest.raises(SystemExit)`).

### Decision Rationale

_Added by `/ll:decide-issue` — evidence-based scoring:_

**Selected: Option B** (check in handler body, `return 1` + stderr, no `SystemExit`)

Option B reuses the exact validation shape `cmd_set_status` already applies three times in this same function (issue-not-found, `--cascade` guard, cascade-failure): `print(..., file=sys.stderr); return 1`. Its test shape (`result == 1` + `captured.err`) already exists in `test_set_status_cli.py` for the analogous `--cascade` guard. Option A (`parser.error(...)`) is a real codebase pattern, but foreign to this file: `cmd_set_status(config, args)` doesn't receive the `parser` object (unlike the three cited precedent sites, which call `parser.error` from the same scope that builds the parser), so adopting it would require a signature change and would introduce a second, inconsistent exit code (2 vs. this function's existing 1) for the same category of error.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|:-:|:-:|:-:|:-:|:-:|
| A — `parser.error()` | 1 | 1 | 1 | 1 | 4/12 |
| B — `return 1` + stderr | 3 | 3 | 3 | 3 | **12/12** |

**Key evidence:**
- `set_status.py:70-78` already implements this exact shape for the `--cascade` guard, in the same function.
- `set_status.py:66-68` and `:139-141` show the `return 1` + stderr shape used two more times in this file.
- `test_set_status_cli.py:631-666` (`test_cascade_rejected_for_non_closing_status`) is the direct test-pattern precedent for Option B.
- `cmd_set_status(config, args)`'s signature does not include `parser`, unlike all three Option A precedent call sites (`history_context.py`, `auto.py`, `parallel.py`), which call `parser.error()` from the scope that owns the parser — adopting Option A would require a structural signature change Option B doesn't need.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/set_status.py` — `_status_updates()`, `--reason` choices/validation
- `scripts/little_loops/cli/issues/__init__.py` — `--reason` argparse definition (line ~774)

### Dependent Files (Callers/Importers)
- `ll-issues show` (ENH-2535) already reads `closed_reason` for closure-context display — no change needed there, just a new writer.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py:208-210,341-343,400,402` — **design gap**: reads `closed_reason` and `cancelled_reason` as *two separate* frontmatter keys (`closure_text = closing_note or closed_reason or cancelled_reason or deferred_reason`). The Proposed Solution's single `elif status in ("done", "cancelled"): updates["closed_reason"] = reason` branch writes only `closed_reason` for both statuses, so `show.py`'s dedicated `cancelled_reason` read path would never be populated by this new writer. Not a functional break (the `or`-chain still surfaces the value via `closed_reason`), but implementers should decide explicitly whether to write `cancelled_reason` for `cancelled` transitions to match `show.py`'s existing dual-key design, or keep the single-key approach and note the `cancelled_reason` field stays writer-less. [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml:456,595,1218,1298` and `scripts/little_loops/loops/rn-implement.yaml:1364` — all five existing `ll-issues set-status ... deferred --by automation --reason <code>` call sites confirmed; none call `set-status ... done --reason ...` today, so this change is purely additive from the loop layer — no loop YAML edits required. [Agent 1 finding]
- `scripts/little_loops/issue_lifecycle.py` (`DeferBy`, `DeferReason` enums) — confirmed unused/unimported outside `issue_lifecycle.py`; no existing enum surface to extend for the new closed-reason codes, consistent with the issue's own note that a new frozenset/tuple constant (not an enum) is the idiomatic choice here. [Agent 1 finding]

### Similar Patterns
- The existing `deferred_by`/`deferred_reason`/`deferred_date` stamping in `_status_updates()` (ENH-2664) is the direct template to follow for closure reasons.

### Tests
- `scripts/tests/` — add coverage for `set-status ID done --reason already_fixed` writing `closed_reason`, and for the existing deferral `--reason` choices remaining rejected on non-deferred statuses (and vice versa).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_automation_reason` (lines 260-298) — exact template to mirror for a new `test_set_status_done_stamps_closed_reason`: same scaffold (seed issue, argv patch, `main_issues()`, `parse_frontmatter()` assertion), asserting `fm.get("closed_reason") == "already_fixed"`. A `@pytest.mark.parametrize` variant over `("done", "cancelled")` mirrors `test_set_status_deferred_stamps_autodev_reason_codes` (lines 300-344). [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py::test_cascade_rejected_for_non_closing_status` (lines 631-666) — confirmed exact precedent for the new Option-B rejection test (`result == 1` + `capsys` stderr substring check, not `pytest.raises(SystemExit)`); use this shape for a new guard test rejecting a deferral code passed with a `done`/`cancelled` target status (or vice versa). [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py::test_set_status_invalid_reason_rejected` (lines 413-442) — **regression risk**: currently asserts `--reason bogus_code` on a `deferred` transition raises `SystemExit(2)`. Must re-verify this still passes once `--reason`'s choices are widened to include closed-reason codes — `bogus_code` must stay outside both choice sets. [Agent 2 + 3 finding]
- `scripts/tests/test_set_status_cli.py::test_set_status_non_deferred_omits_deferral_fields` (lines 346-380) — add a sibling assertion (or new test) that `closed_reason` is likewise absent on non-`done`/`cancelled` transitions with no `--reason` given. [Agent 3 finding]
- No existing test asserts a `cancelled` transition writes nothing extra today (confirmed gap, not a break) — add new coverage alongside the `closed_reason`-writing tests. [Agent 3 finding]
- `scripts/tests/test_show.py` — add/verify coverage that `ll-issues show` still renders the closure reason correctly given the `closed_reason`/`cancelled_reason` dual-key design gap noted above in Dependent Files. [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md:1651-1672` — **correction**: this DOES document `set-status`'s `--by`/`--cascade`/`--cascade-to`/`--reason` flags today, stating `--reason` is for automation-deferral transitions only. Needs an update alongside the code change.
- `docs/reference/API.md` — already documents `close_reason` in a *different*, unrelated pipeline (see Codebase Research Findings below); no change needed there, but worth noting to avoid confusing the two.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~lines 476, 511-513) — documents the `deferred.txt`/`mark_deferred` shell-state reason-code convention this fix mirrors; not incorrect post-fix (scoped to `deferred` only), but a natural place to add a parallel one-line mention of the new closure-reason mechanism for documentation symmetry. [Agent 2 finding]
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (~lines 127-134) — states the `deferred` transition stamps `deferred_by`/`deferred_reason`/`deferred_date`; likewise scoped correctly to `deferred` and not contradicted by this fix, but a candidate for a parallel sentence about the new `done`/`cancelled --reason` mechanism. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact current code** (`scripts/little_loops/cli/issues/__init__.py:773-786`): the `--reason` argparse arg has a single flat `choices=[...]` list — the six deferral codes, hand-duplicated as string literals (not derived from an enum).
- **Exact current code** (`scripts/little_loops/cli/issues/set_status.py:38-63`, `_status_updates()`): `if status == "done": updates["completed_at"] = ...` / `elif status == "deferred": ...`. There is no `elif` for `cancelled` at all today — a `cancelled` transition currently gets `{"status": "cancelled"}` and nothing else (no timestamp, no reason). Implementers should be aware the new `closed_reason` branch needs to cover both `done` and `cancelled`, and this is the first time `cancelled` gets any dedicated handling in this function.
- **Existing enum precedent** (`scripts/little_loops/issue_lifecycle.py:51-74`): `DeferBy` and `DeferReason` `Enum` classes already exist and are the *semantic* source of truth for the deferral codes, but the argparse `choices=` list doesn't import them — it's an independently hand-maintained duplicate. There is no `CloseReason`/`ClosedReason` enum anywhere in the codebase yet; one would need to be created (or, per this codebase's established convention — see `_TERMINAL_STATUSES`/`_VALID_ACTIONS` in `issue_progress.py`/`pii.py` — a plain module-level `frozenset`/tuple constant is the idiomatic choice here, not an `Enum` class).
- **Unrelated same-named concept**: `close_reason` (no `d`) already exists as a free-text field in the `/ll:ready-issue` → `WorkerResult` → `_build_closure_resolution()` pipeline (`scripts/little_loops/parallel/types.py`, `scripts/little_loops/output_parsing.py`, `scripts/little_loops/issue_lifecycle.py:268`), which writes into the markdown `## Resolution` body section — architecturally unconnected to `set_status.py`/`show.py`'s frontmatter `closed_reason` key. `"already_fixed"` is already a recognized string value there, which is independent confirmation the value makes sense, but that pipeline is not what this issue touches.
- **`_TERMINAL_STATUSES` is already imported** into `set_status.py` (`from little_loops.issue_progress import _OPEN_STATUSES, _TERMINAL_STATUSES`) and used for the `--cascade` guard (see Proposed Solution addendum below) — directly reusable for `status in _TERMINAL_STATUSES` rather than writing a new `("done", "cancelled")` tuple inline.
- **Test file location for new coverage**: `scripts/tests/test_set_status_cli.py` — existing deferral-reason tests live at lines 226-443 (`# ── Deferral discriminator tests (ENH-2664) ──` section); the mirror tests for `closed_reason` should sit alongside them. No existing test in this file touches `closed_reason`/`cancelled_reason`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. **Resolve the `closed_reason`/`cancelled_reason` key ambiguity** before writing `_status_updates()`'s new branch: `show.py` already reads a dedicated `cancelled_reason` frontmatter key distinct from `closed_reason`. Decide whether `cancelled` transitions should write `cancelled_reason` (matching `show.py`'s existing dual-key design) or reuse `closed_reason` for both `done` and `cancelled` (simpler, and `show.py`'s `or`-chain still surfaces it, but leaves `cancelled_reason` permanently unpopulated).
5. Add `test_set_status_done_stamps_closed_reason` (+ parametrized `done`/`cancelled` variant) to `test_set_status_cli.py`, following the `test_set_status_deferred_stamps_automation_reason` template.
6. Add a new Option-B rejection test (reason/status mismatch) following `test_cascade_rejected_for_non_closing_status`'s `result == 1` + stderr shape.
7. Re-run `test_set_status_invalid_reason_rejected` after widening `--reason` choices to confirm `bogus_code` still triggers `SystemExit(2)`.
8. Add a sibling assertion to `test_set_status_non_deferred_omits_deferral_fields` (or a new test) confirming `closed_reason` is absent on non-`done`/`cancelled` transitions, and add coverage that a `cancelled` transition with no `--reason` writes nothing extra.

## Impact

- **Priority**: P3 — not blocking, but a documented-sounding CLI flag path currently errors out with no clear alternative, which reads as a bug to callers.
- **Effort**: Small — one file's branching logic plus argparse choices, with tests.
- **Risk**: Low — additive; doesn't change existing deferred-reason behavior.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| .claude/CLAUDE.md | Issue File Format § status values / closed_reason discriminator conventions |

## Status

- [ ] Not started

## Session Log
- `/ll:confidence-check` - 2026-07-23T19:05:00 - `284c5279-747e-4286-b2dd-946e8a72270c.jsonl`
- `/ll:wire-issue` - 2026-07-23T18:47:39 - `fa646d15-753f-442f-9158-3363453b45ac.jsonl`
- `/ll:decide-issue` - 2026-07-23T18:40:25 - `ea4b683d-1cd4-4dbb-97f7-c533ec19a4b5.jsonl`
- `/ll:refine-issue` - 2026-07-23T18:35:26 - `ea4b683d-1cd4-4dbb-97f7-c533ec19a4b5.jsonl`
- `/ll:capture-issue` - 2026-07-23T18:23:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d29bb5ad-a0a6-446c-95d0-04a275aaa8e7.jsonl`
