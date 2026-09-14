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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Files, callers, conventions, and tests relevant to fixing the `_add()` normalizer's underscore stripping.

### Files to Modify
- `scripts/little_loops/issues/program_design.py` — the `_add()` inner normalizer inside `extract_call_path_anchors()` (`:262-288`, buggy strip at `:272`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:1008-1013` — `check_format_gaps()` calls `grade_issue_section()` when a section is named "Program Design"; this is the real entry point `ll-issues format-check` triggers
- `scripts/little_loops/cli/issues/format_check.py:456-457, 65, 521` — surfaces `gaps.program_design_nonspecific` from the CLI
- `scripts/little_loops/cli/issues/check_design.py:32, 40` — a second consumer, backs `ll-issues check-design` via `design_gate_failed(gaps)`
- `scripts/tests/spike/program_design_specificity/program_design.py:124` — a standalone, non-imported ENH-2852 spike copy carrying the identical bug (informational only; not a production dependent)

### Conventions in Force
- Prior narrow fixes in this file cite the fixing bug's ID in an inline comment at the changed site — evidence: `program_design.py:74-77` ("BUG-3071"), `:302-304`/`:356-358` ("BUG-3273").
- Normalizer-level tests call the pure function directly with an inline resolver stand-in; no fixture repo is used unless testing `git_grep_resolver()` itself — evidence: `test_program_design_gate.py::TestGrading`/`TestDuplicateCallPathAnchors` (no fixture) vs `::TestRealRepoResolution` (real git repo fixture).

### Tests
- `scripts/tests/test_program_design_gate.py::TestGrading` (`:293-431`) — direct `grade_program_design(body, resolver)` calls
- `scripts/tests/test_program_design_gate.py::TestDuplicateCallPathAnchors` (`:236-265`) — direct `extract_call_path_anchors(body)` calls
- `scripts/tests/test_program_design_gate.py::TestRealRepoResolution::test_real_repo_anchors_resolve_via_git_grep` (`:434-475`) — real git-repo fixture, named in this issue's own `## Tests` section as the extension point
- `scripts/tests/test_ll_issues_format_check.py`, `scripts/tests/test_ll_issues_check_design.py`, `scripts/tests/test_autodev_loop.py` — exercise the CLI/gate wiring around `program_design_nonspecific`/`design_gate_failed`

### Documentation
- `docs/reference/API.md` — documents `program_design_nonspecific` gap category, `check-design` CLI row, `design_gate_failed` gate-priority prose
- `docs/reference/CLI.md` — documents `ll-issues format-check` flags/output including `program_design_nonspecific`

## Program Design

### Types

- No new types.

### Signatures

- `extract_call_path_anchors(body: str) -> list[str]` (`scripts/little_loops/issues/program_design.py:262`): unchanged signature; the inner `_add()` normalizer changes from `strip("`*_")` to stripping backticks and asterisks, then removing underscores only when the token is wrapped symmetrically (`_x_` / `__x__`) and the inner text is still a valid identifier.
- `git_grep_resolver(symbol: str, root: Path | None = None) -> bool` (`:295`): unchanged.

### Call Path

`grade_issue_section()` (`:543`) -> `grade_program_design()` (`:402`) -> `extract_call_path_anchors()` -> `git_grep_resolver()` -> `_resolve_short_symbol()`. Only the normalizer inside `extract_call_path_anchors()` changes; the resolver already accepts `def _grade(` because `_IDENT` matches a leading underscore.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Confirmed exact operation order inside `_add()` (`program_design.py:271-279`): `.strip()` (whitespace) → `.strip("`*_")` (this is where a leading `_` is lost, along with genuine backtick/asterisk decoration) → `.rstrip(".,;:")` → trailing `()` suffix removal → split at first `(` → final `_IDENT` match. The underscore loss happens before the `()`/`.`-splitting steps, so it fires identically whether the token is a bare name or a full call like `` `_grade()` ``.
- `_IDENT` (`:126`, `^[A-Za-z_][\w.]*$`) and `git_grep_resolver()`/`_resolve_short_symbol()` (`:295-359`) already correctly handle a leading underscore — confirmed `git_grep_resolver("_grade", root)` would resolve `True` against a real `def _grade(...)`. The failure is isolated entirely to the `_add()` normalizer in `extract_call_path_anchors()`, not the resolver or the identifier regex.
- No shared "symmetric wrapper" (`_x_`/`__x__`-pairing-aware) stripping helper exists anywhere in this codebase. Every other markdown-decoration stripper found is also unconditional character-class stripping, not pairing-aware: `verify_evidence.py:613,617-627` (`_EMPHASIS_CHARS_RE = re.compile(r"[*_`]")`, global `.sub("", text)`), `output_parsing.py:90-98` (`_clean_verdict_content()`), `issue_parser.py:2424-2430` (`_extract_option_label()`). There is no existing utility to delegate to; a fix here defines the first paired-delimiter check in this codebase.
- The identical bug also exists in a second, non-production location: `scripts/tests/spike/program_design_specificity/program_design.py:124`, a standalone ENH-2852 spike prototype. Confirmed not imported by production code (no importer found outside its own test file) — out of scope for this fix, but worth knowing so a future grep for this pattern doesn't mistake it for a second live occurrence.
- Real production caller chain, correcting the graph seed's "no importers found" gap (the graph indexes symbol/file edges, not this cross-module function-call chain): `ll-issues format-check` → `check_format_gaps()` (`issue_parser.py:1008-1013`) → `grade_issue_section()` (`program_design.py:543-546`) → `grade_program_design()` (`:402-441`, calls `extract_call_path_anchors()` at `:422`) → the `_add()` normalizer.
- Convention: prior narrow fixes to this exact file leave an inline comment citing the bug ID at the fixed site — evidence: `program_design.py:74-77` ("BUG-3071"), `:302-304`/`:356-358` ("BUG-3273"), `test_program_design_gate.py:236-244` docstring ("BUG-3245's fix routes new heading-emission through a containment check...").
- Testing convention: normalizer-level fixes in this file are unit-tested directly on the pure function with an inline resolver stand-in — no fixture repo needed (`TestGrading`, `TestDuplicateCallPathAnchors`, `test_program_design_gate.py:236-431`). Only resolver-level behavior (`git_grep_resolver()` itself) uses the real-git-repo fixture in `TestRealRepoResolution` (`:434-475`). No existing test in either class currently exercises a leading-underscore/private identifier.

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
- `/ll:refine-issue` - 2026-09-14T21:57:11 - `76fd614d-af9c-461c-9480-143acb792f32.jsonl`
- `/ll:format-issue` - 2026-09-14T21:47:59 - `b8b46581-a38f-4aa7-a1ba-71f0319e7405.jsonl`
