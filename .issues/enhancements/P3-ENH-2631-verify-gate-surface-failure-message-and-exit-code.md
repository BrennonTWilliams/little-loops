---
id: ENH-2631
title: Verify gate discards failure message and exit code
type: enhancement
status: open
priority: P3
captured_at: '2026-07-13T18:30:06Z'
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to:
- BUG-2629
decision_needed: false
learning_tests_required:
- pytest
confidence_score: 96
outcome_confidence: 86
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 20
---

# ENH-2631: Verify gate discards failure message and exit code

## Motivation

When the epic verify gate fails, the only signal that survives is the bare string
`failed` in `verify-verdict.txt`. The failure *message* (`verify: {message}`)
goes to stderr and is lost from `summary.json`; the pytest exit code is discarded
entirely. This makes a **false negative** (e.g. a collection/import error, pytest
exit 2 — see BUG-2629) indistinguishable from a **real** test failure (exit 1)
when triaging a `verify_verdict: failed` run after the fact. A human or a
downstream loop can't tell "the harness mis-imported the code" from "the code is
broken" without re-running by hand.

## Current Behavior

- `verify_epic_branch_before_merge()` truncates stderr/stdout into `message` but
  the caller only prints `passed`/`failed`.
- The `verify` state (`auto-refine-and-implement.yaml` ~line 409-412) writes only
  `passed`/`failed`/`skipped` to `verify-verdict.txt`; `finalize` folds that
  single token into `summary.json`.

## Proposed Change

1. Persist the failure `message` and the process `returncode` into the run_dir
   (e.g. `verify-detail.txt` / add fields to a small `verify.json`), not just
   stderr.
2. Distinguish pytest **exit 2 (collection/usage error)** from **exit 1 (tests
   failed)** — surface it as a distinct verdict such as `collection_error` rather
   than lumping both into `failed`. A collection error is a strong signal of a
   harness/environment problem (like BUG-2629), not a code defect.
3. Include the distinction (and a short detail snippet) in `summary.json` so
   triage doesn't require a manual re-run.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**The exit code already exists but is thrown away.**
`verify_epic_branch_before_merge()` (`scripts/little_loops/worktree_utils.py:245-324`)
runs `subprocess.run(..., capture_output=True)` at lines 311-316 and inspects
`result.returncode` at line 317, but the returncode survives **only as free text**
interpolated into `message`:
`message = f"{label}_cmd failed (exit {result.returncode}): {detail}"` (line 319).
The function's return type is `tuple[bool, str | None]` (line 256) — there is no
structured returncode field. Surfacing the exit code cleanly means either widening
this tuple or parsing it back out of the message string.

**Where the artifact shape is decided — two viable options.** Step 1 above leaves
the persistence format open ("`verify-detail.txt` / a small `verify.json`"). The
codebase has precedent for both shapes:

> **Selected:** Option A (flat text artifacts) — reuses the proven single-token verdict-file idiom and sidesteps Option B's `printf %s` corruption risk from arbitrary-text pytest detail.

**Option A**: Flat text artifact (`verify-detail.txt` + `verify-returncode.txt`).
Matches the existing `echo "$TOKEN" > "$RUN_DIR/<name>-verdict.txt"` → `cat ... ||
echo "not_run"` idiom already used for `verify-verdict.txt`
(`auto-refine-and-implement.yaml:412`, read back at `:728`) and
`epic-merge-verdict.txt` (`:735`). Minimal new machinery; one `cat` per field in
`finalize`.

**Option B**: Structured `verify.json` (`{"verdict","returncode","detail"}`) written
by the `verify` state and parsed in `finalize`. Matches the `SKIPPED_BREAKDOWN`
precedent (`auto-refine-and-implement.yaml:~690-703`), which builds a nested JSON
object via inline `python3 -c "... json.dumps(breakdown)"` and embeds it **unescaped**
into the outer `printf` as a nested `%s` — the one existing case of a structured
sub-field inside `summary.json`. `finalize` would read it with the
`python3 -c` try/except-with-default pattern from `general-task.yaml:570-577`.

**Recommended**: Option B — a structured `verify.json` keeps the exit code, verdict
class, and detail snippet atomic (no partial-write skew across three flat files),
reuses the established nested-JSON-in-summary precedent, and makes the
`collection_error` vs `failed` distinction a first-class field rather than a parsed
substring.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-13.

**Selected**: Option A — flat text artifacts (`verify-detail.txt` + `verify-returncode.txt`).

**Reasoning**: The single-token verdict-file idiom (`echo "$TOKEN" > verify-verdict.txt`
→ `cat ... || echo "not_run"`) is already proven at three call sites
(`auto-refine-and-implement.yaml:412`, `:455`, read back at `:728`/`:735`) with direct
test-seeding precedent in `test_builtin_loops.py`. Option B's build-side
embed-JSON-in-`printf` pattern is a **population of one** (only `SKIPPED_BREAKDOWN` uses
it), the verify state emits no JSON today, and — critically — a `detail` field carrying
arbitrary pytest stderr can contain literal `%`, which would corrupt the outer
`printf %s` format string (SKIPPED_BREAKDOWN is safe only because it holds integers).
Option A avoids that untested failure mode entirely.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (flat text) | 2/3 | 3/3 | 3/3 | 2/3 | **10/12** |
| Option B (verify.json) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- Option A: Proven `verdict.txt` write/read-back idiom at 3 call sites; direct
  file-seed test precedent (`test_builtin_loops.py:2199`, `:2416`). Minor divergence:
  message + returncode as two files vs. the codebase's single-blob multi-field convention.
- Option B: Parse-side `python3 -c` try/except pattern is reusable, but the build-side
  nested-`%s` embed is a single-instance precedent; arbitrary-text `detail` risks `%`
  corrupting `printf`, plus MR-10 parse-swallow exposure in `finalize`.

**Verdict-class split is a well-worn pattern here.** `finalize` already splits one
binary condition into a richer named verdict via a counter branch (ENH-2376:
`partial-with-errors` vs `partial`, `auto-refine-and-implement.yaml:737-751`).
Mapping pytest `returncode` (1 = tests failed → `failed`; 2 = collection/usage
error → `collection_error`) is the identical shape applied to `returncode` instead
of `$ERR`.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — `verify_epic_branch_before_merge()`
  (lines 245-324): thread `result.returncode` out of the failure branch (line
  317-321) so callers can map it to a verdict class. **Caution**: keep the exact
  `f"{label}_cmd failed (exit {result.returncode}): {detail}"` substring intact —
  `test_orchestrator.py:1615` asserts it verbatim.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — three edit sites:
  - `verify` state (lines 332-416, call site 396-412): stop discarding `message`
    to stderr only (line 408); persist returncode + detail + verdict class to the
    chosen artifact (Option A/B above) instead of just `passed`/`failed` →
    `verify-verdict.txt` (line 412). Non-epic `run_checks()` closure (lines
    372-383) collapses to `'passed'`/`'failed'` with **zero** detail capture — same
    fix applies here.
  - `merge_epic_branch` state (lines 428-562, call site 527-541): second caller of
    the same function; `message` printed to stderr only (line 539), verdict token
    `verify_failed` written to `epic-merge-verdict.txt`.
  - `finalize` state (lines 564-762): reads `verify-verdict.txt` (line 728) and
    `epic-merge-verdict.txt` (line 735); `printf` at lines 753-754 has no
    exit-code/detail field. Extend the format string + arg list (Option A) or embed
    the `verify.json` object as a nested `%s` like `SKIPPED_BREAKDOWN` (Option B).

### Dependent Files (Callers)
- `scripts/little_loops/parallel/orchestrator.py` — `_verify_epic_branch_before_merge()`
  (~lines 1310-1386): third caller, same `(ok, message)` unpack. If the tuple
  widens, update this wrapper too (not part of the FSM data flow but shares the
  signature).

### Similar Patterns
- `auto-refine-and-implement.yaml:737-751` — ENH-2376 verdict-class split
  (`partial-with-errors` vs `partial`); model the `collection_error` vs `failed`
  mapping on this.
- `auto-refine-and-implement.yaml:~690-703` — `SKIPPED_BREAKDOWN` nested-JSON-in-
  `summary.json` (Option B precedent).
- `general-task.yaml:570-577` — inline `python3 -c` JSON parse with try/except
  fallback default (how `finalize` would read a `verify.json`).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **`class TestVerifyStateConfigReadShell`
  (~line 2741)** and **`class TestMergeEpicBranchConfigReadShell` (~line 2782)** run
  the real `verify` / `merge_epic_branch` state actions via `bash -c` and assert on
  `verify-verdict.txt` / `epic-merge-verdict.txt` contents (`passed`/`failed`/`skipped`
  at ~2766-2779; merge tokens at ~2876-2928). The shell-embedded Python `ok, message =
  verify_epic_branch_before_merge(...)` unpack (YAML ~396, ~528) **must be updated in
  lockstep** if the tuple widens, or these break. Add a `collection_error` (exit 2) case
  here. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — **`_run_finalize()` helper (~line 2170)** is
  the canonical flat-text seed idiom: it does `(run_dir / "verify-verdict.txt").write_text(...)`
  then executes the finalize action and returns parsed `summary.json`. Extend it with
  optional `verify_detail` / `verify_returncode` kwargs and add read-back tests modeled on
  `test_finalize_surfaces_verify_verdict` (~2428) + `test_finalize_verify_verdict_defaults_to_not_run`
  (~2438). The exit-code→verdict-class mapping should get a table-driven test modeled on
  `test_finalize_verdict_table` (~2247) and a static-substring test like
  `test_finalize_has_partial_with_errors_verdict` (~2144). [Agent 3 finding]
- `scripts/tests/test_orchestrator.py` — `TestEpicBranchVerifyGate` patches
  `little_loops.worktree_utils.subprocess.run` with `MagicMock(returncode=1, ...)` (~1608);
  add a `returncode=2` mirror of `test_blocks_merge_on_test_cmd_failure` (~1594). Note the
  wrapper unpack `ok, message = verify_epic_branch_before_merge(...)`
  (`orchestrator.py:1336`) breaks with the tuple widen. [Agent 3 finding]

- `scripts/tests/test_worktree_utils.py` — `class TestVerifyEpicBranchBeforeMerge`
  (lines 263-354): uses `test_cmd="true"`/`"false"` real subprocesses. Add a case
  that drives a non-1 exit (e.g. `test_cmd="sh -c 'exit 2'"`) and asserts the
  returncode is surfaced. `test_worktree_setup_failure_returns_false_with_message`
  is the precedent for asserting on failure-origin-specific message content.
- `scripts/tests/test_orchestrator.py` — `class TestEpicBranchVerifyGate` (~line
  1549); **line 1615 asserts the verbatim failure-message format** — preserve or
  update in lockstep.
- `scripts/tests/test_builtin_loops.py` — static YAML substring assertions
  (`test_verify_attaches_epic_worktree` ~line 2111 asserts
  `"verify_epic_branch_before_merge"`, `"verify_before_merge=True"`; finalize
  reads `verify-verdict.txt` ~line 2413). Add assertions for the new artifact +
  `summary.json` field.

### Documentation
- `docs/reference/API.md` (~lines 3324-3341) — canonical
  `verify_epic_branch_before_merge` reference; update return contract if the tuple
  widens.
- `docs/development/MERGE-COORDINATOR.md` (~lines 471-474) — describes the
  `verify_before_merge` gate.
- `CHANGELOG.md` — add an entry.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (~lines 892-949) — the `auto-refine-and-implement`
  finalize/summary.json narrative (notes the verify verdict "is advisory, folded into
  summary.json"); update to describe the new `collection_error` verdict class and the
  `verify-detail.txt` / `verify-returncode.txt` artifacts. **Closest doc to the finalize
  change.** [Agent 2 finding]
- `docs/ARCHITECTURE.md` (~lines 471-490) — EPIC-branch merge-flow prose lists
  `verify_epic_branch_before_merge` as a collaborating function; update if the return
  contract / verdict surface changes user-visible behavior. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` (~line 376) and `docs/reference/CLI.md` (~line 334) —
  near-duplicate `epic_branches.verify_before_merge` prose ("a failure blocks the
  merge... surfaced in the run summary"). _Advisory:_ only touch if the failed-vs-
  collection-error distinction is worth documenting at the config level. [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` (~lines 436-440), `config/automation.py`
  (`EpicBranchesConfig`, ~40-63), `parallel/types.py` (`EpicBranchesConfig`, ~312-338) —
  **FYI / no change expected.** These carry only the `verify_before_merge` *boolean* flag;
  there is no enum constraining verdict strings, so the new `collection_error` verdict
  class needs no schema/dataclass edit. Recorded to pre-empt a fruitless audit. [Agent 2 finding]

## Implementation Steps

1. Return/emit `returncode` and `message` from the verify command path.
2. Map exit codes to verdicts in the `verify` state; write detail artifact.
3. Extend `finalize`'s `summary.json` construction to carry the richer verify
   result.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors for each step:_

1. Widen `verify_epic_branch_before_merge()` return
   (`worktree_utils.py:317-321`) to carry `result.returncode`; preserve the
   verbatim `message` substring (`test_orchestrator.py:1615`).
2. In the `verify` state (`auto-refine-and-implement.yaml:396-412`, and the
   non-epic `run_checks()` closure at `:372-383`), map `returncode` → verdict
   class (`1 → failed`, `2 → collection_error`) and persist detail + code via the
   chosen artifact (Option A/B). Mirror the ENH-2376 branch at `:737-751`.
3. In `finalize` (`:728`/`:735`, `printf` at `:753-754`), add the exit-code /
   detail / verdict-class field(s) to `summary.json` (flat field for Option A, or
   nested-`%s` like `SKIPPED_BREAKDOWN` for Option B).
4. Repeat the returncode-surfacing at the `merge_epic_branch` call site
   (`:527-541`) and update the `orchestrator._verify_epic_branch_before_merge`
   wrapper (`orchestrator.py:~1310-1386`) if the tuple widens.

## Acceptance Criteria

- A collection/import error yields a `collection_error`-class verdict, visibly
  different from a real test failure, without re-running the suite.
- The failure detail (message + exit code) is persisted in the run_dir and
  reflected in `summary.json`.

## Session Log
- `/ll:confidence-check` - 2026-07-13T19:15:00 - `f50585fe-3374-421c-8014-87f7e2c49944.jsonl`
- `/ll:wire-issue` - 2026-07-13T19:08:36 - `9c6037dd-59e4-4810-80d3-c2c8497d31c4.jsonl`
- `/ll:decide-issue` - 2026-07-13T19:01:59 - `3d59c4d4-b18d-40a1-874b-1e281c5157ec.jsonl`
- `/ll:refine-issue` - 2026-07-13T18:57:43 - `e555b243-e23c-429d-9cab-61c70b69018b.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:30:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
