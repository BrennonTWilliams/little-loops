---
id: ENH-3616
type: ENH
title: 'll-init: detect src/test/focus dirs from real layout, never propose nonexistent
  dirs'
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T22:32:30Z'
completed_at: '2026-09-28T03:41:21Z'
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 95
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

- Every proposed Source dir and Focus dir value exists in the target project (`(root / value).is_dir()`), or is `.`. This covers template defaults **and** detected candidates (pyproject / tsconfig / Cargo), which today are not existence-checked (e.g. a hatch `packages` entry or tsconfig `rootDir: "app"` naming a dir that does not exist).
- Root-level layouts resolve to `.` with provenance `inferred`: e.g. top-level `*.py` modules / `main.go` / `index.ts` with no package subdir → Source dir `.`; `test_*.py` / `*_test.go` / `*.test.ts` at root → Test dir `.`. This includes Go, whose template default is already `.` — the provenance still comes from root-layout detection, not from the template.
- Test-dir detection also finds nested conventional dirs (e.g. `<src>/tests/`, `scripts/tests/`, Maven/Gradle `src/test/java/`), not just top-level `tests/`/`test/`.
- Co-located tests are detected — Go `*_test.go` files beside sources (e.g. under `pkg/`) and JS/TS `*.test.ts` files under `src/`: Test dir is the Source dir value (or `.`), provenance `inferred`.
- When no existing Source dir can be determined, the value is `.` with provenance `default` and evidence saying so — never empty (see Codebase Research Findings: empty re-adopts the template path) and never a template path that doesn't exist.
- **Test dir exception — no tests anywhere**: when a bounded recursive search finds no test dir and no test files at all, Test dir is `tests/` (provenance `default`, evidence `"no test files found; conventional location for new tests"`) even though it does not exist. Rationale: `test_dir` is a *write target* — the spike skill (`TEST_DIR=$(ll-config get project.test_dir)`) and TDD-mode implementation create new tests there, and `.` would scatter them across the repo root. `.` is proposed only when root-level (or root-scoped co-located) test files actually exist.
- Focus dirs are built only from dirs that exist; template `focus_dirs` entries are filtered by existence. When the final Source dir value is `.` (any provenance), focus dirs are exactly `["."]` (no redundant `tests/` entry). Focus dirs never consist of test dirs alone — a list with no non-test entry becomes `["."]`, so scans never skip source code.
- Ambiguity prompts offer only existing candidates.

## Motivation

A phantom `src_dir`/`test_dir`/`focus_dirs` silently misdirects `scan-codebase`, `find-dead-code`, test commands (`mypy src/`), and other consumers in the target project, and the user must notice and correct it in the TUI/config by hand.

## Proposed Solution

Add an existence filter in `little_loops.init.introspect` and route every template-default fallback through it:

- `_existing_dir(root, value)` calls `canonical_dir(value)` first; returns `.` for `.`; returns `None` for an absolute value or one containing a `..` part (`root / "/abs"` resolves outside the root); otherwise returns the value only if `(root / value).is_dir()`, else `None`.
- `_TEST_FILE_GLOBS` — one module constant used by every test-file check: `test_*.py`, `*_test.py`, `*_test.go`, `*.test.*`, `*.spec.*`, `*Test.java`, `*Tests.java`. `conftest.py` counts as a test-file marker **only inside a candidate test dir** (`_find_nested_test_dir`), never at the root or in the co-located search — src-layout projects routinely keep a root `conftest.py`.
- `_has_test_files(root, rel_dir, *, allow_conftest=False)` — bounded recursive search (max depth 4 below `rel_dir`) for a file matching `_TEST_FILE_GLOBS`; prunes `_SKIP_DIRS` and dot-prefixed dirs; short-circuits on the first hit. Shared by the nested-dir check and the co-located search so both use the same file set and the same pruning.
- `_introspect_src_dir`:
  - Pass every collected candidate (package-marker, pyproject, tsconfig, Cargo) through `_existing_dir` **before** counting, so a nonexistent candidate can neither be adopted nor appear in an `Ambiguity`. Detection logic itself is unchanged.
  - **Ambiguity** (≥2 surviving candidates): value is the filtered template default, or `.` if that is `None`; provenance stays `default` (the existing ambiguity test asserts it); `_detect_root_layout` is not consulted — package subdirs exist, so it is not a root layout.
  - **Zero surviving candidates**: take the filtered template default. If it is a real subdir (e.g. java `src/main/java/` that exists), return it with provenance `default` as today. If it is `None` **or `.`** (the go template ships `.`, which `_existing_dir` always accepts), the value is `.` and `_detect_root_layout` picks the provenance: `True` → `inferred`, evidence `"root-level source files"`; `False` → `default`, evidence `"no existing src dir detected"`. Without the `.` case a flat Go repo would always get `default` and stay hidden from the user.
  - **Why `_detect_root_layout` exists even though both branches yield `.`**: it only changes provenance/evidence, and that is deliberate — `inferred` values are shown to the user (`provenance_rows`, TUI hints, `_print_introspection_summary` all hide `default`), and `_introspect_focus_dirs` adopts src_dir only when `provenance != "default"`. A detected flat layout is a real finding; an empty repo falling back to `.` is not.
- `_detect_root_layout(root)` — `True` when the root holds at least one non-ignored file with extension `.py`, `.go`, `.ts`, `.js`, `.mjs`, or `.cjs`. Ignored (they appear in src-layout projects too, so they alone do not make a root layout):
  - Python tooling: `setup.py`, `conftest.py`, `noxfile.py`, `tasks.py`, `fabfile.py`;
  - JS tooling: `*.config.{js,ts,mjs,cjs}` (vite/jest/eslint/webpack/babel …), `gulpfile.js`, `Gruntfile.js`;
  - every dotfile (`.eslintrc.js`, …);
  - files matching `_TEST_FILE_GLOBS` (tests are not sources).
- `_introspect_test_dir(root, src_dir, default_value)`, in order:
  1. top-level `tests/` / `test/` (no test-file requirement — unchanged behavior);
  2. `_find_nested_test_dir(root, src_dir)` — see below;
  3. root-level files matching `_TEST_FILE_GLOBS` (no `conftest.py`) → `.` (provenance `inferred`, evidence `"root-level test files"`);
  4. co-located tests: `_has_test_files(root, src_dir)` when `src_dir` is a real subdir → `src_dir` (provenance `inferred`, evidence `"co-located test files under <src_dir>"`); else `_has_test_files(root, ".")` → `.` (evidence `"co-located test files"`). Covers Go `*_test.go` files beside sources (e.g. under `pkg/`) and JS/TS `*.test.ts` files under `src/`, where new tests belong beside the code;
  5. template default only if `_existing_dir` accepts it;
  6. otherwise `tests/` (provenance `default`, evidence `"no test files found; conventional location for new tests"`) — the one deliberate nonexistent value; step 4's recursive search makes the "no test files" claim true. See Expected Behavior.
- `_find_nested_test_dir(root, src_dir)`:
  - Prefer `<src_dir>/tests/` then `<src_dir>/test/` when `src_dir` is a real subdir (not `.`). These are strong signals and need no test-file check.
  - Then `src/test/java/` when it exists (the Maven/Gradle standard layout; the java templates already list it in `focus_dirs`). Without this the one-level probe would return `src/test/` instead.
  - Otherwise probe `*/tests/` and `*/test/` one level deep, keeping only dirs where `_has_test_files(root, d, allow_conftest=True)` is true (so fixture/data dirs named `test/` are not picked up); return the match only if exactly one survives. Several matches (e.g. `frontend/test/` + `backend/tests/`) → `None`, falling through to step 3.
  - Skip `_SKIP_DIRS` **and any dot-prefixed dir** (`.claude/`, `.tox/`, `.worktrees/`, `.mypy_cache/` — `_SKIP_DIRS` covers none of these).
- `_introspect_focus_dirs(root, src_dir_iv, test_dir_iv, default_focus_dirs)`:
  - **Reorder `introspect()`** so `project.test_dir` is computed *before* `scan.focus_dirs` and passed in; delete the duplicated `("tests/", "test/")` `is_dir()` probe in `_introspect_focus_dirs` and use `test_dir_iv` instead (only when its provenance is not `default`, i.e. it exists).
  - Rules, in order:
    1. **Final src_dir value is `.`** (any provenance, including the go template default and the ambiguity/no-detection fallback) → exactly `["."]`, provenance mirrors src_dir (`inferred` → evidence `"adopted src_dir"`; `default` → `"no existing src dir detected"`). Adding `tests/` would be redundant. (The `name.startswith(fd)` de-dup does **not** swallow `tests/` under `.` — `"tests/".startswith(".")` is `False` — so this rule must be explicit.)
    2. **src_dir adopted** (provenance not `default`) → `[src_dir]` plus the test dir when it is inferred, not `.`, and not already under src_dir (use `dir_prefix` for the prefix check; e.g. `scripts/tests/` under `scripts/` is dropped).
    3. **src_dir not adopted** (ambiguous or a surviving template default such as java `src/main/java/`) → template `focus_dirs` filtered by `_existing_dir`, plus the inferred test dir if not already covered. Provenance `default` / evidence `"template default (existing dirs only)"` when only template dirs remain; `inferred` when the test dir was added.
  - **Test-dir-only guard**: after the rules above, if no entry is a non-test dir (every entry equals the chosen test dir or has a `tests`/`test` path part — `src/test/java/` counts as test), return `["."]` instead. This closes the hole where an unadopted src_dir plus a detected `tests/` or nested `scripts/tests/` produced `["tests/"]` alone (today's code already does this for src-default + `tests/`; the python-generic template's `["src/", "tests/"]` filtered by existence would do the same) and scans silently skipped all source.
  - Never an empty list — see `core.py:347` / `tui.py:1099` truthiness guards.
- Evidence strings `"adopted src_dir"` and `"adopted src_dir + detected tests/ directory"` must stay verbatim (asserted by `TestFocusDirsEvidence`); build the test-dir evidence part from `test_dir_iv.value` so a top-level `tests/` still yields `"detected tests/ directory"`.
- Update the `introspect()` docstring ("falling back to *template* defaults") to say fallbacks are existence-filtered and end at `.` / `tests/`.

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
- **Moved to BUG-3631 (done, commit `85696dc57`)**: `.`-hostile runtime consumers — `codegraph.py:121` `_is_scan_relevant`, `worker_pool.py:1523` leak detection, `decisions.py:652` export glob, plus `ll-init` introspection emitting `./` / `/` / `**/` for root declarations (`commands/manage-release.md` was later split to BUG-3635, which does not block this issue). These were pre-existing bugs for Go projects (`go.json` ships `src_dir: "."`).
- **Checked, no change needed**: `codegraph.py:234` `_dotted_candidates` (with `.` the prefix strip never applies; returns `[dotted]`, already correct) and `commands/run-tests.md:99` (`^.` matches every changed file, which is correct when src_dir is the whole repo).
- Template defaults under `scripts/little_loops/templates/` — read-only; filtered at read time, contents unchanged

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- **Fallback sites (all in `scripts/little_loops/init/introspect.py`)**: `_introspect_src_dir(root, py_data, default_value) -> tuple[IntrospectedValue, Ambiguity | None]` returns the unchecked template default on both the zero-candidate and the ambiguity branch (on ambiguity the candidates are surfaced only via `Ambiguity`, never adopted). `_introspect_focus_dirs(root, src_dir_iv, default_focus_dirs)` returns `list(default_focus_dirs)` unchecked when nothing was inferred. `_introspect_test_dir(root, default_value)` probes only top-level `tests/`, `test/`; `introspect()` supplies `default_test_dir = project.get("test_dir") or "tests"` and no bundled template defines `project.test_dir`, so the fallback is always the literal `"tests"` (no trailing slash).
- **Callers**: `introspect()` is the sole caller of the three helpers (`introspect.py:152`, `:185`, `:190`; confirmed by grep); `proposal.py:build_proposal` is the sole production caller of `introspect()`.
- **Template defaults that would be filtered**: `project.src_dir` is `src/` in generic/python-generic/typescript/javascript/rust/dotnet, `src/main/java/` in java-maven/java-gradle, and `.` in go (a valid value that must survive filtering). `scan.focus_dirs` lists include non-conventional entries (`lib/`, `cmd/`, `pkg/`, `internal/`, `benches/`, `src/test/java/`) — every one is subject to the existence filter.
- **Unverified candidates**: pyproject (`_pyproject_src_candidate`), tsconfig (`_tsconfig_src_candidate`) and Cargo candidates are not existence-checked today. _(Superseded: Scope Boundaries now put existence-filtering of these candidates in scope — filter only, detection unchanged.)_
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

_Wiring pass added by `/ll:wire-issue` — 2026-09-27:_

- ~~`scripts/little_loops/init/cli.py:422-469` `_warn_config_drift`~~ — _checked 2026-09-27 review, no change needed_: it skips every value whose provenance is not `declared`, and the dir fields are only ever `inferred`/`default`.
- `scripts/little_loops/init/cli.py:636,638` `_render_headless_summary` — imports and calls `summary.py::summary_rows`; headless-mode consumer not previously listed under `summary.py`'s "verify" note
- `scripts/little_loops/init/tui.py:1165,1171` `_render_summary` — same `summary_rows` call, TUI-mode consumer
- `scripts/little_loops/init/tui.py:444` `_render_detection_panel` — calls `proposal.provenance_rows()` and renders evidence strings to the user; visible surface for the new/changed evidence text

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CONFIGURATION.md` (~lines 323, 1969) and `docs/guides/GETTING_STARTED.md:165` — describe `--force` as "resets to template defaults"; now existence-filtered, check wording
- `docs/reference/CLI.md` (lines ~50, 76) — `ll-init` flag text; check for template-default wording
- `skills/init/SKILL.md:167` — "template defaults" sentence; verify still accurate
- `scripts/little_loops/config-schema.json` (`src_dir`/`test_dir`/`focus_dirs` descriptions, ~lines 20, 25, 825) — consider documenting `.` as a valid value; if `skills/` files are edited, re-run `ll-adapt --host <gemini|kimi-code|qwen> --apply` (mirrors under `.qwen/`, `.kimi-code/`, `.gemini/`)
- `skills/configure/show-output.md:11,12,164` — hard-codes "(default: src/)" / "(default: tests)"; schema defaults, not changed by this issue

_Wiring pass added by `/ll:wire-issue` — 2026-09-27:_

- `docs/reference/COMMANDS.md` (`### /ll:init` section, ~lines 30-46) — describes `/ll:init` settling "any `inferred`/`default`-provenance value or listed ambiguity ... that the deterministic introspection pass couldn't confidently resolve"; fewer phantom candidates reach that step once this issue's existence filter lands — wording check alongside the other doc passes

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

_Wiring pass added by `/ll:wire-issue` — 2026-09-27:_

- `scripts/tests/test_init_introspect.py:124-144` `TestManifestDiscoveryNesting` (`test_finds_pyproject_nested_one_level`, `test_ambiguous_nested_pyproject_stays_default`) — existing "sole one-level-nested candidate, else give up on ambiguity" pattern for `_find_manifest`; use as the model for the new `_find_nested_test_dir` tests (direct hit / sole nested match / ambiguous-stays-default)
- `scripts/tests/test_init_proposal.py:159-164` `test_provenance_rows_hide_defaults_by_default` — existing coverage asserting a `"Source dir"` label via `proposal.provenance_rows()` (distinct from the `summary_rows` gap noted above); confirm it still passes once src_dir defaults change
- `scripts/tests/test_init_tui.py:1489` `TestWizardSeedsFromIntrospection.test_prompts_default_to_introspected_values_with_evidence` — asserts the wizard's rendered comma-joined focus-dirs default text (`"mypkg/, tests/"`); verify unaffected by the `introspect()` reorder for this non-empty-layout case
- `scripts/tests/test_init_tui.py:1086-1095` `TestScanScreen.test_custom_focus_dirs_written_to_config` — full wizard-level coverage of the focus_dirs write path; model for a new wizard-level root-layout (`.`) test
- `scripts/tests/test_init_skill_fixtures.py` `TestUnambiguousPlanFixture`, `TestAmbiguousSrcDirMakefileFixture` (`pytest.mark.integration`) — closest existing `--plan` JSON fixture pattern asserting `ambiguities`/`provenance` for `src_dir`; consider extending to cover `test_dir`/`focus_dirs` existence-filtering and the `.` case

## Program Design

### Types

- `IntrospectedValue.value: str | list[str]` (unchanged; `.` is a valid value)

### Signatures

- `_TEST_FILE_GLOBS: tuple[str, ...]` — module constant; the single test-file pattern set
- `_existing_dir(root: Path, value: str) -> str | None` — canonicalized `value` if it is `.` or a relative, `..`-free path with `(root / value).is_dir()`, else `None`
- `_has_test_files(root: Path, rel_dir: str, *, allow_conftest: bool = False) -> bool` — bounded (depth 4) recursive search for `_TEST_FILE_GLOBS`, pruning `_SKIP_DIRS` and dot-dirs
- `_detect_root_layout(root: Path) -> bool` — `True` when root holds a non-ignored `.py/.go/.ts/.js/.mjs/.cjs` file; drives provenance only (value is `.` either way)
- `_find_nested_test_dir(root: Path, src_dir: str) -> str | None` — `<src_dir>/tests|test/`, then `src/test/java/`, else the sole one-level `*/tests|test/` containing test files; skips `_SKIP_DIRS` and dot-dirs
- `_introspect_test_dir(root: Path, src_dir: str, default_value: str) -> IntrospectedValue` — gains `src_dir` (caller narrows `src_dir_iv.value` to `str`, as it already does for `_python_command`)
- `_introspect_focus_dirs(root: Path, src_dir_iv: IntrospectedValue, test_dir_iv: IntrospectedValue, default_focus_dirs: list[str]) -> IntrospectedValue` — gains `test_dir_iv`

### Call Path

`introspect` -> `_introspect_src_dir` -> `_existing_dir`; `_introspect_src_dir` -> `_detect_root_layout`; `introspect` -> `_introspect_test_dir` -> `_find_nested_test_dir` -> `_has_test_files`; `_introspect_test_dir` -> `_has_test_files`; `_introspect_test_dir` -> `_existing_dir`; `introspect` -> `_introspect_focus_dirs` -> `_existing_dir`

`introspect()` order changes: src_dir → commands → test_dir → focus_dirs (test_dir moves ahead of focus_dirs and is passed in).

## Scope Boundaries

- **In scope**: existence filtering of src/test/focus dir defaults **and of detected src_dir candidates** (filter only — detection logic unchanged), root-layout (`.`) detection, nested test-dir probing, the `introspect()` reorder in `little_loops.init.introspect`, and round-tripping `.` through the init proposal/TUI/core.
- **Out of scope**:
  - Changing how package-marker/pyproject/tsconfig/Cargo candidates are *detected* (they are only existence-filtered).
  - Detecting non-conventional test dir names (`__tests__/`, `spec/`). (`src/test/java/` is the Maven/Gradle standard layout and co-located `*_test.go` / `*.test.ts` is the Go/Jest/Vitest standard, so both are in scope.)
  - Changing project-type template contents.
  - Non-dir fields (build/lint/test commands), beyond keeping the `{src_dir or '.'}` derivation sane.
  - Fixing `.`-hostile runtime consumers — **BUG-3631** (done, commit `85696dc57`); those fixes stay in BUG-3631's scope, not this issue's, regardless of blocking status.
  - **Re-init of an existing config**: `proposal.py:build_proposal` pins existing `src_dir`/`test_dir`/`scan.focus_dirs` with provenance `existing`, so a phantom value already in `.ll/ll-config.json` survives a plain re-run of `ll-init`. Only fresh introspection (new install or `--force`) is existence-filtered; revalidating stored values is not part of this issue.

## Implementation Steps

1. Add `_existing_dir` (canonicalize; reject absolute / `..`) and `_TEST_FILE_GLOBS` + `_has_test_files` in `little_loops.init.introspect`. In `_introspect_src_dir`, filter the collected candidate set through `_existing_dir` before the `len(candidates)` checks, and apply it to the template default on the zero-candidate / ambiguity branches. Source dir with no surviving value → `.` (never empty — `build_config` in `core.py`/`tui.py` treats empty as "keep template value" and would re-adopt the phantom dir).
2. Add `_detect_root_layout` with the extension set and ignore list in Proposed Solution. Call it on the zero-candidate branch whenever the resulting value is `.` — including when the template default itself is `.` (go) — to select provenance `inferred` vs `default`. Not called on the ambiguity branch.
3. Add `_find_nested_test_dir(root, src_dir)` — `<src_dir>/tests|test/`, then `src/test/java/`, else the sole one-level match for which `_has_test_files(..., allow_conftest=True)` holds; skip `_SKIP_DIRS` and dot-prefixed dirs.
4. Extend `_introspect_test_dir(root, src_dir, default_value)` with the six-step probe order in Proposed Solution (including the co-located search); final fallback is `tests/` (provenance `default`, evidence `"no test files found; conventional location for new tests"`), not `.`.
5. Reorder `introspect()`: compute test_dir before focus_dirs and pass `test_dir_iv` to `_introspect_focus_dirs`; drop its duplicated `("tests/", "test/")` probe. Implement the three focus rules plus the test-dir-only guard from Proposed Solution: `["."]` whenever the final src_dir value is `.`; adopted src_dir + uncovered test dir; otherwise existence-filtered template `focus_dirs` + test dir; any list with no non-test entry → `["."]`; never empty. Keep the `"adopted src_dir"` / `"... + detected tests/ directory"` evidence strings verbatim. Update the `introspect()` docstring.
6. Round-trip `.` through `proposal.py` / `tui.py` / `core.py` (`choices["src_dir"]`, `scan_focus_dirs`) and `summary_rows`, keeping `mypy {src_dir or '.'}` (`introspect.py:302`) sane. Verify `auto-refine-and-implement.yaml:626,851` pass-through of `.` (the other consumers are in BUG-3631).
7. Update `cli.py:531` `_print_introspection_summary` wording ("kept template default") — on ambiguity the value is now the existence-filtered default or `.`.
8. Tests: rewrite the three phantom-default tests (`test_no_package_marker_keeps_default` → `.`, `test_no_test_dir_keeps_default` → `tests/` with the new evidence, `test_defaults_when_nothing_detected` → `["."]`) and the wiring-listed empty-dir tests. Add a value assertion (`iv.value == "."`) to `test_two_top_level_package_dirs_ambiguous_keeps_default`, which today checks only provenance and candidates. Add:
   - src_dir: flat layout → `.` (inferred); root with only `setup.py`/`conftest.py` → `.` (default); root with only `vite.config.ts` / `jest.config.js` + `src/` → not a root layout; flat Go repo (`go.mod` + `main.go`, go template) → `.` **inferred**; hatch `packages` naming a missing dir → filtered out; tsconfig `rootDir: "app"` with no `app/` → filtered out; `_existing_dir` rejects `/abs` and `../x`.
   - test_dir: nested `scripts/tests/` detected; two nested test dirs → not adopted; test dir under `.claude/` ignored; a `*Test.java` file under `src/test/java/` → `src/test/java/`; Go `*_test.go` files beside sources (e.g. under `pkg/`) → co-located (not `tests/`); `*.test.ts` files under `src/` with src `src/` → `src/`; root `conftest.py` alone → `tests/` fallback; root `foo.spec.ts` → `.`.
   - focus_dirs: template focus_dirs filtered by existence; src `.` (inferred and default, incl. go template) → `["."]`; ambiguous src + nested `scripts/tests/` → never `["scripts/tests/"]` alone; src default + top-level `tests/` only → `["."]`; java layout → `["src/main/java/", "src/test/java/"]`.
   - `.` round-trip.
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

_Wiring pass added by `/ll:wire-issue` — 2026-09-27 (second pass):_

- Check `_render_headless_summary` (`cli.py:636`), `_render_summary` (`tui.py:1165`), and `_render_detection_panel` (`tui.py:444`) render the new `.`/filtered values and evidence strings correctly — these are the user-visible surfaces for `summary_rows`/`provenance_rows` output
- Wording check on `docs/reference/COMMANDS.md` (`### /ll:init`) alongside the other doc passes listed above

## Impact

- **Priority**: P3 - phantom dirs misdirect downstream tooling but the user can correct them in the TUI/config
- **Effort**: Medium - four new helpers, a test-file constant and a call reorder in one module, but ~20 test touch-points across 7 test files (downstream consumer fixes split out to BUG-3631)
- **Risk**: Low - only changes fallback paths where detection was already inconclusive
- **Breaking Change**: No

## Acceptance Criteria

- [ ] On a fresh introspection, no `ll-init` proposal contains a Source or Focus dir absent from the target project; no `Ambiguity` lists an absent candidate. (The tsconfig `include: ["**/*.ts"]` → `**/` case is already fixed by BUG-3631's glob-char check in `_tsconfig_src_candidate`; this AC's remaining scope is the general existence filter for every other unfiltered candidate, e.g. a hatch `include`/`packages` branch or tsconfig `rootDir` declaring a nonexistent dir.) `_existing_dir` rejects absolute and `..` values.
- [ ] Test dir is never an absent path **except** `tests/` when a bounded recursive search finds no test dir and no test files at all (provenance `default`, evidence `"no test files found; conventional location for new tests"`).
- [ ] Root-level source/test layouts are proposed as `.` with provenance `inferred` — including a flat Go repo, whose template default is already `.`; an empty or tooling-only root (`setup.py`, `conftest.py`, `*.config.js`) yields src_dir `.` with provenance `default`.
- [ ] Nested test dirs (e.g. `scripts/tests/`) are detected; `<src_dir>/tests/` wins; `src/test/java/` is detected for Java layouts; two unrelated nested test dirs are not adopted; dot-prefixed dirs are never probed.
- [ ] Co-located tests — `*_test.go` files beside sources, `*.test.ts` files under `src/` — yield an inferred test dir (src_dir or `.`), never the `tests/` "no test files found" fallback.
- [ ] Every test-file check uses one `_TEST_FILE_GLOBS` set; `conftest.py` counts only inside a candidate test dir, not at the root.
- [ ] Existing detection of src_dir candidates is unchanged whenever the candidate dir exists.
- [ ] Source dir never falls back to empty; the focus-dirs value is never an empty list (`["."]` fallback), so `core.py:347` / `tui.py:1099` truthiness guards never re-adopt a phantom template path.
- [ ] When the final src_dir value is `.` (any provenance), focus dirs are exactly `["."]`.
- [ ] Focus dirs never consist only of test dirs; with an unadopted src_dir they are the existence-filtered template `focus_dirs` plus the detected test dir, or `["."]`.
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
- **Dependencies**: `blocked_by: BUG-3631` remains **open** (unresolved) — matches the gap already recorded in the 2026-09-27 Confidence Check Notes; not re-flagged as new. _(Superseded: BUG-3631 is done, commit `85696dc57`; the `blocked_by` edge was removed in the 2026-09-27 review.)_
- **DEP_ISSUES (MISSING_BACKLINK, informational)**: BUG-3631 references this issue only under its `## Related` section ("Blocks ENH-3616 ...", `.issues/bugs/P3-BUG-3631-...md:213`), not a formal `## Blocks` heading. Not corrected here (out of scope for a single-issue verify pass to edit another issue file); flagging for awareness.
- **Evidence quotes** (`ll-verify-evidence --json`): clean, 0 findings. **Decisions log**: `.ll/decisions.d` present, query ran, 0 active required rules — no violation.
- **Graph**: provider=`codegraph` freshness=`stale` — not used to originate the anchor-drift finding; confirmed directly via `sed`/`grep` against HEAD.
- **ENH-3612 coordination note** (Wiring Phase): re-confirmed done (`status: done`); no action needed.

## Resolution

Implemented in `scripts/little_loops/init/introspect.py`: added `_existing_dir`
(canonicalizes and existence-checks a dir value, rejecting absolute/`..`
values), `_TEST_FILE_GLOBS` + `_has_test_files` (bounded depth-4 recursive
test-file search, shared by every check), `_root_level_test_files`,
`_detect_root_layout` (flat-repo detection with a tooling/test-file ignore
list), and `_find_nested_test_dir` (`<src_dir>/tests|test/`, Maven
`src/test/java/`, then a sole one-level `*/tests|test/` match).

- `_introspect_src_dir` now filters every candidate (package-marker,
  pyproject, tsconfig, Cargo) and the template default through `_existing_dir`
  before counting; a filtered-empty/`.` zero-candidate result routes through
  `_detect_root_layout` to pick `inferred` vs `default` provenance for `.`.
- `_introspect_test_dir` gained a `src_dir` parameter and a six-step probe
  order (top-level `tests|test/` → nested → root-level test files → co-located
  under src_dir or root → filtered template default → the one deliberate
  nonexistent fallback `tests/`, evidenced `"no test files found; ..."`).
- `_introspect_focus_dirs` gained a `test_dir_iv` parameter (the `introspect()`
  call order now computes test_dir before focus_dirs); focus dirs collapse to
  `["."]` whenever src_dir is `.` or whenever every surviving entry is a test
  dir, and are never empty.
- Updated `cli.py:531` ambiguity wording ("not adopted" instead of "kept
  template default", since the ambiguity value can now be `.`).

Rewrote the three phantom-default tests plus the mypy-command/e2e-summary
tests that assumed a `src/` dir existing in an empty `tmp_path`, and added new
coverage for the helpers, root-layout/co-located/nested-test-dir detection,
the focus-dirs test-dir-only guard, and the `.`/`""` round-trip through
`build_config`/`summary_rows`. Full suite: `python -m pytest scripts/tests/`
— 4 pre-existing unrelated failures confirmed via `git stash` (issue-corpus
count, evidence-quote gate, prose-dep-drift gate, one flaky process-group
test), 26018 passed.

## Status

**Open** | Created: 2026-09-26 | Priority: P3

## Review Notes

_Added by manual review — 2026-09-27:_

- Focus dirs: `["."]` whenever the final src_dir value is `.` (any provenance); unadopted src_dir uses existence-filtered template `focus_dirs` + test dir; a test-dir-only list becomes `["."]`. Removed the earlier claim that a nested test dir reaching focus dirs on ambiguity was a benefit — alone it made scans skip all source.
- `_detect_root_layout` now also runs when the template default is `.` (go), so flat Go repos get provenance `inferred`; its extension set and JS-tooling ignore list are now specified.
- Test dir: added `src/test/java/` probe and a bounded co-located test-file search (Go/Jest/Vitest) before the `tests/` fallback, whose evidence is now `"no test files found; ..."` and true by construction.
- One `_TEST_FILE_GLOBS` constant + `_has_test_files` helper for every test-file check; `conftest.py` counts only inside a candidate test dir.
- `_existing_dir` canonicalizes and rejects absolute / `..` values.
- Removed the resolved `blocked_by: BUG-3631` edge and the two stale Confidence Check Notes sections (both scored 80/100 solely on that dependency); `_warn_config_drift` marked no-change (declared-only). Effort raised to Medium. Re-run `/ll:confidence-check`.

## Session Log
- `/ll:manage-issue` - 2026-09-28T03:41:21 - `a1114a79-3057-4b58-b7ff-749d67448f3f.jsonl`
- `/ll:manage-issue` - 2026-09-28T03:40:35 - `a1114a79-3057-4b58-b7ff-749d67448f3f.jsonl`
- `/ll:confidence-check` - 2026-09-27T21:40:48 - `232ffda2-5aad-4a53-98cc-f078a39c501d.jsonl`
- `/ll:wire-issue` - 2026-09-27T20:56:39 - `9f137c1a-0103-40a8-9268-05ba85972649.jsonl`
- `/ll:reconcile-issue` - 2026-09-27T20:31:03 - `875ff80d-d1f7-4605-9400-e1a7cf094cda.jsonl`
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
