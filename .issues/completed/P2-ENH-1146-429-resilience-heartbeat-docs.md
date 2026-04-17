---
id: ENH-1146
type: ENH
priority: P2
status: open
discovered_date: 2026-04-17
parent: ENH-1135
related: [ENH-1131, ENH-1144]
size: Very Large
confidence_score: 90
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-1146: 429 Resilience — Heartbeat Documentation

## Summary

Write all documentation updates for the `rate_limit_waiting` heartbeat event and related ENH-1131 config fields: LOOPS_GUIDE, EVENT-SCHEMA, CONFIGURATION, OUTPUT_STYLING, API reference, COMMANDS, CLI reference, analyze-loop SKILL.md, and CHANGELOG entry.

## Parent Issue

Decomposed from ENH-1135: 429 Resilience — Heartbeat Events, Public API & Docs (parent is in `.issues/completed/`).

## Can run in parallel with ENH-1144 and ENH-1145 (docs are independent of code correctness).

## Upstream Dependency (Codebase Research Finding)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `rate_limit_waiting` is **not yet emitted or defined** anywhere in `scripts/little_loops/`. ENH-1144 (core code) adds the emission site and payload. Docs written here describe the forward-looking design spec — verify payload field names/types match ENH-1144's implementation at merge time.
- `scripts/little_loops/fsm/executor.py` uses the labels "short-burst tier" and "long-wait tier" in docstrings at lines 891-893, 942-944, 956. The `tier` field value space is expected to be `"short"` | `"long"` based on this convention.
- No `rate_limit_waiting.json` schema exists yet in `docs/reference/schemas/` (21 schemas present). ENH-1147 generates the schema; this doc issue just references its filename in EVENT-SCHEMA.md file listing.

## Expected Behavior

### 1. `docs/guides/LOOPS_GUIDE.md`

- Lines 1029-1031: add 2 rows for `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` to the per-state property table
- Lines 1668-1680: extend prose + YAML example with two-tier ladder + budget mechanics
- Line 2028: update `with_rate_limit_handling` fragment row "Supplies" column

### 2. `docs/reference/EVENT-SCHEMA.md`

- Lines 224-255: add `### rate_limit_waiting` event detail section (after `rate_limit_storm` or alphabetically between exhausted/storm)
- Lines 538-559: add `rate_limit_waiting` to file listing section
- Lines 629-651: add `rate_limit_waiting` to quick-reference table

Payload fields: `state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`.

**Structure to mirror** (from `docs/reference/EVENT-SCHEMA.md:222-242` — `rate_limit_exhausted` section):

```markdown
---

### `rate_limit_waiting`

Emitted periodically by the FSM executor while sleeping between 429 retry attempts (both short-burst and long-wait tiers). Provides heartbeat visibility into in-progress waits so dashboards/analysis can surface progress toward the wall-clock budget defined by `rate_limit_max_wait_seconds`.

| Field | Type | Description |
|-------|------|-------------|
| `state` | `str` | Name of the state currently retrying |
| `elapsed_seconds` | `number` | Wall-clock seconds elapsed in the current sleep window |
| `next_attempt_at` | `str` | ISO-8601 timestamp at which the next retry will fire |
| `total_waited_seconds` | `number` | Accumulated wall-clock seconds across all 429 waits for this state |
| `budget_seconds` | `number` | Configured `rate_limit_max_wait_seconds` budget |
| `tier` | `str` | Current retry tier: `"short"` or `"long"` |

**Example:**
```json
{"event": "rate_limit_waiting", "ts": "...", "state": "implement", "elapsed_seconds": 60.0, "next_attempt_at": "2026-04-17T12:34:56Z", "total_waited_seconds": 180.0, "budget_seconds": 21600, "tier": "short"}
```

---
```

### 3. `docs/reference/CONFIGURATION.md`

- Lines 69-80: add `commands.rate_limits` to the example block
- Lines 321-327: add to property table
- Line 595: add edge-label color entry if applicable

### 4. `docs/reference/OUTPUT_STYLING.md`

- Lines 60, 204, 216: add `rate_limit_waiting` parallel entries alongside `rate_limit_exhausted` entries

### 5. `docs/reference/API.md`

- Lines 3802-3807: append `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` rows to the `StateConfig` rate-limit field table

### 6. `docs/reference/COMMANDS.md`

- Line 513: add `rate_limit_waiting` alongside `rate_limit_exhausted` in event analysis mention

### 7. `docs/reference/CLI.md`

- Line 1081: `ll-generate-schemas` section reads "all **19** LLEvent types" (two generations stale) → update to "all **22** LLEvent types"

_Research note_: Actual current schema count is **21** (per `scripts/little_loops/generate_schemas.py:78` and `scripts/little_loops/cli/schemas.py:15`). CLI.md is stale. Adding `rate_limit_waiting` (via ENH-1147) brings the count to 22. Confirm the final count at merge by running `ls docs/reference/schemas/*.json | wc -l` after ENH-1147 lands.

### 8. `skills/analyze-loop/SKILL.md`

- Line 108: event payload table lists `rate_limit_exhausted`; add `rate_limit_waiting` row with payload fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`)

### 9. `CHANGELOG.md`

Add entry consistent with prior BUG-1105/1107/1108/1109 style for the full ENH-1131 feature set.

_Research note_: ENH-1131 is a feature addition, so the entry belongs under `### Added`, not `### Fixed` (where BUG-1105/1107/1108/1109 live at `CHANGELOG.md:27-30`). Format to mirror those entries:

```markdown
- **Multi-Hour 429 Resilience with Shared Circuit Breaker** — Two-tier retry ladder (short-burst + long-wait) with wall-clock budget; `rate_limit_waiting` heartbeat events; cross-worktree circuit breaker to pre-sleep peers; new `StateConfig` fields `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder`. (ENH-1131)
```

### 10. `docs/reference/schemas/` (referenced by file listing, generated by ENH-1147)

- File listing at `EVENT-SCHEMA.md:538-562` must include `rate_limit_waiting.json`. The schema file itself is generated by `ll-generate-schemas` after ENH-1144 defines the event dataclass.

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md` — 3 locations
- `docs/reference/EVENT-SCHEMA.md` — 3 locations
- `docs/reference/CONFIGURATION.md` — 3 locations
- `docs/reference/OUTPUT_STYLING.md` — 3 locations
- `docs/reference/API.md` — 1 location
- `docs/reference/COMMANDS.md` — 1 location
- `docs/reference/CLI.md` — 1 location
- `skills/analyze-loop/SKILL.md` — 1 location
- `CHANGELOG.md` — new entry

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1138_doc_wiring.py:44,51,58,65` — string-presence assertions on `docs/reference/API.md` (`circuit: RateLimitCircuit | None = None`, `### little_loops.fsm.rate_limit_circuit`, `RateLimitCircuit,`); `docs/guides/LOOPS_GUIDE.md:76,82` (`circuit_breaker_enabled`); `docs/reference/CONFIGURATION.md:92` (`circuit_breaker_enabled`) — **PRESERVE these exact strings when editing the primary files**
- `scripts/tests/test_circuit_breaker_doc_wiring.py:27,42,48,63,65,67` — string-presence assertions on `docs/reference/API.md` (`rate_limits: RateLimitsConfig`, `circuit_breaker_enabled`, `circuit_breaker_path`) — **PRESERVE these exact strings when editing API.md**

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1146_doc_wiring.py` — **new test file to write**: follow the pattern in `scripts/tests/test_enh1138_doc_wiring.py` (read real files, assert strings present); cover: `rate_limit_waiting` in `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`, `skills/analyze-loop/SKILL.md`; `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` in `API.md`; count `22` in `CLI.md:1081`; `rate_limit_waiting` in `COMMANDS.md`
- `scripts/tests/test_enh1138_doc_wiring.py` — existing; update: run after editing primary files to confirm no regressions
- `scripts/tests/test_circuit_breaker_doc_wiring.py` — existing; run after editing `API.md` to confirm no regressions

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Config sources to consult for defaults** (so doc values stay in sync with code):
- `scripts/little_loops/fsm/executor.py:56` — `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS = 21600`
- `scripts/little_loops/fsm/executor.py:59` — `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER = [300, 900, 1800, 3600]`
- `scripts/little_loops/fsm/schema.py:249-250` — `StateConfig` fields default to `None` (executor substitutes the module constants above)
- `scripts/little_loops/config/automation.py:112` — `RateLimitsConfig` dataclass drives `commands.rate_limits.*` in `.ll/ll-config.json`
- `scripts/little_loops/loops/lib/common.yaml:61-62` — `with_rate_limit_handling` fragment defaults

**Reference patterns already in docs** (to model new content after):
- `docs/reference/EVENT-SCHEMA.md:222-242` — `rate_limit_exhausted` event detail section (full template)
- `docs/reference/EVENT-SCHEMA.md:632-655` — quick-reference table format
- `docs/reference/OUTPUT_STYLING.md:55-61` + `208-217` — two-column and three-column edge color tables
- `docs/reference/API.md:3805-3809` — `StateConfig` field-comment pattern (`field: type | None = None  # inline desc`)
- `docs/reference/CONFIGURATION.md:334-337` — property table for `rate_limits.*` (already contains `max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`). Verify if rows already exist before adding duplicates at 321-327.
- `docs/guides/LOOPS_GUIDE.md:1024-1033` — per-state property table with all 5 rate-limit rows already present per pattern-finder. **Line-drift warning**: issue specifies 1029-1031 but pattern-finder found full 5-row block at 1024-1033. Spot-check the actual file at implementation time before inserting rows — they may already exist.

**Verification commands**:
- `rg -n 'LLEvent types' docs/reference/CLI.md scripts/little_loops/` — check count consistency
- `ls docs/reference/schemas/*.json | wc -l` — current schema count (expect 22 after ENH-1147)
- `ll-verify-docs` — automated event-count check
- `ll-check-links` — catch broken internal links introduced by new sections

## Implementation Steps

1. Update `LOOPS_GUIDE.md` (3 touch points)
2. Update `EVENT-SCHEMA.md` — add event detail, file listing, quick-reference row
3. Update `CONFIGURATION.md` — add rate_limits to example + table
4. Update `OUTPUT_STYLING.md` — parallel entries for rate_limit_waiting
5. Update `API.md` — StateConfig table rows
6. Update `COMMANDS.md` — event analysis mention
7. Update `CLI.md:1081` — count 19→22
8. Update `skills/analyze-loop/SKILL.md:108` — add event row
9. Add `CHANGELOG.md` entry
10. Verify: `ll-verify-docs` (event counts); `ll-check-links`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

11. Write `scripts/tests/test_enh1146_doc_wiring.py` — new doc-wiring test file asserting the new content is present (follow `test_enh1138_doc_wiring.py` pattern)
12. Run `python -m pytest scripts/tests/test_enh1138_doc_wiring.py scripts/tests/test_circuit_breaker_doc_wiring.py` — verify no preservation regressions from edits to `API.md`, `LOOPS_GUIDE.md`, and `CONFIGURATION.md`

## Acceptance Criteria

- All 9 documentation files updated with correct line-range coverage
- `CHANGELOG.md` entry present and consistent with prior entries
- `skills/analyze-loop/SKILL.md` includes `rate_limit_waiting` event row
- `docs/reference/CLI.md` shows correct count (22)
- `ll-verify-docs` passes

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-17T08:56:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdbdbf5d-1514-44d9-a8b7-7ce3308a82dc.jsonl`
- `/ll:wire-issue` - 2026-04-17T08:51:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07b40da8-8090-4f3f-acdd-043663e50f7a.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:43:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2286e7ac-8499-4d0f-8260-0f61fa03bb0c.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a95f7723-f6c7-4abc-9358-01f0d396ef30.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdbdbf5d-1514-44d9-a8b7-7ce3308a82dc.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3a452856-4ad5-4b56-ac67-144c133d5130.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-17
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1150: 429 Resilience — Heartbeat Docs (Reference Files)
- ENH-1151: 429 Resilience — Heartbeat Docs (Guide, Skill, Changelog, Tests)

---

## Status
- [ ] Open
