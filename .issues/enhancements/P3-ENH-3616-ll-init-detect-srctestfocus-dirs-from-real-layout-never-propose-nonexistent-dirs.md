---
id: ENH-3616
type: ENH
title: 'll-init: detect src/test/focus dirs from real layout, never propose nonexistent
  dirs'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T22:32:30Z'
---

# ENH-3616: ll-init: detect src/test/focus dirs from real layout, never propose nonexistent dirs

## Summary

`ll-init`'s detected **Source dir**, **Test dir**, and **Focus dirs** should be (1) detected from the target project's actual layout — including `.` when code or tests live at the repo root — and (2) never pre-filled with a directory that does not exist in the target project.

## Current Behavior

`little_loops.init.introspect` falls back to project-type *template defaults* whenever detection is inconclusive, without checking that the default path exists:

- `_introspect_src_dir` (`introspect.py:686`) returns `default_value` (the template's `project.src_dir`, e.g. `src/`) on zero candidates ("no unambiguous package marker") and on ambiguity ("multiple src_dir candidates").
- `_introspect_test_dir` (`introspect.py:761`) only probes top-level `tests/` and `test/`; otherwise returns the template default (`project.test_dir or "tests"`).
- `_introspect_focus_dirs` (`introspect.py:735`) returns `list(default_focus_dirs)` verbatim ("template default") when nothing was inferred.

None of these paths can produce `.` — a flat-layout project (modules or `test_*.py` at the root) gets a phantom `src/` / `tests/` instead. Test dirs nested under a package dir (e.g. `scripts/tests/`) are also not found.

## Expected Behavior

- Every proposed dir value exists in the target project (`(root / value).is_dir()`), or is `.`.
- Root-level layouts resolve to `.`: e.g. top-level `*.py` modules / `main.go` / `index.ts` with no package subdir → Source dir `.`; `test_*.py` / `*_test.go` / `*.test.ts` at root → Test dir `.`.
- Test-dir detection also finds nested conventional dirs (e.g. `<src>/tests/`, `scripts/tests/`), not just top-level `tests/`/`test/`.
- When no existing dir can be determined, the field is left empty / falls back to `.` (with provenance `default` and evidence saying so) — never a template path that doesn't exist.
- Focus dirs are built only from dirs that exist; template `focus_dirs` entries are filtered by existence.
- Ambiguity prompts still offer only existing candidates.

## Motivation

A phantom `src_dir`/`test_dir`/`focus_dirs` silently misdirects `scan-codebase`, `find-dead-code`, test commands (`mypy src/`), and other consumers in the target project, and the user must notice and correct it in the TUI/config by hand.

## Proposed Solution

Add an existence filter in `little_loops.init.introspect` and route every template-default fallback through it:

- `_existing_dir(root, value)` returns `value` only if `(root / value).is_dir()` (or `value` is `.`), else `None`.
- `_introspect_src_dir`: on zero candidates or ambiguity, use the filtered template default; if that is `None`, detect a root-level layout (top-level `*.py` modules, `main.go`, `index.ts` with no package subdir) and return `.`, else `.` with provenance `default` and evidence "no existing src dir detected".
- `_introspect_test_dir`: probe top-level `tests/`/`test/`, then nested conventional dirs (`<src>/tests/`, `*/tests/`, `*/test/` one level deep), then root-level `test_*.py` / `*_test.go` / `*.test.ts` → `.`; template default only if it exists.
- `_introspect_focus_dirs`: filter template `focus_dirs` by existence; fall back to `["."]` if none survive.
- Keep the ambiguity path offering only existing candidates.

## Integration Map

- `scripts/little_loops/init/introspect.py` — `_introspect_src_dir`, `_introspect_test_dir`, `_introspect_focus_dirs`
- `scripts/little_loops/init/proposal.py`, `scripts/little_loops/init/core.py`, `scripts/little_loops/init/tui.py`, `scripts/little_loops/init/summary.py`
- Template defaults under `scripts/little_loops/templates/`

## Program Design

### Types

- `IntrospectedValue.value: str | list[str]` (unchanged; `.` is a valid value)

### Signatures

- `_existing_dir(root: Path, value: str) -> str | None`
- `_detect_root_layout(root: Path) -> bool`
- `_find_nested_test_dir(root: Path) -> str | None`

### Call Path

`introspect` -> `_introspect_src_dir` -> `_existing_dir`; `introspect` -> `_introspect_test_dir` -> `_find_nested_test_dir`; `introspect` -> `_introspect_focus_dirs` -> `_existing_dir`

## Scope Boundaries

- **In scope**: existence filtering of src/test/focus dir defaults, root-layout (`.`) detection, nested test-dir probing in `little_loops.init.introspect`, and round-tripping `.` through the init proposal/TUI/core.
- **Out of scope**: changing existing package-marker/pyproject/tsconfig/Cargo candidate detection; detecting non-conventional test dir names; changing project-type template contents; non-dir fields (build/lint/test commands) beyond keeping `{src_dir or '.'}` derivation sane.

## Implementation Steps

1. Add an existence filter helper in `little_loops.init.introspect`; apply it to template defaults in `_introspect_src_dir`, `_introspect_test_dir`, `_introspect_focus_dirs`.
2. Add root-layout detection producing `.` for src and test dirs.
3. Extend test-dir probing to nested conventional locations.
4. Check `proposal.py` / `tui.py` / `core.py` (`choices["src_dir"]`, `scan_focus_dirs`) so an empty/`.` value round-trips correctly, and dependent command derivation (e.g. `mypy {src_dir or '.'}` at `introspect.py:302`) stays sane.
5. Tests: flat-layout repo → `.`; repo with no `src/` → no `src/` proposed; nested `scripts/tests/` detected; template focus_dirs filtered by existence.

## Impact

- **Priority**: P3 - phantom dirs misdirect downstream tooling but the user can correct them in the TUI/config
- **Effort**: Small - three localized helpers in one module plus tests
- **Risk**: Low - only changes fallback paths where detection was already inconclusive
- **Breaking Change**: No

## Acceptance Criteria

- [ ] No `ll-init` proposal contains a Source/Test/Focus dir absent from the target project.
- [ ] Root-level source/test layouts are proposed as `.`.
- [ ] Nested test dirs (e.g. `scripts/tests/`) are detected.
- [ ] Existing detection (src/ package marker, pyproject/tsconfig/Cargo candidates) unchanged.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-26T22:33:50 - `f16b1c3d-13dc-4e2c-9a78-1582bd68929b.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:32:37 - `9b05118c-8f95-46d6-ac91-f7fa688ef1a5.jsonl`
