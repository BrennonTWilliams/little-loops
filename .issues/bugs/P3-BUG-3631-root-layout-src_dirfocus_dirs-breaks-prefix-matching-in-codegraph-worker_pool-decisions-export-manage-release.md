---
id: BUG-3631
type: BUG
title: Root-layout '.' src_dir/focus_dirs breaks prefix matching in codegraph, worker_pool,
  decisions export, manage-release
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T05:09:09Z'
blocks:
- ENH-3616
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

## Impact

- **Priority**: P3 — affects Go projects today and every flat-layout project once ENH-3616 lands.
- **Effort**: Small — three prefix sites plus one command doc.
- **Risk**: Low.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `_is_scan_relevant(path, focus_dirs=["."], ...)` returns True for a repo-relative path not matched by exclude patterns.
- [ ] `worker_pool` leaked-file detection flags a new root-level file when `src_dir` is `.`.
- [ ] decisions export with `src_dir: "."` and no configured scope globs emits `**/*`.
- [ ] `manage-release.md` version-file paths are correct for `src_dir: "."`.
- [ ] Existing behavior for trailing-slash values (`src/`, `scripts/`) unchanged.

## Related

- Blocks ENH-3616 (which will emit `.` for Python/JS/generic flat layouts).

## Status

**Open** | Created: 2026-09-27 | Priority: P3
