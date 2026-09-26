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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Conventions in force** (evidence: `introspect.py` whole-module read; `scripts/tests/test_init_introspect.py`):
  - Every derived value is a frozen `IntrospectedValue(value, provenance, evidence)` with `provenance` in `declared|inferred|default`; fallbacks use `"default"` plus a short fixed-phrase evidence string. Helpers are private `_snake_case`, `root: Path` first, `IntrospectedValue | None` / `str | None` / `set[str]` returns.
  - Directory values carry a trailing slash (`src/`, `tests/`); the sole exception is the `"tests"` default. No existing code emits `.` as a value (it appears only inside command strings), so the spelling of the root value (`.` vs `./`) is a new decision — the go template already uses `.`, which favors `.`.
  - Skip-dir handling: `_SKIP_DIRS` / `_SRC_CANDIDATE_SKIP_DIRS` are the module's ignore sets and `_find_manifest` (`root.glob("*/<file>")` filtered by `_SKIP_DIRS`) is the existing one-level-nested probe; a nested test-dir probe should honor the same ignore set. `detect.py` keeps a separate, differing `_EXCLUDE_DIRS` (contested — no shared constant exists).
  - The `("tests/", "test/")` literal and `is_dir()` probe are duplicated in `_introspect_focus_dirs` and `_introspect_test_dir`; no shared existence-filter helper exists.
- **Existing tests that assert the behavior this issue removes** (must be revised, not merely kept passing): `TestSrcDirDetection.test_no_package_marker_keeps_default` (expects `python_template.data["project"]["src_dir"]` i.e. `src/` in an empty tmp dir), `TestTestDirDetection.test_no_test_dir_keeps_default` (expects `"tests"` in an empty dir), `TestFocusDirsDetection.test_defaults_when_nothing_detected` (expects template `["src/","tests/"]` in an empty dir). Ambiguity test `test_two_top_level_package_dirs_ambiguous_keeps_default` expects `provenance == "default"` with candidates `{"scripts/","lib/"}` and must keep passing. Evidence strings `"adopted src_dir"` and `"adopted src_dir + detected tests/ directory"` are asserted verbatim by `TestFocusDirsEvidence` and must be preserved.
- **Contested point — "left empty" vs `.`**: Expected Behavior allows "left empty / falls back to `.`", but `build_config` treats empty as "keep template value", re-introducing the phantom dir. The round-trip constraint above makes `.` the only self-consistent no-detection result.

## Integration Map

- `scripts/little_loops/init/introspect.py` — `_introspect_src_dir`, `_introspect_test_dir`, `_introspect_focus_dirs`
- `scripts/little_loops/init/proposal.py`, `scripts/little_loops/init/core.py`, `scripts/little_loops/init/tui.py`, `scripts/little_loops/init/summary.py`
- Template defaults under `scripts/little_loops/templates/`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Fallback sites (all in `scripts/little_loops/init/introspect.py`)**: `_introspect_src_dir(root, py_data, default_value) -> tuple[IntrospectedValue, Ambiguity | None]` returns the unchecked template default on both the zero-candidate and the ambiguity branch (on ambiguity the candidates are surfaced only via `Ambiguity`, never adopted). `_introspect_focus_dirs(root, src_dir_iv, default_focus_dirs)` returns `list(default_focus_dirs)` unchecked when nothing was inferred. `_introspect_test_dir(root, default_value)` probes only top-level `tests/`, `test/`; `introspect()` supplies `default_test_dir = project.get("test_dir") or "tests"` and no bundled template defines `project.test_dir`, so the fallback is always the literal `"tests"` (no trailing slash).
- **Callers**: `introspect()` is the sole caller of the three helpers (`introspect.py:152`, `:185`, `:190`; confirmed by grep); `proposal.py:build_proposal` is the sole production caller of `introspect()`.
- **Template defaults that would be filtered**: `project.src_dir` is `src/` in generic/python-generic/typescript/javascript/rust/dotnet, `src/main/java/` in java-maven/java-gradle, and `.` in go (a valid value that must survive filtering). `scan.focus_dirs` lists include non-conventional entries (`lib/`, `cmd/`, `pkg/`, `internal/`, `benches/`, `src/test/java/`) — every one is subject to the existence filter.
- **Unverified candidates**: pyproject (`_pyproject_src_candidate`), tsconfig (`_tsconfig_src_candidate`) and Cargo candidates are not existence-checked today; the issue's Scope Boundaries leave them unchanged, so "no proposal contains an absent dir" holds for defaults only unless that boundary is revisited.
- **Downstream round-trip constraint**: `core.py:build_config` and `tui.py:build_config` skip falsy `src_dir`/`test_dir`/`scan_focus_dirs` choices, so an *empty* value silently re-adopts the template's (possibly phantom) path; `tui.py:_answers_from_proposal` `_seed()` likewise falls back to `"src/"`/`"tests"` on a falsy choice, and seeds focus dirs to `["src/"]` when the choice is empty. `.` is truthy and passes through `summary.py:summary_rows` ("Source dir" row) unchanged. Consequence: the "left empty" alternative in Expected Behavior cannot round-trip; only `.` (or an existing dir) does.
- **Focus-dir interaction with `.`**: `_introspect_focus_dirs` de-duplicates tests dirs with `name.startswith(fd)`; an adopted src_dir of `.` would suppress `tests/`/`test/` entries. Whatever value `.` takes, this prefix guard must not swallow real test dirs.
- **Downstream consumers of provenance**: `proposal.py` (`provenance_rows` hides default-provenance rows; `scan.focus_dirs` row shown only when non-default), `tui.py` (hints suppressed for `default`), `cli.py:_print_introspection_summary` (skips default values, prints ambiguity candidates). Emitting `.` with provenance `default` therefore stays hidden from the user by design.
- **`mypy {src_dir or '.'}`** in `_python_command` receives `src_dir_iv.value`; a `.` value yields `mypy .`, an empty string also yields `mypy .`.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Outcome: no `IntrospectedValue` from the three helpers holds a path absent from the target root (other than `.`); verified by a test per helper in `test_init_introspect.py` using `tmp_path` layouts.
- Outcome: the three tests listed under Proposed Solution → Codebase Research Findings that hard-code phantom defaults are rewritten to the new contract; `pytest scripts/tests/test_init_introspect.py scripts/tests/test_init_proposal.py scripts/tests/test_init_core.py scripts/tests/test_init_tui.py scripts/tests/test_init_skill_fixtures.py` passes.
- Outcome: `.` round-trips through `build_proposal` → `build_config` (`core.py` and `tui.py` variants) → `summary_rows`; verified by an added case alongside `test_init_core.py`/`test_init_proposal.py`.
- Outcome: go template (`src_dir: .`) and java templates (`src/main/java/`) still yield existing-dir results when those dirs exist; an integration check in `scripts/tests/integration/test_init_e2e.py` still passes.

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
- `/ll:refine-issue` - 2026-09-26T22:50:46 - `4b810b7f-5ecd-426c-a2b1-3149be2063f7.jsonl`
- `/ll:format-issue` - 2026-09-26T22:33:50 - `f16b1c3d-13dc-4e2c-9a78-1582bd68929b.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:32:37 - `9b05118c-8f95-46d6-ac91-f7fa688ef1a5.jsonl`
