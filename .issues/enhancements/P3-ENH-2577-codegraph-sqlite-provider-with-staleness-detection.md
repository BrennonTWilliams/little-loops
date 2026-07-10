---
id: ENH-2577
title: codegraph SQLite provider with staleness detection and code_query config block
type: ENH
priority: P3
status: open
labels: [code-intelligence, adapters, token-cost, captured]
captured_at: "2026-07-10T05:34:41Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2575
---

# ENH-2577: codegraph SQLite provider with staleness detection and code_query config block

## Summary

Register the first real graph backend behind the FEAT-2576 `CodeQueryProvider` protocol: a read-only provider over the [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph) SQLite index already present at `.codegraph/codegraph.db` (34MB, indexed in this repo). Ship it with the epic's non-negotiable safety feature — staleness detection comparing index build time against git HEAD and dirty files, governed by a configurable `strict | warn | off` policy — and the `code_query` config block that makes the whole integration optional and explicit.

## Current Behavior

After FEAT-2576, `ll-code` answers every query through the grep/AST fallback: correct but heuristic for `callers_of`/`references`, and it re-scans the tree on every call. The codegraph index sits unused at `.codegraph/codegraph.db` even though the external tool has already paid the full parse/link cost for exact caller/callee/import edges. There is no configuration surface to opt a project into (or out of) graph-backed queries, and no freshness guard of any kind.

## Expected Behavior

```bash
ll-code status
# provider: codegraph  available: yes  freshness: stale
# indexed_at: 2026-06-01T14:01:04Z  head_moved: 47 commits  dirty_files: 3
# policy: warn → results will be marked stale; confirm before acting

ll-code callers-of little_loops.state.StateStore.save     # exact edges from the graph
ll-code --provider fallback callers-of <symbol>           # explicit bypass still works
```

- With `policy: strict`, a stale index makes the provider report unavailable → resolver falls through to fallback automatically.
- With `policy: warn` (default), stale results are returned but every `CodeRef` and the envelope carry `freshness: stale`.
- With no `.codegraph/` present or no config opt-in, behavior is identical to FEAT-2576 — the integration is invisible.

## Use Case

An autodev loop runs `/ll:wire-issue` twelve times against the same repo overnight. The codegraph index answers each issue's caller/importer queries exactly and instantly. Mid-run, an implementation loop lands three commits; the next `ll-code status` reports `stale (3 commits)`; under `warn`, wire-issue keeps using the graph for discovery but its confirmation Grep step (ENH-2578) catches the two moved call sites; under `strict`, queries silently degrade to fallback until the user reindexes.

## Proposed Solution

### Provider (`codequery/codegraph.py`)

- Registered lazily in `_PROVIDER_MAP` as `"codegraph"`; listed before `"fallback"` in `auto` resolution.
- Read-only `sqlite3` connection to `<repo>/.codegraph/codegraph.db` (path configurable). **First implementation step is schema discovery** (`sqlite3 .codegraph/codegraph.db .schema`): map the tool's node/edge tables onto the protocol verbs; anything unmappable is simply omitted from `capabilities()` and the resolver falls through to fallback per-query. Pin the discovered schema in a test fixture so an upstream codegraph schema change fails loudly, not wrongly.
- All refs returned with `confidence: exact`.

### Staleness detection

- `status()` compares: index timestamp (db mtime and/or codegraph metadata table if present) vs. `git rev-parse HEAD` commit time, commit count since, and `git status --porcelain` dirty files.
- Fresh = index newer than HEAD and working tree clean; anything else = stale with a human-readable `detail`.
- Enforcement per `code_query.staleness` policy: `strict` (stale → unavailable), `warn` (default; serve + mark), `off` (always trust — for frozen repos/CI).

### Config (`code_query` block in config-schema)

```json
"code_query": {
  "provider": "auto | codegraph | fallback",   // default "auto"
  "codegraph": { "db_path": ".codegraph/codegraph.db" },
  "staleness": "strict | warn | off"           // default "warn"
}
```

Added to `scripts/little_loops/config-schema.json` following existing optional-block conventions; consumed by `resolve_provider` and the CLI.

## Scope Boundaries

- **Not** running, installing, or wrapping the codegraph indexer — reindexing is the user's (or their hook's) job; we only detect and report staleness. A `detail` hint may name the reindex command, nothing more.
- **Not** additional providers (GitNexus etc.) — the registry accepts them later; none built here.
- **Not** auto-reindex hooks — a plausible follow-up (`hooks/`) once ENH-2578 proves value; out of scope.
- **Not** skill changes — ENH-2578.

## API/Interface

- New provider module `scripts/little_loops/codequery/codegraph.py`; no new CLI surface beyond `ll-code status` gaining freshness fields and `--provider codegraph`.
- New `code_query` config block (schema above).

## Integration Map

### Files to Create
- `scripts/little_loops/codequery/codegraph.py`
- `scripts/tests/test_codequery_codegraph.py` + a small checked-in fixture db (or schema-builder fixture) so tests never depend on the real 34MB index

### Files to Modify
- `scripts/little_loops/codequery/core.py` — register `"codegraph"` in `_PROVIDER_MAP`; `auto` ordering; per-query fall-through on missing capability
- `scripts/little_loops/config-schema.json` — `code_query` block
- `.gitignore` conventions doc if `.codegraph/` handling needs stating (db is already git-ignored via `.codegraph/.gitignore`)
- Docs: `ll-code` reference gains provider/config/staleness section; README config table per [[readme_conventions]]

### Dependent Files
- ENH-2578 reads `freshness` from `ll-code --json` envelopes to decide graph-first vs. fallback flow.

### Similar Patterns
- `scripts/little_loops/adapters/codex.py` — concrete adapter behind a shared protocol, lazy-imported.
- Config-schema optional feature blocks (e.g., analytics/learning-tests toggles from ENH-2560) — opt-in shape to mirror.

### Tests
- Reuse FEAT-2576's protocol conformance suite against the fixture db.
- Staleness matrix: fresh / commits-ahead / dirty-tree × strict / warn / off.
- Schema-drift guard: fixture pinned to discovered codegraph schema version.

### Documentation
- Docs + README config/CLI updates; CHANGELOG entry; note that graph results are discovery hints (link epic design rules).

### Configuration
- `code_query` block (above); absent block == fallback-only, zero behavior change.

## Implementation Steps

1. Schema-discover `.codegraph/codegraph.db`; write the mapping note into the module docstring.
2. Implement provider queries + `capabilities()` for the mappable verbs; build the test fixture db.
3. Implement `status()` staleness detection + policy enforcement in resolver/CLI.
4. Add `code_query` config block + plumbing; docs; `ll-verify-docs`.

## Impact

- **Priority**: P3 — turns the protocol from "nice refactor" into actual exact-and-cheap queries.
- **Effort**: Medium — one provider + config + staleness matrix tests.
- **Risk**: Low-Medium — read-only, optional, and fall-through-safe; main risk is upstream schema drift, mitigated by the pinned fixture and capability fall-through.
- **Breaking Change**: No.

## Related Issues

- **EPIC-2575** — parent. **Blocked by FEAT-2576** (protocol/registry/CLI must exist).
- **ENH-2578** — consumer; blocked by this issue.
- **EPIC-2456** — token cost reduction context.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`
