---
id: ENH-1734
type: ENH
priority: P2
status: done
parent: ENH-1691
discovered_date: 2026-05-26
completed_at: 2026-05-27 01:24:58+00:00
labels:
- enhancement
- documentation
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1734: Documentation Updates for ENH-1691 EventBus Wiring

## Summary

Update all documentation and schema files to reflect the ENH-1691 wiring: new `AutoManager.__init__` signature, new event types (`issue.skipped`, `issue.started`), updated backfill framing, and `config-schema.json` description corrections.

## Current Behavior

Documentation files do not reflect the ENH-1691/ENH-1733 EventBus wiring. Specifically: `AutoManager.__init__` docs omit `db_path`, `label_filter`, and `preview_full` parameters; `issue.skipped` and `issue.started` event types are absent from `EVENT-SCHEMA.md`; the ARCHITECTURE.md CLI wiring table has no `ll-auto` row; `CLI.md` and `CONFIGURATION.md` frame `ll-session backfill` as the primary recording mechanism rather than legacy support; and the `config-schema.json` sqlite description says "FSM loop events only" instead of noting issue lifecycle events.

## Expected Behavior

All documentation files accurately reflect the ENH-1733 wiring implementation: `AutoManager.__init__` docs include all parameters; `issue.skipped` and `issue.started` appear in `EVENT-SCHEMA.md` with field tables and JSON examples; `ll-auto` row appears in the ARCHITECTURE.md CLI wiring table; backfill framing updated to reflect live-write as primary mechanism; `config-schema.json` sqlite description includes issue lifecycle events.

## Impact

- **Priority**: P2 — Keeps documentation aligned with the ENH-1733 implementation; required for users to understand `ll-auto`'s event recording behavior and for schema tooling to remain consistent
- **Effort**: Small — Documentation edits with two mechanical code changes (schema definition entries + test count assertions)
- **Risk**: Low — No logic changes; test assertion updates are arithmetic (35 → 37)
- **Breaking Change**: No

## Parent Issue

Decomposed from ENH-1691: Wire Issue Lifecycle EventBus to SQLiteTransport

## Scope

Covers Wiring Phase items 4–7 from ENH-1691 plus the three referenced doc files in "Files to Modify".

**In scope** (all from Wiring Phase added by `/ll:wire-issue`):
- `docs/reference/API.md` — add `db_path: Path | None = None` to `AutoManager.__init__` signature block; fix pre-existing omissions: add `event_bus: EventBus | None = None` to `complete_issue_lifecycle` and `defer_issue` signature blocks
- `docs/reference/CLI.md` (line 1062) — update "run `ll-session backfill`" framing to reflect live writes; (line 1291) update `### ll-session` description to note `AutoManager` also populates via live-write
- `docs/reference/CONFIGURATION.md` (line 883) — update backfill description to reflect live transport
- `docs/ARCHITECTURE.md` (line ~512–517) — add `ll-auto` row to Extensions/Transports table; note `AutoManager` wires `SQLiteTransport` directly in `__init__`, not via `wire_transports()`
- `docs/reference/EVENT-SCHEMA.md` (lines ~909–916) — add `issue.skipped` and `issue.started` to master event-type table; add `### issue.skipped` and `### issue.started` section blocks
- `config-schema.json` (line ~1178) — update `sqlite` block description from "FSM loop events only" to include issue lifecycle events; note `AutoManager.__init__()` wires directly rather than via config-driven `wire_transports`

**Out of scope**: Source code and test changes (ENH-1733).

**Dependency**: Should be done after ENH-1733 merges so actual signatures and event names can be confirmed against the implementation. Can proceed in parallel if the implementer confirms the design decisions match the issue spec.

## Integration Map

### Files to Modify

- `docs/reference/API.md` — Multiple sections need updates (see Implementation Steps for detail)
- `docs/reference/CLI.md` — Two locations: ~line 1062 (backfill framing) and ~line 1291 (ll-session description)
- `docs/reference/CONFIGURATION.md` — Line ~883: backfill description
- `docs/ARCHITECTURE.md` — CLI wiring table (~lines 512–517): add `ll-auto` row
- `docs/reference/EVENT-SCHEMA.md` — Master event-type table (~lines 909–916) + two new section blocks
- `config-schema.json` — Line ~1178: `sqlite` block `description` field

### Additional ARCHITECTURE.md Sections

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — `### Event Emitters` table, "Issue Lifecycle" row (~line 507): "Issue status transitions (move, close, defer)" is stale — must add `skip` and `undefer` (→ `issue.skipped`, `issue.started`)
- `docs/ARCHITECTURE.md` — `SQLiteTransport` prose paragraph (~line 519): describes only the config-driven selection path; must note `AutoManager.__init__()` also wires `SQLiteTransport` directly without `events.transports` config
- `docs/ARCHITECTURE.md` — `AutoManager` class diagram (~lines 622–626): missing `event_bus: EventBus` and `db_path: Path | None` members

### Schema Maintenance Files

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/generate_schemas.py` — `SCHEMA_DEFINITIONS` at line 440+: must add `issue.skipped` and `issue.started` entries (required per `CONTRIBUTING.md` `## Event Schema Maintenance` procedure — adding to `EVENT-SCHEMA.md` without updating `SCHEMA_DEFINITIONS` leaves `docs/reference/schemas/` inconsistent)
- `docs/reference/schemas/` — `issue_skipped.json` and `issue_started.json` are absent; must be generated via `ll-generate-schemas` after updating `SCHEMA_DEFINITIONS`

### Dependent Files (Callers/Importers — for cross-checking signatures)

- `scripts/little_loops/issue_manager.py` — `AutoManager.__init__` (actual impl to verify against): `db_path: Path | None = None` is the only new `__init__` param; `event_bus` is constructed internally via `EventBus()`, not injected
- `scripts/little_loops/issue_lifecycle.py` — `complete_issue_lifecycle`, `defer_issue`, `undefer_issue`, `skip_issue` (all confirmed to accept `event_bus: EventBus | None = None`)
- `scripts/little_loops/session_store.py` — `_ISSUE_TRANSITION_MAP` and `SQLiteTransport` (source of truth for which event types are recorded)

### Event Fields (confirmed from source)

Both new events share the same payload shape:
```json
{ "event": "issue.skipped", "ts": "...", "issue_id": "...", "file_path": "...", "reason": "..." }
{ "event": "issue.started", "ts": "...", "issue_id": "...", "file_path": "...", "reason": "..." }
```

### Similar Patterns

- `docs/reference/EVENT-SCHEMA.md` `### issue.deferred` (line ~738) — 3-column field table + JSON example; use as template for `issue.skipped` and `issue.started`
- ARCHITECTURE.md `### Components` CLI wiring table (4 columns: `CLI Entry Point | File | Extensions Wired | Transports Wired`) — existing rows for `ll-loop run`, `ll-parallel`, `ll-sprint` as style reference
- API.md `### UnixSocketTransport` (line ~6140) — multi-param `#### Constructor` block style

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_schemas.py` — `TestCatalogIntegrity.test_all_34_event_types_defined` (line 17), `test_expected_event_types_present` (line 21), `TestGenerateSchemas.test_creates_34_files` (line 66): all assert count == 35; adding `issue.skipped` + `issue.started` to `SCHEMA_DEFINITIONS` will raise count to 37 — update these three methods
- `scripts/tests/test_enh1734_doc_wiring.py` — **new test file needed**: follow pattern from `scripts/tests/test_enh1639_doc_wiring.py` and `scripts/tests/test_circuit_breaker_doc_wiring.py`; one class per doc file, one method per symbol/phrase that must appear (e.g., `"db_path"` in `API.md`, `"issue.skipped"` in `EVENT-SCHEMA.md`, `"ll-auto"` in `ARCHITECTURE.md`)

### Release Notes

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — no entry exists for ENH-1733 (implementation) or ENH-1734 (documentation); add under the current version block (not `[Unreleased]`)

## Implementation Notes

- **CONFIRMED**: `undefer_issue()` emits `"issue.started"` (not `"issue.undeferred"`) and `skip_issue()` emits `"issue.skipped"` — verified in `issue_lifecycle.py`
- **IMPORTANT**: `AutoManager.__init__` does NOT accept `event_bus` as a parameter — it constructs one internally: `self.event_bus = EventBus()` then `self.event_bus.add_transport(SQLiteTransport(db_path or DEFAULT_DB_PATH))`. The issue scope correctly targets `event_bus` for `complete_issue_lifecycle` and `defer_issue` signatures only.
- The ARCHITECTURE.md row for `ll-auto` differs from other CLI entry points: `AutoManager` calls `SQLiteTransport` in `__init__()` directly, not via the external `wire_transports()` helper — the "Transports Wired" cell should document this distinction
- `config-schema.json` `sqlite` block should clarify both FSM loop events AND issue lifecycle events are written; `AutoManager` is the wiring mechanism for the latter
- **ADDITIONAL GAP** (not in original scope): `undefer_issue` return description in API.md is stale — currently says "New Path of the issue in its active category directory" but the current implementation returns `deferred_issue_path` unchanged (in-place status update, no file move)
- **ADDITIONAL GAP**: `docs/reference/API.md` has no `### SQLiteTransport` section at all — it is only referenced inline in prose. The `### JsonlTransport`, `### UnixSocketTransport`, `### OTelTransport`, `### WebhookTransport` sections exist; `SQLiteTransport` is the only transport without its own section. Adding it is optional but consistent with the existing pattern.
- **ADDITIONAL**: `AutoManager.__init__` docs also missing `label_filter: set[str] | None = None` and `preview_full: bool = False`; `only_ids` type documented as `set[str] | None` but actually `list[str] | set[str] | None`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_manager.py` `AutoManager.__init__` full actual signature confirmed (13 params including `db_path`); no `event_bus` param
- `scripts/little_loops/issue_lifecycle.py` `skip_issue()` emits `issue.skipped`; `undefer_issue()` emits `issue.started` — both confirmed via source inspection
- `scripts/little_loops/session_store.py` `_ISSUE_TRANSITION_MAP`: `"issue.skipped"` → `"cancelled"`, `"issue.started"` → `"in_progress"` — these are the DB-recorded transition values
- API.md currently documents `AutoManager` constructor at lines ~1993–2017 with `**Parameters:**` bullet list style — append new params in same style
- EVENT-SCHEMA.md `## Subsystem: Issue Lifecycle` block starts at line ~663; new sections go at end of that subsystem block, before `## Subsystem: Parallel Orchestrator`

## Implementation Steps

1. **`docs/reference/API.md` — `AutoManager.__init__` constructor block**: Add `label_filter: set[str] | None = None`, `preview_full: bool = False`, `db_path: Path | None = None` bullets to the `**Parameters:**` list; correct `only_ids` type from `set[str] | None` to `list[str] | set[str] | None`; add a `**Behavior:**` note that `EventBus` and `SQLiteTransport` are wired automatically inside `__init__` using `db_path or DEFAULT_DB_PATH`
2. **`docs/reference/API.md` — lifecycle function signatures**: Add `event_bus: EventBus | None = None` bullet to `complete_issue_lifecycle`, `defer_issue`, and `undefer_issue` parameter lists; fix `undefer_issue` return description from "New Path of the issue in its active category directory" to "Same path as `deferred_issue_path` — the issue is updated in-place (status set to `open`), no file is moved"
3. **`docs/ARCHITECTURE.md` — CLI wiring table**: Add row `| \`ll-auto\` | \`cli/auto.py\` | No — EventBus is internal to AutoManager | Yes — \`AutoManager.__init__()\` wires \`SQLiteTransport(db_path)\` directly; does not call \`wire_transports()\` |`
4. **`docs/reference/EVENT-SCHEMA.md` — master event-type table** (~lines 909–916): Add `issue.skipped` and `issue.started` rows; then add `### \`issue.skipped\`` and `### \`issue.started\`` section blocks following the `### issue.deferred` pattern (3-column field table: `event`, `ts`, `issue_id`, `file_path`, `reason`; JSON example; `---` separator)
5. **`docs/reference/CLI.md`**: At ~line 1062, reframe "run `ll-session backfill`" to note that `ll-auto` now writes live; backfill is for pre-ENH-1691 historical data only. At ~line 1291, update `### ll-session` description to note `AutoManager` populates `issue_events` via live-write during `ll-auto` runs.
6. **`docs/reference/CONFIGURATION.md`** (~line 883): Update backfill description to say live-write is the primary mechanism; backfill handles data captured before ENH-1691.
7. **`config-schema.json`** (~line 1178): Update `sqlite` description from `"Records FSM loop events into the per-project session store (.ll/history.db) for indexed cross-cutting queries via the ll-session CLI."` to also mention issue lifecycle events (`issue.completed`, `issue.deferred`, `issue.skipped`, `issue.started`, `issue.closed`, `issue.failure_captured`) recorded by `AutoManager.__init__()` wiring.
8. **Verify**: Run `ll-check-links docs/` to confirm no broken cross-references after edits.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **`docs/ARCHITECTURE.md` — `### Event Emitters` table** (~line 507): Update "Issue Lifecycle" row's events column to add `issue.skipped` (from `skip_issue()`) and `issue.started` (from `undefer_issue()`)
10. **`docs/ARCHITECTURE.md` — `SQLiteTransport` prose paragraph** (~line 519): Append a note that `AutoManager.__init__()` also wires `SQLiteTransport` directly (not via `events.transports` config); contrast with the config-driven path described for other CLI tools
11. **`docs/ARCHITECTURE.md` — `AutoManager` class diagram** (~lines 622–626): Add `+event_bus: EventBus` and `+db_path: Path | None` members to the `AutoManager` class block
12. **`scripts/little_loops/generate_schemas.py` — `SCHEMA_DEFINITIONS`**: Add `issue.skipped` and `issue.started` schema entries following the `issue.deferred` pattern (fields: `event`, `ts`, `issue_id`, `file_path`, `reason`); run `ll-generate-schemas` to regenerate `docs/reference/schemas/issue_skipped.json` and `docs/reference/schemas/issue_started.json`
13. **`scripts/tests/test_generate_schemas.py`**: Update count assertions from `35` to `37` in `test_all_34_event_types_defined`, `test_creates_34_files`, and the CLI test; add `"issue.skipped"` and `"issue.started"` to the expected event types set in `test_expected_event_types_present`
14. **`scripts/tests/test_enh1734_doc_wiring.py`**: Create new doc-wiring test file following the `test_enh1639_doc_wiring.py` pattern — verify `db_path` in `API.md`, `issue.skipped`/`issue.started` in `EVENT-SCHEMA.md`, `ll-auto` row in `ARCHITECTURE.md`, backfill framing in `CLI.md` and `CONFIGURATION.md`
15. **`CHANGELOG.md`**: Add entries for ENH-1733 (AutoManager EventBus wiring) and ENH-1734 (documentation) under the current version block

## Acceptance Criteria

- [ ] `docs/reference/API.md` shows `AutoManager.__init__(db_path=None)` signature
- [ ] `docs/reference/EVENT-SCHEMA.md` has `issue.skipped` and `issue.started` entries
- [ ] `docs/ARCHITECTURE.md` Extensions/Transports table includes `ll-auto` row
- [ ] `docs/reference/CLI.md` backfill references updated to reflect live writes
- [ ] `config-schema.json` sqlite description updated to include issue lifecycle events
- [ ] All existing doc links and cross-references remain valid

## Session Log
- `/ll:ready-issue` - 2026-05-27T01:18:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f657cb51-7ebf-4206-8d71-17b6a8e4c26c.jsonl`
- `/ll:wire-issue` - 2026-05-27T01:13:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/147823b3-5677-4a95-9394-0e44304c03ce.jsonl`
- `/ll:refine-issue` - 2026-05-27T01:08:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71ba2e27-21e9-408e-8681-668910c7758a.jsonl`
- `/ll:issue-size-review` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f138859-02cf-4887-806e-2fe090003148.jsonl`
- `/ll:confidence-check` - 2026-05-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fefabb3d-d79b-4a32-9161-7ae16fb0f115.jsonl`
