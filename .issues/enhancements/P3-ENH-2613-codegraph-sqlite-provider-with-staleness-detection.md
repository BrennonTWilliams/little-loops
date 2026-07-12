---
id: ENH-2613
title: codegraph SQLite provider with staleness detection
type: ENH
priority: P3
status: done
labels:
- code-intelligence
- adapters
- token-cost
parent: ENH-2577
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-07-12T18:41:37Z'
---

# ENH-2613: codegraph SQLite provider with staleness detection

## Summary

Register the first real graph backend behind the FEAT-2576 `CodeQueryProvider`
protocol: a read-only provider over the [colbymchenry/codegraph](https://github.com/colbymchenry/codegraph)
SQLite index at `.codegraph/codegraph.db` (34MB, indexed in this repo), plus the
epic's non-negotiable safety feature — staleness detection comparing index build
time against git HEAD and dirty files, governed by the `code_query.staleness`
policy (`strict | warn | off`) added in ENH-2612.

## Parent Issue

Decomposed from ENH-2577: codegraph SQLite provider with staleness detection and
code_query config block.

## Current Behavior

After FEAT-2576, `ll-code` answers every query through the grep/AST fallback:
correct but heuristic for `callers_of`/`references`, and it re-scans the tree on
every call. The codegraph index sits unused at `.codegraph/codegraph.db` even
though the external tool has already paid the full parse/link cost for exact
caller/callee/import edges. There is no freshness guard of any kind.

## Expected Behavior

```bash
ll-code status
# provider: codegraph  available: yes  freshness: stale
# indexed_at: 2026-06-01T14:01:04Z  head_moved: 47 commits  dirty_files: 3
# policy: warn → results will be marked stale; confirm before acting

ll-code callers-of little_loops.state.StateStore.save     # exact edges from the graph
ll-code --provider fallback callers-of <symbol>           # explicit bypass still works
```

- With `policy: strict`, a stale index makes the provider report unavailable →
  resolver falls through to fallback automatically.
- With `policy: warn` (default), stale results are returned but every `CodeRef`
  and the envelope carry `freshness: stale`.
- With no `.codegraph/` present or no `code_query` config opt-in (ENH-2612),
  behavior is identical to FEAT-2576 — the integration is invisible.

## Use Case

An autodev loop runs `/ll:wire-issue` twelve times against the same repo
overnight. The codegraph index answers each issue's caller/importer queries
exactly and instantly. Mid-run, an implementation loop lands three commits; the
next `ll-code status` reports `stale (3 commits)`; under `warn`, wire-issue keeps
using the graph for discovery but its confirmation Grep step (ENH-2578) catches
the two moved call sites; under `strict`, queries silently degrade to fallback
until the user reindexes.

## Proposed Solution

### Provider (`codequery/codegraph.py`)

- Registered lazily in `_PROVIDER_MAP` as `"codegraph"`; listed before `"fallback"`
  in `auto` resolution.
- Read-only `sqlite3` connection to `<repo>/.codegraph/codegraph.db` (path from
  `code_query.codegraph.db_path`, ENH-2612). **First implementation step is schema
  discovery** (`sqlite3 .codegraph/codegraph.db .schema`): map the tool's
  node/edge tables onto the protocol verbs; anything unmappable is simply omitted
  from `capabilities()` and the resolver falls through to fallback per-query. Pin
  the discovered schema in a test fixture so an upstream codegraph schema change
  fails loudly, not wrongly.
- All refs returned with `confidence: exact`.

### Codebase Research Findings

_Carried over from ENH-2577 — based on codebase analysis:_

- **Schema discovery already run** against this repo's live `.codegraph/codegraph.db`
  (2026-06-01 build, `sqlite3 .codegraph/codegraph.db .schema`):
  - `nodes(id, kind, name, qualified_name, file_path, language, start_line, end_line, start_column, end_column, docstring, signature, visibility, is_exported, is_async, is_static, is_abstract, decorators, type_parameters, updated_at)` — `kind` values present: `class, constant, file, function, import, interface, method, type_alias, variable`.
  - `edges(id, source, target, kind, metadata, line, col, provenance)` FK'd to `nodes(id)` — `kind` values present: `calls, contains, extends, imports, instantiates, references`. This maps directly onto the protocol verbs: `callers_of`/`callees_of` ← `kind='calls'`, `importers_of` ← `kind='imports'`, `references` ← `kind='references'` (plus `calls`), `defines` ← `nodes` filtered by `file_path`. No edge `kind` maps to `impact_of` — that verb must stay omitted from `capabilities()` for this provider.
  - `files(path, content_hash, language, size, modified_at, indexed_at, node_count, errors)` — has an `indexed_at` column per file (not just one global build timestamp), plus `schema_versions(version, applied_at, description)` for the index's own schema version (currently version 4, `applied_at` epoch-ms ≈ this repo's index build time).
  - `nodes_fts` is an FTS5 virtual table over `nodes(name, qualified_name, docstring, signature)` — available for a future `search`-style verb, not needed for the verbs listed above.
- **FEAT-2576 is still `status: open` / unimplemented** — confirmed via `Glob` that
  `scripts/little_loops/codequery/` does not exist anywhere in the tree. This
  issue is fully blocked; there is no `_PROVIDER_MAP`, `resolve_provider`,
  `CodeQueryProvider` Protocol, `CodeRef`, or `ProviderStatus` dataclass to
  register against yet. FEAT-2576's own text specifies the shape this provider
  must conform to: `CodeQueryProvider` Protocol (`name: str`, `capabilities() -> set[str]`,
  `status() -> ProviderStatus`, `callers_of/callees_of/importers_of/defines/references/impact_of`),
  `CodeRef` dataclass (`path, line, symbol, kind, confidence, name`), `ProviderStatus`
  dataclass (`available, freshness, indexed_at, detail`), and a `CodeQueryError`
  exception — mirrored one-directionally on `scripts/little_loops/adapters/core.py`'s
  `AdapterError`.
- **Registry/resolver pattern to mirror**: `scripts/little_loops/adapters/core.py`
  — `HostEmitter` Protocol (line 26, `@runtime_checkable`), `_EMITTER_MAP: dict[str, tuple[str, str]]`
  lazy-import registry (line 45, maps name → `(module_path, class_name)`, resolved
  only via `importlib.import_module` inside the factory), `resolve_emitter()`
  factory (line 52), `AdapterError` (line 21). Concrete provider example:
  `scripts/little_loops/adapters/codex.py`'s `CodexEmitter` class (line 255) — a
  plain class with a `name` class attribute and the Protocol's methods, no
  inheritance required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-12):_

- **FEAT-2576 is no longer unstarted work — it's implemented, just not on `main`
  yet.** Commit `53512663` ("feat(codequery): add CodeQuery provider protocol,
  grep/AST fallback, and ll-code CLI", closes FEAT-2576) exists on branch
  `epic/epic-2575-code-knowledge-graph-adapter-query-protocol-providers-skill-integration`
  but is **not an ancestor of current `main` HEAD** (confirmed:
  `scripts/little_loops/codequery/` still does not exist when checked out on
  `main`). Treat this as "the dependency's shape is now known and stable, land
  ENH-2613 against that branch or wait for the merge" rather than "the protocol
  doesn't exist yet."
- **Exact shapes from that commit's `scripts/little_loops/codequery/core.py`**
  (supersedes/corrects the shape described above from FEAT-2576's own issue text):
  - `CodeRef` dataclass (line 48): `path: str, line: int, symbol: str, kind: str,
    confidence: Confidence, provider: str` — **the last field is named `provider`,
    not `name`** as this issue's Proposed Solution section currently implies.
    `Confidence = Literal["exact", "heuristic"]` (module level). Use
    `confidence="exact", provider="codegraph"` for every `CodeRef` this provider
    returns.
  - `ProviderStatus` dataclass (line 60): `available: bool, freshness: Freshness,
    indexed_at: str | None, detail: str` — matches this issue's description
    exactly. `Freshness = Literal["fresh", "stale", "unknown"]`.
  - `CodeQueryProvider` Protocol (line 70, `@runtime_checkable`): `name: str`
    attribute plus `capabilities() -> set[str]`, `status() -> ProviderStatus`,
    `callers_of`, `callees_of`, `importers_of`, `defines`, `references`,
    `impact_of(paths: list[str], depth: int = 2) -> list[CodeRef]`. All six query
    methods are part of the Protocol — a provider that omits `impact_of` from
    `capabilities()` must still implement the method (raising
    `codequery.core.Unsupported`, a `CodeQueryError` subclass at line ~40, is the
    established idiom — see `fallback.py` for a query kind it doesn't support).
  - `_PROVIDER_MAP: dict[str, tuple[str, str]]` (line 97) currently has one entry:
    `"fallback": ("little_loops.codequery.fallback", "FallbackProvider")`. This
    issue's registration point: add `"codegraph": ("little_loops.codequery.codegraph",
    "CodegraphProvider")` **before** `"fallback"` in this dict (dict insertion
    order is iteration order for `"auto"` resolution, per `resolve_provider` at
    line 102).
  - `resolve_provider(name="auto")` (line 102) iterates `_PROVIDER_MAP` in
    insertion order and returns the first whose `status().available` is `True`;
    `_instantiate()` (line 127) does the lazy `importlib.import_module` +
    `getattr(module, cls_name)()` construction — no changes needed here, only the
    dict entry.
  - `FallbackProvider` (`fallback.py` line 95) is the concrete pattern to mirror:
    `name = _NAME` class attribute (line 98, plain string, no `@property`),
    `capabilities()` (line 100) returns a literal `set[str]` subset of
    `QUERY_KINDS`, `status()` (line 103) always returns `available=True,
    freshness="fresh"` since it reads the working tree directly — the codegraph
    provider's `status()` is the one place this issue adds real logic (the
    staleness comparison below), everything else about the class shape mirrors
    `FallbackProvider`.
- **Test pattern to mirror**: `scripts/tests/test_codequery_core.py` and
  `scripts/tests/test_codequery_fallback.py` (both added in commit `53512663`)
  are the direct precedent for `test_codequery_codegraph.py` — protocol
  conformance via `isinstance(provider, CodeQueryProvider)`, per-method
  correctness against a fixture, and a `capabilities()` completeness check.

### Staleness detection

- `status()` compares: index timestamp (db mtime and/or codegraph metadata table
  if present) vs. `git rev-parse HEAD` commit time, commit count since, and
  `git status --porcelain` dirty files.
- Fresh = index newer than HEAD and working tree clean; anything else = stale with
  a human-readable `detail`.
- Enforcement per `code_query.staleness` policy (from ENH-2612): `strict` (stale →
  unavailable), `warn` (default; serve + mark), `off` (always trust — for frozen
  repos/CI).

### Codebase Research Findings

_Carried over from ENH-2577 — based on codebase analysis:_

- No existing code compares an external index's mtime against `git rev-parse HEAD`
  today — this comparison is genuinely new logic — but the git subprocess
  primitives it needs already exist in two near-identical local helpers:
  `scripts/little_loops/hooks/post_commit.py::_git()` (line 27,
  `subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=_GIT_TIMEOUT)`,
  returns `None` on `OSError`/`TimeoutExpired`/non-zero exit rather than raising)
  and `scripts/little_loops/worktree_utils.py::_git()` (line 41, same shape via a
  `GitLock`-aware closure). `post_commit.py::record_head_commit()` (line 44)
  already calls `_git(root, "log", "-1", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%B")`
  — the `%aI` (ISO-8601 author date) token is exactly what a
  `db_mtime vs. HEAD_commit_time` comparison needs.
- For commit-count-since and dirty-file listing:
  `scripts/little_loops/git_operations.py::check_git_status()` (line 161,
  `git diff --quiet` / `git diff --cached --quiet`, fail-safe-dirty on any
  exception) and `get_untracked_files()` (line 195, `git status --porcelain`,
  parses `"??"`-prefixed lines) are the closest reusable precedents, though this
  issue's design already correctly specifies `git status --porcelain` directly
  rather than `git diff --quiet` (porcelain also surfaces untracked files, which
  the diff-only check misses).
- **Reusable read-only DB pattern for the freshness check itself**:
  `scripts/little_loops/issue_history/evolution.py::_open_db()` (line 30) is a
  closer analog than the other `sqlite3.connect` sites in this codebase, because
  it's the only one that skips this project's own `ensure_db()` migration path —
  it just does `if not db_path.exists(): return None` then
  `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` +
  `conn.execute("PRAGMA query_only = ON")` + `conn.row_factory = sqlite3.Row`,
  returning `None` (never raising) on `sqlite3.Error`. `.codegraph/codegraph.db`'s
  schema is owned by the external `codegraph` tool, not by this repo's migration
  system, so the codegraph provider should follow `_open_db()`'s shape, not
  `history_reader.py::_connect_readonly()`'s (which calls `ensure_db()` first).
- `.codegraph/codegraph.db` in this repo currently has file mtime
  `2026-06-01T22:07:38` (macOS `stat -f %m`) and `schema_versions` row
  `applied_at=1780369658000` (epoch ms, same timestamp) — confirms the index's
  own `files.indexed_at` per-file column and `schema_versions.applied_at` are both
  usable staleness signals in addition to the raw db file mtime.

## Scope Boundaries

- **Not** the `code_query` config block or `CodeQueryConfig` dataclass — ENH-2612
  (a hard dependency: this provider reads `db_path` and `staleness` policy from
  that config).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-12):_

- **ENH-2612 is now `status: Completed`** (was open/blocking when this issue was
  last refined). Its config surface is live on `main` today:
  `CodeQueryConfig` (`scripts/little_loops/config/features.py:744-758`) has
  `provider: str = "auto"`, `codegraph: CodeQueryCodegraphConfig`, `staleness: str
  = "warn"`; `CodeQueryCodegraphConfig` (same file, ~line 720-741) has `db_path:
  str = ".codegraph/codegraph.db"`. Both wired into `BRConfig` in
  `scripts/little_loops/config/core.py`: import at line 26, instantiated at line
  228 (`self._code_query = CodeQueryConfig.from_dict(self._raw_config.get("code_query", {}))`),
  exposed via the `code_query` property at lines 307-309. This provider should
  read `db_path` via `config.code_query.codegraph.db_path` and the policy via
  `config.code_query.staleness` — no new config plumbing needed, just consumption.
- **Config test pattern to mirror**: `scripts/tests/test_config.py::TestCodeQueryConfig`
  (starts line 2187) — `test_from_dict_with_defaults` (2190),
  `test_from_dict_with_all_fields` (2197), `test_from_dict_partial_data` (2209),
  `test_codegraph_from_dict_with_defaults` (2218), `test_brconfig_defaults` (2223)
  is the shape for any test asserting this provider correctly resolves
  `db_path`/`staleness` from a loaded `BRConfig`.
- **Not** running, installing, or wrapping the codegraph indexer — reindexing is
  the user's (or their hook's) job; we only detect and report staleness. A
  `detail` hint may name the reindex command, nothing more.
- **Not** additional providers (GitNexus etc.) — the registry accepts them later;
  none built here.
- **Not** auto-reindex hooks — a plausible follow-up (`hooks/`) once ENH-2578
  proves value; out of scope.
- **Not** skill changes — ENH-2578.

## API/Interface

- New provider module `scripts/little_loops/codequery/codegraph.py`; no new CLI
  surface beyond `ll-code status` gaining freshness fields and `--provider codegraph`.

## Files to Create

- `scripts/little_loops/codequery/codegraph.py`
- `scripts/tests/test_codequery_codegraph.py` (fixture DBs built programmatically
  at test time, no checked-in binary — see Test Patterns below)

## Files to Modify

- `scripts/little_loops/codequery/core.py` — register `"codegraph"` in
  `_PROVIDER_MAP`; `auto` ordering; per-query fall-through on missing capability
- Docs: `ll-code` reference gains provider/config/staleness section
- `docs/reference/CLI.md` — `### ll-code` section: fix stale `ENH-2577`→
  `ENH-2613` reference, document freshness fields (`/ll:wire-issue` finding)
- `docs/reference/API.md` — `## little_loops.codequery` "Built-in providers"
  table: add `CodegraphProvider` row (`/ll:wire-issue` finding)
- `docs/reference/CONFIGURATION.md` — `### code_query` section: remove
  "inert until a provider consumes it" framing once implemented
  (`/ll:wire-issue` finding)
- `scripts/tests/test_cli_code.py` — add `--provider codegraph` CLI case
  (`/ll:wire-issue` finding)

## Dependent Files (Callers/Importers)

No live callers exist today — confirmed via `Glob`/`Grep` that
`scripts/little_loops/codequery/` does not exist anywhere in the tree, so nothing
currently imports `CodeQueryProvider`/`_PROVIDER_MAP`/`resolve_provider`. All
wiring below is either greenfield (created by this issue) or activates only once
FEAT-2576 lands.

- `scripts/tests/test_adapters.py::TestResolveEmitter` (lines 84–99) — the
  registry-resolver test shape to mirror once FEAT-2576's `resolve_provider`/
  `_PROVIDER_MAP` exists: known-key returns correct concrete type, unknown-key
  raises the domain error listing registered names, resolved instance satisfies
  the Protocol via `isinstance()`.

ENH-2578 reads `freshness` from `ll-code --json` envelopes to decide graph-first
vs. fallback flow.

### Similar Patterns

- `scripts/little_loops/adapters/codex.py` — concrete adapter behind a shared
  protocol, lazy-imported.

### Tests

- Reuse FEAT-2576's protocol conformance suite against the fixture db.
- Staleness matrix: fresh / commits-ahead / dirty-tree × strict / warn / off.
- Schema-drift guard: fixture pinned to discovered codegraph schema version.

### Test Patterns to Mirror

- **Three-tier fixture-DB shape** — `scripts/tests/test_history_reader.py`:
  `TestMissingDatabase` (lines 28–54, db path never created), `TestEmptyTables`
  (lines 57–88, schema created with zero rows), `TestStaleRowFiltering` (lines
  91–150, populated with boundary timestamps via a local
  `_insert_old_correction()`-style helper: `conn = connect(db); conn.execute(...);
  conn.commit(); conn.close()`, no checked-in binary fixture). This maps directly
  onto the "fresh / commits-ahead / dirty-tree" matrix.
- **Read-only DB open** —
  `scripts/little_loops/issue_history/evolution.py::_open_db()` (lines 30–47):
  existence pre-check → `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` →
  `conn.row_factory = sqlite3.Row` → `PRAGMA query_only = ON` →
  `try/except sqlite3.Error` returning `None` (never raises). `codegraph.py`'s
  DB-opening code should mirror this exactly.
- **Git-state fixtures for staleness tests** — no existing test in this codebase
  mocks `subprocess.run`/`git rev-parse`/`git status --porcelain` calls. The
  established convention is a **real `tmp_path` git repo**: see
  `scripts/tests/test_worktree_utils.py` (module docstring explains the
  rationale) and `scripts/tests/test_session_store.py::TestBackfillCommitEvents`
  (lines 3492–3565, `repo` fixture that `pytest.skip("git not available")` if
  `shutil.which("git") is None`, then drives real `git init`/`commit`/`checkout`
  to build fixture states). The staleness matrix tests should build real repos
  this way, not mock `_git()`.
- **No checked-in binary `.db` fixture files** — `scripts/tests/fixtures/` holds
  only text fixtures (`.md`/`.yaml`/`.json`). Build fixture DBs programmatically
  at test time via `tmp_path` + raw SQL `INSERT`s, hand-writing the
  `CREATE TABLE nodes(...)`/`CREATE TABLE edges(...)` statements matching the real
  schema recorded above (no `ensure_db()` equivalent to reuse, since the schema is
  externally owned by the `codegraph` tool).

### Documentation

- `ll-code` reference gains a provider/config/staleness section; CHANGELOG entry
  at release time (per [[feedback_changelog_no_unreleased]], not under
  `[Unreleased]`); note that graph results are discovery hints (link epic design
  rules).
- No `.gitignore` change needed — both the root `.gitignore` blanket `.codegraph/`
  entry and the nested `.codegraph/.gitignore` already exist.
- No `.claude/CLAUDE.md` `ll-code` entry needed here — that belongs to FEAT-2576.

### Documentation (exact anchors — `/ll:wire-issue` pass, 2026-07-12)

_FEAT-2576's commit (`53512663`, unmerged epic branch) already forward-references
this provider by name at three specific anchors — these are edits, not new
sections:_

- `docs/reference/CLI.md`, `### ll-code` (~line 1832 on that commit's tree) —
  already says "Graph-backed providers (e.g. ENH-2577's `codegraph`) register in
  the same resolver and take priority under `--provider auto`." Update the stale
  `ENH-2577` reference to `ENH-2613` (post-decomposition) and extend the
  `status` subcommand row / JSON envelope description with the freshness fields
  this issue adds (`indexed_at`, `head_moved`, `dirty_files`, policy detail).
- `docs/reference/API.md`, `## little_loops.codequery` → "Built-in providers"
  table (~line 7743 on that commit's tree) — currently lists only
  `FallbackProvider` / `"fallback"` / Implemented (FEAT-2576). Add a
  `CodegraphProvider` / `"codegraph"` / Implemented (ENH-2613) row.
- `docs/reference/CONFIGURATION.md`, `### code_query` (main, lines 965-976) —
  **this file already exists on `main` today** (landed by ENH-2612) and its
  description literally says: "This block is opt-in and inert — its presence or
  absence causes zero runtime behavior change until a provider consumes it
  (ENH-2613, the codegraph SQLite provider)." This issue is the one that makes
  it non-inert — update this sentence once `CodegraphProvider` is registered so
  the doc no longer describes itself as dead config.

### Tests (exact anchor — `/ll:wire-issue` pass, 2026-07-12)

- `scripts/tests/test_cli_code.py` (added by FEAT-2576 commit `53512663`, not
  yet on `main`) — CLI-level test file for `ll-code`, not previously named in
  this issue's Tests section (only the protocol/fallback test files were).
  Check it for any provider-name enumeration/hardcoding once merged, and add a
  `--provider codegraph` CLI-level case (status freshness fields surfacing
  through `--json`) alongside the existing `--provider fallback` coverage.

### Confirmed no-op (verified during `/ll:wire-issue`, no action needed)

- `scripts/little_loops/config-schema.json:1205-1233` already has `"codegraph"`
  in the `code_query.provider` enum and `code_query.codegraph.db_path` with the
  correct default — ENH-2612 fully anticipated this provider name; no schema
  change needed.
- `scripts/tests/test_config.py::TestCodeQueryConfig` (lines 2187-2261) already
  fully covers `codegraph.db_path` and `staleness` parsing/round-tripping —
  no new config-parsing tests needed, only the runtime `CodegraphProvider`
  tests already planned above.
- `scripts/tests/fixtures/` has no shared SQLite fixture-building helper (only
  text/YAML/JSON fixtures) — the issue's existing plan to hand-write
  `CREATE TABLE` SQL per test (mirroring `test_session_store.py`'s inline-SQL
  convention) is the correct, already-established pattern; nothing to change.

## Implementation Steps

1. Schema-discover `.codegraph/codegraph.db`; write the mapping note into the
   module docstring.
2. Implement provider queries + `capabilities()` for the mappable verbs; build the
   test fixture db.
3. Implement `status()` staleness detection + policy enforcement in
   resolver/CLI, reading `code_query.staleness` from `CodeQueryConfig` (ENH-2612).
4. Docs: `ll-code` reference provider/config/staleness section; `ll-verify-docs`.

### Wiring Phase (added by `/ll:wire-issue`)

_Exact doc/test anchors identified by wiring analysis — FEAT-2576's unmerged
commit already forward-references this provider by name, so these are targeted
edits, not open-ended doc writing:_

5. Update `docs/reference/CLI.md`'s `### ll-code` section: fix the stale
   `ENH-2577` → `ENH-2613` reference and document the `status` freshness
   fields (`indexed_at`, `head_moved`, `dirty_files`, policy detail).
6. Add a `CodegraphProvider` row to `docs/reference/API.md`'s
   `## little_loops.codequery` "Built-in providers" table.
7. Update `docs/reference/CONFIGURATION.md`'s `### code_query` section to
   remove the "opt-in and inert ... until a provider consumes it" framing.
8. Add a `--provider codegraph` case to `scripts/tests/test_cli_code.py`.

## Impact

- **Priority**: P3 — turns the protocol from "nice refactor" into actual
  exact-and-cheap queries.
- **Effort**: Medium — one provider module + staleness matrix tests.
- **Risk**: Low-Medium — read-only, optional, and fall-through-safe; main risk is
  upstream schema drift, mitigated by the pinned fixture and capability
  fall-through.
- **Breaking Change**: No.

## Blocked By

- FEAT-2576: `.issues/features/P3-FEAT-2576-codequery-protocol-fallback-provider-and-ll-code-cli.md`
  — **now `status: done`**, merged to `main` at commit `fa8c3872`
  ("feat(codequery): add CodeQuery provider protocol, grep/AST fallback, and
  ll-code CLI"). Confirmed `scripts/little_loops/codequery/core.py` exists on
  `main` HEAD with the exact shapes this issue's Proposed Solution section
  depends on: `CodeRef`, `ProviderStatus`, `CodeQueryProvider` Protocol,
  `Confidence`/`Freshness` literals, `Unsupported`, `_PROVIDER_MAP`,
  `resolve_provider()`, `_instantiate()`. No longer a blocker — implementation
  can proceed directly against `main`.

## Related Issues

- **ENH-2577** — parent (decomposed).
- **ENH-2612** — sibling; hard dependency, **now `done`** — `CodeQueryConfig`/
  `CodeQueryCodegraphConfig` are live on `main` (see Codebase Research Findings
  under Scope Boundaries).
- **EPIC-2575** — grandparent. **No longer blocked** — FEAT-2576 merged to
  `main` at commit `fa8c3872`.
- **ENH-2578** — consumer; blocked by this issue.
- **EPIC-2456** — token cost reduction context.

## Resolution

Implemented `CodegraphProvider` (`scripts/little_loops/codequery/codegraph.py`) and
registered it as `"codegraph"` in `_PROVIDER_MAP` ahead of `"fallback"`. Read-only
`sqlite3` access to `.codegraph/codegraph.db` mirrors
`issue_history/evolution.py::_open_db()`; `status()` computes staleness by comparing
`MAX(files.indexed_at)` (fallback: `schema_versions.applied_at`) against
`git log --since=<indexed_at>` (commits landed) and `git status --porcelain` (dirty
files), then enforces `code_query.staleness` (`strict` → unavailable when stale,
`warn` → served with `freshness: stale`, `off` → always `fresh`). `callers_of`/
`callees_of`/`references` query `edges.kind='calls'`/`'references'`; `importers_of`
queries `edges.kind='imports'` against `import`-kind nodes; `defines` filters `nodes`
by `file_path`. `impact_of` raises `Unsupported` — no edge kind maps to it, so it's
omitted from `capabilities()` and the resolver falls through to `fallback` for that
query. Added `scripts/tests/test_codequery_codegraph.py` (24 tests: schema-drift
guard, capabilities, missing-index, staleness matrix across
fresh/commits-ahead/dirty-tree × strict/warn/off using deterministic
`GIT_AUTHOR_DATE`-pinned fixture repos, and per-verb query correctness against a
hand-built fixture DB) and a `--provider codegraph` case in `test_cli_code.py`.
Updated `docs/reference/CLI.md`, `docs/reference/API.md`, and
`docs/reference/CONFIGURATION.md` per the issue's wiring plan.

## Status

**Done** | Created: 2026-07-12 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-07-12T18:40:46Z - `db791533-d20c-493a-b5e5-1773772b3319.jsonl`
- `/ll:ready-issue` - 2026-07-12T18:26:12 - `cdc63a6f-8ccf-4d77-bbb5-c7eb9cd913ec.jsonl`
- `/ll:confidence-check` - 2026-07-12T18:22:33Z - `7ef47c57-f220-4887-ad6f-0d69ea727eb7.jsonl`
- `/ll:refine-issue` - 2026-07-12T16:07:00 - `b095603c-f679-498a-ba5a-adcda46b8422.jsonl`
- `/ll:ready-issue` - 2026-07-12T07:14:28 - `c26614d0-bc28-439e-be6f-9d5d43820663.jsonl`
- `/ll:confidence-check` - 2026-07-12T00:00:00Z - `78eedd1f-bba9-4596-ae14-3430dd749470.jsonl`
- `/ll:wire-issue` - 2026-07-12T07:09:36 - `90111e22-2341-47f1-933b-58ffe640f57f.jsonl`
- `/ll:refine-issue` - 2026-07-12T07:03:24 - `e32133e9-14f0-4a05-9eaa-744f94187355.jsonl`
- `/ll:issue-size-review` - 2026-07-12T00:00:00Z - `manual decomposition of ENH-2577`
