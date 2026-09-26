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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/init/__init__.py` — re-exports `IntrospectedValue`, `introspect`, `IntrospectResult`, `Ambiguity` (public symbols; shape unchanged, values change)
- `scripts/little_loops/init/cli.py:531` `_print_introspection_summary` — prints "kept template default — N candidates found"; wording becomes inaccurate if the ambiguity fallback is now a filtered default / `.`
- `scripts/little_loops/init/core.py:347` `build_config` — `if choices.get("scan_focus_dirs")` skips an empty list and re-adopts the unfiltered template `focus_dirs`; the `["."]` fallback in `_introspect_focus_dirs` is what keeps the filter effective
- `scripts/little_loops/init/tui.py:1090` `build_config` wrapper — same `if scan_focus_dirs:` truthiness guard
- `scripts/little_loops/init/proposal.py:296-312` `build_proposal` — existing-config branch pins `src_dir`/`test_dir`/`scan.focus_dirs` with provenance `existing`, so a re-init keeps prior (possibly phantom) values; existence filtering applies to fresh introspection only
- `scripts/little_loops/init/proposal.py:122` plan-JSON serializer — docstring promises `values`/`ambiguities` shapes stay stable for `skills/init/SKILL.md`; new evidence strings must not alter the shape
- **Runtime consumers of a `.` value** (read what init writes; `go.json` already ships `src_dir: "."` so `.` is not new, but the Python/JS/generic paths would now emit it):
  - `scripts/little_loops/codequery/codegraph.py:121` `_is_scan_relevant` — `path == d.rstrip("/") or path.startswith(d.rstrip("/") + "/")` yields `path == "."` / `startswith("./")` for `d="."`; repo-relative paths match neither, so `focus_dirs: ["."]` would exclude every file from the scan-relevant filter
  - `scripts/little_loops/codequery/codegraph.py:234` `_dotted_candidates` — `prefix = src_dir.rstrip("/") + "/"` becomes `./`; no repo-relative path starts with it, so no src-relative dotted candidates are produced
  - `scripts/little_loops/cli/issues/decisions.py:652` — `scope_globs = [f"{src_dir.rstrip('/')}/**/*"]` becomes `./**/*` for `.`; matcher behavior against repo-relative paths unverified
  - `scripts/little_loops/config/core.py` `ProjectConfig` (path property `project_root / src_dir`), `scripts/little_loops/worktree_utils.py:547,746`, `scripts/little_loops/prepatch_check.py:291,453-471`, `scripts/little_loops/loops/oracles/code-run-gate.yaml:210,330-332,393-395` — path joins; `.` resolves to root and works
  - `scripts/little_loops/parallel/worker_pool.py:1523` (iterates `[src_dir, test_dir]`) and `loops/auto-refine-and-implement.yaml:626,851` — pass `src_dir` through; effect of `.` unverified
- **Command/skill string substitution of `{{config.project.src_dir}}`** (most exposed to `.`):
  - `commands/manage-release.md:38,40,249,251,302` — concatenates with no separator (`{{config.project.src_dir}}pyproject.toml`); `.` yields `.pyproject.toml` (breaks; `src/` works only because of the trailing slash)
  - `commands/run-tests.md:99` — `grep -E '^{{config.project.src_dir}}'` becomes regex `^.` and matches everything; `:121` `--cov=.` is fine
  - `skills/spike/SKILL.md:151` — `test_dir` of `.` lands spikes at `./spike/<slug>/`
  - `commands/scan-codebase.md`, `commands/scan-product.md`, `commands/find-dead-code.md` — embed `{{config.scan.focus_dirs}}` in prompts; `["."]` reads oddly but works

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CONFIGURATION.md` (~lines 323, 1969) and `docs/guides/GETTING_STARTED.md:165` — describe `--force` as "resets to template defaults"; now existence-filtered, check wording
- `docs/reference/CLI.md` (lines ~50, 76) — `ll-init` flag text; check for template-default wording
- `skills/init/SKILL.md:167` — "template defaults" sentence; verify still accurate
- `scripts/little_loops/config-schema.json` (`src_dir`/`test_dir`/`focus_dirs` descriptions, ~lines 20, 25, 825) — consider documenting `.` as a valid value; if `skills/` files are edited, re-run `ll-adapt --host <gemini|kimi-code|qwen> --apply` (mirrors under `.qwen/`, `.kimi-code/`, `.gemini/`)
- `skills/configure/show-output.md:11,12,164` — hard-codes "(default: src/)" / "(default: tests)"; schema defaults, not changed by this issue

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/templates/{generic,python-generic,typescript,javascript,rust,java-maven,java-gradle,dotnet}.json` — `src_dir`/`focus_dirs` defaults are the phantom-path source; filtered at read time, template contents unchanged (out of scope); `go.json` `src_dir: "."` must survive the filter

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_init_audit_fixes.py` `TestHeadlessTuiConfigEquivalence.test_tui_and_headless_produce_equivalent_sections` — passes literal `src_dir="src/"` to the TUI path with no `src/` dir; may diverge from headless once headless filters by existence
- `scripts/tests/integration/test_init_e2e.py` `TestInitHeadlessEndToEnd.test_dry_run_writes_nothing_then_apply_generates_config`, `test_generated_config_round_trips_through_brconfig`, `test_plan_apply_produces_same_artifacts_as_yes` — run on empty dirs; verify `BRConfig` round-trip tolerates the new `.`/filtered values
- `scripts/tests/test_init_proposal.py` `TestPlanContract.test_plan_keys_stable_and_fields_additive` — key-stability assertion; new evidence/provenance must not add keys
- `scripts/tests/test_init_core.py` `TestMainInit.test_yes_creates_config`, `test_plan_emits_json` — bodies unread, most likely core candidates to assert defaults on an empty `tmp_project`
- `scripts/tests/test_init_tui.py` `TestWizardSeedsFromIntrospection`, `TestHappyPath`, `TestBuildFinalConfigParity` — check any using real `_TEMPLATES_DIR` on empty `tmp_path`
- `scripts/tests/test_init_introspect.py` lines ~100, 250, 281, 304 — assert `mypy src/` / template-default `src_dir` / `focus_dirs == template` on layouts with no `src/`; will flip (extends the three tests already listed above)
- **New tests to write** (follow `tmp_path` style; models in parentheses):
  - `test_init_introspect.py` — `_existing_dir`, `_detect_root_layout` (root `.`), `_find_nested_test_dir` (`scripts/tests/`)
  - `test_init_proposal.py` — `.` round-trip via `choices` / `field_for("project.src_dir")` / `config` (model: `test_existing_test_dir_survives_reinit`)
  - `test_init_core.py` — `build_config(match, {"src_dir": "."})` and a focus-dirs case (model: `TestBuildConfig.test_test_dir_injected_via_choice`)
  - `test_init_tui.py` — root-layout wizard default `.` (models: `TestWizardSeedsFromIntrospection`, `TestScanScreen.test_custom_focus_dirs_written_to_config`)
  - new `summary_rows` coverage (no direct test exists; extend `test_init_audit_fixes.py::TestOutputLayer` or add a module) asserting the `.` "Source dir" row
  - `integration/test_init_e2e.py` — `--yes` on a root-layout dir yields `project.src_dir == "."`; on an empty dir emits no phantom `src/`

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Decide the `.` spelling and audit `.`-hostile consumers: fix `codegraph.py:121` `_is_scan_relevant` and `:234` `_dotted_candidates` (special-case `.`), verify `decisions.py:652` glob, `worker_pool.py:1523`, `auto-refine-and-implement.yaml:626,851`
- Update `commands/manage-release.md` (lines 38, 40, 249, 251, 302) — src_dir concatenated without separator breaks for `.`; and `commands/run-tests.md:99` — `^.` regex matches all
- Update `cli.py:531` `_print_introspection_summary` wording ("kept template default") to match the new fallback
- Keep `core.py:347` / `tui.py:1090` truthiness guards safe by never returning an empty focus list (`["."]` fallback)
- Update the tests listed under `### Tests` (empty-dir assumptions in `test_init_introspect.py`, `test_init_audit_fixes.py`, `test_init_e2e.py`, `test_init_core.py`, `test_init_tui.py`) and add the new tests
- Review `--force` / "template defaults" wording in `docs/reference/CONFIGURATION.md`, `docs/guides/GETTING_STARTED.md`, `docs/reference/CLI.md`, `skills/init/SKILL.md`; run `ll-adapt` mirrors if any `skills/` file changes
- Coordinate with ENH-3612, which plans to move the `_introspect_src_dir` call above the command loop in `introspect.py`

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
- `/ll:wire-issue` - 2026-09-26T22:54:01 - `f54e5d1b-c94c-4496-a128-5bf9edc4c3c0.jsonl`
- `/ll:refine-issue` - 2026-09-26T22:50:46 - `4b810b7f-5ecd-426c-a2b1-3149be2063f7.jsonl`
- `/ll:format-issue` - 2026-09-26T22:33:50 - `f16b1c3d-13dc-4e2c-9a78-1582bd68929b.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:32:37 - `9b05118c-8f95-46d6-ac91-f7fa688ef1a5.jsonl`
