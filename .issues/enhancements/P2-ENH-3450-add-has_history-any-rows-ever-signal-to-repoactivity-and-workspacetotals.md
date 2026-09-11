---
id: ENH-3450
type: ENH
title: Add has_history any-rows-ever signal to RepoActivity and WorkspaceTotals
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-11'
captured_at: '2026-09-11T20:26:38Z'
decision_needed: false
learning_tests_required:
- sqlite3
confidence_score: 90
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# ENH-3450: Add has_history any-rows-ever signal to RepoActivity and WorkspaceTotals

## Summary

`RepoActivity.instrumented` (in `scripts/little_loops/issue_history/workspace_activity.py`) means "a history.db file exists", not "any activity was ever recorded". A schema'd-but-empty db and a db with rows outside the `--since/--until` window both report `instrumented: true` with zero counts, so a consumer cannot tell "empty db" from "quiet window". Add a separate `has_history` signal; do not redefine `instrumented`.

## Current Behavior

`RepoActivity.instrumented` is true whenever the history.db file exists (`aggregate_workspace_activity()`: non-ok branches set `instrumented = status is not MemberActivityStatus.DB_MISSING`; the count-failure and ok branches hardcode `True`). A schema'd-but-empty db and a db whose rows all fall outside the `--since/--until` window are indistinguishable: both report `instrumented: true` with zero counts. There is no field that answers "were any rows ever recorded".

## Expected Behavior

A separate `has_history` signal on `RepoActivity` distinguishes the two cases: `false` for empty-but-schema'd dbs, `true` when rows exist outside the window, `null` when the db cannot be read (schema_skew/unreadable), `false` for db_missing. `instrumented` keeps its current file-exists meaning and its load-bearing role in the workspace quality reader. `WorkspaceTotals` gains `has_history_members` (count) and `has_history` (any), mirroring the existing `instrumented`/`instrumented_members` pair.

## Motivation

**Verified in code** (`aggregate_workspace_activity()`):

- Non-ok branches: `instrumented=status is not MemberActivityStatus.DB_MISSING` (line 277).
- Count-failure branch: `instrumented=True` (line 291).
- Ok branch: `instrumented=True` (line 304).

So `instrumented` is true whenever the file exists. A downstream consumer (little-loops-hermes) must distinguish "empty db" (tables exist, zero rows ever) from "quiet window" (rows exist, none in window). It reports "measured zero activity" only for the latter; treating the former as measured-zero is exactly the "no answer ≠ zero" conflation its own code exists to prevent.

`instrumented` is load-bearing in the workspace quality reader and its tests, so it must keep its current meaning.

## Proposed Solution

Resolved — see "Decisions (resolved, do not re-derive)" for the field/value semantics and "Implementation Steps" for the landing order. In short: a new `_has_any_history(conn)` helper (EXISTS over `issue_events` OR `loop_runs`, no scan) feeds a new `RepoActivity.has_history: bool | None` in the ok path; `db_missing` → `False`, `schema_skew`/`unreadable` → `None`; `_totals()` mirrors with `has_history_members`/`has_history`; `to_dict()` on both dataclasses plus the text/markdown formatters expose it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

Formatter rendering decision (research finding: per-member `instrumented` is NOT rendered in text/markdown today — only `status`, the four count lines via `_activity_count_lines()` :316-328, or `error`; the sole `instrumented` rendering is the totals line `members: N (ok: X, instrumented: Y)` at :391-394 (text) and :435-438 (markdown). "Show has_history alongside instrumented counts" therefore describes a new rendering, not an extension of an existing per-member display):

**Option A**: Extend the totals line only — render `has_history`/`has_history_members` in the existing `members: N (ok: X, instrumented: Y)` line; per-member output unchanged.

> **Selected:** Option A — extends the only render site of its structural twin `instrumented`; two inline f-string edits, no new rendering shape, zero pinned formatter output.

**Option B**: Add a per-member `has_history` line alongside the count lines in `_activity_count_lines()`, plus the totals-line extension.

**Recommended**: Option A — it extends the only site where `instrumented` renders today, and Option B's per-member `None` values (schema_skew/unreadable) would render as noise.

Known behavior to cover in tests (not a defect): the default no-flag CLI invocation takes the single-repo fallback (cli/history.py:689-699), whose db is pre-created by `cli_event_context` with only a `cli_events` row (writers.py:536-539, table at schema.py:251) — so the fallback member reports `ok` with zero counts and `has_history: false`. This is the canonical empty-but-schema'd case motivating the issue; the CLI golden test should pin it.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-11.

**Selected**: Option A

**Reasoning**: `has_history`/`has_history_members` explicitly mirrors the `instrumented`/`instrumented_members` pair (Decision 3), and that pair renders exclusively in the totals line (`workspace_activity.py:392` text, `:436` markdown — the only `instrumented` render sites repo-wide). Option A is a two-site inline f-string extension with zero pinned text/markdown formatter tests to break; Option B would introduce the first per-member boolean `key: value` line in any formatter in the codebase, require new parameterization of `_activity_count_lines()` to avoid double-rendering in totals (the shared helper serves both the per-member and totals sections: :377/:397 text, :422/:440 markdown), and its per-member output could only ever show the OK-branch True/False subset of the JSON signal (`db_missing → False` never displays — db_missing members render via the error branch).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- Winner (totals-line extension): extends the exact two inline sites where `instrumented` renders today (`workspace_activity.py:391-394`, `:435-438`); no test anywhere pins activity text/markdown output (only loose substring asserts at `test_cli_history.py:663-690`); JSON/YAML untouched by construction (`to_dict()` passthrough at `:340-360`). Reuse score 3.
- Runner-up (per-member variant): `_activity_count_lines()` takes exactly four `int | None` args and is called from both per-member and totals sections — a `has_history` line added there double-renders in totals without new suppression parameterization (no precedent in this helper); no formatter in the codebase renders a per-item boolean as its own line (all None-field precedents — `rework.py:456-460`, `formatting.py:146` — are numeric/date). Reuse score 2. Counterpoint found: None-noise is structurally mitigated (the helper only runs in the OK branch), but per-member rendering still shows a strict subset of the JSON signal.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/workspace_activity.py` — new `_has_any_history()` helper; `RepoActivity`, `WorkspaceTotals`, `_totals()`, `aggregate_workspace_activity()`, `to_dict()` ×2, `format_workspace_activity_text()` / `format_workspace_activity_markdown()`, module docstring.

### Dependent Files (Callers/Importers)
- `ll-history activity` CLI path (consumes `WorkspaceActivityResult.to_dict()` and the formatters) — additive keys only, no code change needed beyond formatters.
- little-loops-hermes (external consumer) — reads the JSON shape; gains the new keys.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/workspace_quality.py` — docstring-only cross-reference: `_gate_member()` docs name `workspace_activity.aggregate_workspace_activity()` (:129) and `workspace_activity.MemberActivityStatus` (:137); no field-level coupling, so no edit needed for the additive fields. Confirmed sole out-of-module source file naming the changed module. [Agent 1 finding, grep-confirmed]

### Similar Patterns
- `WorkspaceTotals.instrumented` / `instrumented_members` pair in the same module — `has_history`/`has_history_members` mirrors it exactly.
- `workspace_quality.py` gates dbs via the shared `_gate_member()`; `has_history` must NOT follow quality's ATTACH/union machinery — a plain per-member EXISTS suffices.

### Tests
- `scripts/tests/test_feat3445_workspace_activity.py` — extend with empty-db / rows-outside-window / loop-only / issue-only / db_missing / schema_skew / unreadable cases per AC.
- `scripts/tests/test_cli_history.py` — REQUIRED (not optional): `_MEMBER_KEYS`/`_TOTALS_KEYS` (:438-462) are exact-list equality asserts (:535/:547/:557), so they must gain the new keys or the suite stays red; also pin the canonical single-repo-fallback empty-db golden per AC.

_Wiring pass added by `/ll:wire-issue`:_
- New formatter tests (genuine gap): zero tests in the repo call `format_workspace_activity_*` directly (grep-verified; formatters are exercised only via loose substring asserts in `test_all_four_formats_render_with_scope_flag`, test_cli_history.py:663-690). The Option A totals-line edit needs direct-construction tests — build `WorkspaceActivityResult` inline, assert the extended totals line renders — following the `TestAggregationResultFormatters` pattern (`scripts/tests/test_feat3410_workspace_quality.py:234-262`). Home: `test_feat3445_workspace_activity.py`. [Agent 3 finding, grep-confirmed]
- `test_no_ok_member_totals_all_null` (`scripts/tests/test_cli_history.py` ~:705-717) — existing all-unknown-workspace test that already asserts `instrumented is False` + `None` counts (:713-717); the natural home for the AC "all-unknown workspace → `has_history_members: 0`, `has_history: false`" pin. [Agent 3 finding, grep-confirmed]

### Documentation
- `docs/reference/API.md` (workspace_activity section)
- `docs/reference/CLI.md` (ll-history activity output shape)
- Module docstring in `workspace_activity.py`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:3397-3399` — sharper anchor inside the known :3395-3405 range: two sentences enumerate keys explicitly and must gain the new ones — the member-key sentence ("...`error`/`instrumented` + the five count fields" — `has_history` is neither an already-listed key nor a count field) and the totals key-order sentence ("`members, instrumented_members, instrumented, ok_members, ...`"). [Agent 1/2 findings, grep-confirmed]
- `docs/ARCHITECTURE.md:714` — reference-only: names `aggregate_workspace_activity()` behaviorally (FEAT-3445 sibling of `aggregate_history_dbs()`), no field enumeration — verified no edit needed under the additive change. [Agent 1 finding, grep-confirmed]
- `docs/guides/HISTORY_SESSION_GUIDE.md:468,480` — reference-only: behavioral mentions of `ll-history activity`, no key/output-shape text — no edit needed. [Agent 2 finding, grep-confirmed]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- `scripts/tests/test_cli_history.py` is missing from this map and MUST change: `TestHistoryActivity` pins exact key lists via `_MEMBER_KEYS`/`_TOTALS_KEYS` (:438-462), enforced as exact-list equality at :535, :547, :557, plus `instrumented` value asserts at :542/:550/:559-560/:714. Any new `to_dict()` key fails these regardless of insertion position — both constants must gain `has_history` (+ totals keys). AC "pytest passes" is unmeetable without editing this file.
- Correction to Similar Patterns: `workspace_quality.py` contains zero references to `instrumented` (full-file read + repo-wide grep verified); its `AggregationResult` carries `skipped` instead. The claim "instrumented is load-bearing in the workspace quality reader and its tests" is mis-attributed — the actual locks are `test_feat3445_workspace_activity.py:267/:281/:298/:308` (per-status semantics) and the CLI exact-list tests above. The design conclusion (never redefine `instrumented`) still holds; AC on workspace_quality tests is trivially satisfied since quality never touches the field.
- `scripts/little_loops/issue_history/__init__.py` re-exports (:202-210, `__all__` :293-300); the CLI imports the formatters through it (:658-664). `_has_any_history` is private — no export change needed.
- Documentation correction: there is no dedicated "workspace_activity section" in `docs/reference/API.md` — the function is one row in the `## little_loops.issue_history` table at API.md:2390 (states "None (never 0) counts when not ok"). CLI-side, the JSON-contract paragraph is `docs/reference/CLI.md:3395-3405`, and CLI.md:3398 states "totals mirrors WorkspaceTotals.to_dict() key order" — both need the new keys.

## Implementation Steps

1. Add `_has_any_history(conn) -> bool` next to `_count_member_activity` in `workspace_activity.py` using the EXISTS query.
2. Call it in the ok path (inside the existing `try`, so `sqlite3.Error` routes to `UNREADABLE`); set `has_history=False` in the `DB_MISSING` case and `None` for `SCHEMA_SKEW`/`UNREADABLE`.
3. Extend `_totals()` with `has_history_members` and `has_history`.
4. Update `to_dict()` on both dataclasses and the text/markdown formatters.
5. Update the module docstring and the `workspace_activity` row in the `## little_loops.issue_history` table in `docs/reference/API.md` (there is no dedicated section — API.md:2390) and `docs/reference/CLI.md` (ll-history activity output shape, :3395-3405).
6. Tests (see AC).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Coverage constraint: step 6's "pytest passes" is unmeetable without extending the exact key lists in `test_cli_history.py:438-462` (`_MEMBER_KEYS`/`_TOTALS_KEYS`, enforced at :535/:547/:557) — that file is not named in this issue's test scope. `test_feat3445_workspace_activity.py:404-422` (`test_totals_to_dict_key_order`) is a second exact-list site; both must gain the new keys at whatever insertion position Decision 4 picks (this is the first post-ship key addition to the FEAT-3446 contract — no precedent constrains position, but all exact-list sites must be edited either way).
- Verification constraint: the new helper's body must not contain `ensure_db(`, `_connect_readonly(`, or `immutable=1` — `test_feat3445_workspace_activity.py:432-450` source-inspects the module text after `def _parse_ts`.
- Fixture shapes already exist for every AC state: schema'd-but-empty via `ensure_db(db)` (pattern: `test_history_reader_runs.py:133-136`); rows-outside-window via `record_loop_run_summary` then unbounded-vs-windowed compare (`test_feat3445_workspace_activity.py:210-225` asserts unbounded == 1, windowed == 0 — exactly the quiet-window shape); loop-only/issue-only via direct SQL mutation (precedent `_insert_running_loop_run`/`_stamp_issue_ts`, :43-71); db_missing (:260-272), schema_skew (`_skewed_member` :74-85), unreadable (:285-299); read-only guarantee via `_sha256` before/after (:110-111, :313-319). Member dbs are created under `<name>-history.db` names to dodge the autouse `_isolate_history_db` fixture (conftest.py:915-949).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add formatter totals-line tests (text + markdown) to `scripts/tests/test_feat3445_workspace_activity.py` — direct-construction pattern from `TestAggregationResultFormatters` (`scripts/tests/test_feat3410_workspace_quality.py:234-262`); zero tests call `format_workspace_activity_*` today, so the Option A totals-line edit lands untested without this
- Extend `test_no_ok_member_totals_all_null` in `scripts/tests/test_cli_history.py` (~:705-717) with `has_history_members == 0` / `has_history is False` asserts — pins the all-unknown-workspace AC as decided behavior
- Update the two key-enumeration sentences in `docs/reference/CLI.md:3397-3399` (member-key list and totals key-order list) — `has_history` is neither an already-enumerated key nor a "count field", so both sentences change, not just the paragraph around them
- Update the trailing semantics sentence in the same paragraph (`with \`instrumented\` as the OR over members and counts summed over \`ok\` members only`) to also state the new totals rule: `has_history` is the OR over members where the member field `is True` (so an all-`null` workspace totals to `false`/`0`, per the all-unknown AC)

## Impact

- **Priority**: P2 - additive signal needed by a real consumer (little-loops-hermes) to avoid reporting measured-zero on empty dbs; no data corruption or user-facing breakage without it.
- **Effort**: Small - one helper, three fields, two `to_dict()`s, two formatters, doc updates, focused tests in one existing test file.
- **Risk**: Low - purely additive; `instrumented` semantics untouched; FEAT-3446 stable-key-order contract preserved for existing keys (new keys appended after `instrumented`).
- **Breaking Change**: No - new dataclass fields default to `None`; JSON/YAML gain keys; consumers ignoring unknown keys are unaffected.

## Program Design

### Signatures
- **New helper** (placement: `workspace_activity.py`, adjacent to `_count_member_activity`):

  ```python
  def _has_any_history(conn: sqlite3.Connection) -> bool:
      ...
  ```

  Body: `SELECT EXISTS(SELECT 1 FROM issue_events) OR EXISTS(SELECT 1 FROM loop_runs)` — cheap index-probe per table, no scan, no window predicates.
- **New field** on `RepoActivity` (after `instrumented`):

  ```python
  has_history: bool | None = None
  ```

- **New fields** on `WorkspaceTotals` (after `instrumented`):

  ```python
  has_history_members: int
  has_history: bool
  ```

### Call Path
`aggregate_workspace_activity()` → `_gate_member()` → `_has_any_history(conn)` → `RepoActivity` → `_totals()` → `WorkspaceTotals` → `to_dict()` → `format_workspace_activity_text()` / `format_workspace_activity_markdown()`

`_has_any_history()` is called in the ok branch inside the existing `try:` whose `except sqlite3.Error` already routes to `MemberActivityStatus.UNREADABLE`, so a failing EXISTS needs no new error path — it lands in the existing branch and `has_history` reads as `None`.

### Decision Rules
- Never redefine `instrumented` — it is load-bearing in the workspace quality reader and its tests.
- `None` (not `False`) whenever the row count is unknowable (schema_skew/unreadable): asserting `False` would repeat the no-answer-≠-zero conflation this issue exists to fix.
- `db_missing` → `False` (a real answer: nothing was ever recorded).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- All cited anchors verified against current code: `instrumented` set at workspace_activity.py:277 (gate-skip: `status is not DB_MISSING`), :291 (count-failure, hardcoded True), :304 (ok, hardcoded True); `_gate_member()` at workspace_quality.py:123-159 returns `(conn, None, None) | (None, reason, kind)` and opens one read-only URI conn per member (`sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)` + `PRAGMA query_only`) — no ATTACH on this path; `_count_member_activity` def :217 / call :284; `_totals` def :228 / call :312; CLI callers at cli/history.py:678 and :689.
- Capability search result (searched `SELECT EXISTS` repo-wide + `has_history` repo-wide): partial precedent exists — `issue_events_ever_recorded()` (`issue_history/parsing.py:421-456`) runs `SELECT EXISTS(SELECT 1 FROM issue_events)` + `bool(row[0])`, but covers only `issue_events` and raises typed `HistoryDbUnavailable`; the new `_has_any_history` adds the `loop_runs` OR-arm and must never raise (routes via the existing per-member try). `SELECT EXISTS` appears in exactly one package file (parsing.py); `has_history`/`_has_any_history` has zero implementation hits — feature unimplemented.
- Construction facts: every `RepoActivity`/`WorkspaceTotals` construction is keyword-based inside workspace_activity.py (:237, :272, :286, :299); no external constructor callers exist. Field placement after `instrumented` keeps non-default-before-default ordering valid on both frozen dataclasses (`has_history: bool | None = None` has a default; the two `WorkspaceTotals` fields are non-default, inserted before `ok_members`).
- Totals aggregation gap (no precedent in module): the mirrored `any()`/`sum(... if r.x)` expressions (:239-240) operate on always-bool `instrumented`; no existing code aggregates a `bool | None` member field into non-optional totals. Decision 3 already pins the rule — count/any over `is True` only; `None` members simply do not count.
- Source-inspection constraint: `test_feat3445_workspace_activity.py:432-450` (`TestNeverUsesMigratingOpener`) asserts the module text after `def _parse_ts` contains no `ensure_db(`, `_connect_readonly(`, or `immutable=1`. The new helper lands inside that inspected slice — it must reuse the gated `conn` passed in, never open its own.
- Gate nuance verified: a db with only a matching `meta` table passes the gate (`_gate_passes_no_activity_tables`, test :88-107) and today lands in UNREADABLE via "count query failed" — a failing EXISTS on such a db lands in the same branch, so `has_history` reads `None`; no classification shifts.

## Scope Boundaries

- **Out of scope**: changing `instrumented` semantics; windowing `has_history` (it is deliberately any-rows-ever, irrespective of `--since/--until`); counting rows (only existence); changes to `workspace_quality.py` or its tests; new CLI flags on `ll-history activity`; hermes-side consumption logic (sibling ENH-3449 covers the opt-out env var for that consumer).
- **In scope**: the three new fields, the helper, serializer/formatter exposure, docs, and tests in `test_feat3445_workspace_activity.py` plus the mandatory exact-list updates (and fallback golden) in `test_cli_history.py`.

## Decisions (resolved, do not re-derive)

1. **New field, not a redefinition.** Add `has_history: bool | None` to `RepoActivity` meaning "at least one row exists in `issue_events` OR `loop_runs`, irrespective of the window".
2. **Values per status:**
   - `ok`: computed via `SELECT EXISTS(SELECT 1 FROM issue_events) OR EXISTS(SELECT 1 FROM loop_runs)` (cheap, no scan).
   - `db_missing`: `False` (a real answer: nothing recorded).
   - `schema_skew` / `unreadable`: `None` (JSON `null`). `False` would assert "no rows", which is the same no-answer-≠-zero conflation. If the EXISTS query itself raises `sqlite3.Error`, it falls into the existing `UNREADABLE` branch → `None`.
3. **Totals mirror the `instrumented` pattern:** `WorkspaceTotals.has_history_members: int` (count of members with `has_history is True`) and `WorkspaceTotals.has_history: bool` (any).
4. **JSON key placement:** `has_history` appended immediately after `instrumented` in `RepoActivity.to_dict()`; `has_history_members` and `has_history` immediately after `instrumented` in `WorkspaceTotals.to_dict()`. Existing key order otherwise unchanged (FEAT-3446 AC 1 stable-order contract preserved for existing keys).
   **Text/markdown totals-line rendering (pinned, review 2026-09-11):** the Option A extension renders the **count**, mirroring the existing line — `members: {N} (ok: {X}, instrumented: {Y}, has_history: {Z})` where `{Z}` is `totals.has_history_members`, not the `has_history` bool (the existing line renders `instrumented: {totals.instrumented_members}`, also a count). Same shape in text and markdown. The new formatter tests and the CLI.md prose must both use this exact shape.
5. **Self-analytics tables don't count as history** (review 2026-09-11): `has_history` deliberately ignores `cli_events` and `skill_events` rows — the EXISTS covers only `issue_events` OR `loop_runs`. The CLI golden pins exactly this (the single-repo fallback db carries a `cli_events` row yet reports `has_history: false`): those tables are ll's own instrumentation churn, not the workspace development activity the signal exists to answer about.

## API/Interface

- `RepoActivity.has_history: bool | None` (new dataclass field, default `None`).
- `WorkspaceTotals.has_history_members: int`, `WorkspaceTotals.has_history: bool` (new fields).
- JSON/YAML output from `ll-history activity` gains the three keys above. Text/markdown formatters show `has_history` in the totals line only, alongside the `instrumented` counts (per Decision on Option A — no per-member rendering).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-11 — based on codebase analysis:_

- Cross-reference: the text/markdown rendering of `has_history` is an open decision (per-member `instrumented` has no rendering today) — see Option A/B under Proposed Solution → Codebase Research Findings.
- JSON/YAML need no formatter code change: `format_workspace_activity_json` (:340-347) is a verbatim `json.dumps(result.to_dict())` and `_yaml()` (:350-360) is `yaml.dump(..., sort_keys=False)` with a JSON fallback — new `to_dict()` keys pass through untouched. Only the text/markdown formatters hand-render fields.

## Acceptance Criteria

- [ ] Empty schema'd db (tables, zero rows): `instrumented: true`, `has_history: false`, counts zero.
- [ ] Db with rows all outside the window: `instrumented: true`, `has_history: true`, counts zero.
- [ ] Db with one `loop_runs` row and no `issue_events` (and vice versa): `has_history: true`.
- [ ] `db_missing`: `has_history: false`. `schema_skew` and `unreadable`: `has_history: null` in JSON.
- [ ] `WorkspaceTotals` JSON contains `has_history_members` and `has_history` with the any/count semantics above.
- [ ] All-unknown workspace (every member `schema_skew`/`unreadable`): totals `has_history_members: 0`, `has_history: false` despite every member being `null` — pinned as decided behavior (count/any over `is True`), not accidental.
- [ ] Exact-list test sites updated: `_MEMBER_KEYS`/`_TOTALS_KEYS` in `test_cli_history.py` and `test_totals_to_dict_key_order` in `test_feat3445_workspace_activity.py` gain the new keys per Decision 4.
- [ ] Option A rendering pinned by test: direct-construction formatter tests (text + markdown) assert the totals line renders the `has_history` **count** in the exact Decision 4 shape — `members: {N} (ok: {X}, instrumented: {Y}, has_history: {Z})`.
- [ ] CLI golden: single-repo fallback member (db pre-created with only a `cli_events` row) reports `ok`, zero counts, `has_history: false` — the canonical empty-but-schema'd case.
- [ ] Existing `instrumented` semantics and all workspace_quality tests unchanged.
- [ ] Docs updated; `python -m pytest scripts/tests/` passes.

## Related

- FEAT-3445, FEAT-3446 (shipped `ll-history activity`).
- Sibling: ENH-3449 (analytics opt-out env var for CLI read paths), same consumer.
- **Implementation-order note (review 2026-09-11):** ENH-3449 and this issue both touch `test_cli_history.py` and `docs/reference/CLI.md` — whoever lands second rebases those two files. The CLI golden AC above (fallback member `ok` + `has_history: false`) depends on `cli_event_context` pre-creating the fallback db, which ENH-3449 makes conditional on `LL_ANALYTICS_CAPTURE`. No extra work is required either way: once ENH-3449 adds the var to `_CMD_RUN_ENV_VARS`, the autouse conftest scrub (`setenv("")` + `delenv`) runs every test with it unset, which is exactly what the golden needs; if this issue lands first, the var does not exist yet. The pair composes: under ENH-3449's env-set poll, a db-less repo reports `db_missing` → `has_history: false`, consistent with Decision 2.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-11 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-11T22:19:33 - `369e3711-4556-4e3c-876a-604507ba84d4.jsonl`
- `/ll:confidence-check` - 2026-09-11T22:06:20 - `04b0bc6a-df8f-4f3b-a7b5-400723a6e9f5.jsonl`
- `/ll:wire-issue` - 2026-09-11T21:19:57 - `ab7c07a0-32fd-4cb6-93e8-64bf011c8239.jsonl`
- `/ll:decide-issue` - 2026-09-11T20:58:18 - `4edab3cd-c7fc-4d55-b641-0b1df5125d0f.jsonl`
- `/ll:refine-issue` - 2026-09-11T20:49:41 - `dc57321a-6cbd-4b3f-bbcf-a2a2264f04d2.jsonl`
- `/ll:format-issue` - 2026-09-11T20:31:22 - `927fc9d3-cc55-46d9-9660-1cb2e288f9d7.jsonl`
- `/ll:capture-issue` - 2026-09-11T20:26:49 - `d2544764-cca3-4cd1-bd27-85b0d1d0f3c3.jsonl`
