---
id: ENH-2577
title: codegraph SQLite provider with staleness detection and code_query config block
type: ENH
priority: P3
status: done
labels:
- code-intelligence
- adapters
- token-cost
- captured
captured_at: '2026-07-10T05:34:41Z'
discovered_date: '2026-07-10'
discovered_by: capture-issue
parent: EPIC-2575
confidence_score: 80
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Schema discovery already run** against this repo's live `.codegraph/codegraph.db` (2026-06-01 build, `sqlite3 .codegraph/codegraph.db .schema`):
  - `nodes(id, kind, name, qualified_name, file_path, language, start_line, end_line, start_column, end_column, docstring, signature, visibility, is_exported, is_async, is_static, is_abstract, decorators, type_parameters, updated_at)` — `kind` values present: `class, constant, file, function, import, interface, method, type_alias, variable`.
  - `edges(id, source, target, kind, metadata, line, col, provenance)` FK'd to `nodes(id)` — `kind` values present: `calls, contains, extends, imports, instantiates, references`. This maps directly onto the protocol verbs: `callers_of`/`callees_of` ← `kind='calls'`, `importers_of` ← `kind='imports'`, `references` ← `kind='references'` (plus `calls`), `defines` ← `nodes` filtered by `file_path`. No edge `kind` maps to `impact_of` — that verb must stay omitted from `capabilities()` for this provider (matches the "anything unmappable is simply omitted" rule already in this section).
  - `files(path, content_hash, language, size, modified_at, indexed_at, node_count, errors)` — has an `indexed_at` column per file (not just one global build timestamp), plus `schema_versions(version, applied_at, description)` for the index's own schema version (currently version 4, `applied_at` epoch-ms ≈ this repo's index build time).
  - `nodes_fts` is an FTS5 virtual table over `nodes(name, qualified_name, docstring, signature)` — available for a future `search`-style verb, not needed for the verbs listed above.
- **FEAT-2576 is still `status: open` / unimplemented** — confirmed via `Glob` that `scripts/little_loops/codequery/` does not exist anywhere in the tree (no `core.py`, `fallback.py`, or CLI module). This issue is fully blocked; there is no `_PROVIDER_MAP`, `resolve_provider`, `CodeQueryProvider` Protocol, `CodeRef`, or `ProviderStatus` dataclass to register against yet. FEAT-2576's own text specifies the shape this provider must conform to: `CodeQueryProvider` Protocol (`name: str`, `capabilities() -> set[str]`, `status() -> ProviderStatus`, `callers_of/callees_of/importers_of/defines/references/impact_of`), `CodeRef` dataclass (`path, line, symbol, kind, confidence, name`), `ProviderStatus` dataclass (`available, freshness, indexed_at, detail`), and a `CodeQueryError` exception — mirrored one-directionally on `scripts/little_loops/adapters/core.py`'s `AdapterError`.
- **Registry/resolver pattern to mirror**: `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (line 26, `@runtime_checkable`), `_EMITTER_MAP: dict[str, tuple[str, str]]` lazy-import registry (line 45, maps name → `(module_path, class_name)`, resolved only via `importlib.import_module` inside the factory — concrete modules never imported at top level), `resolve_emitter()` factory (line 52), `AdapterError` (line 21). Concrete provider example: `scripts/little_loops/adapters/codex.py`'s `CodexEmitter` class (line 255) — a plain class with a `name` class attribute and the Protocol's methods, no inheritance required.

### Staleness detection

- `status()` compares: index timestamp (db mtime and/or codegraph metadata table if present) vs. `git rev-parse HEAD` commit time, commit count since, and `git status --porcelain` dirty files.
- Fresh = index newer than HEAD and working tree clean; anything else = stale with a human-readable `detail`.
- Enforcement per `code_query.staleness` policy: `strict` (stale → unavailable), `warn` (default; serve + mark), `off` (always trust — for frozen repos/CI).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing code compares an external index's mtime against `git rev-parse HEAD` today — this comparison is genuinely new logic — but the git subprocess primitives it needs already exist in two near-identical local helpers: `scripts/little_loops/hooks/post_commit.py::_git()` (line 27, `subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=_GIT_TIMEOUT)`, returns `None` on `OSError`/`TimeoutExpired`/non-zero exit rather than raising) and `scripts/little_loops/worktree_utils.py::_git()` (line 41, same shape via a `GitLock`-aware closure). `post_commit.py::record_head_commit()` (line 44) already calls `_git(root, "log", "-1", "--format=%H%x1f%P%x1f%an%x1f%aI%x1f%B")` — the `%aI` (ISO-8601 author date) token is exactly what a `db_mtime vs. HEAD_commit_time` comparison needs.
- For commit-count-since and dirty-file listing: `scripts/little_loops/git_operations.py::check_git_status()` (line 161, `git diff --quiet` / `git diff --cached --quiet`, fail-safe-dirty on any exception) and `get_untracked_files()` (line 195, `git status --porcelain`, parses `"??"`-prefixed lines) are the closest reusable precedents, though ENH-2577's design already correctly specifies `git status --porcelain` directly rather than `git diff --quiet` (porcelain also surfaces untracked files, which the diff-only check misses).
- **Reusable read-only DB pattern for the freshness check itself**: `scripts/little_loops/issue_history/evolution.py::_open_db()` (line 30) is a closer analog than the other `sqlite3.connect` sites in this codebase, because it's the only one that skips this project's own `ensure_db()` migration path — it just does `if not db_path.exists(): return None` then `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + `conn.execute("PRAGMA query_only = ON")` + `conn.row_factory = sqlite3.Row`, returning `None` (never raising) on `sqlite3.Error`. `.codegraph/codegraph.db`'s schema is owned by the external `codegraph` tool, not by this repo's migration system, so the codegraph provider should follow `_open_db()`'s shape, not `history_reader.py::_connect_readonly()`'s (which calls `ensure_db()` first).
- `.codegraph/codegraph.db` in this repo currently has file mtime `2026-06-01T22:07:38` (macOS `stat -f %m`) and `schema_versions` row `applied_at=1780369658000` (epoch ms, same timestamp) — confirms the index's own `files.indexed_at` per-file column and `schema_versions.applied_at` are both usable staleness signals in addition to the raw db file mtime.

### Config (`code_query` block in config-schema)

```json
"code_query": {
  "provider": "auto | codegraph | fallback",   // default "auto"
  "codegraph": { "db_path": ".codegraph/codegraph.db" },
  "staleness": "strict | warn | off"           // default "warn"
}
```

Added to `scripts/little_loops/config-schema.json` following existing optional-block conventions; consumed by `resolve_provider` and the CLI.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Exact convention to mirror, confirmed at `scripts/little_loops/config-schema.json`: `learning_tests` block (~line 997) and `analytics` block (~line 1577), plus `dependency_mapping` (~line 1068). Shape: top-level `"type": "object"` with a feature-naming `"description"`; every property carries an inline `"description"` and an explicit `"default"`; enum-typed properties (e.g. `learning_tests.discoverability.mode`: `"enum": ["off", "warn", "block"]`, `"default": "warn"`) use a bounded `"enum"` list; every object level — including nested sub-objects like `discoverability`/`retention` — sets `"additionalProperties": false` to reject typos. The proposed `code_query` block should follow this exactly: `provider` and `staleness` as `"enum"` + `"default"` string properties, `codegraph` as a nested object with its own `"additionalProperties": false`.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- No live callers exist today — confirmed via `Glob`/`Grep` that `scripts/little_loops/codequery/` does not exist anywhere in the tree, so nothing currently imports `CodeQueryProvider`/`_PROVIDER_MAP`/`resolve_provider`. All wiring below is either greenfield (created by this issue) or activates only once FEAT-2576 lands. [Agent 1 finding]
- `scripts/little_loops/config/core.py` — the typed config aggregator (`BRConfig`) that wraps `config-schema.json` blocks into dataclasses (mirrors `ProjectConfig`, `IssuesConfig`, etc.); a `CodeQueryConfig` dataclass will need to be added here and wired into `BRConfig`, distinct from and in addition to the raw JSON-schema block. [Agent 1 finding]
- `scripts/tests/test_config.py` — unit tests for `CodeQueryConfig`, following the existing per-block test-class pattern (e.g. `TestProjectConfig`, `TestIssuesConfig`). [Agent 1 finding]
- `scripts/tests/test_config_schema.py` — needs a new `test_code_query_in_schema()` method; no existing test currently references `code_query`. Two precedent shapes to choose from depending on schema placement: `test_analytics_in_schema` (lines 328–347, top-level block) or `test_parallel_epic_branches_in_schema` (lines 744–772, nested-object-under-existing-block). [Agent 1 + Agent 3 finding]
- `scripts/tests/test_adapters.py::TestResolveEmitter` (lines 84–99) — the registry-resolver test shape to mirror once FEAT-2576's `resolve_provider`/`_PROVIDER_MAP` exists: known-key returns correct concrete type, unknown-key raises the domain error listing registered names, resolved instance satisfies the Protocol via `isinstance()`. [Agent 1 + Agent 3 finding]

ENH-2578 reads `freshness` from `ll-code --json` envelopes to decide graph-first vs. fallback flow.

### Similar Patterns
- `scripts/little_loops/adapters/codex.py` — concrete adapter behind a shared protocol, lazy-imported.
- Config-schema optional feature blocks (e.g., analytics/learning-tests toggles from ENH-2560) — opt-in shape to mirror.

### Tests
- Reuse FEAT-2576's protocol conformance suite against the fixture db.
- Staleness matrix: fresh / commits-ahead / dirty-tree × strict / warn / off.
- Schema-drift guard: fixture pinned to discovered codegraph schema version.

### Test Patterns to Mirror

_Wiring pass added by `/ll:wire-issue`:_
- **Three-tier fixture-DB shape** — `scripts/tests/test_history_reader.py`: `TestMissingDatabase` (lines 28–54, db path never created), `TestEmptyTables` (lines 57–88, schema created via `ensure_db()` with zero rows), `TestStaleRowFiltering` (lines 91–150, populated with boundary timestamps via a local `_insert_old_correction()`-style helper: `conn = connect(db); conn.execute(...); conn.commit(); conn.close()`, no checked-in binary fixture). This maps directly onto the "fresh / commits-ahead / dirty-tree" matrix. [Agent 3 finding]
- **Read-only DB open** — `scripts/little_loops/issue_history/evolution.py::_open_db()` (lines 30–47): existence pre-check → `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` → `conn.row_factory = sqlite3.Row` → `PRAGMA query_only = ON` → `try/except sqlite3.Error` returning `None` (never raises). `codegraph.py`'s DB-opening code should mirror this exactly. [Agent 3 finding]
- **Git-state fixtures for staleness tests** — no existing test in this codebase mocks `subprocess.run`/`git rev-parse`/`git status --porcelain` calls. The established convention is a **real `tmp_path` git repo**: see `scripts/tests/test_worktree_utils.py` (module docstring explains the rationale) and `scripts/tests/test_session_store.py::TestBackfillCommitEvents` (lines 3492–3565, `repo` fixture that `pytest.skip("git not available")` if `shutil.which("git") is None`, then drives real `git init`/`commit`/`checkout` to build fixture states). The staleness matrix tests should build real repos this way, not mock `_git()`. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction to "Files to Create" fixture plan**: no checked-in binary `.db` fixture files exist anywhere in this repo (`scripts/tests/fixtures/` holds only text fixtures — `.md`/`.yaml`/`.json`). The established convention (`scripts/tests/test_history_reader.py`) is to build fixture DBs **programmatically at test time** via `tmp_path` + raw SQL `INSERT`s, not to check in a binary file. `TestMissingDatabase` (line 28), `TestEmptyTables` (line 57), and a staleness-insertion helper `_insert_old_correction()` (line 94) model the three-tier shape (absent file → empty schema → populated with boundary timestamps) that maps directly onto this issue's "fresh / commits-ahead / dirty-tree" matrix. Since `.codegraph/codegraph.db`'s schema is externally owned (no `ensure_db()` equivalent to call), the fixture builder will need to hand-write the `CREATE TABLE nodes(...)`/`CREATE TABLE edges(...)` statements matching the real schema recorded below, not reuse any existing schema-creation helper.
- Full real schema for the pinned fixture (from `sqlite3 .codegraph/codegraph.db .schema` against this repo's live index): `nodes(id, kind, name, qualified_name, file_path, language, start_line, end_line, start_column, end_column, docstring, signature, visibility, is_exported, is_async, is_static, is_abstract, decorators, type_parameters, updated_at)`; `edges(id, source, target, kind, metadata, line, col, provenance)` FK'd to `nodes(id)`; `files(path, content_hash, language, size, modified_at, indexed_at, node_count, errors)`; `schema_versions(version, applied_at, description)` (current version `4`); plus an FTS5 `nodes_fts` virtual table (not needed for the verbs in scope here). Observed `kind` values: nodes → `class, constant, file, function, import, interface, method, type_alias, variable`; edges → `calls, contains, extends, imports, instantiates, references`.
- Exact registry/protocol pattern to mirror (once FEAT-2576 lands it): `scripts/little_loops/adapters/core.py` — `HostEmitter` Protocol (line 26), `_EMITTER_MAP` lazy-import registry (line 45), `resolve_emitter()` factory (line 52), `AdapterError` (line 21); concrete implementation example `scripts/little_loops/adapters/codex.py::CodexEmitter` (line 255).
- Config-schema convention anchors: `learning_tests` block (~line 997), `analytics` block (~line 1577), `dependency_mapping` block (~line 1068) in `scripts/little_loops/config-schema.json` — see the Config section above for the shape to mirror.
- Read-only DB connection to model: `scripts/little_loops/issue_history/evolution.py::_open_db()` (line 30) — no `ensure_db()` migration call, `if not db_path.exists(): return None`, then `sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + `PRAGMA query_only = ON` + `conn.row_factory = sqlite3.Row`, returns `None` (never raises) on `sqlite3.Error`.
- Git-metadata subprocess helper to reuse for staleness: `scripts/little_loops/hooks/post_commit.py::_git()` (line 27, timeout-guarded, returns `None` on failure rather than raising) and its sibling `scripts/little_loops/worktree_utils.py::_git()` (line 41).
- **FEAT-2576 blocking status confirmed** (2026-07-12): `scripts/little_loops/codequery/` does not exist yet anywhere in the tree (`status: open` on FEAT-2576) — this issue has no protocol, registry, or CLI to plug into today; all "Files to Modify" above are greenfield until FEAT-2576 lands.

### Documentation
- Docs + README config/CLI updates; CHANGELOG entry; note that graph results are discovery hints (link epic design rules).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — this is the actual per-config-block catalog (README.md has no such table, see below). Add a new `### \`code_query\`` subsection under `## Configuration Sections`, mirroring `### \`dependency_mapping\`` (line 938, `Key | Default | Description` table) or `### \`learning_tests\`` (line 810, 4-column table + fenced JSON example + doc cross-reference). Also add a `code_query` stanza into the master `## Full Configuration Example` fenced block (starts line 7; `dependency_mapping` appears at line 188 within it). [Agent 2 finding]
- `docs/reference/API.md` — add a `little_loops.codequery`/`little_loops.codequery.codegraph` row to the module table (mirror `little_loops.learning_tests` at line 48, `little_loops.analytics` at line 71), plus a `code_query` → `CodeQueryConfig` row in the dataclass table (mirror `dependency_mapping` → `DependencyMappingConfig` at line 135) once the typed dataclass from `config/core.py` exists. [Agent 2 finding]
- `README.md:214` — confirmed there is no per-key config table in README.md, only a single link-row pointing at `docs/reference/CONFIGURATION.md`. No `[[readme_conventions]]` decision-rule entry exists in `.ll/decisions.yaml`; the phrase in this issue's Files-to-Modify list refers to that one link-row, not a table to extend. [Agent 2 finding]
- `.claude/CLAUDE.md` `## CLI Tools` section — confirmed `ll-code` is **not** currently listed (zero grep matches). Adding it is FEAT-2576's responsibility, not this issue's — ENH-2577 only extends the *behavior* of an entry FEAT-2576 will create. No CLAUDE.md change needed here unless FEAT-2576 lands first, in which case its `ll-code` bullet should already account for provider/freshness capability. [Agent 2 finding]
- `CHANGELOG.md` — confirmed most recent entries sit at the top under a concrete version heading (`## [1.142.0] - 2026-07-11` at line 8), with `## [Unreleased]` present further down (line 312) and currently empty of any `code_query`/`ll-code`/`codegraph` mentions. Per [[feedback_changelog_no_unreleased]] this issue's entry should land in the next cut version section at release time, not be inserted under `[Unreleased]`. [Agent 2 finding]
- `.gitignore` / `.codegraph/.gitignore` — verified both the root `.gitignore:131` blanket `.codegraph/` entry and the nested `.codegraph/.gitignore` (ignoring `*.db`, `*.db-wal`, `*.db-shm`, etc.) already exist. **No `.gitignore` change is needed** for this issue's scope — the "if needed" hedge in Files to Modify can be resolved as not needed. [Agent 2 finding]
- `scripts/little_loops/templates/*.json` (e.g. `python-generic.json`) — precedent check: `analytics` gets an explicit `"enabled": false` template stanza (line 78–80), but `learning_tests`/`dependency_mapping` do not appear in templates at all, relying purely on `config-schema.json` defaults. Since `code_query`'s default (`provider: "auto"`, absent block == fallback-only) already matches "zero behavior change when absent," no template stanza is likely needed — judgment call, not a hard requirement. [Agent 2 finding]

### Configuration
- `code_query` block (above); absent block == fallback-only, zero behavior change.

## Implementation Steps

1. Schema-discover `.codegraph/codegraph.db`; write the mapping note into the module docstring.
2. Implement provider queries + `capabilities()` for the mappable verbs; build the test fixture db.
3. Implement `status()` staleness detection + policy enforcement in resolver/CLI.
4. Add `code_query` config block + plumbing; docs; `ll-verify-docs`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `CodeQueryConfig` dataclass to `scripts/little_loops/config/core.py`, wired into `BRConfig`; add unit tests in `scripts/tests/test_config.py`.
6. Add `test_code_query_in_schema()` to `scripts/tests/test_config_schema.py` following the `test_analytics_in_schema`/`test_parallel_epic_branches_in_schema` idiom.
7. Add a `### \`code_query\`` subsection to `docs/reference/CONFIGURATION.md` (plus an entry in its `## Full Configuration Example` block) and a module/dataclass row to `docs/reference/API.md`.
8. Confirm no `.gitignore` or `python-generic.json` template change is required (both already cover this issue's needs per wiring research); do not add a CLAUDE.md `ll-code` entry here — that belongs to FEAT-2576.

## Impact

- **Priority**: P3 — turns the protocol from "nice refactor" into actual exact-and-cheap queries.
- **Effort**: Medium — one provider + config + staleness matrix tests.
- **Risk**: Low-Medium — read-only, optional, and fall-through-safe; main risk is upstream schema drift, mitigated by the pinned fixture and capability fall-through.
- **Breaking Change**: No.

## Related Issues

- **EPIC-2575** — parent. **Blocked by FEAT-2576** (protocol/registry/CLI must exist).
- **ENH-2578** — consumer; blocked by this issue.
- **EPIC-2456** — token cost reduction context.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Concerns
- Critical dependency unresolved: FEAT-2576 (the `CodeQueryProvider` protocol, registry, and `ll-code` CLI this issue registers against) is still `status: open` — `scripts/little_loops/codequery/` does not exist anywhere in the tree. There is no `_PROVIDER_MAP`, `resolve_provider`, `CodeQueryProvider` Protocol, `CodeRef`, or `ProviderStatus` dataclass to build against today. Implementation cannot start until FEAT-2576 lands.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-12
- **Reason**: Issue too large for single session (size score 11/11, Very Large)

### Decomposed Into
- ENH-2612: code_query config block and CodeQueryConfig dataclass
- ENH-2613: codegraph SQLite provider with staleness detection

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log
- `/ll:issue-size-review` - 2026-07-12T00:00:00Z - `manual decomposition into ENH-2612, ENH-2613`
- `/ll:refine-issue` - 2026-07-12T06:34:06 - `965c5e08-03d9-4a04-bf49-6dd36d51ad14.jsonl`
- `/ll:confidence-check` - 2026-07-12T00:00:00 - `d6cd1e78-a373-4e05-bd99-549d1ac936df.jsonl`
- `/ll:wire-issue` - 2026-07-12T06:30:33 - `92216c13-1838-417f-a110-1d9986bdffa0.jsonl`
- `/ll:refine-issue` - 2026-07-12T06:23:40 - `c9facc02-77d7-4604-aa35-146d94881b4c.jsonl`

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`
