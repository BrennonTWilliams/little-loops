---
id: ENH-2612
title: code_query config block and CodeQueryConfig dataclass
type: ENH
priority: P3
status: done
labels:
- code-intelligence
- adapters
- config
parent: ENH-2577
completed_at: '2026-07-12T06:58:39Z'
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2612: code_query config block and CodeQueryConfig dataclass

## Summary

Add the `code_query` config-schema block (provider selection, codegraph db path,
staleness policy) and its typed `CodeQueryConfig` dataclass wiring into `BRConfig`,
so the codegraph provider (ENH-2613) has an opt-in configuration surface to read
from. This is inert config only — no provider consumes it until ENH-2613 lands.

## Current Behavior

No `code_query` config block exists in `config-schema.json`, and there is no
`CodeQueryConfig` dataclass in `BRConfig`. There is no opt-in configuration
surface for provider selection, codegraph db path, or staleness policy — any
future codegraph provider (ENH-2613) would have nowhere to read settings from.

## Expected Behavior

A `code_query` block is defined in `config-schema.json` (provider selection,
codegraph db path, staleness policy) and a typed `CodeQueryConfig` dataclass
(with nested `CodeQueryCodegraphConfig`) is wired into `BRConfig`, addressable
via `resolve_variable()`. The block is inert — its presence or absence causes
zero runtime behavior change until ENH-2613 lands and consumes it.

## Parent Issue

Decomposed from ENH-2577: codegraph SQLite provider with staleness detection and
code_query config block.

## Proposed Solution

### Config (`code_query` block in config-schema)

```json
"code_query": {
  "provider": "auto | codegraph | fallback",   // default "auto"
  "codegraph": { "db_path": ".codegraph/codegraph.db" },
  "staleness": "strict | warn | off"           // default "warn"
}
```

Add to `scripts/little_loops/config-schema.json` following existing optional-block
conventions. Exact convention to mirror: `learning_tests` block (~line 997) and
`analytics` block (~line 1577), plus `dependency_mapping` (~line 1068) — top-level
`"type": "object"` with a feature-naming `"description"`; every property carries
an inline `"description"` and an explicit `"default"`; enum-typed properties use a
bounded `"enum"` list; every object level (including the nested `codegraph`
sub-object) sets `"additionalProperties": false`.

### CodeQueryConfig dataclass

Add a `CodeQueryConfig` dataclass to `scripts/little_loops/config/core.py` (the
typed config aggregator that wraps `config-schema.json` blocks into dataclasses,
mirroring `ProjectConfig`, `IssuesConfig`, etc.) and wire it into `BRConfig`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Module location correction**: config dataclasses are **not** defined
  inside `core.py` itself — `core.py` only hosts `BRConfig` (the aggregator)
  and imports domain dataclasses from elsewhere. The closest analogs live in
  `scripts/little_loops/config/automation.py` (`DependencyMappingConfig` +
  nested `ScoringWeightsConfig`, class defs ~line 228–320) and
  `scripts/little_loops/config/features.py` (`SyncConfig` + nested
  `GitHubSyncConfig`, ~line 676–730; `LearningTestsConfig` + nested
  `DiscoverabilityConfig`, ~line 457–501). Define `CodeQueryConfig` (and a
  nested `CodeQueryCodegraphConfig` for the `codegraph.db_path` sub-object) in
  one of these domain modules — `features.py` is the better fit given
  `code_query` is a feature-flag-shaped block like `learning_tests`/`sync` —
  then import it into `core.py` for wiring. Also add both dataclasses to
  `scripts/little_loops/config/__init__.py`'s export list (confirmed it
  currently exports `LearningTestsConfig`, `DependencyMappingConfig`,
  `AnalyticsCaptureConfig` following this pattern) — missing from the
  "Files to Modify" list below.
- **`from_dict` pattern**: mirror `DependencyMappingConfig.from_dict` —
  plain `data.get(field, default)` per scalar field, and for the nested
  sub-object delegate via `codegraph=CodeQueryCodegraphConfig.from_dict(data.get("codegraph", {}))`
  (never manually unpack the nested dict).
- **`BRConfig` wiring touchpoints** (`scripts/little_loops/config/core.py`):
  1. import at top (mirrors `from little_loops.config.features import (..., SyncConfig, ...)`, lines 23-36)
  2. one line in `_parse_config()`: `self._code_query = CodeQueryConfig.from_dict(self._raw_config.get("code_query", {}))` (mirrors lines 223-226)
  3. a `@property` accessor returning `self._code_query` (mirrors `dependency_mapping`/`sync` properties, lines 294-302)
  4. an entry in `to_dict()` re-flattening every field including the nested sub-object (mirrors `dependency_mapping`, lines 740-751) — this alone makes `code_query.<field>` addressable via `resolve_variable()` with no separate wiring.
- **Enum validation — no shared validator exists.** Two competing conventions coexist in `scripts/little_loops/config/`:

  > **Selected:** Option A — Unvalidated, matches the dominant `SyncConfig.provider` convention and the issue's own "inert config only" scope.

  **Option A**: Unvalidated (majority pattern) — `SyncConfig.provider`,
  `GitHubSyncConfig.pull_template` read via plain `data.get(field, default)`
  with zero Python-side validation; the JSON-Schema `enum` array is the only
  constraint. This is what `dependency_mapping` (no enum fields) and most
  blocks implicitly follow.

  **Option B**: Inline module-level frozenset + `raise ValueError` (minority
  pattern) — e.g. `_VALID_SHOW_DIAGRAMS` in `features.py` (~line 590),
  checked inside `from_dict` with a descriptive error message. Used for
  fields where an invalid runtime value would otherwise silently misbehave
  rather than fail fast.

  **Recommended**: Option A for `provider` and `staleness` — consistent with
  the closest analog (`SyncConfig.provider`), and this block is explicitly
  "inert config only" per the issue's own scope boundary, so a bad enum
  value has no runtime consequence until ENH-2613 lands and can validate at
  the point of use instead.
- **Confirmed schema line numbers** (`scripts/little_loops/config-schema.json`):
  `learning_tests` block spans 997–1039 (not just the single reference line
  in "Files to Modify" above), `dependency_mapping` spans 1068–1142, and a
  `sync` block at 1143+ is actually the closest structural analog (enum
  field + nested sub-object with independent `additionalProperties: false`
  at each level) — worth consulting alongside `dependency_mapping`.
- **Test precedents confirmed with exact locations**: `TestDependencyMappingConfig`
  class at `scripts/tests/test_config.py:2092` (defaults/all-fields/partial/
  BRConfig-defaults/BRConfig-loads-from-file/to_dict/resolve_variable test
  shape to mirror for `TestCodeQueryConfig`); `test_learning_tests_in_schema`
  at `scripts/tests/test_config_schema.py:188` (closest analog: enum field +
  nested sub-object); `test_analytics_in_schema` at
  `scripts/tests/test_config_schema.py:328`; `test_parallel_epic_branches_in_schema`
  at `scripts/tests/test_config_schema.py:744`.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-12.

**Selected**: Option A — Unvalidated enum fields (`data.get(field, default)`, JSON-Schema `enum` as the only constraint)

**Reasoning**: Two parallel `ll:codebase-pattern-finder` agents confirmed Option A matches the dominant convention across `scripts/little_loops/config/` — `SyncConfig.provider`, `GitHubSyncConfig.pull_template`, `DiscoverabilityConfig.mode`, and `LearningTestsConfig.release_gate` are all enum-shaped fields read with zero Python-side validation, versus only 2 validated call sites (`NextIssueConfig.strategy`/`sort_keys`, `LoopRunDefaults.show_diagrams`) in the entire package — and those 2 exceptions guard fields with immediate runtime consequences downstream, unlike `code_query`, which the issue itself scopes as "inert config only" with no consumer until ENH-2613.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Unvalidated | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| B — Frozenset + ValueError | 1/3 | 2/3 | 3/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: `SyncConfig.provider` (`features.py:716,724`) is the direct precedent — enum-constrained-by-schema, zero Python validation; 4+ unvalidated enum fields exist vs. 2 validated call sites in the whole package.
- Option B: `_VALID_SHOW_DIAGRAMS` frozenset (`features.py:597-610`) is a proven, copyable shape with an established `pytest.raises` test template, but it's confined to fields where an invalid value would silently misbehave at the point of use — not the case for this inert block.

## Scope Boundaries

- **Not** the codegraph provider itself, its query verbs, or staleness detection
  logic — ENH-2613.
- **Not** anything that reads/consumes this config at runtime — nothing does until
  ENH-2613 lands; absent block == zero behavior change.

## Files to Modify

- `scripts/little_loops/config-schema.json` — `code_query` block
- `scripts/little_loops/config/features.py` — `CodeQueryConfig` + nested
  `CodeQueryCodegraphConfig` dataclasses (see Codebase Research Findings above
  for why `features.py`, not `core.py`, is the correct definition site)
- `scripts/little_loops/config/core.py` — import `CodeQueryConfig`, wire into
  `BRConfig` (`_parse_config`, `@property`, `to_dict()`)
- `scripts/little_loops/config/__init__.py` — add `CodeQueryConfig` (and
  `CodeQueryCodegraphConfig`) to the package export list, following the
  existing `LearningTestsConfig`/`DependencyMappingConfig` pattern
- `scripts/tests/test_config.py` — unit tests for `CodeQueryConfig`, following the
  existing per-block test-class pattern (e.g. `TestProjectConfig`, `TestIssuesConfig`)
- `scripts/tests/test_config_schema.py` — new `test_code_query_in_schema()` method;
  no existing test currently references `code_query`. Two precedent shapes:
  `test_analytics_in_schema` (top-level block) or `test_parallel_epic_branches_in_schema`
  (nested-object-under-existing-block)
- `docs/reference/CONFIGURATION.md` — new `### \`code_query\`` subsection under
  `## Configuration Sections`, mirroring `### \`dependency_mapping\`` or
  `### \`learning_tests\``; add a `code_query` stanza to the master
  `## Full Configuration Example` fenced block
- `docs/reference/API.md` — add a `code_query` → `CodeQueryConfig` row to the
  dataclass table (mirror `dependency_mapping` → `DependencyMappingConfig`)

## Configuration Precedent Notes

- `scripts/little_loops/templates/*.json` (e.g. `python-generic.json`): `analytics`
  gets an explicit `"enabled": false` template stanza, but `learning_tests`/
  `dependency_mapping` do not appear in templates at all, relying purely on
  `config-schema.json` defaults. Since `code_query`'s default (`provider: "auto"`,
  absent block == fallback-only) matches "zero behavior change when absent," no
  template stanza is needed.
- No `.gitignore` change needed — `.codegraph/` is already covered by the root
  `.gitignore` and `.codegraph/.gitignore`.
- No `.claude/CLAUDE.md` `ll-code` entry needed here — that's FEAT-2576's
  responsibility.

## Tests

- `TestCodeQueryConfig` in `test_config.py`: parses `code_query` block into
  `CodeQueryConfig`, defaults applied when block absent, enum validation.
- `test_code_query_in_schema()` in `test_config_schema.py`: schema shape
  (`additionalProperties: false`, defaults, enums) matches the convention.

## Impact

- **Priority**: P3
- **Effort**: Small — one config-schema block + one dataclass + tests + docs.
- **Risk**: Low — pure config addition, no runtime behavior change.
- **Breaking Change**: No.

## Related Issues

- **ENH-2577** — parent (decomposed).
- **ENH-2613** — sibling; the codegraph provider that will consume this config.
- **FEAT-2576** — the `CodeQueryProvider` protocol/registry this config ultimately feeds.

## Resolution

Implemented per plan: added the `code_query` block to `config-schema.json`
(provider enum, nested `codegraph.db_path`, staleness enum, all with
`additionalProperties: false` and inline descriptions/defaults, mirroring the
`sync` block), and `CodeQueryConfig`/`CodeQueryCodegraphConfig` dataclasses in
`config/features.py` following the `SyncConfig`/`GitHubSyncConfig` shape
(unvalidated enum fields per the issue's Decision Rationale). Wired into
`BRConfig` (`config/core.py`: import, `_parse_config`, `code_query` property,
`to_dict()` flattening) and exported from `config/__init__.py`. Added
`TestCodeQueryConfig` to `test_config.py` and `test_code_query_in_schema` to
`test_config_schema.py`, plus `### code_query` docs in `CONFIGURATION.md` and
a table row in `API.md`. Block is inert — no consumer reads it until
ENH-2613.

## Status

**Done** | Created: 2026-07-12 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-07-12T06:50:17 - `e790b28b-77ad-4da0-a8eb-272c072894b9.jsonl`
- `/ll:confidence-check` - 2026-07-12T00:00:00Z - `0d016e20-da23-4be5-aac3-7ffe2219c05e.jsonl`
- `/ll:decide-issue` - 2026-07-12T06:46:52 - `a591bc0d-6216-48f5-94ab-18e616d35056.jsonl`
- `/ll:refine-issue` - 2026-07-12T06:43:08 - `c1734e8d-ff37-42a9-b2f6-0a61f7c9052b.jsonl`
- `/ll:issue-size-review` - 2026-07-12T00:00:00Z - `manual decomposition of ENH-2577`
- `/ll:manage-issue` - 2026-07-12T06:57:59Z - `ed006d5c-a47c-4f34-b972-76e507a085fc.jsonl`
