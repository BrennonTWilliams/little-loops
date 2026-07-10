---
id: FEAT-2576
title: CodeQuery provider protocol, grep/AST fallback provider, and ll-code CLI
type: FEAT
priority: P3
status: open
labels: [code-intelligence, adapters, cli, token-cost, captured]
captured_at: "2026-07-10T05:34:41Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2575
---

# FEAT-2576: CodeQuery provider protocol, grep/AST fallback provider, and ll-code CLI

## Summary

Add a `little_loops/codequery/` module defining a small provider protocol for structural code queries, a registry-backed resolver modeled on the `HostEmitter` pattern in `adapters/core.py` (FEAT-2391), a **grep/AST fallback provider** as the day-one reference implementation, and an `ll-code` CLI command so `/ll:` skills can call it through their Bash allowlists. The protocol is shaped by the queries our discovery-heavy skills actually ask — not by any external tool's feature set — so graph backends (ENH-2577) plug in behind a stable, tiny surface.

## Current Behavior

Skills answer structural questions by open-ended exploration: `/ll:wire-issue` traces callers/importers/config/tests with repeated Grep/Glob/find rounds; `/ll:find-dead-code` and `/ll:audit-architecture` do the same. There is no shared, cheap, machine-queryable answer to "who calls X" / "who imports Y" / "what is impacted if these files change", even though a codegraph SQLite index already exists at `.codegraph/codegraph.db`. Each agent re-derives the same facts, paying tokens and turns every time.

## Expected Behavior

```bash
ll-code status                          # provider name, availability, freshness, capabilities
ll-code callers-of little_loops.issue_manager.IssueManager.load   # who calls this symbol
ll-code callees-of <symbol>             # what this symbol calls
ll-code importers-of little_loops/frontmatter.py                  # who imports this module/file
ll-code defines little_loops/sync.py    # symbols defined in a file
ll-code references <symbol>             # all reference sites (defs + uses)
ll-code impact-of little_loops/state.py little_loops/events.py    # reverse transitive closure, depth-limited
ll-code --provider fallback callers-of <symbol>                   # force a specific provider
ll-code --json callers-of <symbol>      # machine-readable output for skills/loops
```

Every subcommand works with **no graph tool installed** (fallback provider), and every result carries a `source: <provider>` and `freshness: fresh|stale|unknown` marker so consumers know how much to trust it.

## Use Case

`/ll:wire-issue FEAT-XXXX` needs every caller of a function being re-signatured. Today that is 4–8 Grep rounds interpreted by the agent. With this feature the skill runs `ll-code --json callers-of <symbol>` (one Bash call), seeds its Integration Map candidate list from the result, and spends its remaining budget confirming the handful of hits with targeted Grep — instead of discovering them from scratch.

## Proposed Solution

New package `scripts/little_loops/codequery/` mirroring the `adapters/` layout:

### Protocol (`codequery/core.py`)

```python
@runtime_checkable
class CodeQueryProvider(Protocol):
    name: str
    def capabilities(self) -> set[str]: ...       # subset of QUERY_KINDS
    def status(self) -> ProviderStatus: ...       # available, freshness, index metadata
    def callers_of(self, symbol: str) -> list[CodeRef]: ...
    def callees_of(self, symbol: str) -> list[CodeRef]: ...
    def importers_of(self, module: str) -> list[CodeRef]: ...
    def defines(self, path: str) -> list[CodeRef]: ...
    def references(self, symbol: str) -> list[CodeRef]: ...
    def impact_of(self, paths: list[str], depth: int = 2) -> list[CodeRef]: ...
```

- `CodeRef` dataclass: `path`, `line`, `symbol`, `kind`, `confidence` (`exact | heuristic`), provider `name`.
- `ProviderStatus`: `available: bool`, `freshness: fresh|stale|unknown`, `indexed_at`, `detail`.
- `AdapterError`-style `CodeQueryError`; lazy-import registry `_PROVIDER_MAP` + `resolve_provider(name | "auto")` exactly like `resolve_emitter` in `adapters/core.py`. `"auto"` picks the first registered provider whose `status()` is available (graph providers first, fallback last).
- A provider lacking a capability raises `Unsupported` → resolver falls through to the fallback for that query only.

### Fallback provider (`codequery/fallback.py`)

- `defines` / `callees_of` via Python `ast` parse of the target file (exact).
- `callers_of` / `references` / `importers_of` via `git grep -n` word-boundary search over tracked files (heuristic; `confidence: heuristic` on every ref).
- `impact_of` via import-graph walk built from `ast` imports, depth-limited (this is the codepath `dependency_graph.py` never covered: code-level, not issue-level).
- Always `available`, always `freshness: fresh` (it reads the working tree directly). This provider IS the degradation story — consumers never write `if graph_available` branches.

### CLI (`ll-code`)

- `ll-code = "little_loops.cli:main_code"` in `scripts/pyproject.toml` `[project.scripts]`, implemented in the `little_loops/cli/` package following `main_deps`/`main_issues` conventions (argparse subcommands, `--json`, exit 0/1/2 = hits/no-hits/provider-error).
- Human output compact and scanning-first (grid/track conventions per ENH-2572 learnings); `--json` output is the contract skills consume.

## Scope Boundaries

- **Not** the codegraph SQLite provider — ENH-2577.
- **Not** any skill integration — ENH-2578 wires `/ll:wire-issue` first.
- **Not** index building, watching, or reindexing — providers only read.
- **Not** cross-language support in the fallback — Python `ast` for exact queries, `git grep` heuristics for everything else (matches this repo; other languages arrive with graph providers that support them).
- **Not** MCP transport — `mcp_call.py` exists if a future provider is MCP-only; out of scope here.

## API/Interface

- New module `scripts/little_loops/codequery/` (`__init__.py`, `core.py`, `fallback.py`).
- New CLI `ll-code` with subcommands `status | callers-of | callees-of | importers-of | defines | references | impact-of`, flags `--provider`, `--json`, `--depth`.
- JSON result schema: `{provider, freshness, query, results: [CodeRef...]}` — stable contract for skills and future FSM `evaluate` phases.

## Integration Map

### Files to Create
- `scripts/little_loops/codequery/__init__.py`
- `scripts/little_loops/codequery/core.py` — protocol, dataclasses, registry, resolver
- `scripts/little_loops/codequery/fallback.py` — grep/AST provider
- `scripts/tests/test_codequery_core.py`, `scripts/tests/test_codequery_fallback.py`

### Files to Modify
- `scripts/pyproject.toml` — register `ll-code` console script
- `scripts/little_loops/cli/` — add `main_code` entry point module
- `README.md` / docs CLI reference — new command listed; keep `ll-verify-docs` count checks green (see [[readme_conventions]])
- `docs/` CLI reference page + `mkdocs.yml` nav if commands are enumerated

### Dependent Files
- ENH-2577 registers `codegraph` in `_PROVIDER_MAP`.
- ENH-2578 calls `ll-code --json` from `skills/wire-issue/SKILL.md`.

### Similar Patterns
- `scripts/little_loops/adapters/core.py` — Protocol + lazy registry + `resolve_*` factory (FEAT-2391); copy this shape deliberately.
- `scripts/little_loops/dependency_mapper/` — issue-level analogue; keep domains separate.

### Tests
- Protocol conformance test run against every registered provider (fallback now; codegraph in ENH-2577 reuses it).
- Fallback correctness on this repo's own source (e.g., `callers_of` a known helper returns its known call sites); heuristic queries assert `confidence: heuristic`.
- CLI: `--json` schema stability, exit-code contract.

### Documentation
- README CLI table + docs page per [[readme_conventions]]; CHANGELOG entry.

### Configuration
- None in this issue — the `code_query` config block lands with the first configurable provider (ENH-2577).

## Implementation Steps

1. Write `core.py` (protocol, `CodeRef`, `ProviderStatus`, registry, resolver) mirroring `adapters/core.py`.
2. Implement `fallback.py`; validate `callers_of`/`defines` answers against hand-checked spots in `little_loops/`.
3. Add `main_code` CLI + pyproject script; wire `--json` and exit codes.
4. Protocol conformance + fallback + CLI tests.
5. Register in README/docs; run `ll-verify-docs`.

## Impact

- **Priority**: P3 — foundation for measured token savings (EPIC-2456 alignment); no consumer blocked today.
- **Effort**: Medium — one new package + CLI + tests; no engine or loop YAML changes.
- **Risk**: Low — additive; fallback provider only reads the working tree.
- **Breaking Change**: No.

## Related Issues

- **EPIC-2575** — parent.
- **ENH-2577** — codegraph provider behind this protocol (blocked by this issue).
- **ENH-2578** — wire-issue consumer + measurement (blocked by this issue and ENH-2577).
- **EPIC-2456** — token cost reduction; this epic's payoff is measured there-style.
- **FEAT-2391** — `HostEmitter` adapter precedent being mirrored.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`
