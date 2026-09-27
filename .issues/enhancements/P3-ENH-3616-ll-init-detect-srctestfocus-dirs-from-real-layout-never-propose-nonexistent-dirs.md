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
reconcile_attempted: true
confidence_score: 80
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
blocked_by:
- BUG-3631
---

# ENH-3616: ll-init: detect src/test/focus dirs from real layout, never propose nonexistent dirs

## Summary

`ll-init`'s detected **Source dir**, **Test dir**, and **Focus dirs** should be (1) detected from the target project's actual layout — including `.` when code or tests live at the repo root — and (2) never pre-filled with a directory that does not exist in the target project. The one deliberate exception is Test dir `tests/` for a project with no tests at all, because `test_dir` is where new tests get written.

## Current Behavior

`little_loops.init.introspect` falls back to project-type *template defaults* whenever detection is inconclusive, without checking that the default path exists:

- `_introspect_src_dir` (`introspect.py:686`) returns `default_value` (the template's `project.src_dir`, e.g. `src/`) on zero candidates ("no unambiguous package marker") and on ambiguity ("multiple src_dir candidates").
- `_introspect_test_dir` (`introspect.py:761`) only probes top-level `tests/` and `test/`; otherwise returns the template default (`project.test_dir or "tests"`).
- `_introspect_focus_dirs` (`introspect.py:735`) returns `list(default_focus_dirs)` verbatim ("template default") when nothing was inferred.

None of these paths can produce `.` — a flat-layout project (modules or `test_*.py` at the root) gets a phantom `src/` / `tests/` instead. Test dirs nested under a package dir (e.g. `scripts/tests/`) are also not found.

## Expected Behavior

- Every proposed Source dir and Focus dir value exists in the target project (`(root / value).is_dir()`), or is `.`. This covers template defaults **and** detected candidates (pyproject / tsconfig / Cargo), which today are not existence-checked (e.g. tsconfig `include: ["**/*.ts"]` yields the phantom candidate `**/`).
- Root-level layouts resolve to `.` with provenance `inferred`: e.g. top-level `*.py` modules / `main.go` / `index.ts` with no package subdir → Source dir `.`; `test_*.py` / `*_test.go` / `*.test.ts` at root → Test dir `.`.
- Test-dir detection also finds nested conventional dirs (e.g. `<src>/tests/`, `scripts/tests/`), not just top-level `tests/`/`test/`.
- When no existing Source dir can be determined, the value is `.` with provenance `default` and evidence saying so — never empty (see Codebase Research Findings: empty re-adopts the template path) and never a template path that doesn't exist.
- **Test dir exception — no tests anywhere**: when the project contains no test dir and no test files at all, Test dir is `tests/` (provenance `default`, evidence `"no tests found; conventional location for new tests"`) even though it does not exist. Rationale: `test_dir` is a *write target* — the spike skill (`TEST_DIR=$(ll-config get project.test_dir)`) and TDD-mode implementation create new tests there, and `.` would scatter them across the repo root. `.` is proposed only when root-level test files actually exist.
- Focus dirs are built only from dirs that exist; template `focus_dirs` entries are filtered by existence. When Source dir is `.`, focus dirs are exactly `["."]` (no redundant `tests/` entry).
- Ambiguity prompts offer only existing candidates.

## Motivation

A phantom `src_dir`/`test_dir`/`focus_dirs` silently misdirects `scan-codebase`, `find-dead-code`, test commands (`mypy src/`), and other consumers in the target project, and the user must notice and correct it in the TUI/config by hand.

## Proposed Solution

Add an existence filter in `little_loops.init.introspect` and route every template-default fallback through it:

- `_existing_dir(root, value)` returns `value` only if `(root / value).is_dir()` (or `value` is `.`), else `None`.
- `_introspect_src_dir`:
  - Pass every collected candidate (package-marker, pyproject, tsconfig, Cargo) through `_existing_dir` **before** counting, so a nonexistent candidate can neither be adopted nor appear in an `Ambiguity`. Detection logic itself is unchanged.
  - On zero surviving candidates or ambiguity, use the filtered template default. If that is `None`, call `_detect_root_layout`: `True` → `.` with provenance `inferred`; `False` → `.` with provenance `default` and evidence `"no existing src dir detected"`.
  - **Why `_detect_root_layout` exists even though both branches yield `.`**: it only changes provenance/evidence, and that is deliberate — `inferred` values are shown to the user (`provenance_rows`, TUI hints, `_print_introspection_summary` all hide `default`), and `_introspect_focus_dirs` adopts src_dir only when `provenance != "default"` (`introspect.py:740`). A detected flat layout is a real finding; an empty repo falling back to `.` is not.
  - `_detect_root_layout` ignores common root tooling files that appear in src-layout projects too (`setup.py`, `conftest.py`, `noxfile.py`, `tasks.py`, `fabfile.py`), so they alone do not count as a root layout.
- `_introspect_test_dir(root, src_dir, default_value)`, in order:
  1. top-level `tests/` / `test/`;
  2. `_find_nested_test_dir(root, src_dir)` — see below;
  3. root-level `test_*.py` / `*_test.py` / `*_test.go` / `*.test.ts` / `*.test.js` → `.` (provenance `inferred`);
  4. template default only if `_existing_dir` accepts it;
  5. otherwise `tests/` (provenance `default`, evidence `"no tests found; conventional location for new tests"`) — the one deliberate nonexistent value; see Expected Behavior.
- `_find_nested_test_dir(root, src_dir)`:
  - Prefer `<src_dir>/tests/` then `<src_dir>/test/` when `src_dir` is a real subdir (not `.`).
  - Otherwise probe `*/tests/` and `*/test/` one level deep; return the match only if exactly one exists. Several matches (e.g. `frontend/test/` + `backend/tests/`) → `None`, falling through to step 3.
  - Skip `_SKIP_DIRS` **and any dot-prefixed dir** (`.claude/`, `.tox/`, `.worktrees/`, `.mypy_cache/` — `_SKIP_DIRS` covers none of these).
  - Require at least one test file inside the dir (`test_*.py`, `*_test.py`, `conftest.py`, `*_test.go`, `*.test.*`, `*.spec.*`), so fixture/data dirs named `test/` are not picked up.
- `_introspect_focus_dirs(root, src_dir_iv, test_dir_iv, default_focus_dirs)`:
  - **Reorder `introspect()`** so `project.test_dir` is computed *before* `scan.focus_dirs` and passed in; delete the duplicated `("tests/", "test/")` `is_dir()` probe in `_introspect_focus_dirs` and use `test_dir_iv` instead (only when its provenance is not `default`, i.e. it exists). This also lets a nested test dir reach focus dirs when src_dir is ambiguous.
  - When adopted src_dir is `.`, return exactly `["."]` — adding `tests/` would be redundant. (The `name.startswith(fd)` de-dup does **not** swallow `tests/` under `.` — `"tests/".startswith(".")` is `False` — so redundancy, not suppression, is the real hazard.)
  - Keep the existing prefix de-dup for a test dir nested under src_dir (e.g. `scripts/tests/` under `scripts/`).
  - Nothing inferred → filter template `focus_dirs` by existence; fall back to `["."]` if none survive (never an empty list — see `core.py:347` / `tui.py:1099` truthiness guards).
- Evidence strings `"adopted src_dir"` and `"adopted src_dir + detected tests/ directory"` must stay verbatim (asserted by `TestFocusDirsEvidence`); build the test-dir evidence part from `test_dir_iv.value` so a top-level `tests/` still yields `"detected tests/ directory"`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Conventions in force** (evidence: `introspect.py` whole-module read; `scripts/tests/test_init_introspect.py`):
  - Every derived value is a frozen `IntrospectedValue(value, provenance, evidence)` with `provenance` in `declared|inferred|default`; fallbacks use `"default"` plus a short fixed-phrase evidence string. Helpers are private `_snake_case`, `root: Path` first, `IntrospectedValue | None` / `str | None` / `set[str]` returns.
  - Directory values carry a trailing slash (`src/`, `tests/`); the sole exception is the `"tests"` default. No existing code emits `.` as a value (it appears only inside command strings), so the spelling of the root value (`.` vs `./`) is a new decision — the go template already uses `.`, which favors `.`.
  - Skip-dir handling: `_SKIP_DIRS` / `_SRC_CANDIDATE_SKIP_DIRS` are the module's ignore sets and `_find_manifest` (`root.glob("*/<file>")` filtered by `_SKIP_DIRS`) is the existing one-level-nested probe; a nested test-dir probe should honor the same ignore set. `detect.py` keeps a separate, differing `_EXCLUDE_DIRS` (contested — no shared constant exists).
  - The `("tests/", "test/")` literal and `is_dir()` probe are duplicated in `_introspect_focus_dirs` and `_introspect_test_dir`; no shared existence-filter helper exists.
- **Existing tests that assert the behavior this issue removes** (must be revised, not merely kept passing): `TestSrcDirDetection.test_no_package_marker_keeps_default` (expects `python_template.data["project"]["src_dir"]` i.e. `src/` in an empty tmp dir), `TestTestDirDetection.test_no_test_dir_keeps_default` (expects `"tests"` in an empty dir), `TestFocusDirsDetection.test_defaults_when_nothing_detected` (expects template `["src/","tests/"]` in an empty dir). Ambiguity test `test_two_top_level_package_dirs_ambiguous_keeps_default` expects `provenance == "default"` with candidates `{"scripts/","lib/"}` and must keep passing. Evidence strings `"adopted src_dir"` and `"adopted src_dir + detected tests/ directory"` are asserted verbatim by `TestFocusDirsEvidence` and must be preserved.
- **Resolved — "left empty" vs `.`**: `build_config` treats empty as "keep template value", re-introducing the phantom dir, so `.` is the no-detection result (Expected Behavior updated). Spelling is `.` (not `./`): the go template already ships `.`, and consumers `rstrip("/")` either way.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **AC #1's tsconfig example is now resolved, not open**: `_tsconfig_src_candidate` (`introspect.py:661`) already returns `.` for `include: ["**/*.ts"]` — the glob-char check `if any(ch in first for ch in "*?["): return "."` was added by BUG-3631's commit `85696dc57` and is asserted by `test_tsconfig_include_glob_returns_root` (`test_init_introspect.py:286`). The specific phantom-candidate string (`**/`) the AC names no longer arises from this code path. The general requirement is unaffected: `_introspect_src_dir` still adds `_pyproject_src_candidate`/`_tsconfig_src_candidate` output straight into `candidates` with no existence check, so a manifest naming a real-looking but nonexistent nested dir (e.g. `rootDir: "app"` with no `app/`) still produces an unfiltered candidate today. `_existing_dir` remains necessary for that case and for every template-default fallback, none of which BUG-3631 touched.
- **Convention confirmation — helper placement**: `_existing_dir`/`_detect_root_layout`/`_find_nested_test_dir` are each called only from `_introspect_src_dir`/`_introspect_test_dir`/`_introspect_focus_dirs`, all within `introspect.py` — matching this module's existing precedent for helpers used only by its own `_introspect_*` functions (e.g. `_iter_candidate_dirs`, `_iter_top_level_package_dirs`, `_read_text`), which stay private module-level functions rather than being extracted to a new leaf module. `canonical_dir`/`dir_prefix` (`config/dirs.py`) were extracted to a separate module only because of a real circular-import constraint between `config/core.py` and `config/features.py` — a condition that does not apply here, so keeping the three new helpers inline in `introspect.py` (as already planned) is the codebase's established choice, not merely one of two equally-valid options.
- **Skip-set composition idiom for `_find_nested_test_dir`**: `_SRC_CANDIDATE_SKIP_DIRS = _SKIP_DIRS | {"tests", "test"}` (`introspect.py:618`) is the existing pattern for deriving a specialized skip-set from the module's base `_SKIP_DIRS`; a nested-test-dir skip-set can follow the same `_SKIP_DIRS | {...}` composition rather than a new literal.

## Integration Map

- `scripts/little_loops/init/introspect.py` — `introspect` (reorder: test_dir before focus_dirs), `_introspect_src_dir`, `_introspect_test_dir`, `_introspect_focus_dirs`; new `_existing_dir`, `_detect_root_layout`, `_find_nested_test_dir`
- `scripts/little_loops/init/cli.py:531` — `_print_introspection_summary` wording
- `scripts/little_loops/init/proposal.py`, `core.py`, `tui.py`, `summary.py` — verify `.` round-trip (modify only if a test shows a break)
- **Moved to BUG-3631 (blocks this issue)**: `.`-hostile runtime consumers — `codegraph.py:121` `_is_scan_relevant`, `worker_pool.py:1523` leak detection, `decisions.py:652` export glob, plus `ll-init` introspection emitting `./` / `/` / `**/` for root declarations (`commands/manage-release.md` was later split to BUG-3635, which does not block this issue). These are pre-existing bugs for Go projects (`go.json` ships `src_dir: "."`).
- **Checked, no change needed**: `codegraph.py:234` `_dotted_candidates` (with `.` the prefix strip never applies; returns `[dotted]`, already correct) and `commands/run-tests.md:99` (`^.` matches every changed file, which is correct when src_dir is the whole repo).
- Template defaults under `scripts/little_loops/templates/` — read-only; filtered at read time, contents unchanged

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Fallback sites (all in `scripts/little_loops/init/introspect.py`)**: `_introspect_src_dir(root, py_data, default_value) -> tuple[IntrospectedValue, Ambiguity | None]` returns the unchecked template default on both the zero-candidate and the ambiguity branch (on ambiguity the candidates are surfaced only via `Ambiguity`, never adopted). `_introspect_focus_dirs(root, src_dir_iv, default_focus_dirs)` returns `list(default_focus_dirs)` unchecked when nothing was inferred. `_introspect_test_dir(root, default_value)` probes only top-level `tests/`, `test/`; `introspect()` supplies `default_test_dir = project.get("test_dir") or "tests"` and no bundled template defines `project.test_dir`, so the fallback is always the literal `"tests"` (no trailing slash).
- **Callers**: `introspect()` is the sole caller of the three helpers (`introspect.py:152`, `:185`, `:190`; confirmed by grep); `proposal.py:build_proposal` is the sole production caller of `introspect()`.
- **Template defaults that would be filtered**: `project.src_dir` is `src/` in generic/python-generic/typescript/javascript/rust/dotnet, `src/main/java/` in java-maven/java-gradle, and `.` in go (a valid value that must survive filtering). `scan.focus_dirs` lists include non-conventional entries (`lib/`, `cmd/`, `pkg/`, `internal/`, `benches/`, `src/test/java/`) — every one is subject to the existence filter.
- **Unverified candidates**: pyproject (`_pyproject_src_candidate`), tsconfig (`_tsconfig_src_candidate`) and Cargo candidates are not existence-checked today; the issue's Scope Boundaries leave them unchanged, so "no proposal contains an absent dir" holds for defaults only unless that boundary is revisited.
- **Downstream round-trip constraint**: `core.py:build_config` and `tui.py:build_config` skip falsy `src_dir`/`test_dir`/`scan_focus_dirs` choices, so an *empty* value silently re-adopts the template's (possibly phantom) path; `tui.py:_answers_from_proposal` `_seed()` likewise falls back to `"src/"`/`"tests"` on a falsy choice, and seeds focus dirs to `["src/"]` when the choice is empty. `.` is truthy and passes through `summary.py:summary_rows` ("Source dir" row) unchanged. Consequence: the "left empty" alternative in Expected Behavior cannot round-trip; only `.` (or an existing dir) does.
- **Focus-dir interaction with `.`** (corrected in review): `_introspect_focus_dirs` de-duplicates test dirs with `name.startswith(fd)`; `"tests/".startswith(".")` is `False`, so an adopted `.` does **not** suppress `tests/`. The actual hazard is the opposite — `[".", "tests/"]` is redundant — so focus dirs are exactly `["."]` when src_dir is `.`.
- **Downstream consumers of provenance**: `proposal.py` (`provenance_rows` hides default-provenance rows; `scan.focus_dirs` row shown only when non-default), `tui.py` (hints suppressed for `default`), `cli.py:_print_introspection_summary` (skips default values, prints ambiguity candidates). Emitting `.` with provenance `default` therefore stays hidden from the user by design.
- **`mypy {src_dir or '.'}`** in `_python_command` receives `src_dir_iv.value`; a `.` value yields `mypy .`, an empty string also yields `mypy .`.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **BUG-3631 (former blocker) is now done**: commit `85696dc57` ("fix(config): canonicalize root dir spellings so '.' works everywhere", 2026-09-27) landed a new leaf module `little_loops/config/dirs.py` with `canonical_dir(value) -> str` and `dir_prefix(value) -> str` (root spellings `.`, `./`, `.//`, `/` normalize to `.`; stdlib-only, no `little_loops` imports, to avoid a circular import between `config/core.py` and `config/features.py`). `blocked_by: BUG-3631` in this issue's frontmatter now points at a `done` issue — the edge is resolved per the status-based deferral rule, though the frontmatter field itself is not this pass's to remove.
- **`introspect.py` already reuses `canonical_dir`**: imported at `introspect.py:23` and called inside `_pyproject_src_candidate` (`:649`) and `_tsconfig_src_candidate` (`:671`) to normalize a `where`/`rootDir` root spelling to `.` before this issue's own existence-filter work begins. The planned `_existing_dir` helper calling `canonical_dir(value)` first, then short-circuiting on `"."`, else checking `.is_dir()`, follows the established in-module precedent (same import already present) rather than introducing a new pattern.
- **`config/core.py:238-244` (`ProjectConfig.from_dict`) and `config/features.py` (`ScanConfig.from_dict`) already canonicalize `src_dir`/`test_dir`/`focus_dirs` at config-*load* time** via the same `canonical_dir()` — an existing downstream safety net for the `.` round-trip, independent of `init/proposal.py`/`init/core.py`/`init/tui.py`. Confirmed by direct file search: none of those three `init/` files import `canonical_dir` or `dir_prefix`.
- **Anchor drift since this issue's last refine pass** (confirmed via `ll-code` + direct grep against HEAD): `_introspect_src_dir` is now at `introspect.py:693` (issue cites `:686`), `_introspect_focus_dirs` at `:742` (cites `:735`), `_introspect_test_dir` at `:768` (cites `:761`); `introspect()`'s three call sites are now `:153`/`:186`/`:191` (cites `:152`/`:185`/`:190`). Call order itself is unchanged: src_dir -> commands loop -> focus_dirs -> test_dir, confirming the reorder this issue proposes is still needed.
- **Gap the BUG-3631 fix left standing**: `_pyproject_src_candidate`'s hatch `include`/`packages` branch (`introspect.py:651-657`) does not call `canonical_dir` — only the `setuptools.where` branch does. A hatch-declared root-ish spelling is not yet normalized; existence-filtering it stays in this issue's scope (filter-only, detection unchanged).
- **Existing dedicated test module for the reused helper**: `scripts/tests/test_config.py` (`test_canonical_dir_table`, `test_dir_prefix_root_is_empty`, `test_dir_prefix_non_root`, `test_dir_prefix_empty_raises`) covers `canonical_dir`/`dir_prefix` directly — a model for this issue's own root-spelling test cases if `_existing_dir` needs equivalent coverage.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/init/__init__.py` — re-exports `IntrospectedValue`, `introspect`, `IntrospectResult`, `Ambiguity` (public symbols; shape unchanged, values change)
- `scripts/little_loops/init/cli.py:531` `_print_introspection_summary` — prints "kept template default — N candidates found"; wording becomes inaccurate if the ambiguity fallback is now a filtered default / `.`
- `scripts/little_loops/init/core.py:347` `build_config` — `if choices.get("scan_focus_dirs")` skips an empty list and re-adopts the unfiltered template `focus_dirs`; the `["."]` fallback in `_introspect_focus_dirs` is what keeps the filter effective
- `scripts/little_loops/init/tui.py:1099` `build_config` wrapper — same `if scan_focus_dirs:` truthiness guard
- `scripts/little_loops/init/proposal.py:296-312` `build_proposal` — existing-config branch pins `src_dir`/`test_dir`/`scan.focus_dirs` with provenance `existing`, so a re-init keeps prior (possibly phantom) values; existence filtering applies to fresh introspection only
- `scripts/little_loops/init/proposal.py:122` plan-JSON serializer — docstring promises `values`/`ambiguities` shapes stay stable for `skills/init/SKILL.md`; new evidence strings must not alter the shape
- **Runtime consumers of a `.` value** — _review 2026-09-27: the broken ones are now tracked in BUG-3631 (blocks this issue); `_dotted_candidates` and `run-tests.md:99` were checked and need no change. List kept for reference._ (read what init writes; `go.json` already ships `src_dir: "."` so `.` is not new, but the Python/JS/generic paths would now emit it):
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

- `_existing_dir(root: Path, value: str) -> str | None` — `value` if `(root / value).is_dir()` or `value == "."`, else `None`
- `_detect_root_layout(root: Path) -> bool` — `True` when root holds source modules / entry files with no package subdir; drives provenance only (value is `.` either way)
- `_find_nested_test_dir(root: Path, src_dir: str) -> str | None` — `<src_dir>/tests|test/` first, else the sole one-level `*/tests|test/` containing test files; skips `_SKIP_DIRS` and dot-dirs
- `_introspect_test_dir(root: Path, src_dir: str, default_value: str) -> IntrospectedValue` — gains `src_dir`
- `_introspect_focus_dirs(root: Path, src_dir_iv: IntrospectedValue, test_dir_iv: IntrospectedValue, default_focus_dirs: list[str]) -> IntrospectedValue` — gains `test_dir_iv`

### Call Path

`introspect` -> `_introspect_src_dir` -> `_existing_dir`; `_introspect_src_dir` -> `_detect_root_layout`; `introspect` -> `_introspect_test_dir` -> `_find_nested_test_dir`; `_introspect_test_dir` -> `_existing_dir`; `introspect` -> `_introspect_focus_dirs` -> `_existing_dir`

`introspect()` order changes: src_dir → commands → test_dir → focus_dirs (test_dir moves ahead of focus_dirs and is passed in).

## Scope Boundaries

- **In scope**: existence filtering of src/test/focus dir defaults **and of detected src_dir candidates** (filter only — detection logic unchanged), root-layout (`.`) detection, nested test-dir probing, the `introspect()` reorder in `little_loops.init.introspect`, and round-tripping `.` through the init proposal/TUI/core.
- **Out of scope**:
  - Changing how package-marker/pyproject/tsconfig/Cargo candidates are *detected* (they are only existence-filtered).
  - Detecting non-conventional test dir names (`__tests__/`, `spec/`).
  - Changing project-type template contents.
  - Non-dir fields (build/lint/test commands), beyond keeping the `{src_dir or '.'}` derivation sane.
  - Fixing `.`-hostile runtime consumers — **BUG-3631**, which blocks this issue.
  - **Re-init of an existing config**: `proposal.py:build_proposal` pins existing `src_dir`/`test_dir`/`scan.focus_dirs` with provenance `existing`, so a phantom value already in `.ll/ll-config.json` survives a plain re-run of `ll-init`. Only fresh introspection (new install or `--force`) is existence-filtered; revalidating stored values is not part of this issue.

## Implementation Steps

0. BUG-3631 is done (commit `85696dc57`) — this step's precondition is already satisfied; proceed directly to Step 1.
1. Add `_existing_dir` in `little_loops.init.introspect`. In `_introspect_src_dir`, filter the collected candidate set through it before the `len(candidates)` checks, and apply it to the template default on the zero-candidate / ambiguity branches. Source dir with no surviving value → `.` (never empty — `build_config` in `core.py`/`tui.py` treats empty as "keep template value" and would re-adopt the phantom dir).
2. Add `_detect_root_layout` (ignoring `setup.py`/`conftest.py`/`noxfile.py`/`tasks.py`/`fabfile.py`); it selects provenance `inferred` vs `default` for the `.` result.
3. Add `_find_nested_test_dir(root, src_dir)` — `<src_dir>/tests|test/` first, else the sole one-level match containing test files; skip `_SKIP_DIRS` and dot-prefixed dirs.
4. Extend `_introspect_test_dir(root, src_dir, default_value)` with the probe order in Proposed Solution; final fallback is `tests/` (provenance `default`, evidence `"no tests found; conventional location for new tests"`), not `.`.
5. Reorder `introspect()`: compute test_dir before focus_dirs and pass `test_dir_iv` to `_introspect_focus_dirs`; drop its duplicated `("tests/", "test/")` probe. Return exactly `["."]` when src_dir is `.`; filter template `focus_dirs` by existence; fall back to `["."]`, never an empty list. Keep the `"adopted src_dir"` / `"... + detected tests/ directory"` evidence strings verbatim.
6. Round-trip `.` through `proposal.py` / `tui.py` / `core.py` (`choices["src_dir"]`, `scan_focus_dirs`) and `summary_rows`, keeping `mypy {src_dir or '.'}` (`introspect.py:302`) sane. Verify `auto-refine-and-implement.yaml:626,851` pass-through of `.` (the other consumers are in BUG-3631).
7. Update `cli.py:531` `_print_introspection_summary` wording ("kept template default") — on ambiguity the value is now the existence-filtered default or `.`.
8. Tests: rewrite the three phantom-default tests (`test_no_package_marker_keeps_default` → `.`, `test_no_test_dir_keeps_default` → `tests/` with the new evidence, `test_defaults_when_nothing_detected` → `["."]`) and the wiring-listed empty-dir tests. Add: flat-layout → `.` (inferred); root with only `setup.py`/`conftest.py` → `.` (default); tsconfig `include: ["**/*.ts"]` → no `**/` candidate; nested `scripts/tests/` detected; two nested test dirs → not adopted; test dir under `.claude/` ignored; template focus_dirs filtered by existence; src `.` → focus `["."]`; `.` round-trip.
9. Review `--force` / "template defaults" wording in the docs listed under `### Documentation`; re-run `ll-adapt` if any `skills/` file changes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Outcome: no `IntrospectedValue` from the three helpers holds a path absent from the target root (other than `.`, and the no-tests `tests/` test_dir exception); verified by a test per helper in `test_init_introspect.py` using `tmp_path` layouts.
- Outcome: the three tests listed under Proposed Solution → Codebase Research Findings that hard-code phantom defaults are rewritten to the new contract; `pytest scripts/tests/test_init_introspect.py scripts/tests/test_init_proposal.py scripts/tests/test_init_core.py scripts/tests/test_init_tui.py scripts/tests/test_init_skill_fixtures.py` passes.
- Outcome: `.` round-trips through `build_proposal` → `build_config` (`core.py` and `tui.py` variants) → `summary_rows`; verified by an added case alongside `test_init_core.py`/`test_init_proposal.py`.
- Outcome: go template (`src_dir: .`) and java templates (`src/main/java/`) still yield existing-dir results when those dirs exist; an integration check in `scripts/tests/integration/test_init_e2e.py` still passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- `.` spelling decided: `.`. `.`-hostile consumers (`codegraph.py:121`, `worker_pool.py:1523`, `decisions.py:652`) moved to BUG-3631 (blocker); `commands/manage-release.md` split further to BUG-3635 (non-blocking); `_dotted_candidates` and `run-tests.md:99` need no change. Still verify `auto-refine-and-implement.yaml:626,851` here.
- Update `cli.py:531` `_print_introspection_summary` wording ("kept template default") to match the new fallback
- Keep `core.py:347` / `tui.py:1099` truthiness guards safe by never returning an empty focus list (`["."]` fallback)
- Update the tests listed under `### Tests` (empty-dir assumptions in `test_init_introspect.py`, `test_init_audit_fixes.py`, `test_init_e2e.py`, `test_init_core.py`, `test_init_tui.py`) and add the new tests
- Review `--force` / "template defaults" wording in `docs/reference/CONFIGURATION.md`, `docs/guides/GETTING_STARTED.md`, `docs/reference/CLI.md`, `skills/init/SKILL.md`; run `ll-adapt` mirrors if any `skills/` file changes
- ENH-3612 is done; the `_introspect_src_dir` call already sits above the command loop (`introspect.py:152`) at HEAD — no coordination needed

## Impact

- **Priority**: P3 - phantom dirs misdirect downstream tooling but the user can correct them in the TUI/config
- **Effort**: Small - three new helpers and a call reorder in one module, plus tests (downstream consumer fixes split out to BUG-3631)
- **Risk**: Low - only changes fallback paths where detection was already inconclusive
- **Breaking Change**: No

## Acceptance Criteria

- [ ] On a fresh introspection, no `ll-init` proposal contains a Source or Focus dir absent from the target project; no `Ambiguity` lists an absent candidate (e.g. tsconfig `include: ["**/*.ts"]` produces no `**/`).
  > ⚠ Superseded — glob example fixed by BUG-3631, see Proposed Solution
- [ ] Test dir is never an absent path **except** `tests/` when the project has no test dir and no test files at all (provenance `default`, evidence `"no tests found; conventional location for new tests"`).
- [ ] Root-level source/test layouts are proposed as `.` with provenance `inferred`; an empty or tooling-only root (`setup.py`, `conftest.py`) yields src_dir `.` with provenance `default`.
- [ ] Nested test dirs (e.g. `scripts/tests/`) are detected; `<src_dir>/tests/` wins; two unrelated nested test dirs are not adopted; dot-prefixed dirs are never probed.
- [ ] Existing detection of src_dir candidates is unchanged whenever the candidate dir exists.
- [ ] Source dir never falls back to empty; the focus-dirs value is never an empty list (`["."]` fallback), so `core.py:347` / `tui.py:1099` truthiness guards never re-adopt a phantom template path.
- [ ] When src_dir is `.`, focus dirs are exactly `["."]`.
- [ ] `introspect()` computes test_dir before focus_dirs, and `_introspect_focus_dirs` has no duplicated `tests/`/`test/` probe; `TestFocusDirsEvidence` evidence strings unchanged.
- [ ] `.` round-trips proposal → `build_config` (`core.py` and `tui.py`) → `summary_rows` unchanged.
- [ ] Go (`src_dir: .`) and java (`src/main/java/`) template defaults still survive the filter when those dirs exist.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-26_

Verdict at time of check: **DIRECTIVE_DRIFT** (not corrected in this pass — fix is confined to Acceptance Criteria / Program Design, which `/ll:reconcile-issue` owns; the selected mechanism stands)

- **Claims verified**: all `path:line` anchors match HEAD — `_introspect_src_dir` (`introspect.py:686`), `_introspect_focus_dirs` (`:735`), `_introspect_test_dir` (`:761`), callers (`:152`, `:185`, `:190`), `default_test_dir` (`:189`), `mypy {src_dir or '.'}` (`:302`), `cli.py:531`, `core.py:347`, `tui.py:1090`, `codegraph.py:121`/`:234`, `decisions.py:652`; the four named existing tests exist; quoted `commands/manage-release.md` / `run-tests.md:99` / `skills/spike/SKILL.md:151` strings match. No files in the issue moved.
- **Decisions rules**: no active required rules — no violation. **Evidence quotes** (`ll-verify-evidence`): clean, 0 findings.
- **Proposal-vs-code consequence check (B6)**:
  - *AC coverage gap*: the four Acceptance Criteria cover only detection output. The Integration Map / Wiring Phase list `.`-hostile consumers (`codegraph.py` `_is_scan_relevant` / `_dotted_candidates`, `manage-release.md` no-separator concatenation, `run-tests.md:99` `^.` regex), the `.` round-trip through `build_config`/`tui.py`/`summary_rows`, and the `["."]` focus fallback that keeps the `core.py:347`/`tui.py:1090` truthiness guards effective — none has a corresponding AC. Add ACs for: `.` round-trips proposal → config → summary; `.`-consuming code paths behave correctly; empty focus list is never emitted.
  - *Program Design gap*: Call Path omits `_detect_root_layout` (named in Proposed Solution / Signatures); add `_introspect_src_dir -> _detect_root_layout` and `_introspect_test_dir -> _existing_dir`.
  - *Test-fixture invalidation*: already covered by the Tests section (three phantom-default tests + wiring-listed tests).
- **Graph**: provider=`codegraph` freshness=`stale` (not used to originate any verdict; direct Grep/Read confirmed all anchors).

Remaining: the AC and Call Path additions above. _(Addressed in the 2026-09-27 review: ACs cover round-trip, the `["."]` fallback and the non-empty guard; `.`-consumer ACs moved to BUG-3631; Call Path now includes `_detect_root_layout` and `_introspect_test_dir -> _existing_dir`.)_

_Added by `/ll:verify-issues` — 2026-09-27_

Verdict at time of check: **NEEDS_UPDATE** (one anchor had drifted; corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item).

- **Anchors re-verified against HEAD**: all `path:line` citations checked (`introspect.py:686/735/761/152/185/189/190/302`, `cli.py:531`, `core.py:347`, `codegraph.py:121/234`, `decisions.py:652`) match exactly, **except** `tui.py:1090` — the `if scan_focus_dirs:` truthiness guard now sits at `tui.py:1099` (9-line drift from unrelated edits above it in the file). Fixed in place at all four live citations (lines 77, 121, 229, 248 pre-edit); the historical `2026-09-26` Verification Notes entry above is left as-is (a record of that pass, not a live claim).
- **Dependencies**: `blocked_by: BUG-3631` remains **open** (unresolved) — matches the gap already recorded in the 2026-09-27 Confidence Check Notes; not re-flagged as new.
- **DEP_ISSUES (MISSING_BACKLINK, informational)**: BUG-3631 references this issue only under its `## Related` section ("Blocks ENH-3616 ...", `.issues/bugs/P3-BUG-3631-...md:213`), not a formal `## Blocks` heading. Not corrected here (out of scope for a single-issue verify pass to edit another issue file); flagging for awareness.
- **Evidence quotes** (`ll-verify-evidence --json`): clean, 0 findings. **Decisions log**: `.ll/decisions.d` present, query ran, 0 active required rules — no violation.
- **Graph**: provider=`codegraph` freshness=`stale` — not used to originate the anchor-drift finding; confirmed directly via `sed`/`grep` against HEAD.
- **ENH-3612 coordination note** (Wiring Phase): re-confirmed done (`status: done`); no action needed.

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Program Design Call Path still omits nothing material now; ENH-3612 coordination note is stale (completed) — re-read the `_introspect_src_dir` call site at HEAD before editing.

### Gaps to Address
- `blocked_by: BUG-3631` is unresolved (status: open). Implementation Step 0 requires it to land first so a `.` value is safe for codegraph, worker_pool and decisions export (manage-release moved to BUG-3635). Remedy: implement BUG-3631 first, or drop the `blocked_by` edge if `.` output is gated until it lands.

### Outcome Risk Factors
- Moderate cross-module depth: signature changes plus a call reorder in `introspect()` and `.` round-trip through proposal/core/tui/summary.
- Several existing tests assert phantom-default behavior and must be rewritten; docs and markdown edits have no automated validation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override)
**Outcome Confidence**: 64/100 → MODERATE

### Gaps to Address
- `blocked_by: BUG-3631` is still unresolved (status: open) — re-checked directly via `ll-issues show BUG-3631 --json`. Implementation Step 0 still requires it to land first. No change since the prior pass.

### Outcome Risk Factors
- Moderate cross-module depth: signature changes plus a call reorder in `introspect()` and `.` round-trip through proposal/core/tui/summary.
- Several existing tests assert phantom-default behavior and must be rewritten; docs and markdown edits have no automated validation.

## Session Log
- `/ll:refine-issue` - 2026-09-27T20:25:47 - `dd64463d-e434-4e56-8ab0-f62c72a4ecea.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:43:32 - `bf6e1e8c-2c0c-4865-99bf-f1fcae8fc265.jsonl`
- `/ll:verify-issues` - 2026-09-27T05:36:55 - `e18b63f4-fc4d-4093-b00f-89d5c0e394ec.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:14:52 - `0cc16b1e-d681-4781-832d-b9145e4dc4f5.jsonl`
- `/ll:confidence-check` - 2026-09-26T23:01:16 - `2dc3f1af-4938-467b-8164-481af936e116.jsonl`
- `/ll:reconcile-issue` - 2026-09-26T22:59:39 - `2140791c-2fb1-4f71-ba9c-43289547febe.jsonl`
- `/ll:verify-issues` - 2026-09-26T22:58:20 - `3fd33dbe-1f15-463a-a944-4883dfb19b30.jsonl`
- `/ll:wire-issue` - 2026-09-26T22:54:01 - `f54e5d1b-c94c-4496-a128-5bf9edc4c3c0.jsonl`
- `/ll:refine-issue` - 2026-09-26T22:50:46 - `4b810b7f-5ecd-426c-a2b1-3149be2063f7.jsonl`
- `/ll:format-issue` - 2026-09-26T22:33:50 - `f16b1c3d-13dc-4e2c-9a78-1582bd68929b.jsonl`
- `/ll:capture-issue` - 2026-09-26T22:32:37 - `9b05118c-8f95-46d6-ac91-f7fa688ef1a5.jsonl`
