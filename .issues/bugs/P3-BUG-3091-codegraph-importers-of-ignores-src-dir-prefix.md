---
id: BUG-3091
title: CodegraphProvider.importers_of/impact_of can't resolve paths nested under project.src_dir
type: BUG
priority: P3
captured_at: '2026-08-06T20:15:36Z'
completed_at: '2026-08-06T23:38:34Z'
discovered_date: 2026-08-06
discovered_by: session
status: done
testable: true
verify_verdict: VALID
labels:
- bug
- codequery
- codegraph
relates_to:
- ENH-3092
decision_needed: false
learning_tests_required:
- codegraph
confidence_score: 95
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3091: `CodegraphProvider.importers_of`/`impact_of` can't resolve paths nested under `project.src_dir`

## Summary

`CodegraphProvider.importers_of()` guesses a dotted module name from a repo-relative
file path (`_module_to_file_guess` / the `dotted_guess` local in `importers_of()`,
`scripts/little_loops/codequery/codegraph.py:195-199,403-440`) by taking the path
verbatim relative to the **repo root**. But the `codegraph` tool indexes import
`qualified_name`s relative to the project's **source root** (this repo's
`project.src_dir: "scripts/"`), so every lookup for a path under `src_dir` fails to
match and silently returns no results.

`impact_of()` (added this session, wired on top of `importers_of()`) inherits this
gap directly, since it's a transitive walk of the same relation.

## Current Behavior

```
$ sqlite3 .codegraph/codegraph.db "select qualified_name from nodes where kind='import' and qualified_name like '%issue_manager%'"
little_loops.issue_manager
```

But:

```
$ ll-code --json importers-of scripts/little_loops/issue_manager.py
{"provider": "codegraph", "freshness": "stale", "query": "importers_of", "results": []}
$ ll-code --json impact-of scripts/little_loops/issue_manager.py --depth 1
{"provider": "codegraph", "freshness": "stale", "query": "impact_of", "results": []}
```

despite `issue_manager` being imported by many files in this repo (confirmed via
`edges.kind='imports'` count and direct grep). `_module_to_file_guess("scripts/little_loops/issue_manager.py")`
produces the dotted guess `scripts.little_loops.issue_manager`, which never matches
the index's `little_loops.issue_manager` (indexed relative to `scripts/`, the
project's `src_dir`).

## Steps to Reproduce

1. In a project with `project.src_dir` set to a non-root package directory (this
   repo: `"scripts/"`), build/refresh the `codegraph` index.
2. Run `ll-code --json importers-of <path under src_dir>` for a module known to
   have importers (e.g. `scripts/little_loops/issue_manager.py`).
3. Observe `results: []` even though `edges.kind='imports'` rows referencing that
   module exist in `.codegraph/codegraph.db`.
4. Run `ll-code --json impact-of <same path>` — also `results: []`, since
   `impact_of()` is a transitive walk of `importers_of()`.

## Expected Behavior

`importers_of()` (and transitively `impact_of()`) should strip the configured
`project.src_dir` prefix before computing the dotted-module guess, so file paths
that are valid arguments to `defines`/`callers-of`/etc. also resolve correctly here.

A package `__init__.py` path must resolve to the **package** qualified name, not a
`.__init__`-suffixed one — the index stores packages as bare qnames. Verified against
this repo's `.codegraph/codegraph.db`:

```
qualified_name = 'little_loops.config'          → 92 importer nodes
qualified_name = 'little_loops.config.__init__' →  0 (never indexed)
```

So `importers-of scripts/little_loops/config/__init__.py` returns `[]` both today
*and* after a src_dir strip alone. `__init__.py` paths are a common input: they
appear in the "Files to Modify" lists `wire-issue` feeds to these queries.

## Root Cause

- **File**: `scripts/little_loops/codequery/codegraph.py:194-198` (`_module_to_file_guess`)
  and `:395-432` (`importers_of`) — both operate on the path as given (repo-relative),
  with no knowledge of `BRConfig(...).project.src_dir`.
- The `codegraph` external tool indexes files/imports relative to whatever root it
  was pointed at (this repo's project root), but Python import statements are
  naturally relative to the *package* root (`scripts/`), not the repo root — so the
  qualified names in the index never carry the `scripts.` prefix.

## Proposed Solution

In `importers_of()` (and the shared guess helper), read `project.src_dir` from
`self._config()`'s owning `BRConfig` (already fetched via `self._config()` for
other methods) and strip it from the front of the repo-relative path before
building `dotted_guess`. Should also try the un-stripped guess as a fallback for
providers/repos where `src_dir` is unset or `"."`, so behavior is unchanged for
projects with no src layout.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- **Files to Modify**
  - `scripts/little_loops/codequery/codegraph.py:408-414` — `importers_of()` must also match a src_dir-stripped dotted guess. `dotted_guess` is computed at line 409 from the repo-relative `file_guess`; the OR-candidate set at lines 410-414 (`dotted_guess`, `module`, `_short_symbol(module)`) must keep all three existing candidates and add the stripped guess.
  - `scripts/little_loops/codequery/codegraph.py:432` — the `symbol=row["sym"] or dotted_guess` fallback should prefer the candidate that actually matched so `CodeRef.symbol` carries the index's src-relative name, not the repo-root-relative one.
  - `scripts/little_loops/codequery/codegraph.py:499-530` — `impact_of()` needs no change; it is a transitive BFS over `importers_of()` (line 514) and inherits the fix.
- **Dependent Files (Callers/Importers)**
  - `scripts/little_loops/cli/code.py:136` — `ll-code importers-of` passes `args.module` to `provider.importers_of()` verbatim; no path normalization at the CLI boundary.
  - `scripts/little_loops/cli/code.py:142` — `ll-code impact-of <paths> --depth N` passes `args.paths` to `provider.impact_of()` verbatim.
  - `scripts/little_loops/codequery/core.py:20-29,87,90` — `QUERY_KINDS` includes both `importers_of` and `impact_of`; the `CodeQueryProvider` Protocol declares both. Any signature change must keep the Protocol contract.
  - `scripts/little_loops/codequery/fallback.py:217,240` — `FallbackProvider` implements both; it tolerates a src_dir prefix because it matches on the last dotted segment only. The two providers already diverge on the path→module contract — a decision to make knowingly, not a template to copy.
  - `skills/wire-issue/graph-discovery-layer.md:29-30` — downstream consumer passes repo-relative "Files to Modify" paths to these queries.
- **Conventions in Force**
  - Directory-membership checks normalize `src_dir` with `.rstrip("/")` before `==`/`startswith(dir + "/")` — evidence: `scripts/little_loops/git_operations.py:320-323`, `scripts/little_loops/codequery/codegraph.py:121`, `scripts/little_loops/parallel/worker_pool.py:1431-1434`.
  - The provider reads project-level settings by building a fresh `BRConfig(root)` locally, not through `_config()` (which returns only `.code_query`) — evidence: `scripts/little_loops/codequery/codegraph.py:267-269` (`scan = BRConfig(root).scan`).
  - Import-node lookup already uses a multi-candidate OR against `nodes.qualified_name`/`name` — evidence: `scripts/little_loops/codequery/codegraph.py:410-414`; the fix is an additional candidate, not a replacement.
- **Tests**
  - `scripts/tests/test_codequery_codegraph.py` — existing suite. `importers_of` tests at lines 632-643; `impact_of` one-hop/no-hits at 649-658; `TestImpactOfTransitive` at 661-695.
  - Fixture `_build_index()` (lines 185-210) already encodes the mismatch: import node `qualified_name="pkg.b"` (line 203) is src-relative while `file_path="pkg/a.py"` (line 202) is repo-relative.
  - `_write_config()` (lines 213-221) writes only `{"code_query": ...}` — a regression test must write `project.src_dir` (e.g. `"scripts/"`) so the stripped candidate is exercised. Precedent for that config shape exists across the suite (`test_worker_pool.py`, `conftest.py`, `test_issue_parser.py`).
  - `TestSchemaGuard` (class at `test_codequery_codegraph.py:224`; `_SCHEMA_COLUMNS` pin at lines 31-48) pins the codegraph DB schema and must keep passing.
- **Documentation**
  - `docs/reference/CLI.md:2546,2549` — `importers-of`/`impact-of` rows.
  - `docs/reference/CONFIGURATION.md:297` — `project.src_dir` row.
  - `docs/reference/API.md:9617` — `CodegraphProvider` row.
- **Configuration**
  - `project.src_dir` — `.ll/ll-config.json:6` sets `"scripts/"`; default `"src/"` per `scripts/little_loops/config-schema.json:20-24` and `scripts/little_loops/config/core.py:153`.
  - `BRConfig.project` property — `scripts/little_loops/config/core.py:291-292`; `BRConfig.get_src_path()` — `config/core.py:500-502`.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/codequery/__init__.py` — package facade re-exporting `QUERY_KINDS`, `CodeQueryProvider`, `CodeRef`, `ProviderStatus`, `resolve_provider`; the fix adds no new public names, so no edit needed (informational) [Agent 1 finding]
- `skills/wire-issue/SKILL.md:142` — Phase 3.6 gate consumer invoking `ll-code --json importers-of`/`impact-of`; generated host mirrors `.kimi-code/skills/wire-issue/SKILL.md:141` and `.gemini/skills/wire-issue/SKILL.md:141` carry the same flow. Reads `results[].path`, `freshness`, and exit codes — the fix preserves the JSON/exit-code contract, so no edit needed [Agent 1/2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py:2556-2572` — the only place in the suite where `project.src_dir` and a `code_query` block coexist in one `ll-config.json`; the exact shape `_write_config()` (currently `test_codequery_codegraph.py:213-221`) must grow to for the regression test [Agent 3 finding]
- `scripts/tests/test_worker_pool.py:1771-1785` — precedent for a `BRConfig(tmp_path)` + `project.src_dir` fixture (`json.dumps({"project": {"src_dir": "scripts/", ...}})`) [Agent 3 finding]
- `scripts/tests/test_issue_parser.py:1867` — inline `BRConfig` + `project.src_dir` config-writer pattern [Agent 3 finding]
- `scripts/tests/test_codequery_fallback.py:94-118` — pins `FallbackProvider.importers_of`/`impact_of` behavior; evidence of the cross-provider path→module divergence the Decision Rules call out — no edit needed, but must stay green [Agent 2/3 finding]
- `scripts/tests/test_cli_code.py` — CLI exit-code/JSON contract surface (`status`/`defines` only; no `importers-of`/`impact-of` case today); an optional CLI-layer regression test for the src_dir fix would land here [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2537,2551-2552` — documents the `ll-code --json` output shape and exit-code contract (`0`=hits, `1`=no hits, `2`=error); the fix preserves both — contract surface only, no edit needed [Agent 2 finding]
- `docs/reference/API.md:9587-9600` — `CodeQueryProvider` Protocol signature block; `importers_of`/`impact_of` signatures are unchanged by the fix [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:1035-1047` — `code_query` block description; no src_dir→path-resolution note exists here today (informational) [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/features.py:818-848` — `CodeQueryConfig`/`CodeQueryCodegraphConfig` dataclasses; confirms `src_dir` lives outside the `code_query` block, so the fix (reading `project.src_dir` via a fresh `BRConfig`) requires no schema or dataclass change [Agent 2 finding]

## Program Design

### Types

- `ProjectConfig.src_dir: str` — trailing-slash dir string; default `"src/"` (`scripts/little_loops/config/core.py:153`), this repo `"scripts/"` (`.ll/ll-config.json:6`). Must be normalized with `.rstrip("/")` before any prefix comparison (convention at `scripts/little_loops/git_operations.py:320-323`).
- `CodeRef.symbol: str` — **fallback branch only.** At `codegraph.py:432` the expression is `row["sym"] or dotted_guess`, and `row["sym"]` is `src.qualified_name` — the *importing* node's symbol, not the imported module. Do **not** replace `row["sym"]`. Only the `or`-fallback (used when the source node has a NULL `qualified_name`) should carry the candidate that actually matched — the index's src-relative name (e.g. `little_loops.issue_manager`) rather than the repo-root-relative `dotted_guess`.

### Signatures

- `_module_to_file_guess(module: str) -> str` — `scripts/little_loops/codequery/codegraph.py:195-199`; dotted module → repo-relative `.py` path (passthrough for `.py`). Sole caller: `importers_of` (line 408).
- `CodegraphProvider.importers_of(module: str) -> list[CodeRef]` — `codegraph.py:403-440`; `dotted_guess` built at line 409, OR-candidate SQL at lines 410-414.
- `CodegraphProvider.impact_of(paths: list[str], depth: int = 2) -> list[CodeRef]` — `codegraph.py:499-530`; transitive BFS over `importers_of`, no own path manipulation.
- `CodegraphProvider._config() -> CodeQueryConfig` — `codegraph.py:217-220`; returns only `.code_query`. Reading `project.src_dir` requires a fresh `BRConfig(_git_root())` (pattern at `codegraph.py:267-269`).

### Call Path

- `ll-code importers-of <path>` → `scripts/little_loops/cli/code.py:136` → `CodegraphProvider.importers_of(module)` → `_module_to_file_guess` (line 408) → `dotted_guess` (line 409) → SQL over `nodes`/`edges` (lines 410-427).
- `ll-code impact-of <paths> --depth N` → `cli/code.py:142` → `impact_of(paths, depth)` → `importers_of(path)` per frontier element (line 514).

### Decision Rules

- New path→module transformation: when the repo-relative `file_guess` starts with the configured `project.src_dir` (normalized as `src_dir.rstrip("/") + "/"`), strip that prefix before converting slashes to dots, and add the stripped dotted guess as an **additional** OR candidate while retaining the un-stripped `dotted_guess` as fallback — projects with `src_dir` unset/default (`"src/"`) or `"."` see no behavioral change because the strip is a no-op for paths not under `src_dir`.
- Package-`__init__` normalization: when the repo-relative `file_guess` basename is `__init__.py`, the dotted form must drop the trailing `.__init__` segment so it resolves to the package qname the index actually stores (`little_loops.config`, not `little_loops.config.__init__`). Applies to both the stripped and un-stripped candidates, and is independent of `src_dir` — a root-layout project has the same defect.
- `impact_of` introduces no independent decision — it inherits the candidate set through `importers_of`.
- Out of scope (measured, not assumed): relative-import nodes are indexed under their literal dotted form (`.core`, `.writer`) and are unreachable by any absolute-path candidate. This repo's index has 6 such nodes out of 4446 (`select case when qualified_name like '.%' ...`), all from non-Python sources. Not worth a candidate; do not expand scope to cover it.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

1. `importers_of()` resolves a repo-relative `.py` path under `project.src_dir` (e.g. `scripts/little_loops/issue_manager.py`) by also matching a src_dir-stripped dotted guess against `nodes.qualified_name`; the existing candidates at `codegraph.py:410-414` (`dotted_guess`, `module`, `_short_symbol(module)`) remain, so today's passing lookups keep working.
2. The `CodeRef.symbol` emitted for matched importers (`codegraph.py:432`) carries the index's src-relative `qualified_name` when the stripped candidate is the match, not the repo-root-relative `dotted_guess`.
3. `impact_of()` returns non-empty transitive results for the same inputs through its existing `importers_of()` walk (`codegraph.py:514`); `impact_of` itself is unchanged.
4. A regression test in `scripts/tests/test_codequery_codegraph.py` exercises the fixture mismatch (`qualified_name="pkg.b"` at line 203 vs `file_path="pkg/a.py"` at line 202) with a `project.src_dir`-bearing config; verified by `python -m pytest scripts/tests/test_codequery_codegraph.py -v`.
   > ⚠ Superseded — existing fixture resolves via un-stripped guess; strip not load-bearing
5. `TestSchemaGuard` (`test_codequery_codegraph.py:224`) and the existing `TestQueries`/`TestImpactOfTransitive` (lines 591-695) pass unchanged — the fix is additive against the pinned schema.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

```text
- A second regression test must cover the package-`__init__` case: an index row with import `qualified_name="pkg"` (bare package) and a query of `scripts/pkg/__init__.py` under `src_dir="scripts/"`, asserting non-empty. This case fails both before *and* after a src_dir-strip-only fix, so it is not covered by the test below.
- In `scripts/tests/test_codequery_codegraph.py`, the regression test must force the strip path with index rows whose `qualified_name` excludes the `src_dir` prefix while `file_path` includes it (e.g. `file_path="scripts/pkg/a.py"`, `qualified_name="pkg.b"`, query `scripts/pkg/b.py` with `src_dir="scripts/"`) — the current fixture row (`qualified_name="pkg.b"`, `file_path="pkg/a.py"`) already resolves via the un-stripped `dotted_guess` and the `_short_symbol` candidate, so adding `src_dir` to `_write_config()` alone does not exercise the stripped candidate.
```
- No caller, registration, or schema changes are required: the fix adds no new public symbols, changes no `CodeQueryProvider` Protocol signatures, and alters no `--format json` fields or exit codes.

## Impact

- **Priority**: P3 — degrades an already-optional acceleration path (`ll-code`
  always has a working, if slower, `fallback` provider); not user-facing breakage,
  but silently makes `importers_of`/`impact_of` return false negatives (empty
  results, not errors) for any project using a `src_dir` layout — including this
  repo.
- **Effort**: Small — one path-prefix-stripping fix, localized to `codegraph.py`.
- **Risk**: Low — additive resolution attempt; existing successful lookups keep
  working.

## Related Key Documentation

- [[ENH-3090]] — added `impact_of` to `CodegraphProvider`; this bug was discovered
  while verifying that change against this repo's real `.codegraph/codegraph.db`
  index.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- Stale cross-reference: the body credits `[[ENH-3090]]` with adding `impact_of`, but on-disk ENH-3090 (`P3-ENH-3090-convert-rn-remediate-to-shared-decision-cluster-sub-loop.md`) is unrelated. The enhancement that added `impact_of` is **ENH-3092** (`P3-ENH-3092-codegraph-provider-impact-of-support.md`) — matching the `relates_to` frontmatter on line 16. Implementers should read ENH-3092 for the `impact_of` design.

## Labels

`bug`, `codequery`, `codegraph`

## Status

**Open** | Created: 2026-08-06 | Priority: P3

## Acceptance Criteria

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-06 — based on codebase analysis:_

- `importers_of()` returns non-empty for a repo-relative path nested under `project.src_dir` when the index stores the src-relative import `qualified_name` — the Current Behavior repro (`results: []`) flips to non-empty.
- `importers_of("scripts/little_loops/config/__init__.py")` returns the same non-empty result set as `importers_of("little_loops.config")` (92 rows against this repo's current index) — the `.__init__` suffix is dropped before matching.
- `impact_of()` returns non-empty for the same input via its existing transitive walk (`codegraph.py:514`), no change to `impact_of` itself.
- Existing resolutions are unchanged: dotted-module inputs (`little_loops.issue_manager`), repo-relative paths not under `src_dir`, and `src_dir` unset/`"."` layouts (strip is a no-op) resolve exactly as before.
- `python -m pytest scripts/tests/` passes, including a new regression test in `test_codequery_codegraph.py` whose config writer sets `project.src_dir` (today `_write_config()` at lines 213-221 writes only `code_query`).


## Session Log
- `/ll:manage-issue` - 2026-08-06T23:38:14 - `304efef5-84e8-4f90-bcb1-2c715d8e2940.jsonl`
- `/ll:ready-issue` - 2026-08-06T23:25:58 - `cdb7e470-93e0-4781-9573-7c5e633437ca.jsonl`
- `/ll:confidence-check` - 2026-08-06T23:03:48 - `45d23f17-20f2-477b-8ebe-0c8ee65c5e61.jsonl`
- `/ll:wire-issue` - 2026-08-06T22:57:38 - `88167c0c-eda5-4b33-af85-8b5220a43ff7.jsonl`
- `/ll:refine-issue` - 2026-08-06T22:41:48 - `046a1620-bd2e-485d-9777-bc6571cad05e.jsonl`

## Resolution

- **Action**: fix
- **Completed**: 2026-08-06
- **Status**: Completed

### Changes Made
- `scripts/little_loops/codequery/codegraph.py`: added `_dotted_candidates()` helper that
  produces a repo-root-relative dotted guess plus a `project.src_dir`-stripped guess
  (dropping a trailing `.__init__` segment for package `__init__.py` paths); `importers_of()`
  now reads `project.src_dir` via a fresh `BRConfig` and OR-matches the additional candidate,
  with the `CodeRef.symbol` fallback preferring the src-relative name. `impact_of()` unchanged —
  inherits through its `importers_of()` walk.
- `scripts/tests/test_codequery_codegraph.py`: `_write_config()` now accepts an optional
  `src_dir`; added `TestImportersOfSrcDir` (4 regression tests covering src_dir-prefixed file
  paths, package `__init__.py` → bare-qname resolution, and both through `impact_of`).

### Verification Results
- Tests: PASS — `python -m pytest scripts/tests/` (18534 passed, 42 skipped)
- Lint: PASS — `ruff check` on changed files
- Types: N/A (no `type_cmd` mismatch; mypy not run for this scoped change)
- Run: PASS — live index smoke: `importers_of("scripts/little_loops/issue_manager.py")` 0→4,
  `importers_of("scripts/little_loops/config/__init__.py")` 0→92, `impact_of(...)` 0→4
- Integration: PASS — no signature/JSON/exit-code contract changes; existing
  `TestQueries`/`TestImpactOfTransitive`/`TestSchemaGuard`/`test_codequery_fallback.py` green
