---
id: BUG-3478
type: BUG
title: format-check Program Design gate strips leading underscore from private Call
  Path anchors
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T21:45:35Z'
---

# BUG-3478: format-check Program Design gate strips leading underscore from private Call Path anchors

## Summary

`ll-issues format-check`'s Program Design gate strips leading underscores from Call Path anchors before resolving them, so a `### Call Path` that names only private functions (`_grade()`, `_run_sample_loop()`) is graded `program_design_nonspecific` with "no call-path anchor resolves against the repo" even though every named symbol is defined.

## Current Behavior

`extract_call_path_anchors()` (`scripts/little_loops/issues/program_design.py:262`) normalizes each token with `token.strip().strip("`*_")` (`:272`). The `_` in that strip set was meant to remove markdown emphasis underscores, but it also removes the leading underscore of a private Python identifier. `git_grep_resolver()` (`:295`) then greps for `def grade(` / `class grade`, which does not exist, and the anchor fails. `_IDENT` (`:126`) explicitly allows a leading `_`, so the intent to accept private names is already there; only the normalization defeats it.

## Expected Behavior

`_grade` resolves as `def _grade(`. Emphasis underscores should be stripped only when they are paired markdown delimiters (`_foo_`, `__foo__`), not when they are part of the identifier. A Call Path naming only private functions that all exist must pass the resolution check.

## Program Design

### Types

- No new types.

### Signatures

- `extract_call_path_anchors(body: str) -> list[str]` (`scripts/little_loops/issues/program_design.py:262`): unchanged signature; the inner `_add()` normalizer changes from `strip("`*_")` to stripping backticks and asterisks, then removing underscores only when the token is wrapped symmetrically (`_x_` / `__x__`) and the inner text is still a valid identifier.
- `git_grep_resolver(symbol: str, root: Path | None = None) -> bool` (`:295`): unchanged.

### Call Path

`grade_issue_section()` (`:543`) -> `grade_program_design()` (`:402`) -> `extract_call_path_anchors()` -> `git_grep_resolver()` -> `_resolve_short_symbol()`. Only the normalizer inside `extract_call_path_anchors()` changes; the resolver already accepts `def _grade(` because `_IDENT` matches a leading underscore.

## Impact

- **Priority**: P3 - every issue whose hooks are private helpers either fails the readiness gate spuriously or is padded with an unrelated public anchor to get past it, which weakens the gate's signal.
- **Effort**: Small - one normalizer change and three tests.
- **Risk**: Low - resolution can only become more permissive for identifiers that actually exist; unresolvable tokens still fail.
- **Breaking Change**: No

## Steps to Reproduce

1. Write an issue whose `### Call Path` reads `` `_run_sample_loop()` -> `_grade()` -> new `grader_error` on the outcome `` (both functions exist in `scripts/little_loops/cli/harness.py`).
2. Run `ll-issues format-check <ID>`.
3. Output: `program_design_nonspecific: Program Design: no call-path anchor resolves against the repo: run_sample_loop, grade, grader_error` — note the anchors are reported without their leading underscore.
4. Add a public anchor such as `` `evaluate_llm_structured()` `` to the same chain; the gate passes. Observed 2026-09-14 on BUG-3477.

## Tests

- `scripts/tests/test_program_design_gate.py::TestGrading` — add `test_private_function_anchor_resolves`: a Call Path naming only `` `_grade()` `` against a fixture repo defining `def _grade(` passes.
- Same class — add `test_markdown_emphasis_underscores_still_stripped`: `_evaluate_` (emphasis) normalizes to `evaluate`.
- `TestRealRepoResolution::test_real_repo_anchors_resolve_via_git_grep` (`:437`) — extend with a private-function anchor.

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-14T21:47:59 - `b8b46581-a38f-4aa7-a1ba-71f0319e7405.jsonl`
