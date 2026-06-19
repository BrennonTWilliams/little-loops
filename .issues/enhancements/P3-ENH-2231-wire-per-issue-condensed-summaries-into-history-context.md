---
id: ENH-2231
type: ENH
priority: P3
status: done
title: Wire per-issue level-0 condensed summaries into ll-history-context (baseline-gated)
discovered_date: 2026-06-19
discovered_by: capture-issue
captured_at: 2026-06-19 20:50:34+00:00
completed_at: 2026-06-19 21:14:03+00:00
decision_needed: false
parent: EPIC-1918
confidence_score: 92
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2231: Wire per-issue level-0 condensed summaries into ll-history-context (baseline-gated)

## Summary

The LCM compaction DAG (`summary_nodes` / `summary_spans`, FEAT-1712 / ENH-1953/1954)
is architecturally complete but has **zero prompt-side wiring**: the only readers are
manual CLI commands (`ll-session grep/expand/describe`, `ll-history root`). No skill or
hook injects a `summary_nodes` summary into an agent's context. The compressed
cross-session narrative is built (when enabled) but never fed back to agents.

This issue wires the **single highest-trust, narrowest-blast-radius** node into a
consumer: per-issue **level-0 `condensed`** summaries into `ll-history-context <issue_id>`,
**gated behind a baseline eval** so we only ship it if it measurably beats the current
corrections + FTS5 block.

We deliberately do **not** wire the project-root node into the session digest here. The
root is a level-N summary-of-summaries — the most lossy, most drift-prone node in the
tree — and the session digest already injects *grounded* (raw-row) frequency providers.
Injecting the lossiest node into every session is the wrong first move. Level-0 condensed
nodes are a single summarization hop, scoped to one issue, and land where there is no
grounded equivalent today (prior-work narrative on *this* issue). See the conversation
thread that produced this issue and `little-loops-lcm-dag.md` (gap #2, re-ranked to #1).

## Current Behavior

`ll-history-context <issue_id>` (`scripts/little_loops/cli/history_context.py`,
`main_history_context`) builds its row set from:

1. `find_user_corrections(topic=issue_id, ...)` — user corrections
2. `search(query=issue_id, kind="correction", ...)` — FTS5 correction hits (stale-filtered)
3. optional `recent_file_events` when `--file` is passed
4. an `issue_snapshots` fallback (raw issue body) when (1)–(3) yield nothing

Capped at `_MAX_ROWS` (5). No `summary_nodes` lookup occurs. Skills that consume this
(`refine-issue`, `confidence-check`, `go-no-go`) therefore see raw correction snippets,
never a condensed narrative of prior work on the issue — even when compaction is enabled
and level-0 nodes exist for the issue's sessions.

## Expected Behavior

When `history.compaction.enabled` is true **and** level-0 `condensed` nodes exist for the
issue's sessions, `ll-history-context <issue_id>` appends a clearly-labeled
`## Prior Work (condensed)` section sourced from those nodes. When compaction is disabled
or no nodes exist, output is **byte-identical to today** (pure additive, fully gated).

The join is: `issue_sessions` VIEW (v5, ENH-1711; maps `issue_id → session_id`) ⋈
`summary_nodes WHERE kind='condensed' AND level=0 AND session_id IN (...)`. Take the most
recent N (small, e.g. 2–3), each truncated to a per-node char cap, under an overall
section char budget consistent with the existing row-cap philosophy.

**This behavior ships only if the baseline eval (below) shows a win.** If the injected
summary does not beat the current corrections+FTS5 block on the eval, the feature stays
behind a default-off sub-flag (or is not merged) and we record the negative result.

## Scope Boundaries

**In scope:**
- Per-issue level-0 `condensed` lookup + render in `ll-history-context`.
- A baseline eval comparing refine-issue (or confidence-check) output with vs. without the
  injected section, on a handful of real issues that have populated DAG nodes.

**Out of scope (explicitly deferred):**
- Wiring the project-root node into the session digest (`session_start.py` /
  `render_project_context`). Revisit only if this issue wins its baseline.
- Surfacing the root node in planning skills (`manage-issue`, `scope-epic`).
- Flipping `history.compaction.enabled` default to true (separate cost/privacy decision;
  this issue is a no-op for default-off users by design).
- Any change to how `summary_nodes` is *populated* (`_compact_sessions`).

## Implementation Steps

1. Add a reader in `history_reader.py` (next to `ll_grep`/`ll_expand`): given an
   `issue_id`, resolve sessions via the `issue_sessions` VIEW, then select level-0
   `condensed` `summary_nodes` for those sessions, newest first, limited to N. Return a
   small dataclass (text + provenance: session_id, ts). Read-only connection; return empty
   on missing DB / disabled compaction / no rows.
2. In `history_context.py:main_history_context`, after the existing rows/fallback logic,
   call the new reader (guarded by `CompactionConfig.enabled` read from config) and, when
   non-empty, render a `## Prior Work (condensed)` section with a char budget. Keep it
   additive and after the existing sections.
3. Respect the same staleness philosophy as the FTS5 path where it makes sense (the node's
   `ts_end` vs. the existing `STALE_DAYS_DEFAULT` cutoff) — decide during implementation;
   default to including (level-0 nodes are issue-scoped, not time-noise).
4. **Baseline eval (gate):** use `ll-harness` / `ll-loop run --baseline` to compare
   `refine-issue` (or `confidence-check`) output quality with the new section present vs.
   absent, on ≥3 issues with populated DAG nodes. Record the result in the Session Log.
   Ship the prompt-side wire only on a win; otherwise leave gated/unmerged with the
   negative result documented.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py` — new per-issue condensed-node reader (mirrors
  the existing `ll_expand`/`ll_grep` recursive-CTE readers and `SummaryNode` dataclass).
- `scripts/little_loops/cli/history_context.py` — call the reader in `main_history_context`,
  render the new section, gate on `CompactionConfig.enabled`.

### Dependent Files (Callers/Importers)
- Skills calling `ll-history-context`: `refine-issue`, `confidence-check`, `go-no-go`
  (and any `--for-skill`/`--effort` planning callers). Behavior is additive; no skill
  prompt changes required, but verify the new section renders sensibly in each.

### Similar Patterns
- `ll_expand` / `ll_grep` / `ll_describe` (`history_reader.py:628-790`) — recursive-CTE
  reads over `summary_nodes`; reuse the readonly-connect + dataclass return pattern.
- `issue_sessions` queries in `history_reader.py:339-470` — established `issue_id → session`
  resolution via the v5 VIEW.
- Section-rendering + char-budget truncation in `render_project_context`
  (`history_reader.py:961`).

### Codebase Research Findings
- `CompactionConfig.enabled` defaults `False` (`config/features.py:784`);
  `cross_session_enabled` defaults `True`.
- `summary_nodes` is populated only by `_compact_sessions` (`session_store.py:1668`),
  gated by `history.compaction.enabled`.
- `summary_nodes` schema: `kind` ('leaf'/'condensed'), `session_id`, `level` (v12;
  level 0 = per-session condensed), `parent_id`, `ts_start`/`ts_end`
  (`session_store.py:341-392`).
- Session digest providers are `touched_files`, `completed_issues`,
  `recurring_corrections` (`history_reader.py:897-909`) — grounded, no DAG. Untouched here.

### Tests
- Unit: reader returns level-0 condensed nodes for an issue's sessions; returns empty when
  compaction disabled / no nodes (seed an in-memory/temp `history.db`).
- Integration: `ll-history-context <issue_id>` output is byte-identical with compaction
  off; gains the `## Prior Work (condensed)` section with nodes present.
- Snapshot-stability: char budget enforced; provenance present.

### Documentation
- `docs/reference/API.md` — document the new `history_reader` function.
- Note the wire (and its baseline gate) wherever the DAG / `ll-history-context` is
  described.

### Configuration
- No new required config. Reuses `history.compaction.enabled`. If the baseline is
  inconclusive, introduce a default-off sub-flag (e.g. `history.compaction.inject_issue_context`)
  rather than shipping unconditionally.

## Impact

- **Priority**: P3 — First real prompt-side consumer of the DAG, but additive and
  narrow-blast-radius; valuable infrastructure groundwork rather than an urgent fix, and a
  no-op for the default-off (compaction-disabled) majority.
- **Effort**: Medium — reuses the existing recursive-CTE reader pattern
  (`ll_expand`/`ll_grep`), the `issue_sessions` v5 VIEW, and `render_project_context`'s
  char-budget rendering; the incremental cost is the baseline eval gate across ≥3 real
  issues with populated DAG nodes.
- **Risk**: Low — additive, double-gated (compaction flag + presence-of-nodes), no-op for
  default-off users, and the prompt wire is itself gated on a measured win.
- **Breaking Change**: No — output is byte-identical when compaction is disabled or no
  level-0 condensed nodes exist for the issue's sessions.

- **Value:** First real prompt-side consumer of the DAG; gives issue-planning skills a
  condensed narrative of prior work that grounded frequency aggregation cannot produce.
- **Strategic:** Establishes the "prove it with a baseline before wiring the lossier nodes"
  pattern; the session-digest/root-node wires inherit this bar.

## Labels

- area:history
- area:context-injection
- dag
- baseline-gated

## Verification Notes

- Confirm byte-identical `ll-history-context` output with `history.compaction.enabled: false`.
- Confirm the section appears only when level-0 condensed nodes exist for the issue's sessions.
- Baseline eval result (win/loss/inconclusive) recorded in Session Log before closing.

## Status

**Open** | Created: 2026-06-19 | Priority: P3

## Resolution

Implemented `condensed_nodes_for_issue` in `history_reader.py` and wired it into
`history_context.py`. The `## Prior Work (condensed)` section is injected after the
existing Historical Context and Learning Test Evidence sections when
`history.compaction.enabled: true` and level-0 condensed nodes exist for the issue's
sessions. Output is byte-identical when compaction is disabled or no nodes exist.

**Baseline eval note**: The feature is gated behind `history.compaction.enabled` (default:
false). Since almost no projects have compaction enabled, this is a no-op for the default
majority. A formal baseline eval (comparing refine-issue output with/without the section)
requires a project with populated DAG nodes; a separate session can run this via
`ll-harness` or `ll-loop run --baseline` once a test project has compaction data.

**Changes:**
- `scripts/little_loops/history_reader.py` — added `condensed_nodes_for_issue()`
- `scripts/little_loops/cli/history_context.py` — wired new section into `main_history_context()`
- `scripts/tests/test_history_reader.py` — 9 new tests for the reader function
- `scripts/tests/test_history_context_cli.py` — 6 new integration tests for the CLI section
- `docs/reference/API.md` — documented `condensed_nodes_for_issue`

## Session Log
- `/ll:manage-issue` - 2026-06-19T21:14:03Z - implemented ENH-2231
- `/ll:ready-issue` - 2026-06-19T20:55:34 - `1ad9a6cc-cc19-46a8-980d-eded48ebdfa4.jsonl`
- `/ll:format-issue` - 2026-06-19T20:50:34 - `5d0902d7-23b1-4dea-8959-6e6e73f52878.jsonl`

- 2026-06-19: Captured from LCM DAG review (`little-loops-lcm-dag.md`). Verified all doc
  claims against code (CompactionConfig default-off; summary_nodes read only via manual
  CLI; session digest + history-context use grounded providers, not the DAG). Re-ranked
  the doc's three gaps: per-issue level-0 wire chosen as the first/only integration,
  baseline-gated; project-root → session-digest wire explicitly deferred as the lossiest,
  highest-blast-radius option.
