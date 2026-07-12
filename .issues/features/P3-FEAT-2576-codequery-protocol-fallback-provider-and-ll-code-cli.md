---
id: FEAT-2576
title: CodeQuery provider protocol, grep/AST fallback provider, and ll-code CLI
type: FEAT
priority: P3
status: open
labels:
- code-intelligence
- adapters
- cli
- token-cost
- captured
captured_at: '2026-07-10T05:34:41Z'
discovered_date: '2026-07-10'
discovered_by: capture-issue
parent: EPIC-2575
decision_needed: false
confidence_score: 98
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 24
score_ambiguity: 25
score_change_surface: 20
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**A complete, tested implementation of this issue already exists on an unmerged branch.** Commit `53512663` ("feat(codequery): add CodeQuery provider protocol, grep/AST fallback, and ll-code CLI") on branch `epic/epic-2575-code-knowledge-graph-adapter-query-protocol-providers-skill-integration` implements this issue in full — `codequery/core.py`, `codequery/fallback.py`, `cli/code.py`, and 20 tests across `test_codequery_core.py`, `test_codequery_fallback.py`, `test_cli_code.py` (13 files changed, 1025 insertions). It is **not** an ancestor of current `main` (`git merge-base --is-ancestor 53512663 main` fails). A dry-run cherry-pick (`git cherry-pick --no-commit -n 53512663`, reverted after inspection) applies cleanly against current `main` with only one trivial auto-merge in `docs/reference/API.md` — no conflicts in `scripts/little_loops/cli/__init__.py` or `scripts/pyproject.toml` despite `main` having since landed `4c4dcc79` (ENH-2612's `code_query` config block).

> **Selected:** Option A — cherry-pick applies cleanly (independently verified) and reuses 20 already-passing tests instead of duplicating the work.

**Option A**: Cherry-pick commit `53512663` onto `main`, then adjust only what changed underneath it (rebase the `code_query` config wiring from ENH-2612 into `resolve_provider`'s `"auto"` default if desired), and run the full test suite.

**Option B**: Reimplement from scratch per this issue's `## Proposed Solution`, ignoring the unmerged commit.

**Recommended**: Option A — the unmerged commit already matches this issue's design almost exactly (see corrections below) and includes 20 passing tests; reimplementing would duplicate verified work for no benefit.

**Exact landed shapes (differ slightly from this issue's draft above — use these if reimplementing, or as the base if cherry-picking):**

- `CodeRef` and `ProviderStatus` are `@dataclass(frozen=True)`, not plain `@dataclass` — matches the `HostInvocation` frozen-value-object convention in `scripts/little_loops/host_runner.py:92-104`.
- `CodeRef`'s last field is `provider: str`, **not** `name` as drafted in this issue's Proposed Solution.
- `Unsupported(CodeQueryError)` is a real subclass in `codequery/core.py` (not just described prose) — providers raise it for capabilities outside `capabilities()`; the resolver catches it to fall through per-query.
- `QUERY_KINDS: frozenset` enumerates the six verbs (`callers_of`, `callees_of`, `importers_of`, `defines`, `references`, `impact_of`) at module level in `core.py` — `capabilities()` returns a subset of this constant.
- `_PROVIDER_MAP: dict[str, tuple[str, str]]` currently has exactly one entry: `{"fallback": ("little_loops.codequery.fallback", "FallbackProvider")}` — mirrors `_EMITTER_MAP` in `scripts/little_loops/adapters/core.py:45` field-for-field (lazy-import tuple registry, same reason: avoids circular imports since concrete providers import back from `core.py`).
- `resolve_provider(name="auto")` in the landed commit iterates `_PROVIDER_MAP` in insertion order, returning the first provider whose `status().available` is `True`; `_instantiate()` does `importlib.import_module` + `getattr`, same as `resolve_emitter` (`adapters/core.py:52`).

**Config interaction**: `CodeQueryConfig` (`provider: str = "auto"`, plus a `codegraph` sub-block and `staleness` field) already landed on `main` via a separate commit (`4c4dcc79`, tracked as ENH-2612/ENH-2613 — note: `.issues/enhancements/P3-ENH-2577-codegraph-sqlite-provider-with-staleness-detection.md` was superseded/renumbered to `P3-ENH-2613-codegraph-sqlite-provider-with-staleness-detection.md` per the working tree). Its docstring reads `"Code-query provider selection and staleness policy (inert until ENH-2613)"` — i.e. it's already wired into `BRConfig.code_query` (`scripts/little_loops/config/core.py`) and `config-schema.json` (lines ~1205-1233, `provider` enum already includes `"auto" | "codegraph" | "fallback"`), but nothing reads it yet. This issue's CLI (`ll-code --provider`) is the first consumer; wiring `resolve_provider()`'s `"auto"` default to read `BRConfig.code_query.provider` is in scope here even though `CodeQueryConfig` itself was built in a separate issue.

**Existing patterns to reuse (already present on `main`, independent of the unmerged branch)**:
- `scripts/little_loops/cli/deps.py::main_deps()` — CLI shape to follow: `cli_event_context(...)` wrapper, `argparse` subparsers, `add_json_arg()` from `little_loops.cli_args`, `print_json()`/`success`/`error` from `little_loops.cli.output`.
- `scripts/tests/test_adapters.py::TestResolveEmitter` (lines 84-99) — exact test shape for `resolve_provider`: known-key resolves correct class, unknown-key raises domain error listing registered keys, resolved instance satisfies the Protocol via `isinstance()`.
- `scripts/little_loops/observability/audit.py::_ast_extract_event_types` (line 75) — only existing `ast.parse`/`ast.walk` usage in the package; wraps parsing in `try/except SyntaxError: return` (fail-soft on unparseable files), the convention to follow in `fallback.py`'s `defines`/`callees_of`.
- No existing `git grep` subprocess call exists anywhere in `scripts/little_loops/*.py` (only a loop-YAML shell state uses it) — the `_git()` helper idiom in `scripts/little_loops/hooks/post_commit.py:27` and `scripts/little_loops/worktree_utils.py:41` (`subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=...)`, returns `None` on failure rather than raising) is the closest precedent for `callers_of`/`references`/`importers_of`'s `git grep -n` calls.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option A — cherry-pick commit `53512663`

**Reasoning**: Independent verification (`git cherry-pick --no-commit -n 53512663` against current `main`, reverted after inspection) confirmed the commit applies with zero conflicts, only one trivial auto-merge in `docs/reference/API.md`. The commit is an isolated single-commit branch off an ancestor of `main`, and no fragment of the `codequery/` package exists on `main` today (confirmed via Glob/Grep), so there is nothing to reconcile. Reimplementing would discard 20 already-passing tests and re-derive `git grep`-based logic that has zero precedent elsewhere in the codebase — the highest-risk, least-templated part of the feature.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A (cherry-pick) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (reimplement) | 2/3 | 1/3 | 1/3 | 1/3 | 5/12 |

**Key evidence**:
- Option A: Branch `epic/epic-2575-...` tip is exactly commit `53512663`, forked from an ancestor of `main` with only one commit of divergence. Main has advanced by exactly two commits since the fork point (`4c4dcc79` ENH-2612 config, `c9fa7082` unrelated), and the cherry-pick's only conflict is a trivial auto-merge in `docs/reference/API.md`. `codequery/`, `cli/code.py`, and the three new test files do not exist on `main` — nothing to duplicate or reconcile.
- Option B: General scaffolding patterns exist (`adapters/core.py` registry shape, `cli/deps.py` CLI convention, `observability/audit.py` ast-walk idiom) but none are CodeQuery-domain-specific; the `git grep`-based `callers_of`/`references`/`importers_of` logic has zero existing precedent in `scripts/little_loops/*.py`, making it the riskiest part of a from-scratch rewrite of already-tested code.



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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — add `from little_loops.cli.code import main_code`, append `"main_code"` to `__all__`, and add an `ll-code` line to the module docstring's CLI list (lines ~37-46/95-98) [confirmed against landed commit 53512663]
- `.claude/CLAUDE.md` — append an `ll-code` bullet to the "## CLI Tools" list (after the `ll-deps` entry, ~line 203) [confirmed against landed commit 53512663]

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_code.py` — new test file (CLI JSON schema + exit-code contract); was implied by "Files to Create" prose but not explicitly listed there [confirmed present in landed commit 53512663, 78 lines]

### Documentation
- README CLI table + docs page per [[readme_conventions]]; CHANGELOG entry.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — new `## little_loops.codequery` section (Protocol, `resolve_provider`, built-in providers) added after the `adapters/` section [confirmed against landed commit 53512663, ~48 lines]
- `docs/reference/CLI.md` — new `### ll-code` section (global flags table, subcommand table, examples) added after the `ll-deps` section [confirmed against landed commit 53512663, ~40 lines]
- Correction: the landed commit does **not** touch `README.md` or `mkdocs.yml` — `README.md` has no CLI-tools list to update (0 matches for `ll-` bullets) and `mkdocs.yml`'s nav does not enumerate individual CLI reference sections. Treat the generic "README.md / mkdocs.yml" line above as superseded by this finding rather than a real touchpoint.

### Configuration
- `CodeQueryConfig` already landed on `main` (`scripts/little_loops/config/features.py:729-758`, wired into `BRConfig.code_query` at `scripts/little_loops/config/core.py:228,307-309`) ahead of this issue, via a separate commit. This issue should read `BRConfig.code_query.provider` as `resolve_provider()`'s `"auto"` default source rather than treating config as fully out of scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- If Option A (cherry-pick) is chosen: run `git cherry-pick 53512663` on a feature branch off current `main`, resolve the trivial `docs/reference/API.md` auto-merge, then re-run `python -m pytest scripts/tests/test_codequery_core.py scripts/tests/test_codequery_fallback.py scripts/tests/test_cli_code.py scripts/tests/test_adapters.py scripts/tests/test_config.py -v` to confirm no regressions against the config work that landed after the original commit.
- `scripts/tests/test_deps_cli.py` (`_setup_project`/`_write_issue` helpers, `patch.object(sys, "argv", ...)` invocation pattern) is the CLI-test convention `test_cli_code.py` already follows in the unmerged commit — reuse if reimplementing.

## Implementation Steps

1. Write `core.py` (protocol, `CodeRef`, `ProviderStatus`, registry, resolver) mirroring `adapters/core.py`.
2. Implement `fallback.py`; validate `callers_of`/`defines` answers against hand-checked spots in `little_loops/`.
3. Add `main_code` CLI + pyproject script; wire `--json` and exit codes.
4. Protocol conformance + fallback + CLI tests.
5. Register in README/docs; run `ll-verify-docs`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Register `main_code` in `scripts/little_loops/cli/__init__.py` — import, `__all__`, and docstring CLI list entry.
7. Append an `ll-code` bullet to `.claude/CLAUDE.md`'s CLI Tools list.
8. Add `## little_loops.codequery` to `docs/reference/API.md` and `### ll-code` to `docs/reference/CLI.md` (not README.md/mkdocs.yml — see Documentation correction above).
9. Add `scripts/tests/test_cli_code.py` alongside the two `test_codequery_*.py` files.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-12_

**Readiness Score**: 98/100 → READY
**Outcome Confidence**: 89/100 → High confidence

### Outcome Risk Factors
- Independent re-verification of the cherry-pick (`git cherry-pick --no-commit -n 53512663`, reverted) found a **real conflict in this issue's own frontmatter/body** — not just the "trivial `docs/reference/API.md` auto-merge" claimed in the Codebase Research Findings. The conflict exists because `/ll:refine-issue`, `/ll:decide-issue`, and `/ll:wire-issue` have all edited this issue file since commit `53512663` was authored, so its stale copy of the issue markdown collides with the current one. Trivially resolvable (keep the current issue file, discard the commit's copy of it), but implementers should expect one more conflict than the issue currently documents. All code/test/docs files (`codequery/`, `cli/code.py`, `docs/reference/*.md`, `pyproject.toml`) applied with zero conflicts in this re-verification.

## Status

**Open** | Created: 2026-07-10 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-07-12T00:00:00 - `a03c42b0-4719-47ff-b40c-07de6db2a3cb.jsonl`
- `/ll:wire-issue` - 2026-07-12T17:49:07 - `2beb02be-92aa-450c-93a9-e259ca395e8e.jsonl`
- `/ll:decide-issue` - 2026-07-12T17:46:10 - `3f8a7dab-b194-4168-92a6-36d34389d5fd.jsonl`
- `/ll:refine-issue` - 2026-07-12T16:33:00 - `62f65534-90b9-48f0-b94e-3a884a85b403.jsonl`

- `/ll:capture-issue` - 2026-07-10T05:34:41Z - `manual capture via Claude Cowork session (EPIC-2575 design discussion)`
