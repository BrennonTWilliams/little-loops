---
id: BUG-3631
type: BUG
title: Root-layout '.' src_dir/focus_dirs breaks prefix matching in codegraph, worker_pool,
  decisions export, and ll-init introspection
priority: P3
status: open
verify_verdict: EVIDENCE_UNVERIFIED
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T05:09:09Z'
blocks:
- ENH-3616
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 92
score_complexity: 19
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 23
---

# BUG-3631: Root-layout '.' src_dir/focus_dirs breaks prefix matching in codegraph, worker_pool, decisions export, and ll-init introspection

## Summary

Several runtime consumers of `project.src_dir` / `project.test_dir` / `scan.focus_dirs` build a path prefix as `value.rstrip("/") + "/"`. For a root-layout value of `.` that prefix is `./`, which no repo-relative path (git porcelain output, codegraph paths) ever starts with. Separately, `ll-init` introspection emits malformed root spellings (`./`, `/`, `**/`) for common flat-layout manifests. The `go` template already ships `src_dir: "."`, and ENH-3616 will make `.` common for Python/JS/generic flat layouts, so `.` must be safe everywhere before ENH-3616 lands.

_Consolidated 2026-09-27: this body replaces the earlier layered refine/remediation notes. `commands/manage-release.md` was split out to BUG-3635 (its version-file paths are little-loops-specific, so fixing the separator alone would not help consuming projects)._

## Current Behavior

**Runtime consumers**

- `little_loops.codequery.codegraph._is_scan_relevant` (`codegraph.py:121`) tests `path == d.rstrip("/")` or `path.startswith(d.rstrip("/") + "/")`. For `focus_dirs: ["."]` or `["./"]` that is `path == "."` / `path.startswith("./")`; repo-relative paths match neither, so **every file is dropped** from the scan-relevant set (callers `codegraph.py:177`, `:316`).
- `little_loops.parallel.worker_pool.WorkerPool._detect_main_repo_leaks` (def `worker_pool.py:1478`, prefix build `:1523-1527`) appends `dir_path.rstrip("/") + "/"` for `src_dir` and `test_dir` to `source_prefixes` (which always also holds `backend/`, `src/`, `lib/`, `tests/`). For `.` the added prefix is `./`, so a worker-leaked root-level file such as `main.go` matches nothing and is **silently not detected**.
- `little_loops.cli.issues.decisions` export (`decisions.py:650-660`) builds `f"{src_dir.rstrip('/')}/**/*"`, yielding `./**/*` for `.` instead of the `**/*` form the no-`src_dir` branch already emits.

**Introspection emits malformed root spellings** (`little_loops.init.introspect`)

- `_pyproject_src_candidate` (`introspect.py:641-653`): `[tool.setuptools.packages.find] where = ["."]` (the documented setuptools flat-layout pattern) returns `"./"`. When it is the sole candidate, `_introspect_src_dir` adopts it as `inferred` and `_introspect_focus_dirs` copies it, so `ll-init` writes `src_dir: "./"` and `focus_dirs: ["./", ...]` today with no manual config — the codegraph defect above fires for real Python projects now, independent of ENH-3616.
- `_tsconfig_src_candidate` (`introspect.py:656-671`): `compilerOptions.rootDir` of `"."` or `"./"` goes through `root_dir.strip('./').split('/')[0]` → `""` and returns **`"/"`** — the filesystem root. `project_root / "/"` resolves to `/` in every `ProjectConfig` path join (e.g. `BRConfig` src path at `core.py:613`, `worktree_utils.py:547`, `prepatch_check.py:291`), and `{{config.project.src_dir}}` interpolation makes `check-code` run `ruff check /`.
- `_tsconfig_src_candidate` include branch: `"include": ["**/*.ts"]` returns **`"**/"`** (the hatch branch strips `*`; this one does not).
- No test covers the pyproject `where` branch or either tsconfig branch (`scripts/tests/test_init_introspect.py::TestSrcDirDetection` has none).

**Checked, not affected**

- `codegraph.py:234` `_dotted_candidates` — guards `prefix != "/"`; for `.` the strip never applies and it returns `[dotted]`, already correct for a root layout.
- `commands/run-tests.md:99` `grep -E '^{{config.project.src_dir}}'` — correct for exactly `.` (`^.` matches every file, and every file is under the source dir). It is **wrong for `./`** (`^./` = any char then `/`, dropping root files); the load-time canonicalization below removes `./` from config-derived interpolation.
- `parallel/file_hints.py:259,280` — `MIN_DIRECTORY_DEPTH = 2` already makes `./` a non-signal.
- `ProjectConfig` path joins, `worktree_utils.py`, `prepatch_check.py`, `code-run-gate.yaml` — `root / "."` resolves to root.

## Steps to Reproduce

1. `_is_scan_relevant("main.go", ["."], [])` → `False` (expected `True`). Same for `["./"]`.
2. With `project.src_dir: "."`, run `ll-parallel` on an issue whose worker writes a stray root-level `main.go` into the main checkout → `_detect_main_repo_leaks` does not report it.
3. With `project.src_dir: "."` and no `decisions.export.scope_globs`, run `ll-issues decisions export` → scope glob is `./**/*`.
4. `ll-init` in a Python project whose `pyproject.toml` has `[tool.setuptools.packages.find] where = ["."]` and no other package marker → `.ll/ll-config.json` gets `src_dir: "./"`.
5. `ll-init` in a TS project whose `tsconfig.json` has `"compilerOptions": {"rootDir": "."}` → `src_dir: "/"`.

## Expected Behavior

A dir value of `.` means "the whole repo", and every root spelling (`.`, `./`, `.//`, `/`) is canonicalized to `.`:

- **Config load**: `ProjectConfig.from_dict` (`src_dir`, `test_dir`) and `ScanConfig.from_dict` (each `focus_dirs` entry) store canonical values: root spellings → `.`; a leading `./` is dropped (`./src/` → `src/`); everything else unchanged, including trailing-slash style (`src/` stays `src/`, `src` stays `src`), `""` (unset), and `..`-relative values.
- **codegraph**: a root focus dir matches every non-excluded path; exclude patterns still win.
- **worker_pool**: a new root-level file that matches *only* because `src_dir`/`test_dir` is `.` is **reported as a warning and never auto-discarded**. See Proposed Solution for why.
- **decisions export**: root `src_dir` emits `**/*` with no stderr warning.
- **introspection**: a root declaration in pyproject `where` or tsconfig `rootDir`/`include` yields `.` — never `./`, `/`, or `**/`.

## Proposed Solution

### Helpers (new leaf module `little_loops.config.dirs`, not re-exported)

The helpers cannot live in `config/core.py`: `core.py` imports `config/features.py` at module level (`core.py:25`), so `ScanConfig.from_dict` in `features.py` importing from `core` would be circular. Put them in a new dependency-free `scripts/little_loops/config/dirs.py`, imported by both `core.py` and `features.py` and by the call sites as `from little_loops.config.dirs import canonical_dir, dir_prefix`. `config/__init__.py:36-38` documents that helper functions are not re-exported — no `__init__.py` or `__all__` change.

```python
def canonical_dir(value: str) -> str:
    """Canonical spelling of a repo-relative dir value; root spellings -> '.'."""
    if not value:
        return value                      # "" = unset; callers decide
    while value.startswith("./") and value != "./":
        value = value[2:]                 # "./src/" -> "src/"
    if value.rstrip("/") in ("", "."):
        return "."                        # ".", "./", ".//", "/"
    return value

def dir_prefix(value: str) -> str:
    """Path prefix for startswith() matching; '' means whole repo."""
    if not value:
        raise ValueError("dir_prefix() requires a non-empty dir; test for unset first")
    value = canonical_dir(value)
    return "" if value == "." else value.rstrip("/") + "/"
```

Rules: "unset" is decided by each caller's existing truthiness guard *before* calling `dir_prefix`, so a `""` return unambiguously means "whole repo". Mapping `/` to `.` is deliberate — a repo-relative dir field can never legitimately be the filesystem root, and `/` only arises from the tsconfig introspection bug above.

### Load-time canonicalization

`ProjectConfig.from_dict` applies `canonical_dir` to `src_dir` and `test_dir`; `ScanConfig.from_dict` applies it to each `focus_dirs` entry. Keep the `type_cmd` default computed from the canonical `src_dir` (`mypy .` for root). This makes `BRConfig.resolve_variable` — and therefore `skill_expander` `{{config.project.src_dir}}` interpolation — see `.` instead of `./`. (Interactive hosts that read `.ll/ll-config.json` directly still see what is on disk; fixing introspection stops `ll-init` writing `./`.)

### Site changes

- **`_is_scan_relevant`**: skip empty entries (today `""` never matches; keep that); for each `d`, `p = dir_prefix(d)`; `p == ""` → return `True` (after the exclude check, which stays first); otherwise `path == p[:-1] or path.startswith(p)`.
- **`_detect_main_repo_leaks`** — the root case must NOT go into `source_prefixes`, and must NOT feed `_cleanup_leaked_files`:
  - `""` in the prefix tuple would make `startswith` match everything *before* the `.issues/` branch, bypassing `_has_other_issue_id` and discarding other workers' issue files.
  - More importantly, `_cleanup_leaked_files` (`worker_pool.py:1556`) runs `git checkout --` on tracked files and `unlink()`s untracked ones, and `_process_issue` calls it unconditionally on the result (`worker_pool.py:689-697`). The main checkout is shared with the operator, so a match-all rule would revert or delete any concurrent edit or new non-ignored file made during a worker run.
  - Rule: compute `root_layout = any(d and dir_prefix(d) == "" for d in (src_dir, test_dir))`; build `source_prefixes` from the non-root dirs only. After the existing `issue-id` / `source_prefixes` / `thoughts/` / `.issues/` branches all decline a path, a `root_layout` match is collected into a separate list and logged once via `self.logger.warning` (issue ID + paths, "not auto-discarded: root-layout src_dir/test_dir"). The method's return value — the cleanup list — excludes these. Signature unchanged.
  - Consequence (accepted): root-layout leaks become visible but are not cleaned, so they can still cause the stash conflicts cleanup exists to prevent — same as today, minus the silence. Auto-cleanup for root layouts is out of scope.
- **`_cmd_export`**: `scope_globs = [f"{dir_prefix(src_dir)}**/*"]` inside the existing `if src_dir:` branch — `src/` and `src` → `src/**/*` (unchanged), root → `**/*`, no warning. The warning stays exclusive to the unset branch.
- **`_pyproject_src_candidate`**: `c = canonical_dir(str(where[0]))`; return `"."` when `c == "."`, else `f"{c.rstrip('/')}/"`.
- **`_tsconfig_src_candidate`**: `rootDir` — `c = canonical_dir(root_dir)`; `"."` → `"."`, else first path segment + `/`. `include` — if the first segment contains a glob character (`*`, `?`, `[`), return `"."` (the include covers the repo root); otherwise first segment + `/`. Leave the hatch branch as is.
- **Do not touch** `_introspect_focus_dirs`: ENH-3616 reworks it (including returning exactly `["."]` for a root src_dir and dropping the redundant `[".", "tests/"]`). After this issue, a root pyproject/tsconfig declaration yields `focus_dirs` of `["."]` or `[".", "tests/"]` — both correct, the latter redundant until ENH-3616.

## Integration Map

### Files to Modify

- `scripts/little_loops/config/dirs.py` (new) — `canonical_dir`, `dir_prefix`; stdlib-only, no `little_loops` imports.
- `scripts/little_loops/config/core.py` — canonicalize in `ProjectConfig.from_dict`.
- `scripts/little_loops/config/features.py` — canonicalize `focus_dirs` in `ScanConfig.from_dict`.
- `scripts/little_loops/codequery/codegraph.py` — `_is_scan_relevant`.
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._detect_main_repo_leaks`.
- `scripts/little_loops/cli/issues/decisions.py` — `_cmd_export` scope-glob fallback.
- `scripts/little_loops/init/introspect.py` — `_pyproject_src_candidate`, `_tsconfig_src_candidate`.

### Dependent Files (no edit)

- `codegraph.py:177`, `:316` — `_is_scan_relevant` callers inherit the fix.
- `worker_pool.py:689-697` — `_process_issue` passes the leak list to `_cleanup_leaked_files`; unchanged because root matches are excluded from that list.
- `scripts/little_loops/skill_expander.py:_substitute_config` — reads via `BRConfig.resolve_variable`, so it picks up canonical values automatically.
- `scripts/little_loops/templates/go.json` — ships `src_dir: "."`; already canonical.

### Documentation

- `docs/reference/API.md` (`## little_loops.config`, `### ProjectConfig` ~`:404`) — document `canonical_dir` and `dir_prefix` (cite `little_loops.config.dirs`), and that `from_dict` canonicalizes dir values.
- `docs/reference/CONFIGURATION.md` — `src_dir` (`:300`), `test_dir` (`:301`), `focus_dirs` (`:483`) rows: `.` = repo root; `./` and other root spellings are normalized to `.`; a leading `./` is dropped.
- `docs/guides/DECISIONS_LOG_GUIDE.md` — `:411-413` and the `decisions.export.scope_globs` table row (`:593`): `src_dir: .` yields `**/*` without the warning.
- `docs/reference/CLI.md:3238` (`--scope-glob` row) — same clarification.

### Tests

- `scripts/tests/test_config.py` — `canonical_dir` and `dir_prefix` tables (see Acceptance Criteria); `ProjectConfig.from_dict({"src_dir": "./", "test_dir": "./"})` → `"."`; `ScanConfig.from_dict({"focus_dirs": ["./", "./src/", "tests/"]})` → `[".", "src/", "tests/"]`.
- `scripts/tests/test_codequery_codegraph.py` — beside the existing focus-dirs tests (~`:315-355`): root match-all, exclude still wins, non-root unchanged, `[""]` matches nothing, `_dotted_candidates(..., ".")` pinned to `[dotted]`.
- `scripts/tests/test_worker_pool.py` — beside `test_detect_main_repo_leaks_uses_configured_src_dir`: root-layout warn-only, cross-worker `.issues/` file, issue-ID file still returned.
- `scripts/tests/test_cli_decisions.py` — root `src_dir` → `**/*`, no stderr warning.
- `scripts/tests/test_init_introspect.py::TestSrcDirDetection` — pyproject `where`, tsconfig `rootDir` / `include` cases.

Existing tests that must keep passing: `test_worker_pool.py::test_detect_main_repo_leaks_uses_configured_src_dir` (`src_dir: "scripts/"`), `test_cli_decisions.py::test_config_scope_globs_overrides_src_dir` (`src_dir: "src/"`), `test_codequery_codegraph.py`, `test_decisions_export.py`, `test_config.py`, `test_init_introspect.py`.

## Program Design

### Types

- No new types; dir values stay `str`.

### Signatures

- `canonical_dir(value: str) -> str` — new public helper in `little_loops.config.dirs`; root spellings to `.`, leading `./` dropped, `""` and other values unchanged
- `dir_prefix(value: str) -> str` — new public helper in `little_loops.config.dirs`; `""` for a root dir, else the canonical value with exactly one trailing slash; raises `ValueError` on `""`
- `_is_scan_relevant(path: str, focus_dirs: list[str], exclude_patterns: list[str]) -> bool` — unchanged signature; a root focus dir matches every non-excluded path
- `WorkerPool._detect_main_repo_leaks(self, issue_id: str, baseline_status: set[str]) -> list[str]` — unchanged signature; root-only matches are logged and excluded from the return value
- `_cmd_export(config, args, path) -> int` — unchanged signature; emits `**/*` for a root `src_dir`

### Call Path

`ProjectConfig.from_dict` -> `canonical_dir`; `ScanConfig.from_dict` -> `canonical_dir`; `dir_prefix` -> `canonical_dir`; `_is_scan_relevant` -> `dir_prefix`; `WorkerPool._detect_main_repo_leaks` -> `dir_prefix`; `_cmd_export` -> `dir_prefix`; `_pyproject_src_candidate` -> `canonical_dir`; `_tsconfig_src_candidate` -> `canonical_dir`

### Decision Rules

- Root classification: `canonical_dir(v) == "."` iff `v`, after dropping leading `./` segments, rstrips to `""` or `.`. `..`-relative values are never root.
- Worker-pool root matches: warn, never discard (see Proposed Solution).
- Decisions export: the "no src_dir" warning fires only when `src_dir` is unset, never for root.

## Implementation Steps

1. Add `canonical_dir` / `dir_prefix` in new `config/dirs.py` with unit tests (TDD: tests first).
2. Canonicalize in `ProjectConfig.from_dict` and `ScanConfig.from_dict`; tests.
3. Update `_is_scan_relevant`; tests including the `_dotted_candidates` pin.
4. Update `_detect_main_repo_leaks` per the warn-only rule; tests.
5. Update `_cmd_export`; tests.
6. Fix `_pyproject_src_candidate` and `_tsconfig_src_candidate`; tests.
7. Update API.md, CONFIGURATION.md, DECISIONS_LOG_GUIDE.md, CLI.md.
8. `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`, `ruff format` on changed files only.

## Impact

- **Priority**: P3 — affects Go projects today (worker_pool, decisions export), Python setuptools-flat and TS `rootDir: "."` projects today via `ll-init` (codegraph; `src_dir: "/"` for TS), and every flat-layout project once ENH-3616 lands.
- **Effort**: Small — one new two-function module, two loaders, five call sites, docs.
- **Risk**: Low. Load-time canonicalization changes the stored value only for root spellings and leading `./`; worker-pool change is additive (warning) and never widens cleanup.
- **Breaking Change**: No.

## Acceptance Criteria

- [ ] `canonical_dir`: `.`, `./`, `.//`, `/` → `.`; `./src/` → `src/`; `./src` → `src`; `src/` → `src/`; `src` → `src`; `""` → `""`; `..` → `..`; `../x` → `../x`.
- [ ] `dir_prefix`: `.`, `./`, `/` → `""`; `src`, `src/`, `./src` → `src/`; `""` raises `ValueError`.
- [ ] `ProjectConfig.from_dict` and `ScanConfig.from_dict` store canonical values; `src/`, `scripts/`, `tests` round-trip unchanged.
- [ ] `_is_scan_relevant` returns True for a root file (`main.go`) and a file nested one dir deep, with `focus_dirs` `["."]` and `["./"]`; False when an exclude pattern matches; `["src/"]` still matches the bare path `src` and a file under it but not a file under a sibling dir named `srcx`; `[""]` matches nothing.
- [ ] `_dotted_candidates("pkg/b.py", ".")` returns `["pkg.b"]` (pin).
- [ ] With `src_dir: "."`, a new root-level `main.go` is NOT in `_detect_main_repo_leaks`' return value and IS named in a `logger.warning` call; same with `test_dir: "."`.
- [ ] With `src_dir: "."`, a new issue file under `.issues/bugs` whose name carries a different issue ID is not returned; a new file containing the worker's own issue ID is returned; a new `.py` file under the `src` fallback prefix is returned.
- [ ] Decisions export with no configured scope globs emits `["**/*"]` and no stderr warning for `src_dir` `.` and `./`; `src/` and `src` emit `["src/**/*"]`.
- [ ] Introspection: pyproject `where = ["."]` → `src_dir` `"."`; tsconfig `rootDir` `"."` and `"./"` → `"."`; tsconfig `include: ["**/*.ts"]` → `"."`; `include: ["src/**/*"]` → `"src/"`; `rootDir: "src"` → `"src/"`.
- [ ] API.md, CONFIGURATION.md (`src_dir`, `test_dir`, `focus_dirs` rows), DECISIONS_LOG_GUIDE.md (`:411-413`, `:593`) and CLI.md `:3238` describe `.` as repo root.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related

- Blocks ENH-3616 (which will emit `.` for Python/JS/generic flat layouts and owns the `_introspect_focus_dirs` rework).
- BUG-3635 — `commands/manage-release.md` version-file paths (split out of this issue).

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-27T06:24:00 - `d1ce99b0-6533-4a9f-af3f-f35128797a41.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:57:53 - `d9cc873e-f17d-4bf9-b8ac-9770c6d93a16.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-27T05:43:06 - `bf6e1e8c-2c0c-4865-99bf-f1fcae8fc265.jsonl`
- `/ll:reconcile-issue` - 2026-09-27T05:38:00 - `48e27ed8-8bad-43ec-ade3-1d77009a2e15.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:35:45 - `e18b63f4-fc4d-4093-b00f-89d5c0e394ec.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-27T05:23:02 - `aae621bb-c067-4881-b3ce-b0e08bc3edb0.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:21:25 - `2bf90db8-8241-42d1-a2f3-16851c36676b.jsonl`
- `/ll:verify-issues` - 2026-09-27T05:20:08 - `2bf90db8-8241-42d1-a2f3-16851c36676b.jsonl`
- `/ll:wire-issue` - 2026-09-27T05:19:22 - `456ac708-7949-4003-8fee-84b53705067e.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:18:02 - `09cdddd4-4608-4727-809d-efaaa771aaf2.jsonl`
