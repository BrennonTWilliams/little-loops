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

`ll-issues show ENH-3623` renders `Blocked by: ENH-3630` with no indication that ENH-3630 is `done`. The card gives no way to tell a satisfied edge from a live blocker without running `ll-issues show` on each target. `--json` likewise exposes only the raw comma-joined `blocked_by` / `depends_on` strings.

## Expected Behavior

Resolved edges (target status `done` or `cancelled`) are visibly annotated in the card, e.g. `Blocked by: ENH-3630 (done), ENH-3600` with the resolved entry dimmed. Live edges (`open`, `in_progress`, `blocked`, `deferred`) and unknown IDs render exactly as today. `--json` keeps `blocked_by` / `depends_on` byte-identical and additionally exposes the still-unresolved subset.

## Motivation

`blocked_by` / `depends_on` edges are durable by design — nothing prunes them when the target completes (`set_status.py:268` documents that these association edges never cascade). Resolution is computed at read time: `DependencyGraph.get_blocking_issues()` returns `blockers - completed` (`dependency_graph.py:283`), so schedulers (`next-issue`, sprints, autodev) already treat ENH-3623 as unblocked. Only the display disagrees, which prompted a false "is refine-to-ready-issue broken?" investigation on 2026-09-27 after a refine-to-ready-issue run on ENH-3623 (the run's `gate_unmet` failure was unrelated).

## Program Design

### Types

- No new types — annotated fields stay `str | None`, same as the existing `blocked_by` / `depends_on` keys.

### Signatures

- `_parse_card_fields(path: Path, config: BRConfig) -> dict[str, str | None]` (`show.py:63`, unchanged signature) — return dict gains four keys: `blocked_by_display`, `depends_on_display`, `unresolved_blocked_by`, `unresolved_depends_on`.
- `_id_matches(candidate: str, pattern: str) -> bool` (`cli_args.py:408`) — reused as-is to resolve bare-numeric edge IDs against loaded issue IDs.
- `_render_relationships_block(fields: dict[str, str | None]) -> list[tuple[str, str]]` (`show.py:535`, unchanged signature) — reads `_RELATIONSHIP_KEYS` (repointed to the `*_display` keys) and applies `_dim(text: str) -> str` (`show.py:401`) to resolved entries.

### Call Path

`ll-issues show` CLI entry -> `_parse_card_fields` -> `_id_matches` (per edge ID, against `_all = find_issues(...)`) -> `_render_relationships_block` -> `_dim`

## Proposed Solution

Display-side only — do not mutate frontmatter, and do not change the existing `blocked_by` / `depends_on` field values.

Design decisions (settled):

- **Inline annotation, not a separate row.** Annotate only resolved IDs as `ID (done)` / `ID (cancelled)`, dimmed in the text card only. Live IDs stay plain — card values clip with an ellipsis (`_truncate_to_width`), not wrap, so tagging every ID would push long rows into truncation.
- **Resolved = `done` / `cancelled` only.** `deferred` is non-terminal for dependency edges and renders as a live blocker.
- **Unknown / unresolvable IDs render unchanged** — no `(missing)` tag.
- **New display keys, mirroring `parent_display`.** Add `blocked_by_display` / `depends_on_display` to the fields dict and point `_RELATIONSHIP_KEYS` at them; raw `blocked_by` / `depends_on` stay untouched.
- **New machine-readable JSON keys:** `unresolved_blocked_by` / `unresolved_depends_on`, comma-joined strings in the same shape as the existing fields (`None` when empty). Purely additive.
- **Fail-open:** if the issue scan raises, the display keys fall back to the raw joined IDs (no annotation) and the `unresolved_*` keys fall back to the full raw lists.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/show.py`:
  - `_parse_card_fields` (~261-392): inside the existing `try` block (line 282), reuse the already-loaded `_all = find_issues(config, status_filter=set(_ALL_STATUSES))` (line 284) to build an ID → raw status map, mirroring the existing `parent_display` ID→title resolution (BUG-3392 pattern, same function). Compute `blocked_by_display`, `depends_on_display`, `unresolved_blocked_by`, `unresolved_depends_on`; defaults set before the `try` so the `except` path yields the unannotated fallback.
  - `_RELATIONSHIP_KEYS` (521-532): swap `"blocked_by"` → `"blocked_by_display"` and `"depends_on"` → `"depends_on_display"` (same labels).

### Dependent Files (Callers/Importers)
- `skills/confidence-check/SKILL.md:163` — parses `blocked_by` from `ll-issues show --json` by splitting on commas. **The `blocked_by` value must stay byte-identical** (raw IDs, no annotation). A later follow-up could switch this skill to `unresolved_blocked_by` and drop its per-blocker `ll-issues show` calls — out of scope here.
- `scripts/little_loops/mcp_server/tools.py:138` (`issue_get`) and `scripts/little_loops/mcp_server/resources.py:264` — return `_parse_card_fields` output verbatim; they pick up the new keys automatically (additive, no code change).
- `dep_graph.get_blocking_issues()` scheduler callers (`issue_manager.py:1882,1972`) — untouched.

### Similar Patterns
- `parent_display` resolution at `show.py:270-292` (BUG-3392) — same "resolve ID via already-loaded issue list" shape; follow it rather than adding a new lookup helper.
- **ID matching:** unlike `parent_display`'s exact `i.issue_id == parent_str`, match with `_id_matches` (`cli_args.py:408`, already imported by `issue_parser`) so a bare-numeric frontmatter ID (`blocked_by: [3630]`) still resolves — the numeric ID is the canonical key.

### Tests
- Model after `test_relationships_fields_extracted` (`test_show.py:509`), `test_parent_display_resolves_title_when_parent_is_done` (`test_show.py:559`), and `test_relationships_block_renders_blocked_by` (`test_show.py:802`).

### Documentation
- `docs/reference/CLI.md:1659` (Relationships bullet under `ll-issues show`) — note that resolved `blocked_by` / `depends_on` targets are annotated `(done)` / `(cancelled)`.
- `docs/reference/CLI.md` `--json` row (~1665) — list the new `unresolved_blocked_by` / `unresolved_depends_on` keys.

### Configuration
- N/A

## Implementation Steps

1. In `_parse_card_fields`, initialize `blocked_by_display = _join_ids(blocked_by_raw)`, `depends_on_display = _join_ids(depends_on_raw)`, and `unresolved_* = ` the same raw joins, before the `try` block.
2. Inside the `try` (after `_all` is loaded), build the ID → raw status lookup and, for each edge ID, find its target via `_id_matches`. Resolved = status in `{"done", "cancelled"}` — **do not reuse `show.py`'s local `_TERMINAL_STATUSES` (line 455, `{"done", "cancelled", "deferred", "closed"}`)**; that set is for closure-note rendering and treats `deferred` as terminal. Use `issue_progress._TERMINAL_STATUSES` (`issue_progress.py:14`), consistent with `dependency_graph.py:283`.
3. Build the display strings as **plain text** (no ANSI — the fields dict is emitted verbatim by `--json` and MCP): resolved IDs → `f"{id} ({status})"`, others unchanged. Build `unresolved_*` from the non-resolved IDs (including unknown IDs), `None` if empty.
4. Add the four keys to the returned dict; repoint `_RELATIONSHIP_KEYS` at the `*_display` keys. Apply the gray `_dim` to resolved entries in `_render_relationships_block` (text card only), e.g. by dimming each comma-separated item ending in ` (done)` / ` (cancelled)`.
5. Update `docs/reference/CLI.md` (see Documentation).
6. Tests (see Acceptance Criteria).

## Scope Boundaries

- **In scope**: Annotating `blocked_by` / `depends_on` display in `ll-issues show` (text card and `--json`) with resolved status; adding the additive `unresolved_blocked_by` / `unresolved_depends_on` JSON keys.
- **Out of scope**: Migrating `skills/confidence-check/SKILL.md` to consume `unresolved_blocked_by` instead of parsing raw `blocked_by` (noted as a follow-up in Integration Map); changing `DependencyGraph.get_blocking_issues()` or any scheduler logic — resolution computation is untouched, only the `show` display; annotating `parent` or other relationship fields beyond `blocked_by` / `depends_on`.

## Impact

- **Priority**: P4 - Cosmetic/diagnostic; schedulers already compute resolution correctly, but the misleading display has already caused one false investigation.
- **Effort**: Small - One function plus a keys-table change in `show.py`, following an existing in-function pattern.
- **Risk**: Low - Display-only and additive JSON keys; the one JSON consumer's field is preserved byte-identically.
- **Breaking Change**: No

## Acceptance Criteria

- `ll-issues show ENH-3623` makes it visible that ENH-3630 is resolved.
- A `deferred`, `open`, or unknown blocker renders without a resolved annotation.
- `--json` `blocked_by` / `depends_on` values are byte-identical to pre-change output when a target is `done`.
- `--json` exposes `unresolved_blocked_by` / `unresolved_depends_on` containing only non-`done`/`cancelled` targets.
- A bare-numeric frontmatter ID (e.g. `blocked_by: [3630]`) resolves to its target's status.
- If the issue scan raises, edges render unannotated (no crash, no `(missing)`), and `unresolved_*` equals the raw lists.
- No frontmatter is modified by `show`.
- No `--json` value contains ANSI escape codes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-09-28T21:10:25 - `98bade11-bd68-4a4b-be5c-a80038f306cd.jsonl`
- `/ll:capture-issue` - 2026-09-27T17:29:56 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
