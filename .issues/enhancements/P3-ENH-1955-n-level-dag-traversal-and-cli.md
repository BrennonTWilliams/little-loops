---
id: ENH-1955
title: N-level DAG traversal and CLI for project-root summary
type: ENH
priority: P3
status: open
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

## Scope

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

## Files to Modify

- `scripts/little_loops/history_reader.py:715` — `ll_expand()` (N-level traversal)
- `scripts/little_loops/history_reader.py:627` — `ll_grep()` (N-level filtering)
- `scripts/little_loops/cli/history.py` — root-traversal subcommand
- `scripts/little_loops/cli/session.py:374` — describe output format (add `level`)
- `scripts/tests/test_history_reader.py:845` — add root-traversal test
- `scripts/tests/test_ll_session.py:529,678` — add N-level CLI tests
- `docs/reference/CONFIGURATION.md:1150` — update compaction config docs
- `docs/reference/CLI.md:1755` — document root-traversal subcommand
- `CONTRIBUTING.md:246` — update migration version range

## Acceptance Criteria

- `ll-session expand <root-node-id>` returns ALL messages across all sessions condensed into that root
- `ll-session grep --summary-id <root-node-id> <pattern>` searches across all condensed sessions
- `ll-history root` (or equivalent) identifies and displays the project-root summary node
- Existing 2-level traversal behavior is preserved (no regression for single-session condensed queries)
- Documentation reflects N-level DAG structure (not "two-hop")

## Session Log
- `/ll:issue-size-review` - 2026-06-04T19:28:00Z - `8b66735f-5337-46b3-ba3c-44648e5faca2.jsonl`
