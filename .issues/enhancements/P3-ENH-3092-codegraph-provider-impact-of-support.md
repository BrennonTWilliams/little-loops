---
id: ENH-3092
title: Add impact_of support to CodegraphProvider (indexed 'imports' edges, transitive)
type: ENH
priority: P3
captured_at: '2026-08-06T20:15:36Z'
completed_at: '2026-08-06T20:15:36Z'
discovered_date: 2026-08-06
discovered_by: session
status: done
testable: true
labels:
- enhancement
- codequery
- codegraph
- wire-issue
relates_to:
- BUG-3091
decision_needed: false
---

# ENH-3092: Add `impact_of` support to `CodegraphProvider` (indexed 'imports' edges, transitive)

## Summary

`/ll:wire-issue`'s Phase 3.6 graph-acceleration step (`skills/wire-issue/graph-discovery-layer.md`)
was observed always falling back to the exploratory pass with "Graph-accelerated
discovery is unavailable for this query (exit 2)" whenever it ran `ll-code --json
impact-of <path>`, even though `ll-code --json status` reported the `codegraph`
provider `available: true`. Root cause: `CodegraphProvider.impact_of()`
(`scripts/little_loops/codequery/codegraph.py`) unconditionally raised `Unsupported`
— `capabilities()` never advertised `impact_of`, so under `--provider auto` (which
resolves `codegraph` first whenever it's available) every `impact-of` query paid a
guaranteed `Unsupported` → exit 2 → fallback round trip, independent of index
freshness or health.

## Current Behavior

`CodegraphProvider.capabilities()` excluded `impact_of`, and `impact_of()`
unconditionally `raise Unsupported(...)`. Under `--provider auto`, `codegraph`
resolves first whenever available, so every `ll-code impact-of` call hit this
raise and exited 2, forcing every caller (notably `/ll:wire-issue` Phase 3.6)
onto the silent-fallback path — the `fallback` provider's slower live AST scan
— every single time, regardless of index freshness.

## Expected Behavior

`ll-code --json impact-of <paths...>` should return real, indexed results with
exit 0/1 when the `codegraph` provider is available and holds the requested
files, matching the exact/heuristic contract every other `ll-code` subcommand
already follows across providers.

## Motivation

- `impact-of` is the only `ll-code` query that always exercised the slow
  `fallback` provider (live AST re-parse of every tracked `.py` file) even when a
  fast, indexed `codegraph` provider was available and fresh — the opposite of
  what an "index-backed provider" is for.
- This surfaced directly in `/ll:wire-issue` runs (Phase 3.6), which calls
  `impact-of` on every planned change target to seed candidate wiring points
  before the exhaustive agent trace; the silent fallback was working as designed
  (zero regression) but meant the acceleration never actually accelerated this
  query.

## Investigation Findings

- `codegraph` (the external CLI, `colbymchenry/codegraph`) does expose a
  first-class `codegraph impact <symbol> --depth N --json` command, but it is
  **symbol-scoped** (blast radius over `calls`/`references`/`extends`/`instantiates`
  edges from one named symbol) — verified directly:
  `codegraph impact IssueManager --depth 2 --json` returns `{symbol, depth,
  nodeCount, edgeCount, affected: [{name, kind, filePath, startLine}]}`.
- `ll-code impact-of <paths...>` is **file-scoped** by design
  (`scripts/little_loops/cli/code.py:88-92`) — wire-issue's planned-change
  targets are usually files, not symbols (`skills/wire-issue/graph-discovery-layer.md:26-30`),
  and `impact-of` is specifically meant to catch non-call dependents (tests,
  config, docs referencing the path/module) that a symbol-scoped call-graph
  traversal would miss.
- Passing a filename as the `symbol` argument to `codegraph impact` does **not**
  produce a real traversal — it resolves only the file's own node with
  `nodeCount: 1, edgeCount: 0` (verified directly). Bridging file-scoped
  `impact-of` to symbol-scoped `codegraph impact` would require enumerating every
  symbol `defines()` returns for a file (up to ~29 for a mid-size module in this
  repo) and shelling out once per symbol — high subprocess fan-out for a query
  shape mismatch (call/reference edges instead of import edges), and would
  silently narrow what `impact-of` catches.
- **Conclusion**: the correct backing relation for `impact_of` is the same
  `edges.kind='imports'` relation `importers_of()` already queries
  (`codegraph.py:395-432`), walked transitively to `depth`. This matches the
  `FallbackProvider.impact_of()` semantics exactly (reverse transitive closure of
  the import graph) — just backed by the persisted SQL index instead of a live
  AST re-parse — and requires no external subprocess call at query time.

## Resolution

Implemented `CodegraphProvider.impact_of()` as a pure-SQL, in-process BFS over
`importers_of()`:

```python
def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]:
    visited = set(paths)
    frontier = set(paths)
    impacted: dict[str, CodeRef] = {}
    for _ in range(max(depth, 1)):
        next_frontier: set[str] = set()
        for path in frontier:
            for ref in self.importers_of(path):
                if ref.path in visited:
                    continue
                visited.add(ref.path)
                impacted[ref.path] = CodeRef(
                    path=ref.path, line=ref.line, symbol=ref.symbol,
                    kind="impact", confidence="exact", provider=self.name,
                )
                next_frontier.add(ref.path)
        if not next_frontier:
            break
        frontier = next_frontier
    return sorted(impacted.values(), key=lambda r: (r.path, r.line))
```

Added `"impact_of"` to `capabilities()`. No changes needed anywhere above the
provider layer (`ll-code` CLI, `/ll:wire-issue`'s Phase 3.6 skill markdown) —
that's the point of the `CodeQueryProvider` protocol (ENH-2578/ENH-2577):
capability gaps close at the provider layer, transparently to every caller that
just checks the exit code / `capabilities` list.

**Follow-up filed**: [[BUG-3091]] — verifying this change against this repo's
real `.codegraph/codegraph.db` index surfaced a pre-existing, separate gap in
`importers_of()`'s path→module-name resolution (doesn't strip `project.src_dir`),
which makes both `importers_of` and (now, transitively) `impact_of` return false
negatives for any path nested under a configured `src_dir` — including every
path in this repo. Left unfixed here as out of scope for this change.

## Integration Map

### Files to Modify
- `scripts/little_loops/codequery/codegraph.py` — `impact_of()` implementation,
  `capabilities()`, module docstring's verb-mapping table.

### Tests
- `scripts/tests/test_codequery_codegraph.py` — replaced the stale
  "`impact_of` raises `Unsupported`" tests with real coverage: one-hop closure,
  transitive two-hop closure (new `TestImpactOfTransitive` fixture chaining
  `pkg/c.py -> pkg/a.py -> pkg/b.py`), input-path exclusion, no-hits.

### Documentation
- `docs/reference/CLI.md:2549` — `impact-of` row updated from "`fallback` only"
  to "heuristic on `fallback`, exact on `codegraph`".

### Configuration
- N/A

## Implementation Steps

1. Investigated `/ll:wire-issue`'s "Graph-accelerated discovery is unavailable"
   fallback message back to `CodegraphProvider.impact_of()` raising `Unsupported`
   unconditionally.
2. Confirmed `codegraph impact <symbol>` is symbol-scoped and not a drop-in
   backing for file-scoped `impact-of` (verified via direct CLI invocation
   against this repo's live index).
3. Implemented `impact_of()` as a transitive BFS over the existing
   `importers_of()` SQL query instead.
4. Added `impact_of` to `capabilities()`.
5. Rewrote `test_codequery_codegraph.py` coverage for the new behavior.
6. Updated `docs/reference/CLI.md`.
7. Verified against the real repo index; discovered and filed [[BUG-3091]] for
   the `src_dir`-prefix resolution gap this surfaced.

## Impact

- **Priority**: P3 — closes an acceleration gap in an already-safe (silent
  fallback) code path; no user-facing breakage either way.
- **Effort**: Small — single-method implementation reusing an existing query.
- **Risk**: Low — additive capability; `Unsupported`/fallback path still exists
  as a safety net for providers that don't implement `impact_of`.

## Related Key Documentation

- [[BUG-3091]] — `importers_of`/`impact_of` false negatives under `src_dir`
  layouts, discovered verifying this change.

## Labels

`enhancement`, `codequery`, `codegraph`, `wire-issue`

## Verification Notes

- `python -m pytest scripts/tests/test_codequery_codegraph.py scripts/tests/test_codequery_fallback.py -q` — 51 passed.
- `ruff check scripts/little_loops/codequery/codegraph.py scripts/tests/test_codequery_codegraph.py` — clean.
- `python -m mypy scripts/little_loops/codequery/codegraph.py` — no issues.
- Manually verified `ll-code --json impact-of <path>` returns `capabilities` including `impact_of` and exits 0/1 (not 2) against this repo's real `.codegraph/codegraph.db`; result *count* is limited by the separate `src_dir` gap filed as BUG-3091.

## Resolution

**Fixed.** `CodegraphProvider.impact_of()` implemented as a transitive walk of
`importers_of()`'s existing `edges.kind='imports'` query; advertised in
`capabilities()`. Tests, docs, and CLI reference updated.

---

**Done** | Created: 2026-08-06 | Priority: P3


## Session Log
- `hook:posttooluse-status-done` - 2026-08-06T20:17:03 - `2295520d-0eb9-4e41-987f-c967b29af520.jsonl`
