---
id: ENH-3636
type: ENH
title: 'll-issues show: annotate resolved blocked_by/depends_on edges with status'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T17:29:51Z'
---

# ENH-3636: ll-issues show: annotate resolved blocked_by/depends_on edges with status

## Summary

`ll-issues show` renders the `Blocked by:` and `Depends on:` relationship rows as raw frontmatter IDs without resolving each target's status, so an already-satisfied blocker reads as a live one. Example: ENH-3623 shows `Blocked by: ENH-3630` even though ENH-3630 is `done`.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

`blocked_by` / `depends_on` edges are durable by design — nothing prunes them when the target completes (`set_status.py:268` documents that these association edges never cascade). Resolution is computed at read time: `DependencyGraph.get_blocking_issues()` returns `blockers - completed` (`dependency_graph.py:283`), so schedulers (`next-issue`, sprints, autodev) already treat ENH-3623 as unblocked. Only the display disagrees, which prompted a false "is refine-to-ready-issue broken?" investigation on 2026-09-27 after a refine-to-ready-issue run on ENH-3623 (the run's `gate_unmet` failure was unrelated).

## Proposed Solution

Display-side only — do not mutate frontmatter:

- In `_render_relationships_block` (`scripts/little_loops/cli/issues/show.py`, keys table `_RELATIONSHIP_KEYS`; fields built via `_join_ids` around the `"blocked_by"` / `"depends_on"` entries), resolve each ID's status and annotate resolved ones, e.g. `Blocked by: ENH-3630 (done)`, or split them into a separate `Resolved blockers:` row.
- Only `done` / `cancelled` resolve an edge; `deferred` is non-terminal and must still render as a live blocker.
- Unknown / unresolvable IDs render unchanged (maybe `(missing)`).
- `--json`: consider adding a structured per-edge status (e.g. `blocked_by_status` or `unresolved_blocked_by`) rather than changing the existing string field. Note `--json` status is display-cased ("Completed" = done), so any comparison must normalize.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py`:
  - `_parse_card_fields` (~261-392): reuse the already-loaded `_all = find_issues(config, status_filter=set(_ALL_STATUSES))` (line 284) to build an ID → status map, mirroring the existing `parent_display` ID→title resolution (BUG-3392 pattern, same function).
  - `_RELATIONSHIP_KEYS` (521-532) / `_render_relationships_block` (535-542): annotate resolved `blocked_by`/`depends_on` entries.

### Dependent Files (Callers/Importers)
- None. `dep_graph.get_blocking_issues()` is otherwise only used by scheduler logic (`issue_manager.py:1882,1972`), which already excludes completed blockers and is untouched by this display-only change.

### Similar Patterns
- `parent_display` resolution at `show.py:270-292` (BUG-3392) — same "resolve ID via already-loaded issue list" shape; follow it rather than adding a new lookup helper.

### Tests
- Model after `test_relationships_fields_extracted` (`test_show.py:509`), `test_parent_display_resolves_title_when_parent_is_done` (`test_show.py:559`), and `test_relationships_block_renders_blocked_by` (`test_show.py:802`).

### Documentation
- N/A (display-only CLI output change; no doc claims to update).

### Configuration
- N/A

## Implementation Steps

1. Reuse the issue list already loaded in `_parse_card_fields` (`_all`, show.py:284) to build an ID → raw status map — no extra scan needed.
2. **Do not reuse `show.py`'s local `_TERMINAL_STATUSES` (line 455, `{"done", "cancelled", "deferred", "closed"}`) to decide "resolved"** — that set is for closure-note rendering and treats `deferred` as terminal, which is wrong here. Use `{"done", "cancelled"}` explicitly (matching `issue_progress._TERMINAL_STATUSES`, `issue_progress.py:14`), consistent with `deferred` staying non-terminal for dependency edges per `dependency_graph.py:283`.
3. Annotate or split resolved edges in the text renderer for `blocked_by` and `depends_on`.
4. Add the structured field to `--json` output if chosen (purely additive — current `show.py:806` just does `print_json(fields)`, so a new key like `blocked_by_status` is non-breaking).
5. Tests: resolved (`done`, `cancelled`), unresolved (`open`, `deferred`), and missing targets.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- `ll-issues show ENH-3623` makes it visible that ENH-3630 is resolved.
- A `deferred` or `open` blocker renders without a resolved annotation.
- No frontmatter is modified by `show`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-09-27T17:29:56 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
