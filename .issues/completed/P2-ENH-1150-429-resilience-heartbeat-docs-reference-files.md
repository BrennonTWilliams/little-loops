---
id: ENH-1150
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
parent: ENH-1146
related: [ENH-1144, ENH-1147, ENH-1151]
confidence_score: 93
outcome_confidence: 83
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 25
testable: false
---

# ENH-1150: 429 Resilience — Heartbeat Docs (Reference Files)

## Summary

Update all `docs/reference/` files for the `rate_limit_waiting` heartbeat event and related `rate_limit_max_wait_seconds` / `rate_limit_long_wait_ladder` config fields.

## Current Behavior

`docs/reference/` files do not describe the `rate_limit_waiting` heartbeat event introduced by ENH-1144:
- `EVENT-SCHEMA.md` lists `rate_limit_exhausted` and `rate_limit_storm` in the event detail section (lines 224-256), schemas directory tree (lines 540-563), and quick-reference table (lines 632-654), but no `rate_limit_waiting` entry.
- `OUTPUT_STYLING.md` has parallel `rate_limit_exhausted` entries in color tables (lines 54-61, 208-217) and edge description (line 204) with no `rate_limit_waiting` sibling.
- `COMMANDS.md:513` mentions `rate_limit_exhausted` event analysis without the new heartbeat.
- `CLI.md:1081` reads "all 19 `LLEvent` types" — stale (actual count is currently 21; target is 22 after ENH-1147 adds the `rate_limit_waiting.json` schema).
- `API.md` and `CONFIGURATION.md` already contain the relevant rate-limit rows per refine-issue verification, but need final spot-check against ENH-1144's merged payload.

## Parent Issue

Decomposed from ENH-1146: 429 Resilience — Heartbeat Documentation (parent is in `.issues/completed/`).

## Can run in parallel with ENH-1151.

## Upstream Dependency

`rate_limit_waiting` is emitted by ENH-1144 (core code). Docs here describe the forward-looking design spec — verify payload field names/types match ENH-1144's implementation at merge time.

## Expected Behavior

### 1. `docs/reference/EVENT-SCHEMA.md`

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

### 2. `docs/reference/CONFIGURATION.md`

- Lines 69-80: add `commands.rate_limits` to the example block
- Lines 321-327: add to property table (verify rows don't already exist per codebase research note below)
- Line 595: add edge-label color entry if applicable

**Note**: `docs/reference/CONFIGURATION.md:334-337` already contains `rate_limits.*` rows (`max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`). Spot-check before inserting to avoid duplicates.

### 3. `docs/reference/OUTPUT_STYLING.md`

- Lines 60, 204, 216: add `rate_limit_waiting` parallel entries alongside `rate_limit_exhausted` entries
- Reference pattern: `docs/reference/OUTPUT_STYLING.md:55-61` + `208-217` — two-column and three-column edge color tables

### 4. `docs/reference/API.md`

- Lines 3802-3807: append `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` rows to the `StateConfig` rate-limit field table
- Reference pattern: `docs/reference/API.md:3805-3809` — `StateConfig` field-comment pattern

**PRESERVE these existing strings** (tested by existing doc-wiring tests):
- `rate_limits: RateLimitsConfig`
- `circuit_breaker_enabled`
- `circuit_breaker_path`
- `circuit: RateLimitCircuit | None = None`
- `### little_loops.fsm.rate_limit_circuit`
- `RateLimitCircuit,`

### 5. `docs/reference/COMMANDS.md`

- Line 513: add `rate_limit_waiting` alongside `rate_limit_exhausted` in event analysis mention

### 6. `docs/reference/CLI.md`

- Line 1081: `ll-generate-schemas` section reads "all **N** LLEvent types" (stale) → update to "all **22** LLEvent types"
- Verify actual count with: `ls docs/reference/schemas/*.json | wc -l` after ENH-1147 lands

## Integration Map

### Files to Modify

- `docs/reference/EVENT-SCHEMA.md` — 3 locations
- `docs/reference/CONFIGURATION.md` — 3 locations (verify no duplicates first)
- `docs/reference/OUTPUT_STYLING.md` — 3 locations
- `docs/reference/API.md` — 1 location
- `docs/reference/COMMANDS.md` — 1 location
- `docs/reference/CLI.md` — 1 location

### Tests (run after edits)

- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py scripts/tests/test_circuit_breaker_doc_wiring.py` — verify no preservation regressions from edits to `API.md`
- ENH-1151 writes `scripts/tests/test_enh1146_doc_wiring.py` which covers these files; run after ENH-1151 completes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — asserts `"ll-create-extension"` present in `CLI.md` and `"installs/shows/validates"` absent from `COMMANDS.md`; run to catch regressions after editing either file [Agent 3 finding]

### Codebase Research Findings (from parent ENH-1146)

- `scripts/little_loops/fsm/executor.py:56` — `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS = 21600`
- `scripts/little_loops/fsm/executor.py:59` — `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER = [300, 900, 1800, 3600]`
- `scripts/little_loops/fsm/schema.py:249-250` — `StateConfig` fields default to `None`
- `scripts/little_loops/config/automation.py:112` — `RateLimitsConfig` dataclass
- Tier values: `"short"` | `"long"` (from executor.py docstrings at lines 891-893, 942-944, 956)

### Codebase Research Findings

_Added by `/ll:refine-issue` on 2026-04-17 — line-number verification and corrections:_

**EVENT-SCHEMA.md** (verified 2026-04-17):
- Line 224: `### rate_limit_exhausted` heading. Block runs 224-241. Payload fields at 228-235, example JSON at line 239.
- Line 244: `### rate_limit_storm` heading. Block runs 244-256. Insert new `rate_limit_waiting` section after `rate_limit_storm` (after line 258's `---` separator), or alphabetically between exhausted (224) and storm (244).
- Schemas directory tree: lines 540-563 (not 538-559 as the issue claims); `rate_limit_exhausted.json` at line 556, `rate_limit_storm.json` at line 557. Insert `rate_limit_waiting.json` entry here (after ENH-1147 writes the schema file).
- Quick-reference table: lines 632-654 (not 629-651). `rate_limit_exhausted` at line 642, `rate_limit_storm` at line 643.
- `rate_limit_exhausted` payload fields (for reference): `state`, `retries`, `short_retries`, `long_retries`, `total_wait_seconds`, `next`.

**CONFIGURATION.md** (verified 2026-04-17):
- Example block: `rate_limits` object already present at lines 80-84 with `max_wait_seconds`, `long_wait_ladder`, `circuit_breaker_enabled`, `circuit_breaker_path`. **No changes needed here** (issue's line 69-80 note was imprecise).
- Property table: all four `rate_limits.*` rows already present at lines 334-337. **No changes needed** unless adding new config fields (this issue does not).
- Line 595 is inside `cli.colors.fsm_edge_labels` section — only relevant if OUTPUT_STYLING changes add a new edge color. Likely a no-op.
- **Net**: CONFIGURATION.md may require **zero edits** for this issue. Confirm during implementation.

**OUTPUT_STYLING.md** (verified 2026-04-17):
- Line 60: `rate_limit_exhausted` with ANSI `38;5;214` (Amber) in color table (lines 54-61).
- Line 204: `on_rate_limit_exhausted` in `_collect_edges()` description.
- Line 216: `rate_limit_exhausted` → Amber in second color table (lines 208-217).

**API.md** (verified 2026-04-17):
- `StateConfig` rate-limit fields are already at **lines 3805-3809**, not "3802-3807 (append rows)". All five rows present: `max_rate_limit_retries`, `on_rate_limit_exhausted`, `rate_limit_backoff_base_seconds`, `rate_limit_max_wait_seconds`, `rate_limit_long_wait_ladder`. **No new rows needed** — the `rate_limit_max_wait_seconds` / `rate_limit_long_wait_ladder` rows the issue says to "append" already exist. Verify inline comments are accurate; no structural change required.
- Field format (fenced code block): `    name: type | None = None  # inline comment`.

**COMMANDS.md** (verified 2026-04-17):
- Line 513: contains `rate_limit_exhausted` event-analysis mention. Add `rate_limit_waiting` parallel reference here.

**CLI.md** (verified 2026-04-17):
- Line 1081 currently reads: `Generate JSON Schema (draft-07) files for all 19 `LLEvent` types...`
- Actual schema count in `docs/reference/schemas/*.json`: **21 files** (count is already stale by 2 — missing recent events).
- After ENH-1147 adds `rate_limit_waiting.json`: target count = **22**.
- Phrasing pattern: `for all <N> \`LLEvent\` types`.

**Upstream state (verified 2026-04-17)**:
- `scripts/tests/test_enh1146_doc_wiring.py` does NOT yet exist — written by sibling ENH-1151.
- `docs/reference/schemas/rate_limit_waiting.json` does NOT yet exist — written by sibling ENH-1147.
- Existing doc-wiring tests present: `test_enh1138_doc_wiring.py`, `test_circuit_breaker_doc_wiring.py` (both use simple `path.read_text()` + `assert "literal" in content` pattern grouped in `class Test<File>Wiring`).

**Scope correction**: Based on the verification above, the likely actual edits are narrower than the issue's 6-file list:
- **Required**: EVENT-SCHEMA.md (3 insertions), COMMANDS.md (1 line), CLI.md (count bump), OUTPUT_STYLING.md (3 parallel entries).
- **Likely no-op**: CONFIGURATION.md (existing rows), API.md (existing rows) — reconfirm at merge time against ENH-1144's actual payload field names.

## Implementation Steps

1. Update `docs/reference/EVENT-SCHEMA.md` — add event detail, file listing, quick-reference row
2. Update `docs/reference/CONFIGURATION.md` — add rate_limits to example + table (check for duplicates first)
3. Update `docs/reference/OUTPUT_STYLING.md` — parallel entries for rate_limit_waiting
4. Update `docs/reference/API.md` — StateConfig table rows
5. Update `docs/reference/COMMANDS.md` — event analysis mention
6. Update `docs/reference/CLI.md` — count update
7. Run: `python -m pytest scripts/tests/test_enh1138_doc_wiring.py scripts/tests/test_circuit_breaker_doc_wiring.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Run `python -m pytest scripts/tests/test_create_extension_wiring.py` after editing `CLI.md` and `COMMANDS.md` — guards against accidentally removing `"ll-create-extension"` from `CLI.md` or re-introducing `"installs/shows/validates"` in `COMMANDS.md`
9. Use these exact string literals when writing ENH-1150 content — ENH-1151's `test_enh1146_doc_wiring.py` will assert them [Agent 2 finding]:
   - `"rate_limit_waiting"` must appear in `EVENT-SCHEMA.md`, `OUTPUT_STYLING.md`, and `COMMANDS.md`
   - `"22"` must appear in `CLI.md` (the LLEvent count phrase after ENH-1147 lands)
   - `"rate_limit_max_wait_seconds"` and `"rate_limit_long_wait_ladder"` must appear in `API.md` (already present per codebase research; verify they survive any edits)

## Acceptance Criteria

- All 6 `docs/reference/` files updated with correct content
- `docs/reference/CLI.md` shows correct LLEvent type count (22)
- No regressions in `test_enh1138_doc_wiring.py` or `test_circuit_breaker_doc_wiring.py`

## Proposed Solution

Follow the refine-issue verification (section "Codebase Research Findings" above) as the primary source of truth for line numbers and scoped edits. Mirror the `rate_limit_exhausted` section in `EVENT-SCHEMA.md:224-241` when adding the new `rate_limit_waiting` detail block, the file-listing row, and the quick-reference row. For `OUTPUT_STYLING.md`, add parallel entries alongside each existing `rate_limit_exhausted` line. `COMMANDS.md:513` and `CLI.md:1081` are single-line edits. Re-verify `API.md:3805-3809` and `CONFIGURATION.md:80-84, 334-337` against ENH-1144's merged payload before declaring those files no-ops. Preserve the test-asserted strings listed in the "Wiring Phase" section.

## Scope Boundaries

Out of scope:
- Guide, skill, and changelog docs (ENH-1151)
- Test file additions / doc-wiring tests (ENH-1148, ENH-1149, ENH-1151)
- Core executor / event emission code (ENH-1144)
- New schema JSON file for `rate_limit_waiting` (ENH-1147)
- Any `docs/reference/` changes unrelated to the heartbeat event or its two config fields

## Impact

- **Priority**: P2 — doc reference completeness for a merged feature; does not block functionality but affects operator observability docs.
- **Effort**: Small — single-pass edits across 4-6 files, mostly parallel insertions mirroring existing `rate_limit_exhausted` patterns.
- **Risk**: Low — documentation-only changes; wiring tests in ENH-1138 and circuit-breaker suites guard preserved-string regressions.
- **Breaking Change**: No.

## Labels

`documentation`, `rate-limits`, `observability`, `enh`, `captured`

## Session Log
- `/ll:manage-issue` - 2026-04-17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53dc8b4f-7e4a-42e8-85be-ba83c469faf5.jsonl`
- `/ll:ready-issue` - 2026-04-17T09:07:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/89dc1663-7a45-4bd7-ba02-baa5a06f7344.jsonl`
- `/ll:wire-issue` - 2026-04-17T09:03:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0af5b5de-c80f-4fc3-9d7b-cedf43719307.jsonl`
- `/ll:refine-issue` - 2026-04-17T08:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f6cd2c8-d35f-4d0e-872a-45b1e75854b5.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cdbdbf5d-1514-44d9-a8b7-7ce3308a82dc.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ffc3179-29ef-4f5d-ac8b-5c4c7d151d9e.jsonl`

---

## Status
- [x] Completed 2026-04-17

## Resolution

Updated `docs/reference/` files to document the `rate_limit_waiting` heartbeat event introduced by ENH-1144:

- **EVENT-SCHEMA.md**: Added `### rate_limit_waiting` detail section (after `rate_limit_storm`) with payload fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`), example JSON, schemas-directory tree entry (`rate_limit_waiting.json`), and quick-reference table row.
- **OUTPUT_STYLING.md**: Added `rate_limit_waiting` rows (Amber, `38;5;214`) to both edge-color tables and a clarifying note that it is a heartbeat event sharing styling with `rate_limit_exhausted` (not a diagram edge label).
- **COMMANDS.md**: Appended `rate_limit_waiting` heartbeat context to the `rate_limit_exhausted` analyze-loop signal-detection bullet.
- **CLI.md**: Bumped `ll-generate-schemas` LLEvent-type count from 19 to 22 (target after ENH-1147 adds the schema file).
- **CONFIGURATION.md**: No changes required — `rate_limits.*` rows already present (verified in refine pass).
- **API.md**: No changes required — `rate_limit_max_wait_seconds` / `rate_limit_long_wait_ladder` rows already present (verified in refine pass).

Verification: `test_enh1138_doc_wiring.py`, `test_circuit_breaker_doc_wiring.py`, and `test_create_extension_wiring.py` — 38 passed.
