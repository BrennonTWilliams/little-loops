---
id: FEAT-3301
title: Advisor consult telemetry - ll-ctx-stats reporting
type: FEAT
parent: EPIC-3041
priority: P4
status: deferred
testable: true
discovered_date: 2026-08-23
verify_verdict: PROPOSAL_UNSOUND
depends_on:
- FEAT-3300
labels:
- planning-hub
reconcile_attempted: true
size: Large
deferred_by: automation
deferred_date: '2026-08-23T18:30:09Z'
deferred_reason: low_readiness
relates_to:
- FEAT-3040
---

# FEAT-3301: Advisor consult telemetry - ll-ctx-stats reporting

> **Recovery note (2026-08-23):** originally drafted as FEAT-3117/FEAT-3118 in the epic-3041 sub-loop worktree (abandoned ref b972a9c7c), whose stale .issues tree allocated IDs colliding with the existing wire-trigger issues FEAT-3117/FEAT-3118 on main. Renumbered to FEAT-3300/FEAT-3301 on recovery.


## Summary

Reporting half of FEAT-3040 (Slice 4 of the host-agnostic advisor,
FEAT-3037): surface `consult_stats`/`query_advisor_consults` (landed by
FEAT-3300) in `ll-ctx-stats`, so an operator can see consult counts by signal
and their aggregate token cost without querying `history.db` directly.

## Parent Issue

Decomposed from FEAT-3040: Advisor consult telemetry in history.db.

## Current Behavior

- FEAT-3300 lands `advisor_consults`, `write_advisor_consult`,
  `query_advisor_consults`, and `consult_stats`, but nothing calls them from
  `ll-ctx-stats` — the data is queryable but not surfaced.
- `scripts/little_loops/cli/ctx_stats.py` (`main_ctx_stats`, line 726) is the
  concrete `ll-ctx-stats` implementation. Not every telemetry table has a
  report section: `harness_events`, `verdict_events`, and `review_events`
  currently have none, so adding one here is this issue's own work, not
  automatic.

## Expected Behavior

- `ll-ctx-stats` reports consult counts by signal and their aggregate token
  cost, both in the human-readable report and the `--json` payload.

## Use Case

After a month of running `autodev` with `confidence_gate` consults enabled,
an operator asks whether they are paying off. `ll-ctx-stats` shows 47
consults, 31 from `confidence_gate`, at a measurable token cost — and that
runs with a consult reached `done` at a materially different rate than runs
that blocked without one. That is the evidence that decides whether to keep
the trigger on.

## Proposed Solution

Follow the existing `_aggregate_<x>(db_path) -> dict|list|None` pattern
(e.g. `_aggregate_waste` delegating to `history_reader.waste_attribution`):

1. `_aggregate_consults(db_path)` in `cli/ctx_stats.py`, delegating to
   `history_reader.consult_stats`.
2. Unconditional call in `main_ctx_stats` (`:726-790`).
3. Both `_print_json` payload dict literals (`sqlite` and `fallback`
   branches, `:555-619`) gain a `consult_stats` key, always present (even
   empty) — matching `_aggregate_waste`'s JSON-key-always-present contract.
4. `_render`'s trailing optional param and a new truthy-gated block
   (`:417-426` pattern) for the human-readable section.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- The `_aggregate_waste` analog does NOT add its key to both `_print_json`
  branches as step 3 states. Currently, in `scripts/little_loops/cli/ctx_stats.py`,
  the `waste` key is inserted only in the sqlite/summary branch's dict literal
  (`:588-607`, key at `:605`), always present there (even `None`/`[]`). The
  fallback branch's dict literal (`:608-616`) has no `waste` key at all — not
  even `null` — and the `else` "none" branch (`:617-618`) has none either.
  A `consult_stats` key that must be "always present even when zero consults"
  per Acceptance Criteria 2 should confirm which of `_print_json`'s branches
  that guarantee is meant to cover before wiring it in.
- Confirmed net-new: no trace of `advisor_consults`/`consult_stats`/
  `query_advisor_consults`/`write_advisor_consult` exists in any `.py` file
  today (grep across the worktree matches only issue markdown) — FEAT-3300
  is genuinely unlanded, so this issue's `_aggregate_consults` has no
  existing reader symbol to call yet.

## Program Design

### Types

- `consult_stats`/`query_advisor_consults` do not exist in application code yet
  — grep for `advisor_consults|consult_stats|query_advisor_consults|
  write_advisor_consult` across the worktree returns matches only in issue
  markdown (FEAT-3040, FEAT-3116, FEAT-3300, this file), none in
  `history_db.py`/`history_reader.py`/any `.py` file. FEAT-3300 is genuinely
  unlanded; this issue has no existing symbol to extend and must build the
  shape net-new. The nearest existing precedent for that shape is
  `waste_attribution(*, since: str | None = None, db: Path | str =
  DEFAULT_DB_PATH) -> list[dict]` (`scripts/little_loops/history_reader.py:1008-1062`).

### Signatures

- `_aggregate_waste(db_path: Path) -> list[dict[str, Any]] | None`
  (`scripts/little_loops/cli/ctx_stats.py:183-194`) — direct template for
  `_aggregate_consults`: returns `None` when `db_path` doesn't exist, else
  delegates to the reader function via a function-local import (not a
  module-top-level import).
- `_render(summary, logger, skill_stats=None, cache_rate=None, lt_stats=None,
  mcp_health=None, waste=None, pressure=None) -> None`
  (`scripts/little_loops/cli/ctx_stats.py:417-426`) — `waste` is the
  second-to-last param, before the trailing `pressure` param; a new
  `consults` param follows this same trailing-optional-param convention.
- `_print_json(summary, state, skill_stats=None, cache_rate=None,
  lt_stats=None, usage_events=None, mcp_health=None, waste=None,
  pressure=None) -> None` (`scripts/little_loops/cli/ctx_stats.py:555-565`).

### Call Path

`ll-ctx-stats` -> `_aggregate_consults` -> `history_reader.consult_stats` ->
`query_advisor_consults` (FEAT-3300)

`main_ctx_stats` calls `_aggregate_waste` unconditionally at
`ctx_stats.py:750`, inside the single unconditional `_aggregate_*` call
block (`:742`-`:751`) a new `_aggregate_consults` call would join.

### Decision Rules

N/A — no new decision logic.

## Acceptance Criteria

1. `ll-ctx-stats` reports consult counts by signal and aggregate token cost
   in the human-readable report.
2. `ll-ctx-stats --json` includes a `consult_stats` (or equivalent) key,
   always present even when there are zero consults.
3. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` pass.
4. `docs/reference/CLI.md` and `docs/reference/API.md` are updated to
   document the new `consult_stats` key/section, per the Integration Map's
   Documentation subsection.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_consults`, wired
  into `main_ctx_stats`, `_print_json` (all three dict-literal branches —
  sqlite `:588-607`, fallback `:608-616`, and the `else`/"none" branch
  `:617-618` — since AC2 requires `consult_stats` always present even at
  zero consults, a stronger guarantee than `waste`'s, which appears only in
  the sqlite branch), `_render`.

### Dependent Files (Callers/Importers)

- `history_reader.consult_stats` / `query_advisor_consults` — landed by
  FEAT-3300; this issue is blocked on that landing first.

### Similar Patterns

- `_aggregate_waste` -> `history_reader.waste_attribution` ->
  `TestAggregateWaste` (`:535`) / `TestMainCtxStatsWasteSection` (`:570`) —
  the direct template for this issue's aggregate function, CLI wiring, and
  tests.

### Tests

- `scripts/tests/test_cli_ctx_stats.py` — new `TestAggregateConsults` +
  `TestMainCtxStatsConsultsSection` classes following `TestAggregateWaste`
  (`:535`) / `TestMainCtxStatsWasteSection` (`:570`): unconditional
  aggregate call, JSON key always present (even empty), human-readable
  section only under a truthy guard.

### Documentation

- `docs/reference/CLI.md:299` — the `ll-ctx-stats --json` payload paragraph
  listing every key (`skill_health`, `learning_tests`, `waste`,
  `context_pressure`, ...) gains `consult_stats`; a new prose block follows
  the "When `<table>` has rows... the report also includes a **<Name>**
  section" template (line 301's pattern) for the human-readable section.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (`main_ctx_stats` entry, `:4574-4580`) — a second,
  independently-maintained copy of the `--json` payload key list (currently
  enumerates `skill_health` and `waste`, citing `_aggregate_waste()` ->
  `history_reader.waste_attribution()`); needs the same `consult_stats`
  mention added to `docs/reference/CLI.md`, following the ENH-2722 precedent
  of touching both files together. [Agent 2 finding]

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-23:_

All cited line numbers and signatures were re-confirmed against current code
and are accurate: `main_ctx_stats` (`:726`), `_aggregate_waste` (`:183-194`),
`_render` (`:417-426`), `_print_json` (`:555-565`), the unconditional
aggregate-call block (`:742-751`, `_aggregate_waste` call at `:750`), and the
`waste`-key placement in `_print_json` (sqlite branch key at `:605`, absent
from the fallback branch `:608-616` and the `else` branch `:617-618`). The
"net-new, no existing symbol" claim also re-confirmed: no
`advisor_consults`/`consult_stats`/`query_advisor_consults`/
`write_advisor_consult` match in any `.py` file.

Two defects, not yet reconciled:

1. **Proposed Solution step 3 contradicts its own Codebase Research
   Findings.** Step 3 states both `_print_json` branches (sqlite and
   fallback) gain `consult_stats`, "always present (even empty) — matching
   `_aggregate_waste`'s JSON-key-always-present contract." Re-reading the
   code confirms the Codebase Research Findings note directly below it: that
   contract doesn't exist — `waste` appears only in the sqlite branch
   (`:605`); the fallback branch (`:608-616`) and the `else`/"none" branch
   (`:617-618`) have no `waste` key at all, not even `null`. Step 3's literal
   text was never corrected after the research note flagged it, so an
   implementer following the Proposed Solution as written would either (a)
   copy the actual `_aggregate_waste` pattern and leave `consult_stats` out
   of the fallback/none payloads, silently failing AC2 ("always present even
   when zero consults"), or (b) add it to all three branches, which is a
   stronger guarantee than any existing `_print_json` key has and isn't
   flagged anywhere as a deliberate scope increase.
2. **AC coverage gap.** The Integration Map's Documentation section (added by
   `/ll:wire-issue`) lists both `docs/reference/CLI.md` and
   `docs/reference/API.md` as files needing a `consult_stats` mention, but no
   Acceptance Criterion requires the doc updates — AC1-3 cover only the
   human-readable report, the JSON key, and the test/lint/type gates.

Recommend resolving before implementation: rewrite step 3 to state
explicitly that `consult_stats` must appear in all three `_print_json`
branches (sqlite, fallback, none) to satisfy AC2 — a broader guarantee than
`waste` — and add an AC (or fold into AC1) covering the CLI.md/API.md doc
updates.

## Impact

- **Priority**: P4 — pure observability, thin reporting layer over
  FEAT-3300's already-tested data.
- **Effort**: Small — one aggregate function plus three call sites, all
  following an established template (`_aggregate_waste`).
- **Risk**: Low — read-only, additive CLI section.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/reference/CLI.md`

## Status

**Open** | Created: 2026-08-23 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-08-23T18:28:34 - `d93fba25-f368-4e95-bd5e-68eee2858e99.jsonl`
- `/ll:reconcile-issue` - 2026-08-23T18:27:37 - `59674322-b29b-42c4-92fc-307bc76bbbd8.jsonl`
- `/ll:verify-issues` - 2026-08-23T18:26:12 - `0a33e0c0-e24b-496c-b956-bdd4e40b7018.jsonl`
- `/ll:refine-issue` - 2026-08-23T18:24:47 - `5c094b02-43f9-441d-94d3-1470ead8e70f.jsonl`
- `/ll:verify-issues` - 2026-08-23T18:23:30 - `1e97da10-6a35-4ecd-83b2-699402b15360.jsonl`
- `/ll:wire-issue` - 2026-08-23T18:21:14 - `8c914054-260d-4263-bbab-36397302872d.jsonl`
- `/ll:refine-issue` - 2026-08-23T18:17:23 - `77d4b578-53af-4996-b98b-73fe53d26cfd.jsonl`
- `/ll:issue-size-review` - 2026-08-23T17:46:16 - `797c9631-7573-4a96-864e-cad371610ef8.jsonl`
