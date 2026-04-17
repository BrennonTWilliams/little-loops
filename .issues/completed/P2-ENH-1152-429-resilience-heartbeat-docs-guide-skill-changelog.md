---
id: ENH-1152
type: ENH
priority: P2
status: completed
discovered_date: 2026-04-17
completed_date: 2026-04-17
parent: ENH-1151
related: [ENH-1144, ENH-1150, ENH-1153]
size: Medium
confidence_score: 100
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
testable: false
---

# ENH-1152: 429 Resilience — Heartbeat Docs (LOOPS_GUIDE, SKILL.md, CHANGELOG)

## Summary

Update `docs/guides/LOOPS_GUIDE.md` (3 touch points), `skills/analyze-loop/SKILL.md` (event payload table), and `CHANGELOG.md` (new `### Added` entry) for the `rate_limit_waiting` heartbeat event and ENH-1131 config fields.

## Parent Issue

Decomposed from ENH-1151: 429 Resilience — Heartbeat Docs (Guide, Skill, Changelog, Tests).

## Current Behavior

User-facing docs lag the `rate_limit_waiting` heartbeat event and ENH-1131 config fields:

- `docs/guides/LOOPS_GUIDE.md` — prose + YAML example around lines 1670-1691 describe only the short-burst 429 tier, not the two-tier ladder + wall-clock budget; the `with_rate_limit_handling` fragment row at line 2051 doesn't reflect the current injection.
- `skills/analyze-loop/SKILL.md` — event payload table (line 108) lists `rate_limit_exhausted` but not `rate_limit_waiting`; analyze-loop can't guide users on the new heartbeat event.
- `CHANGELOG.md` — `[Unreleased]` has no `### Added` subsection covering multi-hour 429 resilience and the new StateConfig fields.

`docs/reference/EVENT-SCHEMA.md:260-276` and `docs/reference/COMMANDS.md`/`OUTPUT_STYLING.md` already document `rate_limit_waiting` (landed under ENH-1150), so this issue closes the remaining guide/skill/changelog gap.

## Expected Behavior

### 1. `docs/guides/LOOPS_GUIDE.md`

- Lines 1020-1033: per-state property table. Rows for `rate_limit_max_wait_seconds` (line 1032) and `rate_limit_long_wait_ladder` (line 1033) are **already present** as of 2026-04-17 refine-issue verification (re-verified 2026-04-17). Spot-check content/formatting of those rows; update only if stale.
- Lines 1670-1691: extend prose + YAML example with two-tier ladder + budget mechanics (issue originally said 1668-1680; drifted ~2 lines). Line 1670 opens the 429 safeguard paragraph; the YAML example spans 1677-1687; cross-worktree circuit breaker sub-section begins at line 1693.
- Line 2051: update `with_rate_limit_handling` fragment row. Fragment table columns (header at line 2045) are **`Fragment` | `Description` | `Provides` | `Caller must supply`** — the column to update is **`Provides`** (issue previously called this "Supplies" — incorrect column name).

**Line-drift warning**: All line numbers above re-verified at refine time (2026-04-17, no drift). Lines drift with edits — always spot-check before inserting.

**PRESERVE these existing strings** (tested by `test_enh1138_doc_wiring.py` — only these two substrings are asserted against LOOPS_GUIDE.md, verified at `scripts/tests/test_enh1138_doc_wiring.py:75-83`):
- `circuit_breaker_enabled` (LOOPS_GUIDE.md line 76)
- `circuit_breaker_path` (LOOPS_GUIDE.md line 82)

### 2. `skills/analyze-loop/SKILL.md`

- Line 108: event payload table lists `rate_limit_exhausted`; add `rate_limit_waiting` row with payload fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`).
- Table format (2 columns: `Event type` | `Key fields`, header at lines 101-102). Each field is backtick-quoted followed by `(type)` in plain English; multiple fields are comma-separated inline.
- Row to insert (match format of adjacent `rate_limit_exhausted` row at line 108), aligned with `docs/reference/EVENT-SCHEMA.md:260-276` (the authoritative committed reference):

```markdown
| `rate_limit_waiting` | `state` (str), `elapsed_seconds` (number), `next_attempt_at` (str), `total_waited_seconds` (number), `budget_seconds` (number), `tier` (str: `"short"` or `"long"`) |
```

**Payload-spec discrepancies** (authoritative source = `EVENT-SCHEMA.md`; resolve other disagreements there):
- `tier`: ENH-1144 implementation spec currently hardcodes `"long_wait"` in the emit lambda (only emits from the long-wait tier); `EVENT-SCHEMA.md:271` and ENH-1151 research say `"short"` or `"long"`. Match `EVENT-SCHEMA.md` ("short" | "long") in this doc; ENH-1144 will be reconciled at code time.
- `next_attempt_at`: `EVENT-SCHEMA.md:269` documents as `str` (ISO-8601); ENH-1144 lambda passes `time.time() + _wait` (Unix float). Match `EVENT-SCHEMA.md` (`str`/ISO-8601) in SKILL.md; ENH-1144 will need to emit an ISO string to match.

### 3. `CHANGELOG.md`

**Current state (verified 2026-04-17)**: `[Unreleased]` at line 8, with `### Changed` at line 10 and `### Planned` at line 14. No `### Added` subsection. Previous release `## [1.83.0] - 2026-04-16` begins at line 19; prior 429 entries at lines 27-30 are under `### Fixed` (style reference only).

**Insert point**: create new `### Added` subsection between line 8 (`## [Unreleased]`) and line 10 (`### Changed`).

**Established entry format** (from lines 23, 27-30): `- **Title** — description (ISSUE-ID)` — bold title, spaced em-dash, no period before `(...)`, no trailing punctuation.

```markdown
### Added

- **Multi-Hour 429 Resilience with Shared Circuit Breaker** — Two-tier retry ladder (short-burst + long-wait) with wall-clock budget; `rate_limit_waiting` heartbeat events; cross-worktree circuit breaker to pre-sleep peers; new `StateConfig` fields `rate_limit_max_wait_seconds` and `rate_limit_long_wait_ladder` (ENH-1131)
```

(Note: earlier draft in this issue had a period before `(ENH-1131)` — strip it to match existing convention.)

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md` — 3 locations
- `skills/analyze-loop/SKILL.md` — 1 location
- `CHANGELOG.md` — new `### Added` entry

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1138_doc_wiring.py` — existing coverage; asserts `circuit_breaker_enabled` (line 76) and `circuit_breaker_path` (line 82) in LOOPS_GUIDE.md. Both strings live at LOOPS_GUIDE.md:1702-1703, outside all three edit zones — must not break. No update needed.
- `scripts/tests/test_enh1146_doc_wiring.py` — new file, does not yet exist; created by ENH-1153 (sequenced after ENH-1152). Assertion 3 of 7 in that file asserts `"rate_limit_waiting" in skills/analyze-loop/SKILL.md` — this assertion only passes after ENH-1152's SKILL.md edit lands. ENH-1152 must complete before ENH-1153 runs.

### Codebase Research Findings

_Refined 2026-04-17 — codebase verified, no line drift since initial refine._

**Implementation-side constants (for doc accuracy):**
- `scripts/little_loops/fsm/executor.py:56` — `_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS: int = 21600` (6h)
- `scripts/little_loops/fsm/executor.py:59` — `_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER: list[int] = [300, 900, 1800, 3600]` (5/15/30/60 min; index caps at last entry)
- `scripts/little_loops/fsm/executor.py:874-882` — `_emit()` dispatches events via flat-dict callback (not `LLTestBus`, no typed event class)
- `scripts/little_loops/loops/lib/common.yaml:61-62` — `with_rate_limit_handling` fragment defaults

**Authoritative doc references:**
- `docs/reference/EVENT-SCHEMA.md:260-276` — authoritative `rate_limit_waiting` payload spec (6 fields documented). SKILL.md row must align with this.
- `docs/reference/COMMANDS.md`, `docs/reference/OUTPUT_STYLING.md` — already mention `rate_limit_waiting` (completed under ENH-1150).

**Emit-site status (for context only — not in scope for ENH-1152):**
- `rate_limit_waiting` is **not yet emitted** in any Python source — ENH-1144 is still open and will add it. Doc updates here land ahead of the emit wiring (consistent with ENH-1150 precedent).
- ENH-1144 plans to emit only from the long-wait tier at `executor.py:~963`; short tier at `~952` is intentionally callback-free.
- `RATE_LIMIT_WAITING_EVENT` constant is **not** exported from `scripts/little_loops/fsm/__init__.py` (contrast: `RATE_LIMIT_EXHAUSTED_EVENT` is exported at line 90).
- `scripts/little_loops/generate_schemas.py` does not register `rate_limit_waiting` (module docstring line 1 still says "21 LLEvent types"; `docs/reference/schemas/rate_limit_waiting.json` does not exist). Covered by ENH-1147, not here.

**Table format references:**
- `skills/analyze-loop/SKILL.md:101-111` — 2-column event payload table. Line 108: existing `rate_limit_exhausted` row for format reference. Insert new row adjacent.
- `docs/guides/LOOPS_GUIDE.md:1024-1033` — 3-column per-state property table (`Field` | `Type` | `Description`), field names include trailing colon, types in plain English (`integer`, `list of integers`, etc.).
- `docs/guides/LOOPS_GUIDE.md:2045-2051` — 4-column fragments table (`Fragment` | `Description` | `Provides` | `Caller must supply`). `with_rate_limit_handling` is the last row at line 2051.

**Test preservation (scripts/tests/test_enh1138_doc_wiring.py):**
- Only 2 substring assertions against LOOPS_GUIDE.md at lines 75-77 and 80-83: `circuit_breaker_enabled` and `circuit_breaker_path`.
- No assertions against `skills/analyze-loop/SKILL.md` or `CHANGELOG.md` in the repo.
- `scripts/tests/test_file_hints.py:195,199` references LOOPS_GUIDE.md as a test fixture path, not content — edits here do not affect it.

## Implementation Steps

1. Spot-check `docs/guides/LOOPS_GUIDE.md` lines 1020-1033 — confirm `rate_limit_max_wait_seconds` (line 1032) and `rate_limit_long_wait_ladder` (line 1033) rows match current defaults (21600; `[300, 900, 1800, 3600]`). Update only if stale.
2. Update `docs/guides/LOOPS_GUIDE.md` lines 1670-1691 — extend prose + YAML example with two-tier ladder + wall-clock budget mechanics. Do not remove `circuit_breaker_enabled` or `circuit_breaker_path` strings elsewhere in the file.
3. Update `docs/guides/LOOPS_GUIDE.md` line 2051 — `with_rate_limit_handling` fragment row. Column to update is `Provides` (3rd column, header at line 2045). Confirm it reflects the current fragment injection: `max_rate_limit_retries: 3`, `rate_limit_backoff_base_seconds: 30`, plus inherited defaults.
4. Add `rate_limit_waiting` row to `skills/analyze-loop/SKILL.md` event payload table adjacent to line 108 (`rate_limit_exhausted`). Use the exact row format in Expected Behavior §2 above, aligned with `docs/reference/EVENT-SCHEMA.md:260-276`.
5. Insert `### Added` subsection under `## [Unreleased]` in `CHANGELOG.md` (between lines 8 and 10). Entry format matches established `(ISSUE-ID)` convention — no period before the ID.
6. Run `python -m pytest scripts/tests/test_enh1138_doc_wiring.py -v` — must still pass (asserts `circuit_breaker_enabled` and `circuit_breaker_path` substrings in LOOPS_GUIDE.md).

## Scope Boundaries

Explicitly **out of scope** for ENH-1152:

- Emitting `rate_limit_waiting` in `scripts/little_loops/fsm/executor.py` (ENH-1144).
- Reconciling payload-field discrepancies in the emit lambda (tier values, `next_attempt_at` type) — ENH-1144 will be adjusted to match `EVENT-SCHEMA.md`.
- Exporting `RATE_LIMIT_WAITING_EVENT` from `scripts/little_loops/fsm/__init__.py` (ENH-1144).
- Registering `rate_limit_waiting` in `scripts/little_loops/generate_schemas.py` or generating `docs/reference/schemas/rate_limit_waiting.json` (ENH-1147).
- Creating `scripts/tests/test_enh1146_doc_wiring.py` or any new doc-wiring tests (ENH-1153).
- Any edits outside the three target files (`LOOPS_GUIDE.md`, `skills/analyze-loop/SKILL.md`, `CHANGELOG.md`).

## Impact

- **Priority**: P2 — user-facing docs lag shipped/nearly-shipped behavior; not a functional bug but blocks ENH-1153's doc-wiring test (assertion 3 of 7).
- **Effort**: Medium — 3 files, 5 distinct edits, all with verified line numbers and exact row formats. No investigation needed.
- **Risk**: Low — docs-only, no runtime code paths. Only regression vector is removing the two strings asserted by `test_enh1138_doc_wiring.py` (`circuit_breaker_enabled`, `circuit_breaker_path`), both at LOOPS_GUIDE.md:1702-1703 — outside all edit zones.
- **Breaking Change**: No.

## Labels

`enhancement`, `documentation`, `rate-limits`, `429-resilience`, `captured`

## Acceptance Criteria

- `docs/guides/LOOPS_GUIDE.md` updated at all 3 touch points
- `skills/analyze-loop/SKILL.md` includes `rate_limit_waiting` event row
- `CHANGELOG.md` entry present under `### Added`
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py` passes

## Session Log
- `/ll:ready-issue` - 2026-04-17T09:39:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bcc8b6a0-49de-4289-b808-995617cb7c5e.jsonl`
- `/ll:confidence-check` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/09a5962f-7509-4701-9f36-3c3386a6db3b.jsonl`
- `/ll:wire-issue` - 2026-04-17T09:35:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/529266d7-1fa4-49c1-8940-1a6b07e6d9de.jsonl`
- `/ll:refine-issue` - 2026-04-17T09:28:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1adc9784-cf29-4652-8a48-f355207157a2.jsonl`
- `/ll:issue-size-review` - 2026-04-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ee709210-6491-4684-b5fd-fd33f555658f.jsonl`
- `/ll:manage-issue` - 2026-04-17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb81c897-3ff8-451f-a2de-0780c83a4339.jsonl`

---

## Status
- [x] Completed

## Resolution

**Completed**: 2026-04-17

### Changes
- `skills/analyze-loop/SKILL.md` — added `rate_limit_waiting` row to the event payload table with 6 documented fields (`state`, `elapsed_seconds`, `next_attempt_at`, `total_waited_seconds`, `budget_seconds`, `tier`), aligned with `docs/reference/EVENT-SCHEMA.md:260-276`.
- `CHANGELOG.md` — added `### Added` subsection under `[Unreleased]` with **Multi-Hour 429 Resilience with Shared Circuit Breaker** entry (ENH-1131) matching established `(ISSUE-ID)` convention.
- `docs/guides/LOOPS_GUIDE.md` — all 3 touch points already up-to-date at implementation time (per-state property table rows 1032-1033 match current defaults; lines 1670-1691 prose + YAML already cover two-tier ladder + wall-clock budget; fragment row at 2051 already reflects current injection). Spot-checked; no edits required.

### Verification
- `python -m pytest scripts/tests/test_enh1138_doc_wiring.py -v` — all 10 tests passed; `circuit_breaker_enabled` and `circuit_breaker_path` substrings preserved in LOOPS_GUIDE.md.
