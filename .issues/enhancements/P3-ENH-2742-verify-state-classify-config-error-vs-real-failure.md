---
id: ENH-2742
title: Verify state's classify() should distinguish "missing npm script" config error
  from real test failure
type: ENH
priority: P3
status: done
captured_at: '2026-07-23T00:25:52Z'
completed_at: '2026-07-23T00:57:30Z'
discovered_date: 2026-07-23
discovered_by: audit
size: Small
labels:
- loops
- verify
- captured
confidence_score: 98
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 22
---

# ENH-2742: Verify state's classify() should distinguish "missing npm script" config error from real test failure

## Summary

The FSM verify state's `classify()` returns `'failed'` for any non-zero exit
code other than 2 (`collection_error`). A missing npm script (e.g. `npm error
Missing script: "test"`) yields exit 1 with that stderr — semantically a
config/usage error, not a code defect — but it's indistinguishable from a real
test failure in `summary.json`'s `verify_verdict` field.

On this repo, every `sprint-refine-and-implement` run currently reports
`verify_verdict: "failed"` due to a `test_cmd` misconfiguration (`"npm test"`
run from repo root, where `package.json` lives in `studio/`) even though no
tests ever ran. A human reviewer can't tell "config broken" from "tests
broke" without opening `verify-detail.txt`.

## Current Behavior

```python
def classify(returncode):
    if returncode == 0: return 'passed'
    if returncode == 2: return 'collection_error'
    return 'failed'
```

## Expected Behavior

`classify()` accepts `stderr` and returns a distinct `'config_error'` verdict
when stderr indicates a missing/misconfigured script, rather than collapsing
it into `'failed'`.

## Proposed Solution

```python
def classify(returncode, stderr=""):
    if returncode == 0: return 'passed'
    if returncode == 2: return 'collection_error'
    if 'missing script' in stderr.lower(): return 'config_error'
    return 'failed'
```

**Note**: this is defense-in-depth. The simplest fix for the current repo is
correcting `test_cmd` in `.ll/ll-config.json` (tracked separately — see
P3-ENH-044, being investigated for reopening). This proposal guards against
future misconfigs of the same shape and makes `verify_verdict` a more
reliable closure signal generally.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`classify()` is not a standalone Python module function — it's an inline
closure defined inside the FSM `verify` state's `shell` action heredoc in
`scripts/little_loops/loops/auto-refine-and-implement.yaml:381-386`, and it
has **two call sites** in the same action:

- **In-place path** (`auto-refine-and-implement.yaml:428-430`): already
  computes `detail = format_verify_detail(result.stdout, result.stderr)`
  from `subprocess.run(..., capture_output=True, text=True)` *before*
  calling `classify(result.returncode)` — `result.stderr` is in scope and
  currently discarded from the classify call, only folded into the free-text
  `detail` artifact.
- **Epic-branch path** (`auto-refine-and-implement.yaml:456-475`): delegates
  to `verify_epic_branch_before_merge()` in
  `scripts/little_loops/worktree_utils.py:364`, which returns
  `(ok, message, returncode)` — there's no raw `stderr` in scope here, only
  `message` (itself built from `format_verify_detail(result.stdout,
  result.stderr)` inside `worktree_utils.py:476-480`). Both call sites need
  updating; the epic path should pass `message` where the in-place path
  passes `stderr`/`detail`.

Established pattern for string-based stderr classification already exists in
`scripts/little_loops/issue_lifecycle.py:96` (`classify_failure`): lowercase
once (`error_lower = error_output.lower()`), then
`any(pattern in error_lower for pattern in patterns)`, falling back to
`re.search(r"\bword\b", ...)` only where a bare substring risks false
positives (their own comment: `"enotfound" shouldn't match
"ModuleNotFoundError"`). The proposed `'missing script' in stderr.lower()`
check is consistent with this convention and low collision-risk as a plain
substring match.

`emit()` (`auto-refine-and-implement.yaml:392-402`, the sibling helper that
writes `verify-verdict.txt`/`verify-returncode.txt`/`verify-detail.txt`)
requires no change — it treats `verdict` as an opaque string, so a
`'config_error'` token flows through unchanged.

## Impact

- **Priority**: P3 — advisory triage-quality improvement, not a functional bug
- **Effort**: Small — one function signature change, two call-site edits, test coverage
- **Risk**: Low — additive verdict class; `emit()`/`finalize` treat it as an opaque string
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: `classify()`'s signature and its two call sites in
  `auto-refine-and-implement.yaml`; test coverage for both the in-place and
  epic-branch paths; documenting `config_error` in the verdict vocabulary.
- **Out of scope**: fixing the actual `test_cmd` misconfiguration in this
  repo's `.ll/ll-config.json` (tracked separately under P3-ENH-044); adding a
  general-purpose stderr-classification taxonomy beyond the single "missing
  script" pattern; any change to `finalize`'s pass-through handling of
  `verify_verdict` (already confirmed to require none).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `classify()`
  definition (lines 381-386): add `stderr=""` param and the `config_error`
  branch.
  - Line 430 (in-place call site): `emit(classify(result.returncode),
    result.returncode, detail)` → pass `result.stderr` (already captured,
    already in scope) into `classify()`.
  - Line 474 (epic-branch call site): `verdict = classify(returncode) if
    returncode is not None else 'failed'` → pass `message` (the epic path's
    only available stderr-derived text) into `classify()`.

### Dependent Files (pass-through, no code change expected)
- `finalize` state, same YAML (~lines 886-935) — reads `verify-verdict.txt`
  verbatim and `printf`s it into `summary.json`'s `"verify_verdict"` key with
  no allowlist/enum validation; a new `config_error` value passes through
  unchanged (confirmed by existing test
  `test_finalize_surfaces_verify_returncode`'s loop-over-arbitrary-strings
  shape).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` `merge_epic_branch`
  state (~lines 619-647) — reads `verify-verdict.txt` to decide whether to
  reuse a SHA-matched `passed` verdict; unaffected by a new non-`passed`
  value.

### Similar Patterns
- `scripts/little_loops/issue_lifecycle.py:96` `classify_failure(error_output,
  returncode) -> tuple[FailureType, str]` — nearest structural precedent for
  a `(text, returncode)` → classification signature and the
  lowercase-then-substring-match convention.

### Tests
- `scripts/tests/test_builtin_loops.py` `TestVerifyStateConfigReadShell`
  (~line 3425) — extracts the `verify` state's `action` string directly from
  the parsed loop YAML and runs it via `bash -c` against a stub `test_cmd`.
  Mirror the existing `test_collection_error_when_test_cmd_exits_2` case with
  a `test_cmd="sh -c 'echo \"npm error Missing script: \\\"test\\\"\" >&2;
  exit 1'"` fixture asserting the verdict is `"config_error"`.
- `scripts/tests/test_builtin_loops.py` (~line 2949, comment-tagged `# ---
  ENH-2631: verify_returncode + collection_error verdict class ---`) —
  extend `test_finalize_surfaces_verify_returncode`'s `(verdict, code)` tuple
  list with `("config_error", "1")` to confirm finalize's pass-through
  handles the new value (should require no finalize code change, only test
  coverage).

_Wiring pass added by `/ll:wire-issue`:_
- **Epic-branch call site (line ~474) has zero existing test coverage
  today.** `TestVerifyStateConfigReadShell`
  (`scripts/tests/test_builtin_loops.py:3425`) never sets `epic_branch` in
  context, so it only ever exercises the non-epic call site (line 430).
  `TestVerifyEpicBranchBeforeMerge`
  (`scripts/tests/test_worktree_utils.py:352`) tests
  `verify_epic_branch_before_merge()`'s own `(ok, message, returncode)`
  return tuple, but not the YAML's wrapping `classify(returncode)`/
  `emit(...)` logic that consumes `message` at line 474. Add a new test
  combining `test_worktree_utils.py`'s epic-branch git scaffolding
  (`_repo_with_epic_branch`, line 357) with `test_builtin_loops.py`'s
  shell-action-extraction pattern, asserting a "missing script" stderr on
  the epic-branch path also yields `config_error` via the final
  `verify-verdict.txt`, not just the in-place path.

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — documents the verdict vocabulary as
  `passed`/`failed`/`collection_error`/`skipped`/`not_run`; add
  `config_error`.
- `skills/audit-loop-run/SKILL.md` (~line 294) — documents `verify_verdict`
  as advisory-only triage guidance; note that `config_error` indicates a
  harness/config problem, not a code defect, distinct from `failed`.

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — needs a new dated-release entry following this
  project's convention (no `[Unreleased]` section; see
  `feedback_changelog_no_unreleased`), matching the precedent set by the
  ENH-2601 (`verify_verdict` introduction) and ENH-2631
  (`collection_error` verdict class) entries already present.

## Implementation Steps

1. Locate the verify state's `classify()` implementation — inline Python
   heredoc in the `verify` state's `action` block,
   `scripts/little_loops/loops/auto-refine-and-implement.yaml:381-386`.
2. Add `stderr=""` to `classify()`'s signature; add the `'missing script' in
   stderr.lower()` → `'config_error'` branch before the final `'failed'`
   fallback.
3. Thread `result.stderr` into the in-place call site (line 430) and
   `message` into the epic-branch call site (line 474) — both are already
   computed in scope at each call.
4. No change needed in `finalize` (summary.json writer) — it passes
   `verify_verdict` through verbatim with no enum validation.
5. Add a test in `TestVerifyStateConfigReadShell`
   (`scripts/tests/test_builtin_loops.py:3425`) asserting a "Missing script"
   stderr yields `config_error`, not `failed`, following the
   `test_collection_error_when_test_cmd_exits_2` pattern. Optionally extend
   `test_finalize_surfaces_verify_returncode`'s value list with
   `config_error` to confirm pass-through.
6. Update `docs/guides/LOOPS_REFERENCE.md`'s verdict vocabulary list to
   include `config_error`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

7. Add a new epic-branch-path test (combining `test_worktree_utils.py`'s
   `_repo_with_epic_branch` scaffolding with `test_builtin_loops.py`'s
   shell-action-extraction pattern) asserting the line-474 call site also
   yields `config_error` for a "missing script" stderr — this path has no
   existing coverage at all today.
8. Add a `CHANGELOG.md` entry for this change, following the ENH-2601 /
   ENH-2631 precedent pattern (new dated-release section, not
   `[Unreleased]`).

## Sources

- `audit-loop-run-sprint-refine-and-implement-2026-07-18T045753.md` —
  Proposal #2 (state-level)
- `.issues/enhancements/P3-ENH-2631-verify-gate-surface-failure-message-and-exit-code.md`
  — introduced the `classify()`/`emit()` pair and the `collection_error`
  verdict class this issue extends
- `.issues/enhancements/P3-ENH-2601-epic-branch-aware-fsm-refine-implement-loops.md`
  — introduced `verify_verdict` as an additive/advisory `summary.json` field
- `.issues/enhancements/P3-ENH-2630-merge-epic-branch-reuse-verify-verdict-avoid-double-run.md`
  — the SHA-reuse fast path in `merge_epic_branch` that reads
  `verify-verdict.txt`, unaffected by a new verdict value

## Resolution

`classify()` in the `verify` state's Python heredoc
(`scripts/little_loops/loops/auto-refine-and-implement.yaml`) now accepts an
optional `stderr` param and returns `'config_error'` when stderr contains
`"missing script"`, before falling back to `'failed'`. Both call sites were
updated: the in-place path now passes `result.stderr`; the epic-branch path
now passes `message` (the only stderr-derived text available there). Added
test coverage for both call sites in
`scripts/tests/test_builtin_loops.py::TestVerifyStateConfigReadShell`
(`test_config_error_when_stderr_reports_missing_script`,
`test_config_error_on_epic_branch_path`), plus a `config_error` case in
`test_finalize_surfaces_verify_returncode`. Documented the new verdict class
in `docs/guides/LOOPS_REFERENCE.md` and `skills/audit-loop-run/SKILL.md`. Per
this repo's convention (CHANGELOG entries land only via `docs(release):`
commits during release prep, not per-issue commits), no CHANGELOG.md edit was
made here.

## Status

**Done** | Created: 2026-07-23 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-23T00:56:57Z - `23478c7d-c99c-4a08-9d83-170385b86c03.jsonl`
- `/ll:ready-issue` - 2026-07-23T00:49:38 - `18e8a982-ab5a-44b8-9a97-5c73746660b9.jsonl`
- `/ll:wire-issue` - 2026-07-23T00:45:26 - `9095e294-b9ad-4eef-bebf-152308577080.jsonl`
- `/ll:refine-issue` - 2026-07-23T00:39:36 - `a153c918-3421-4ec5-85c6-dfddf1e4c4a6.jsonl`
- `/ll:capture-issue` - 2026-07-23T00:25:52Z - `01b32c17-cae1-4173-b77e-b51fe2c99146.jsonl`
