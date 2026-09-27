---
id: BUG-3631
type: BUG
title: Root-layout '.' src_dir/focus_dirs breaks prefix matching in codegraph, worker_pool,
  decisions export, manage-release
priority: P3
status: open
verify_verdict: EVIDENCE_UNVERIFIED
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T05:09:09Z'
blocks:
- ENH-3616
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
reconcile_attempted: true
---

# BUG-3631: Root-layout '.' src_dir/focus_dirs breaks prefix matching in codegraph, worker_pool, decisions export, manage-release

## Summary

Several runtime consumers of `project.src_dir` / `project.test_dir` / `scan.focus_dirs` build a path prefix as `value.rstrip("/") + "/"`. For a root-layout value of `.` that prefix becomes `./`, which no repo-relative path (git porcelain output, codegraph paths) ever starts with. The `go` project-type template already ships `src_dir: "."`, so Go projects hit these bugs today; ENH-3616 will make `.` a common value for Python/JS/generic flat layouts too.

## Current Behavior

- `little_loops.codequery.codegraph._is_scan_relevant` (`scripts/little_loops/codequery/codegraph.py:121`) — `path == d.rstrip("/") or path.startswith(d.rstrip("/") + "/")`. For `focus_dirs: ["."]` this tests `path == "."` / `path.startswith("./")`; repo-relative paths match neither, so **every file is excluded** from the scan-relevant set.
- `little_loops.parallel.worker_pool` leaked-file detection (`scripts/little_loops/parallel/worker_pool.py:1523`) — appends `dir_path.rstrip("/") + "/"` to `source_prefixes`. For `src_dir: "."` the prefix is `./`, which never matches `git status --porcelain` paths, so files a worker leaks into the repo root are **silently not detected** (only the hard-coded `backend/`, `src/`, `lib/`, `tests/` fallbacks still work).
- `little_loops.cli.issues.decisions` export (`scripts/little_loops/cli/issues/decisions.py:652`) — `scope_globs = [f"{src_dir.rstrip('/')}/**/*"]` yields `./**/*` for `.`; whether the exported target's glob matcher accepts a `./` prefix is unverified. The no-src_dir branch already uses `**/*`.
- `commands/manage-release.md` (lines 38, 40, 249, 251, 302) — concatenates `{{config.project.src_dir}}pyproject.toml` with no separator, relying on the trailing slash; `.` yields a dot-prefixed filename (`.pyproject.toml`) and the same broken prefix on the package `__init__.py` path.

Checked and **not** affected (no change needed):
- `codegraph.py:234` `_dotted_candidates` — with `.` the prefix strip never applies and it returns `[dotted]`, which is already the correct dotted name for a root layout.
- `commands/run-tests.md:99` — `grep -E '^{{config.project.src_dir}}'` becomes `^.`, matching every changed file; with `src_dir: .` every file *is* under the source dir, so this is correct.
- `ProjectConfig` path joins, `worktree_utils.py`, `prepatch_check.py`, `code-run-gate.yaml` — `root / "."` resolves to root.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Anchor corrections (remediation pass): the `worker_pool` prefix line `normalized = dir_path.rstrip("/") + "/"` is at `scripts/little_loops/parallel/worker_pool.py:1525` (not `:1523`; the `if dir_path:` guard is `:1524`), matching the Integration Map. The "only configured prefix" wording in Steps to Reproduce step 3 is loose: `source_prefixes` always also holds the hard-coded `backend/`, `src/`, `lib/`, `tests/`, so the defect is that a root-level file such as `main.go` matches none of them.
- Full `commands/manage-release.md` site list (supersedes the partial list above): lines 38, 40, 249, 251, 302, 304, 310, 453, 455. Identical concatenation sites exist in both git-tracked mirrors: `.gemini/commands/manage-release.toml` lines 18, 20, 229, 231, 282, 284, 290, 433, 435 and `.qwen/commands/ll/manage-release.md` lines 19, 21, 230, 232, 283, 285, 291, 434, 436.
- Trigger split (supersedes the Summary's "Go projects hit these bugs today" for codegraph): the `go` template writes `src_dir: "."` but `focus_dirs` of `cmd/`, `pkg/`, `internal/` and no `test_dir`, so Go projects hit the `worker_pool`, decisions-export and `manage-release` defects today; the `_is_scan_relevant` defect requires an explicit `scan.focus_dirs: ["."]`. Repro step 2 is therefore triggered only by that explicit config, and steps 3-4 by `src_dir: "."` alone.
- Decisions-export warning: the no-`src_dir` branch (`decisions.py:654-660`) prints a stderr warning that a bare `**/*` replaces OCR's built-in language rules; `docs/reference/CLI.md:3238` documents that warning as part of the `**/*` fallback. The glob-matcher question above is moot: the fix emits `**/*` for `.`, which is already a form the exporter produces.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Additional independent trigger for `_is_scan_relevant` (remediation pass, extends the "Trigger split" bullet above): `little_loops.init.introspect._pyproject_src_candidate` (`scripts/little_loops/init/introspect.py:641-648`) returns `f"{where[0].rstrip('/')}/"` for a `[tool.setuptools.packages.find] where = ["."]` declaration (the documented setuptools flat-layout pattern) without stripping the leading dot, yielding the literal candidate `"./"`. When that is the sole `src_dir` candidate, `_introspect_src_dir` (`introspect.py:686-727`) returns an `inferred` `IntrospectedValue("./", ...)`, and `_introspect_focus_dirs` (`introspect.py:735-753`) then appends `src_dir_iv.value` to `focus_dirs` whenever its provenance is not `"default"`, producing `scan.focus_dirs == ["./"]` automatically. So `ll-init` can already write both `project.src_dir: "./"` and `scan.focus_dirs: ["./"]` into `.ll/ll-config.json` for a real Python flat-layout project today, hitting the `_is_scan_relevant` defect with zero manual config and independent of ENH-3616 — the "requires an explicit `scan.focus_dirs: ['.']` config" framing above describes only the manual-config path, not this automatic one. No existing test covers the `where` branch of `scripts/little_loops/init/introspect.py:_pyproject_src_candidate`; `scripts/tests/test_init_introspect.py` has no case for it (confirmed absent by search) and the file is not currently in the issue's test list — see the Integration Map correction above.

## Steps to Reproduce

1. In a Go project initialized with `ll-init` (the `go` template writes `project.src_dir: "."`), or any project with `scan.focus_dirs: ["."]` in `.ll/ll-config.json`:
2. Call `_is_scan_relevant("main.go", ["."], [])` → returns `False` (expected `True`); the codegraph scan-relevant filter drops every file.
3. Run `ll-parallel` on an issue whose worker writes a stray root-level file into the main repo → `_detect_main_repo_leaks` does not report it, because the only configured prefix is `./`.
4. Run `ll-issues decisions export` with no `decisions.export.scope_globs` configured → the emitted scope glob is `./**/*` instead of `**/*`.

## Expected Behavior

A dir value of `.` (or `./`) means "the whole repo":

- `_is_scan_relevant` treats a focus dir of `.` as matching every (non-excluded) path.
- `worker_pool` leak detection treats a `src_dir`/`test_dir` of `.` as matching every new file (subject to the existing state-file / `.gitignore` skips).
- decisions export emits `**/*` for a `.` src_dir.
- `manage-release.md` resolves the version files to repo-root paths (plain `pyproject.toml`) for `.`.

## Proposed Solution

Add a small shared normalizer (e.g. `little_loops.config` helper `dir_prefix(value) -> str` returning `""` for `.`/`./`/empty-root and `value.rstrip("/") + "/"` otherwise) and use it at the three Python sites so "empty prefix" means match-all. For `manage-release.md`, change the concatenation so a `.` value resolves correctly (e.g. instruct the model to treat `src_dir` of `.` as the repo root, or join with an explicit separator).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Convention in force: `_is_scan_relevant` treats an empty `focus_dirs` list as "no scope restriction" (`codegraph.py:113-119`), and the decisions export already falls back to `**/*` when `src_dir` is unset (`decisions.py:654-660`). An empty-prefix result from the normalizer maps onto both existing "match everything" semantics.
- Contested point: `dir_prefix` returning `""` conflates "root" with "unset"; a caller doing `if prefix:` guards (as `worker_pool` does with `if dir_path:`) must not skip the root case, and a bare `startswith("")` is match-all only if the sole prefix source is trusted (see the `.issues/` cross-worker hazard in Integration Map).
- `manage-release.md` is prose consumed by a model after `{{config.*}}` interpolation; the fix must hold for the interpolated literal `.` value, and trailing-slash values (`src/`, `scripts/`) must still yield `scripts/pyproject.toml`-style paths.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Resolved design constraints (remediation pass), replacing the open alternatives above:
  - Import path: define the helper in `scripts/little_loops/config/core.py` and import it as `little_loops.config.core.dir_prefix`. `config/__init__.py:36-38` states that helper functions are intentionally NOT re-exported (only dataclass types and `BRConfig`); that policy stands, so no `__init__.py` export and no `__all__` change. Program Design and API.md cite the `config.core` path.
  - Root vs unset: `dir_prefix` returns `""` only for the root spellings `.`, `./` and (after stripping) an all-slash/dot value. "Unset" is decided by each caller's existing truthiness guard BEFORE calling (`if dir_path:` at `worker_pool.py:1524`, `if src_dir:` at `decisions.py:650`); a caller must not re-test the returned prefix for falsiness to mean "unset". Under that rule `""` from the helper unambiguously means "whole repo".
  - `_is_scan_relevant` (`codegraph.py:121`): the predicate has two clauses (`path == d.rstrip("/")` and `path.startswith(d.rstrip("/") + "/")`). For a root focus dir both must collapse to match-all, so `.` and `./` behave identically and are still subject to the exclude-pattern check that runs first; non-root dirs keep both clauses so a directory path equal to the dir itself still matches.
  - `worker_pool._detect_main_repo_leaks` (`worker_pool.py:1519-1550`): match-all must not be expressed by putting `""` into the `source_prefixes` tuple, because that `elif` precedes the `thoughts/` and `.issues/`/`issues/` branches and would bypass `_has_other_issue_id`, flagging (and `_cleanup_leaked_files` discarding) other workers' issue files. Constraint: root layout is tracked separately from the prefix list and is evaluated only after the issue-ID, `thoughts/` and issue-directory branches have declined a path; the state-file and `.gitignore` skips stay first.
  - `decisions.py:650-660`: non-root `src_dir` keeps `f"{prefix}**/*"` (identical output to today for `src/` and `scripts/`); root emits `**/*`. The stderr "no project.src_dir" warning is NOT emitted for `.`, because the operator explicitly configured a repo-wide source dir; the warning stays exclusive to the unset branch.
  - `commands/manage-release.md`: pick ONE mechanism, stated once in the file: the version-file paths resolve to `pyproject.toml` / `little_loops/__init__.py` at repo root when `{{config.project.src_dir}}` is `.` or `./`, and to `<src_dir>pyproject.toml` (single separator, no doubling) for `src/`, `scripts/` and no-trailing-slash values. Do not switch to `{{src_dir}}/x` joins (breaks trailing-slash values with `scripts//`). Edits above line 134 must be line-count-neutral, or the `("commands/manage-release.md", 134)` pin in `test_wiring_skills_and_commands.py:754` must be updated in the same change (line 134 precedes sites 249+ but follows 38/40).

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Anchor correction (remediation pass): the "if src_dir:" truthiness guard cited above is at `scripts/little_loops/cli/issues/decisions.py:651`, not `:650` — line 650 is the `src_dir = getattr(config.project, "src_dir", None)` assignment that guard tests.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Files to modify (anchors verified this pass): `scripts/little_loops/codequery/codegraph.py:121` (`_is_scan_relevant`, callers at `codegraph.py:177` and `:316`); `scripts/little_loops/parallel/worker_pool.py:1525` (in `_detect_main_repo_leaks`, def at `:1478`, sole caller `:689`); `scripts/little_loops/cli/issues/decisions.py:652`; `commands/manage-release.md` lines 38, 40, 249, 251, 302, 304, 310, 453, 455 (the issue lists 38/40/249/251/302; 304, 310, 453, 455 use the same `{{config.project.src_dir}}` concatenation).
- `little_loops.config` is a package (`scripts/little_loops/config/__init__.py` re-exports from `core.py`, `automation.py`, ...); a new public helper must be exported from `__init__.py`, not only defined in `core.py`, for the `little_loops.config.dir_prefix` signature in Program Design to resolve.
- Worker-pool consequence of an empty prefix: `file_path.startswith(tuple(source_prefixes))` with `""` in the tuple is True for every path, so the state-file and `.gitignore` skips run first but the issue-file/`thoughts/` branches become unreachable-in-effect; `.issues/` files of OTHER workers would then be flagged as leaks (the `_has_other_issue_id` cross-worker guard lives only in the `.issues/` elif branch, which the source-prefix elif precedes). This ordering hazard is a constraint on how "match all" is expressed.
- Do-not-touch sites checked: `scripts/little_loops/parallel/file_hints.py:259,280` also use `rstrip("/") + "/"`, but `MIN_DIRECTORY_DEPTH = 2` (`file_hints.py:41`) already makes a `./` directory a non-signal, so behavior is intended; `codegraph.py:234` `_dotted_candidates` and `git_operations.py:325` `file_matches_pattern` are not affected.
- Repro correction: `scripts/little_loops/templates/go.json` ships `project.src_dir: "."` but its `scan.focus_dirs` are `cmd/`, `pkg/`, `internal/`, so Go projects hit the worker_pool and decisions-export bugs today, not the `_is_scan_relevant` one (that needs `focus_dirs: ["."]`, which ENH-3616 would emit).
- Existing tests that must keep passing: `scripts/tests/test_worker_pool.py::test_detect_main_repo_leaks_uses_configured_src_dir` (`src_dir: "scripts/"`), `scripts/tests/test_cli_decisions.py` (`test_config_scope_globs_overrides_src_dir`, `src_dir: "src/"`), `scripts/tests/test_codequery_codegraph.py`, `scripts/tests/test_decisions_export.py`, `scripts/tests/test_config.py`.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Re-export claims superseded (remediation pass): the bullet above stating "a new public helper must be exported from `__init__.py`" and the `scripts/little_loops/config/__init__.py` entry under Dependent Files (Callers/Importers) below (offering export-or-cite as an open either/or) are both superseded by the Resolved design constraints in Proposed Solution and by this section's own Program Design correction: `config/__init__.py:36-38`'s policy of not re-exporting helpers stands, so `dir_prefix` is imported only via `little_loops.config.core.dir_prefix` — no `__init__.py` edit, no `__all__` change. Treat both of those lines as superseded by this note.
- Missing test coverage (remediation pass): `scripts/little_loops/init/introspect.py:_pyproject_src_candidate`'s `where` branch (lines 646-648) and its `focus_dirs` propagation via `_introspect_focus_dirs` (`introspect.py:735-753`) have no covering case anywhere in the suite — see the new Current Behavior finding on this trigger path. A new case belongs in `scripts/tests/test_init_introspect.py`, asserting that a `[tool.setuptools.packages.find] where = ["."]` pyproject declaration yields `src_dir` candidate `"./"` and that `focus_dirs` becomes `["./"]`, alongside the other new tests already listed under Tests above.
- Documentation gap — test_dir and second scope_globs site (remediation pass): `worker_pool._detect_main_repo_leaks` applies the identical `dir_prefix` normalization to both `project.src_dir` and `project.test_dir` (it loops over both, `worker_pool.py:1523`), so `test_dir: "."` gets the same "repo root" behavior change — but `docs/reference/CONFIGURATION.md`'s `test_dir` row (adjacent to the `src_dir` row, `CONFIGURATION.md:~299`) is not currently listed for the same doc clarification alongside the `src_dir` row noted under Documentation below. Separately, `docs/guides/DECISIONS_LOG_GUIDE.md` has a second site describing the same `src_dir` → `**/*` fallback chain in its config-key table (`decisions.export.scope_globs` row, "Empty falls through to `project.src_dir`, then `**/*`", ~`DECISIONS_LOG_GUIDE.md:597`), beyond the `:411-413` lines already named under Documentation — both sites need the same "`.` means repo root" clarification so the doc doesn't describe the case once and omit it once.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/codequery/codegraph.py` — `_is_scan_relevant` callers at `:177` and `:316` inherit the fix; no edit needed [wiring pass]
- `scripts/little_loops/config/__init__.py` — re-export `dir_prefix` and add to `__all__`; note the comment at `:36-38` says helpers are intentionally NOT re-exported (direct `config.core` imports), so either export it deliberately or cite `little_loops.config.core.dir_prefix` in Program Design [wiring pass]
- `scripts/little_loops/config/core.py` — natural definition site for `dir_prefix` (alongside `ProjectConfig`) [wiring pass]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/templates/go.json` — ships `project.src_dir: "."`; the live trigger, no edit needed [wiring pass]
- `scripts/little_loops/config-schema.json` and `scripts/little_loops/config/features.py` — `decisions.export.scope_globs` override; behavior unchanged, confirm the `**/*` default path in `decisions.py:654-660` stays consistent [wiring pass]

### Files to Modify (mirrors)

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/manage-release.toml` (lines 18, 20, 229, 231) and `.qwen/commands/ll/manage-release.md` — git-tracked host mirrors of `commands/manage-release.md` carrying the same `{{config.project.src_dir}}` concatenation; regenerate with `ll-adapt --host <gemini|qwen> --apply` after editing the command (mirror gates otherwise fail) [wiring pass]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`## little_loops.config`, ~`:108`) — document the new `dir_prefix` helper [wiring pass]
- `docs/reference/CONFIGURATION.md:300` (`src_dir` row) — note that `.` means repo root for flat layouts [wiring pass]
- `docs/guides/DECISIONS_LOG_GUIDE.md` and `docs/reference/CLI.md` — mention `scope_globs`; update only if the `.` -> `**/*` default is described there [wiring pass]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_codequery_codegraph.py` — add `_is_scan_relevant("main.go", ["."], [])` cases (also `"./"`) beside the existing focus_dirs tests (~`:315-355`) [wiring pass]
- `scripts/tests/test_worker_pool.py` — add a `_detect_main_repo_leaks` case with `src_dir: "."` next to `test_detect_main_repo_leaks_uses_configured_src_dir`; include a cross-worker `.issues/` file to guard the ordering hazard [wiring pass]
- `scripts/tests/test_cli_decisions.py` / `scripts/tests/test_decisions_export.py` — add `src_dir: "."` -> `**/*` case [wiring pass]
- `scripts/tests/test_config.py` — unit tests for `dir_prefix` (`.`, `./`, `""`, `src`, `src/`) [wiring pass]
- `scripts/tests/test_wiring_skills_and_commands.py:754` — pins `("commands/manage-release.md", 134)` line number for an agent-marker detector; edits shifting lines in `manage-release.md` may break this pin [wiring pass]

## Program Design

### Types

- No new types; dir values stay `str`.

### Signatures

- `dir_prefix(value: str) -> str` — new public helper in `little_loops.config`; `""` for `.`, `./`, or `""`; otherwise `value.rstrip("/") + "/"`
- `_is_scan_relevant(path: str, focus_dirs: list[str], exclude_patterns: list[str]) -> bool` — unchanged signature; an empty prefix from `dir_prefix` matches every path
- `WorkerPool._detect_main_repo_leaks(self, issue_id: str, baseline_status: set[str]) -> list[str]` — unchanged signature; an empty prefix matches every new file
- `_cmd_export(config, args, path) -> int` — unchanged signature; emits `**/*` when `dir_prefix(src_dir)` is empty

### Call Path

`_is_scan_relevant` -> `dir_prefix`; `_detect_main_repo_leaks` -> `dir_prefix`; `_cmd_export` -> `dir_prefix`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Remediation-pass corrections: the helper lives at `little_loops.config.core.dir_prefix(value: str) -> str` (not re-exported from `little_loops.config`, per `config/__init__.py:36-38`). `_cmd_export` handles two cases: `dir_prefix(src_dir) == ""` -> `["**/*"]` with no stderr warning, otherwise `[f"{prefix}**/*"]`. `_detect_main_repo_leaks` keeps the root case out of the `source_prefixes` tuple (see Proposed Solution) so the `.issues/` cross-worker guard still runs. `codegraph.py:234` `_dotted_candidates` and `init/introspect.py:648` (`_pyproject_src_candidate`, builds `where[0].rstrip('/') + '/'`) build similar prefixes but are unaffected: `_dotted_candidates` already guards `prefix != "/"` and returns `[dotted]` for `.`.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Signatures correction (remediation pass): the `dir_prefix` entry listed under Signatures above reads `little_loops.config.dir_prefix`; per the Resolved design constraints (Proposed Solution) and this section's own "Remediation-pass corrections" bullet directly below, the importable path is `little_loops.config.core.dir_prefix` — it is not re-exported from `little_loops.config`. Treat the Signatures bullet's module qualifier as superseded by this note.

### Decision Rules
- N/A — no new decision logic (root-dir spellings `.` / `./` are the only new classification; literal values and the no-warning rule are stated in Proposed Solution).

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Define `dir_prefix` in `scripts/little_loops/config/core.py` and export it from `config/__init__.py`
  > ⚠ Superseded — do not re-export; import via config.core.dir_prefix
- Update the three Python sites (`codegraph.py`, `worker_pool.py`, `decisions.py`) to use it
- Update `commands/manage-release.md`, then regenerate `.gemini/` and `.qwen/` mirrors with `ll-adapt --apply`
- Re-check the `test_wiring_skills_and_commands.py:754` line pin after editing `manage-release.md`
- Add tests in `test_config.py`, `test_codequery_codegraph.py`, `test_worker_pool.py`, `test_cli_decisions.py`
- Update `docs/reference/API.md` and `docs/reference/CONFIGURATION.md`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Outcome: `little_loops.config.core.dir_prefix` exists, is unit-tested in `test_config.py` for `.`, `./`, `""`, `src`, `src/`, and is imported directly from `config.core` (no `config/__init__.py` change).
- Outcome: `_is_scan_relevant("main.go", ["."], [])` and `["./"]` are True; exclude patterns still win; a pin test asserts `_dotted_candidates` still returns `[dotted]` for `src_dir="."` (unchanged behavior). Verified by `pytest scripts/tests/test_codequery_codegraph.py`.
- Outcome: root `src_dir`/`test_dir` flags a new root-level file in `_detect_main_repo_leaks` while a cross-worker `.issues/` file with a different issue ID is NOT flagged; verified in `test_worker_pool.py` next to `test_detect_main_repo_leaks_uses_configured_src_dir`.
- Outcome: decisions export emits `**/*` with no stderr warning for `src_dir` of `.`, `./`; `src/` still yields `src/**/*`. Verified in `test_cli_decisions.py`.
- Outcome: all nine `{{config.project.src_dir}}` concatenation sites in `commands/manage-release.md` (38, 40, 249, 251, 302, 304, 310, 453, 455) follow the single rule from Proposed Solution; `.gemini/` and `.qwen/` mirrors regenerated via `ll-adapt --host <gemini|qwen> --apply`; mirror gates pass; the `:754` line pin is unchanged or updated to the new line.
- Outcome (docs, all required): `docs/guides/DECISIONS_LOG_GUIDE.md:411-413` and `docs/reference/CLI.md:3238` state that `src_dir: .` yields `**/*` without the warning; `docs/reference/CONFIGURATION.md:300` notes `.` = repo root; `docs/reference/API.md` (`## little_loops.config`) documents `dir_prefix`.
- Verification: `python -m pytest scripts/tests/` exits 0, including mirror and docs-audience gates.

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Outcome (remediation pass): a new case in `scripts/tests/test_init_introspect.py` covers the `where` branch of `scripts/little_loops/init/introspect.py:_pyproject_src_candidate` and its `focus_dirs` propagation (see Integration Map correction), alongside the tests already listed above.
- Outcome (remediation pass): `docs/reference/CONFIGURATION.md`'s `test_dir` row and `docs/guides/DECISIONS_LOG_GUIDE.md`'s second `scope_globs` table row (~`:597`) also document the `.` repo-root meaning, matching the `src_dir` row / `:411-413` lines already required above (see Integration Map correction).

## Impact

- **Priority**: P3 — affects Go projects today and every flat-layout project once ENH-3616 lands.
- **Effort**: Small — three prefix sites plus one command doc.
- **Risk**: Low.
- **Breaking Change**: No

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Priority/Impact correction (remediation pass): the `_is_scan_relevant` defect is not gated solely behind an explicit `scan.focus_dirs: ["."]` config or ENH-3616 landing — `ll-init` can already emit `scan.focus_dirs: ["./"]` automatically for a real Python `pyproject.toml` flat-layout project via the `_pyproject_src_candidate` `where` branch (see Current Behavior, Codebase Research Findings). This defect therefore affects Python flat-layout projects today, via `ll-init`, not only once ENH-3616 lands.

## Acceptance Criteria

- [ ] `_is_scan_relevant(path, focus_dirs=["."], ...)` returns True for a repo-relative path not matched by exclude patterns.
- [ ] `worker_pool` leaked-file detection flags a new root-level file when `src_dir` is `.`.
- [ ] decisions export with `src_dir: "."` and no configured scope globs emits `**/*`.
- [ ] `manage-release.md` version-file paths are correct for `src_dir: "."`.
- [ ] Existing behavior for trailing-slash values (`src/`, `scripts/`) unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- [ ] `_is_scan_relevant` treats both `["."]` and `["./"]` as match-all and `_dotted_candidates` behavior for `.` is pinned by a test.
- [ ] A cross-worker `.issues/` file (different issue ID) is NOT flagged by `_detect_main_repo_leaks` when `src_dir` is `.`.
- [ ] decisions export emits `**/*` with no stderr warning for `src_dir` of `.` and `./`.
- [ ] No `{{config.project.src_dir}}` directly followed by a filename remains in `commands/manage-release.md`, `.gemini/commands/manage-release.toml` or `.qwen/commands/ll/manage-release.md` (all nine sites per file); mirrors match after `ll-adapt --apply`.
- [ ] `DECISIONS_LOG_GUIDE.md`, `CLI.md:3238`, `CONFIGURATION.md`, `API.md` updated as listed in Implementation Steps.
- [ ] `python -m pytest scripts/tests/` exits 0 (mirror gates, the `test_wiring_skills_and_commands.py:754` pin, and the new tests included).

## Related

- Blocks ENH-3616 (which will emit `.` for Python/JS/generic flat layouts).

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-27T05:57:53 - `d9cc873e-f17d-4bf9-b8ac-9770c6d93a16.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-27T05:43:06 - `bf6e1e8c-2c0c-4865-99bf-f1fcae8fc265.jsonl`
- `/ll:reconcile-issue` - 2026-09-27T05:38:00 - `48e27ed8-8bad-43ec-ade3-1d77009a2e15.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:35:45 - `e18b63f4-fc4d-4093-b00f-89d5c0e394ec.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-27T05:23:02 - `aae621bb-c067-4881-b3ce-b0e08bc3edb0.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:21:25 - `2bf90db8-8241-42d1-a2f3-16851c36676b.jsonl`
- `/ll:verify-issues` - 2026-09-27T05:20:08 - `2bf90db8-8241-42d1-a2f3-16851c36676b.jsonl`
- `/ll:wire-issue` - 2026-09-27T05:19:22 - `456ac708-7949-4003-8fee-84b53705067e.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:18:02 - `09cdddd4-4608-4727-809d-efaaa771aaf2.jsonl`
