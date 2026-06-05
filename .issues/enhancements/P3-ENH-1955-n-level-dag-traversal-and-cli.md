---
id: ENH-1955
title: N-level DAG traversal and CLI for project-root summary
type: ENH
priority: P3
status: done
parent: ENH-1927
relates_to:
- FEAT-1712
- ENH-1953
- ENH-1954
labels:
- enhancement
- history
- cli
- traversal
---

# ENH-1955: N-level DAG traversal and CLI for project-root summary

## Summary

Generalize the hard-coded 2-level DAG traversal in `ll_expand()` and `ll_grep()` to support N levels, add root-traversal capability to `ll-history` CLI, and update documentation to reflect the multi-level DAG structure.

## Parent Issue

Decomposed from ENH-1927: Recursive cross-session condensation for a project-root summary

## Dependencies

- **ENH-1953** must be completed first (schema v12 with `level` column must exist).
- **ENH-1954** must be completed first (cross-session condensation must actually create the multi-level DAG before traversal can navigate it).

## Motivation

This enhancement completes the reader-side of the cross-session condensation pipeline (ENH-1927). Without N-level traversal, condensed summaries can only be queried one level deep — the project-root summary created by ENH-1954 would exist in the database but its full message set would be unreachable. Each additional condensation level is invisible to users, undermining the value of the recursive condensation pass.

## Current Behavior

The 2-level DAG traversal in `ll_expand()` and `ll_grep()` hard-codes a single parent hop: when a row's `kind` is `"condensed"`, it performs one `parent_id` lookup to reach the leaf messages. Summaries of summaries (level > 1) cannot be traversed — intermediate condensed nodes act as opaque leaf nodes, and their descendant messages are invisible. The `ll-history` CLI has no concept of a project-root summary node.

## Expected Behavior

N-level recursive traversal walks the full `parent_id` chain from any node (including the project root with `session_id IS NULL`) down to all descendant leaf messages:

- `ll-session expand <any-node-id>` returns ALL messages across all condensed sessions, regardless of DAG depth
- `ll-session grep --summary-id <any-node-id> <pattern>` searches across all descendant messages
- `ll-history root` identifies and displays the project-root summary node
- Existing 2-level queries continue to work without regression

## Proposed Solution

Replace the hard-coded 2-level `kind` check with a SQLite recursive CTE (`WITH RECURSIVE`) that walks `parent_id` chains from any starting node. A single query path handles both leaf nodes (CTE returns one row, direct span join) and condensed nodes at any depth (CTE descends through intermediates to leaves). Expose the root node via a new `ll-history root` subcommand. Update documentation references from "two-hop" to "N-level DAG traversal."

This is a reader-side-only change — schema v12 (ENH-1953) and the cross-session condensation pass (ENH-1954) are prerequisites that provide the multi-level DAG structure.

## Scope Boundaries

This child covers the reader-side generalization of DAG traversal and the CLI/documentation surface. It does NOT include the schema migration (ENH-1953) or the condensation algorithm (ENH-1954).

## Implementation Steps

### 1. Generalize DAG traversal to N levels

`history_reader.py:715` — `ll_expand()`:
- Replace the hard-coded 2-level check (`if kind_row["kind"] == "condensed": ... else: ...`) with an iterative `parent_id` walk
- Start at the given node, collect descendant leaf nodes via recursive SQL or Python loop, then join to `summary_spans → message_events`
- Alternative: Use a SQLite recursive CTE (`WITH RECURSIVE`) to walk `parent_id` chains — no precedent in this codebase (tree traversal is Python-based; see `dependency_graph.py:272` Kahn's algorithm) but SQLite supports it
- Ensure the existing 2-level path remains correct while adding N-level support

`history_reader.py:627` — `ll_grep()`: same N-level generalization for `--summary-id` filtering.

### 2. Update `ll-history` CLI

`scripts/little_loops/cli/history.py` — Add a root-traversal path:
- Identify the root node as the condensed node with `session_id IS NULL` (or max `level`) that has no parent (`parent_id IS NULL`)
- Expose via a new subcommand (e.g., `ll-history root`) or as the default starting point for `ll-history summary`
- Note: `ll_expand`/`ll_grep` are exposed through `ll-session` CLI (`cli/session.py:330`), not `ll-history` — ensure the root-traversal entry point is navigable from both CLIs

### 3. CLI output format

`scripts/little_loops/cli/session.py:374-377` — If `level` is added to `describe` text output, update the print block which hardcodes which fields are shown.

`scripts/tests/test_ll_session.py:622` — Update `test_describe_returns_node_metadata` assertions if `level=` is added to describe output.

### 4. Documentation updates

- `docs/reference/CONFIGURATION.md:1150-1182`: Add `cross_session_enabled`/`max_level` to config key table and JSON example; update "two-hop traversal" to "N-level"; remove the `update-docs` TODO stub after completing the write-up.
- `CONTRIBUTING.md:246`: Update `session_store.py` description from "v1–v10 migrations" to "v1–v12 migrations".
- `docs/reference/CLI.md:1755`: If a root-traversal subcommand is added to `ll-history`, document it; `ll-session describe` already mentions "level" preemptively.

## Tests

- Add `test_expand_root_node_returns_all_messages()` to `TestSummaryDagRetrieval` in `test_history_reader.py:845`
- Add N-level variants of CLI integration tests in `test_ll_session.py:529` (`TestGrepExpandDescribe`)
- Add `test_expand_condensed_node_n_levels_cli` and `test_grep_with_condensed_summary_id_n_levels_cli` in `test_ll_session.py:678`

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py:715` — `ll_expand()` (N-level traversal)
- `scripts/little_loops/history_reader.py:627` — `ll_grep()` (N-level filtering)
- `scripts/little_loops/cli/history.py` — root-traversal subcommand
- `scripts/little_loops/cli/session.py:374` — describe output format (add `level`)
- `scripts/tests/test_history_reader.py:845` — add root-traversal test
- `scripts/tests/test_ll_session.py:529,678` — add N-level CLI tests
- `docs/reference/CONFIGURATION.md:1150` — update compaction config docs
- `docs/reference/CLI.md:1755` — document root-traversal subcommand
- `CONTRIBUTING.md:246` — update migration version range

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py:330` — exposes `ll_expand()`/`ll_grep()` via `ll-session` CLI
- Any code calling `ll_expand()` or `ll_grep()` directly

### Tests
- `scripts/tests/test_history_reader.py:845` — `TestSummaryDagRetrieval`
- `scripts/tests/test_ll_session.py:529,678` — `TestGrepExpandDescribe`

### Documentation
- `docs/reference/CONFIGURATION.md` — compaction config section
- `docs/reference/CLI.md` — CLI reference
- `CONTRIBUTING.md` — migration version range

## API/Interface

New CLI surface:
- `ll-history root [--expand] [--limit N] [--json]` — identify and display the project-root summary node
- `ll-session expand <node-id>` — generalized from 2-level to N-level DAG traversal
- `ll-session grep --summary-id <node-id> <pattern>` — generalized from 2-level to N-level
- `ll-session describe` — may include `level=` field in text output

No Python API changes — internal function signatures for `ll_expand()` and `ll_grep()` remain compatible.

## Acceptance Criteria

- `ll-session expand <root-node-id>` returns ALL messages across all sessions condensed into that root
- `ll-session grep --summary-id <root-node-id> <pattern>` searches across all condensed sessions
- `ll-history root` (or equivalent) identifies and displays the project-root summary node
- Existing 2-level traversal behavior is preserved (no regression for single-session condensed queries)
- Documentation reflects N-level DAG structure (not "two-hop")

## Impact

- **Priority**: P3 — Reader-side generalization blocked on two prerequisite ENHs (ENH-1953, ENH-1954). Non-blocking for other work.
- **Effort**: Medium — Primarily refactoring two functions in `history_reader.py`, adding one CLI subcommand, and documentation updates.
- **Risk**: Low — Traversal is read-only; existing 2-level behavior preserved. No schema changes (schema migration is ENH-1953).
- **Breaking Change**: No — New subcommand is additive; existing `expand`/`grep` behavior is unchanged.

## Resolution

Generalized the hard-coded two-hop DAG traversal in `ll_expand()` and `ll_grep()` to N levels using a SQLite recursive CTE (`WITH RECURSIVE`), added `ll-history root` subcommand for project-root summary display, and updated documentation to reflect N-level DAG structure.

### Implementation

- **Core traversal** (`history_reader.py`): Replaced the `kind='condensed'` branch in both `ll_expand()` and `ll_grep()` with a single recursive CTE path that works uniformly for leaf nodes (CTE = 1 row, direct span join) and condensed nodes at any depth (CTE descends through intermediate nodes to reach leaves). The `kind` check and two-branch `if/else` are removed — one query handles everything.
- **CLI** (`cli/history.py`): Added `ll-history root` subcommand with `--expand`, `--limit`, and `--json` flags. Finds the project-root node as the condensed node with `session_id IS NULL AND parent_id IS NULL` with the highest `level`.
- **Tests**: 5 new tests across `test_history_reader.py` (3: root expansion, intermediate node expansion, multi-level grep) and `test_ll_session.py` (2: CLI expand/grep with multi-level DAG).

### Design Decision

Chose a recursive CTE over iterative Python loops because:
- Single SQL round-trip vs. N+1 queries
- SQLite fully supports `WITH RECURSIVE`
- The approach naturally handles both leaf and condensed nodes uniformly
- No precedent for recursive CTEs in the codebase, but tree traversal is already Python-based (`dependency_graph.py:272` Kahn's algorithm) — the CTE keeps traversal logic in the DB layer where the data lives

### Files Modified (7 files, +310/-45)

| File | Change |
|------|--------|
| `scripts/little_loops/history_reader.py:628-760` | Replaced two-hop traversal with recursive CTE in `ll_grep()` and `ll_expand()` |
| `scripts/little_loops/cli/history.py:204-222,307-353` | Added `root` subparser and command handler |
| `scripts/tests/test_history_reader.py:1016-1112` | 3 new multi-level DAG tests |
| `scripts/tests/test_ll_session.py:702-814` | 2 new CLI multi-level DAG tests |
| `docs/reference/CLI.md:1499-1517,1773-1774` | Documented `ll-history root` and updated expand/grep descriptions |
| `docs/reference/CONFIGURATION.md:1160` | "two-hop traversal" → "N-level DAG traversal" |
| `CONTRIBUTING.md:246` | "v1–v10 migrations" → "v1–v12 migrations" |

### Verification
- ✓ All 9,871 tests passed (0 failures)
- ✓ Ruff linting: clean
- ✓ MyPy type checking: clean

## Session Log
- `/ll:format-issue` - 2026-06-05T02:04:08 - `9f7cb561-1b94-4485-bab6-c7b6f0688f94.jsonl`
- `/ll:manage-issue` - 2026-06-05T01:50:00Z - implementation and verification session
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
