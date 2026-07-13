---
id: ENH-2631
title: Verify gate discards failure message and exit code
type: enhancement
status: open
priority: P3
captured_at: "2026-07-13T18:30:06Z"
discovered_date: 2026-07-13
discovered_by: capture-issue
relates_to: [BUG-2629]
decision_needed: true
learning_tests_required: [pytest]
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
- `/ll:refine-issue` - 2026-07-13T18:57:43 - `e555b243-e23c-429d-9cab-61c70b69018b.jsonl`
- `/ll:capture-issue` - 2026-07-13T18:30:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e418041f-97b9-4193-89df-c4643e9794aa.jsonl`

---

## Status

- **Status**: open
- **Priority**: P3
