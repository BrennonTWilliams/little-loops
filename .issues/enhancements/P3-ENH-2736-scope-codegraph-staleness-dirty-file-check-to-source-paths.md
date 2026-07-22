---
id: ENH-2736
type: enhancement
status: done
priority: P3
captured_at: '2026-07-22T17:06:04Z'
completed_at: '2026-07-22T17:39:25Z'
discovered_date: 2026-07-22
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2736: Scope codegraph staleness dirty-file check to source-relevant paths

## Summary

`ll-code status` (via `CodegraphProvider.status()`) reports the codegraph index
as `stale` even when the index content is fully current, because the
staleness check counts *every* line of `git status --porcelain` output
repo-wide — including untracked/dirty files that have nothing to do with
source code (e.g. `.ll/decisions.d/*.json` fragments).

## Current Behavior

In `scripts/little_loops/codequery/codegraph.py`, `status()` computes:

```python
dirty_raw = _git(root, "status", "--porcelain")
dirty_files = len(dirty_raw.splitlines()) if dirty_raw else 0

is_fresh = head_moved == 0 and dirty_files == 0
```

`dirty_files` is a raw count of all porcelain lines with no path filtering.
Observed live: two untracked `.ll/decisions.d/*.json` fragments made
`ll-code status` report `freshness: stale` immediately after a fresh
`codegraph sync` (`head_moved=0`, `indexed_at` current), because
`dirty_files=2`. The index was in fact fully up to date — the signal was a
false positive.

## Expected Behavior

The dirty-file check should only count files that are relevant to the
indexed source tree (i.e. paths that would affect `nodes`/`edges` content —
tracked source files matching the provider's scan scope), not every
untracked/modified file anywhere in the repo. Non-code paths such as
`.ll/`, `.issues/`, `thoughts/`, and other config/metadata directories
should not be able to flip freshness to `stale` on their own.

## Motivation

A staleness signal that can be tripped by unrelated files (decision logs,
scratch notes, issue files) undermines trust in `ll-code status`: users see
`stale` and either ignore it (defeating the point of the check) or waste
time re-syncing an index that was never actually behind. Under
`policy: strict` this is worse — it would make the codegraph provider report
`available: false` and silently fall back to the grep/AST provider for a
reason unrelated to code staleness at all.

## Proposed Solution

Filter `git status --porcelain` output before counting, keeping only paths
that fall under the provider's effective scan scope (e.g. reuse
`scan.focus_dirs`/`scan.exclude_patterns` from `BRConfig`, or restrict to
extensions/paths the codegraph index actually covers per its `files` table
languages). Alternatively, cross-reference dirty paths against
`SELECT path FROM files` in the codegraph DB — only count a dirty file as
staleness-relevant if it's a path the index tracks.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Option A**: Filter porcelain output by `scan.focus_dirs`/`scan.exclude_patterns`
from `BRConfig`. `CodegraphProvider._config()` (`codegraph.py:113-116`)
already does `BRConfig(_git_root()).code_query` — `status()` would add a
sibling read of `.scan` (`BRConfig(_git_root()).scan`, exposed via the
`scan` property at `config/core.py:286-288`) and apply
`ScanConfig.focus_dirs`/`exclude_patterns` (`config/features.py:290-310`,
defaults `["src/", "tests/"]` / `["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]`)
as a path filter before counting `dirty_raw.splitlines()`. No runtime
consumer of `scan.focus_dirs`/`exclude_patterns` exists yet anywhere in the
codebase — today they're read only by `init`-time tooling
(`init/tui.py`, `init/introspect.py:_introspect_focus_dirs()`) — so this
filter would be new code, not a reuse of an existing scope-matcher. The
closest reusable primitive for the glob half is `_file_matches_pattern()`
in `git_operations.py:266` (fnmatch-based, gitignore-pattern-style,
already used against `get_untracked_files()` porcelain output at
`git_operations.py:195-232`); for a directory-prefix style filter, the
established pattern is `EXCLUDED_DIRECTORIES` /
`filter_excluded_files()` in `work_verification.py:18,28` (plain
`str.startswith(prefix)` against a hardcoded tuple, applied to
`git diff --name-only` output), re-exported from `git_operations.py:15-19`.

> **Selected:** Option A (scan.focus_dirs/exclude_patterns filter) — reuses the already-loaded `BRConfig` at the exact call site and two existing matching-primitive helpers, with a directly reusable test fixture and no structural correctness gap.

**Option B**: Cross-reference dirty paths against `SELECT path FROM files`
in the codegraph DB. The `files` table schema (documented in the
`codegraph.py` module docstring, lines 5-17) is
`files(path, content_hash, language, size, modified_at, indexed_at, node_count, errors)`
— a `path` column already exists, but `status()` today only ever
aggregates `MAX(indexed_at)` from it (line 137); no code path selects
`files.path` values. This option is self-contained (no config coupling,
automatically matches whatever the index actually covers) but requires a
new query and only knows about *already-indexed* files — a newly-added
source file that hasn't been indexed yet would not appear in `files.path`
and so a dirty status on it would be silently ignored rather than flagged
stale (a correctness gap Option A doesn't have, since `scan.focus_dirs`
covers new files under the scanned tree regardless of index state).

**Recommended**: Option A (`scan.focus_dirs`/`exclude_patterns`) — for v1.
It matches the issue's stated intent ("paths that fall under the
provider's effective scan scope") and correctly flags stale on new
untracked source files, which Option B structurally cannot detect. It also
reuses the same `BRConfig` instance already loaded in `_config()`, so the
`status()` change is additive (one extra property access) rather than a
DB schema/query addition. Compose with `EXCLUDED_DIRECTORIES`-style
prefix filtering for the metadata directories the issue calls out (`.ll/`,
`.issues/`, `thoughts/`) even if `scan.exclude_patterns` doesn't already
cover them by default — `ScanConfig.exclude_patterns`'s default list
(`**/node_modules/**`, `**/__pycache__/**`, `**/.git/**`) does not include
`.ll/`, `.issues/`, or `thoughts/`, so those must be added to this
project's `.ll/ll-config.json` `scan.exclude_patterns` (or the default
list updated) for the fix to actually suppress the reported false
positive — filtering logic alone is not sufficient without matching
config.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-22.

**Selected**: Option A (scan.focus_dirs/exclude_patterns filter)

**Reasoning**: Option A composes existing primitives at the exact call site — `BRConfig(_git_root()).scan` is a sibling read next to the already-loaded `code_query` config in `CodegraphProvider._config()`, and both a glob matcher (`_file_matches_pattern()`) and a prefix matcher (`filter_excluded_files()`/`EXCLUDED_DIRECTORIES`) already exist in the codebase for filtering git-derived file lists. Option B has zero existing call sites for `SELECT path FROM files` cross-referencing, bypasses the established `_config()` pattern, and structurally cannot flag staleness on newly-added, not-yet-indexed source files — a correctness gap Option A doesn't have.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (scan.focus_dirs/exclude_patterns) | 2/3 | 2/3 | 3/3 | 3/3 | 10/12 |
| Option B (files table cross-reference) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: `BRConfig` already loaded at `codegraph.py:113-116`; `_file_matches_pattern()` (`git_operations.py:266`) and `EXCLUDED_DIRECTORIES`/`filter_excluded_files()` (`work_verification.py:18,28`) are existing, actively-used filter helpers; `TestStalenessMatrix` fixture (`test_codequery_codegraph.py:76-289`) is directly reusable for the new test.
- Option B: only existing `files` table query is an unrelated `MAX(indexed_at)` aggregate (`codegraph.py:137`); no "is path indexed" utility exists; silently misses dirty-but-unindexed new source files, the exact gap the issue's own research (lines 102-106) flagged as disqualifying.

## Integration Map

### Files to Modify
- `scripts/little_loops/codequery/codegraph.py` — `CodegraphProvider.status()`
  (lines 122-192, specifically the `dirty_raw`/`dirty_files` computation at
  lines 157-158 and the `is_fresh` check at line 160). `status()` already
  calls `self._config()` for `code_query`; add a sibling `BRConfig(_git_root()).scan`
  read and filter `dirty_raw.splitlines()` through it before counting.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/codequery/core.py` — `resolve_provider("auto")`
  (lines 103-123) picks the first provider whose `status().available` is
  `True`; under `policy: strict` a false-positive `stale` currently makes
  `available=False` and silently falls through to `FallbackProvider`
  (grep/AST) instead of the SQLite index — this is the concrete downstream
  breakage the fix resolves.
- `scripts/little_loops/cli/code.py` (lines 109-128) — `ll-code status`
  prints/serializes `available`/`freshness`/`detail` directly from
  `status()`.

### Config
- `.ll/ll-config.json` — `scan.focus_dirs`/`scan.exclude_patterns`
  (`ScanConfig`, `scripts/little_loops/config/features.py:290-310`) is the
  scope source the fix reads from. Default `exclude_patterns` does not
  include `.ll/`, `.issues/`, or `thoughts/` — verify/update this project's
  config alongside the code change or the reported false positive will
  persist.
- `code_query.staleness` (`CodeQueryConfig`, `config/features.py:829-844`)
  — the `strict`/`warn`/`off` policy already consumed by `status()`,
  unaffected by this change but relevant context for why `strict` is the
  policy that actually breaks under the bug.

### Tests
- `scripts/tests/test_codequery_codegraph.py` — `TestStalenessMatrix.test_dirty_tree_marks_stale_per_policy`
  (lines 327-340) currently asserts ANY dirty file (a `README.md` edit)
  marks the index stale under `strict`/`warn`; this test's fixture
  (`_repo_with_fresh_index`, `_write_config`, `_init_repo`, `_commit_at` —
  lines 87-289) is the direct model for a new test asserting a dirty file
  *outside* `scan.focus_dirs` (e.g. writing to `.ll/decisions.d/foo.json`
  instead of `README.md`) leaves `freshness == "fresh"`. No mocking is used
  in this file — all tests run against a real `tmp_path` git repo via
  `monkeypatch.chdir(repo)`, which the new test should follow.
- `scripts/tests/test_cli_code.py` — covers `ll-code status` output;
  extend if the CLI's status detail text changes shape.

### Documentation
- `docs/reference/API.md` (lines ~8621-8667) — documents
  `CodeQueryProvider` protocol and `CodegraphProvider.status()` freshness
  semantics; update the staleness description if the dirty-file scope
  changes what `stale` means.

## Impact

- **Priority**: P3 - Not blocking (default `policy: warn` still serves
  results), but produces a persistently misleading signal and would degrade
  functionality under `policy: strict`.
- **Effort**: Small - localized to `CodegraphProvider.status()` in
  `scripts/little_loops/codequery/codegraph.py`.
- **Risk**: Low - read-only status computation, no schema or provider
  interface changes.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/reference/API.md | Documents `little_loops.codequery` provider protocol and `CodegraphProvider.status()` freshness semantics |

## Session Log
- `/ll:manage-issue` - 2026-07-22T17:38:56Z - `331fe26d-b607-4831-9850-9e904c9c469c.jsonl`
- `/ll:ready-issue` - 2026-07-22T17:32:44 - `a4de3802-c496-4d73-b328-bd8ac73ddbc9.jsonl`
- `/ll:confidence-check` - 2026-07-22T17:31:17 - `bd2e48f1-8274-4cce-84ca-e4205b6ae5df.jsonl`
- `/ll:decide-issue` - 2026-07-22T17:28:44 - `98daa12d-eaff-488a-bc7e-2c774da8f712.jsonl`
- `/ll:refine-issue` - 2026-07-22T17:25:49 - `fe743be7-55ce-40c2-9c24-338fd1d2275d.jsonl`
- `/ll:capture-issue` - 2026-07-22T17:06:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cc696539-106a-4954-8d48-1f64b8a112c0.jsonl`

---

## Status

**Open** | Created: 2026-07-22 | Priority: P3
