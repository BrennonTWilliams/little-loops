---
id: ENH-3406
title: harness_events run-model columns + harness_admissions table (schema)
type: ENH
priority: P1
status: open
discovered_date: '2026-09-08'
verify_verdict: NON_VALID
parent: ENH-3397
labels:
- harness
- evaluation
- statistics
size: Large
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3406: harness_events run-model columns + harness_admissions table (schema)

## Summary

Add the schema foundation for ll-harness's run model: new columns on `harness_events`
(`cell_key`, `repetition`, `attempt_kind`, `continuations`, `superseded_by`) and a new
append-only `harness_admissions` audit table. First of three issues decomposed from
ENH-3397 (schema → writers/gate → read-path counting). This issue is additive schema
only — no existing CLI command's behavior changes here.

## Parent Issue

Decomposed from ENH-3397: Distinguish repetition, infrastructure retry, and continuation
in ll-harness.

## Design Decisions (inherited from parent)

- Cell identity: `cell_key = (target, task, subject)` where `subject = runner_label +
  head_sha`; `repetition` is a stamped index per cell, reused (not incremented) by an
  `infra_retry`.
- Admission reason enum: `timeout | host_crash | harness_error | network` — no free-text.
- `harness_admissions` is INSERT-only (matches `hook_events`/`test_run_events`/
  `commit_events` precedent in `writers.py`), never updated or deleted — the contrasting
  UPSERT shape (`correction_retirements`) does not apply here.

## Program Design

### Types
- `harness_admissions` row: `attempt_id: int`, `superseded_id: int | None`,
  `reason: Literal["timeout", "host_crash", "harness_error", "network"]`, `ts: str`
  (ISO-8601, matching every other `_events`-style table's `ts TEXT NOT NULL` convention).
- `harness_events` gains: `cell_key: str | None`, `repetition: int | None`,
  `attempt_kind: Literal["repetition", "infra_retry"] | None`, `continuations: int | None`,
  `superseded_by: int | None` — all nullable, no `DEFAULT`, matching the "Fix-forward only"
  convention (existing rows are not backfilled).

### Signatures
- No new Python function signatures. The sole artifact is one new element appended to
  `_MIGRATIONS: list[str]` (`schema.py:124`) — a plain SQL string, not a function or tuple.
  `_apply_migrations()` (`schema.py:1382`) consumes it automatically; no separate
  registration call exists.

### Call Path
`ensure_db()` (`schema.py:1460`) -> `connect()` (`schema.py:1501`) -> `_apply_migrations()`
(`schema.py:1382`) -> executes `_MIGRATIONS[48]` (this issue's new entry, stamping schema
version `49`) via `_split_sql_statements()` (`schema.py:1352`) inside one `BEGIN IMMEDIATE`
transaction -> `ALTER TABLE harness_events ADD COLUMN ...` x5 and
`CREATE TABLE IF NOT EXISTS harness_admissions (...)` -> `meta.schema_version` stamped `49`.

### Decision Rules
- **Registry placement** (kinded vs. kindless): `harness_admissions` must resolve to
  exactly one of `_KIND_TABLE`/`_KINDLESS_TABLES` or `ll-verify-kinds`
  (`cli/verify_kinds.py::_run()`) exits 1. The `credential_scope_events` precedent this
  issue already directs mirroring (v47, kinded) supports a kinded placement — but
  `_EXPORT_TABLE_MAP` membership is a separate, independently-decided registration
  regardless of kinded/kindless choice (`credential_scope_events` is kinded with no
  export-map entry; see Files to Modify findings).
- **`reason` enum enforcement**: exact input set is fixed by Acceptance Criteria —
  `timeout | host_crash | harness_error | network`. No `session_store` writer validates a
  `Literal` at the Python INSERT boundary today; this codebase's precedent for enforcing a
  closed string enum at the schema level is a `CHECK` constraint
  (`verdict_events.verdict`/`abstention_reason` at `schema.py:1216-1220`,
  `research_triage_events.axis`/`reason` at `schema.py:1291-1298`). Escape hatch: a bare
  `TEXT` column with no `CHECK` is also viable (matches `harness_events.semantic_verdict`,
  an enum-like `TEXT` column with no `CHECK`) — implementer's call, not fixed by research.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **CHECK-constraint retrofit cost differs for new vs. existing tables**: SQLite cannot `ALTER TABLE ADD COLUMN ... CHECK (...)` — retrofitting a CHECK onto an *existing* column requires the full rename/copy/drop/rename rebuild pattern (`verdict_events`, v44/ENH-230, `schema.py:1195-1230`). `harness_admissions` is a from-scratch table, so declaring `reason TEXT CHECK (reason IN (...))` directly in its `CREATE TABLE` carries none of that rebuild cost — the "implementer's call" framing in the Decision Rules escape hatch above holds regardless of which option is chosen; neither is more expensive to land for this specific table.
- **Additional no-CHECK precedent** (strengthens the existing escape-hatch citation): besides `harness_events.semantic_verdict`, three more enum-like `TEXT` columns carry no CHECK: `session_lifecycle_events.event` (`schema.py:643`, with an explicit comment at `schema.py:632-634` stating it is deliberately open so ENH-2509's `worktree_*` values can share the table), `orchestration_runs.status` and `loop_runs.final_state`/`terminated_by` (`schema.py:540-561,570-587`), and `advisor_consults.outcome` (`schema.py:1259`, despite its migration comment describing it as mirroring a `Literal` type). Only 2 of at least 6 enum-like `TEXT` columns in this file carry a CHECK (`verdict_events`, `research_triage_events`) — both from the two most recent precedents (v44, v46), not a supermajority convention.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Correction (stale line citations)**: the Call Path anchors above have drifted — `_apply_migrations()` is now at `schema.py:1395` (not `1382`), `ensure_db()` at `schema.py:1473` (not `1460`), `connect()` at `schema.py:1514` (not `1501`), and `_split_sql_statements()` at `schema.py:1365` (not `1352`). Function names and call order are unchanged; only line numbers moved (working tree currently has uncommitted edits to `schema.py` ahead of this migration landing).

## Files to Modify

- `scripts/little_loops/session_store/schema.py` — add `cell_key`/`repetition`/
  `attempt_kind`/`continuations`/`superseded_by` columns to `harness_events` via an
  additive migration in `_MIGRATIONS` (next `SCHEMA_VERSION`, currently 47), following the
  "Fix-forward only" comment convention (`schema.py:931,947-948,973,1011-1018`). Add a new
  `harness_admissions` table: `attempt_id`, `superseded_id`, `reason`
  (`Literal["timeout","host_crash","harness_error","network"]`), `ts`.
  > ⚠ Superseded — stale: SCHEMA_VERSION now 48, fix-forward cites wrong lines
- Registry decision: `harness_admissions` needs an explicit kinded (`VALID_KINDS` +
  `_KIND_TABLE` entry, `schema.py:27-83`) vs. kindless (`_KINDLESS_TABLES`,
  `schema.py:85-100`) placement — mirror the `credential_scope_events` precedent (v47,
  ENH-3204): `VALID_KINDS`/`_KIND_TABLE` entries plus a companion test asserting
  `"harness_admissions" not in _KINDLESS_TABLES` (`test_session_store_schema.py:2800-2812`
  is the worked example).
- Decide whether `harness_admissions` needs an `_EXPORT_TABLE_MAP` entry
  (`session_store/queries.py:88-134`) for `ll-history export` symmetry with
  `harness_events`.
- `scripts/little_loops/session_store/lifecycle.py:930-941` — add `harness_admissions` to
  the `_REBUILD_TABLES` exclusion comment alongside `harness_events` (documentation only;
  `rebuild()` already excludes new tables by default).
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate after the DDL
  change (recipe in `test_session_store_schema.py:2852-2865`);
  `test_schema_manifest_matches_checked_in_file` fails otherwise.
- `docs/guides/HISTORY_SESSION_GUIDE.md:91-101,143` — add a new row to the
  schema-version-history table (new rows currently end at v48, `:108`) and update the
  line-143 `harness_events` prose to mention the new columns/table.
  > ⚠ Superseded — stale: was line 142, current line is 143 (`/ll:verify-issues`,
  > 2026-09-08).
- `docs/ARCHITECTURE.md:670` — update the `harness_events` v31 row in the schema-version
  table (`### Write Path`, the `## History DB: Producer→Consumer Flow` section); this is
  a full paragraph entry, not a one-liner.
  > ⚠ Superseded — stale: line 142 in ARCHITECTURE.md is inside the `## Directory
  > Structure` tree diagram, unrelated to `harness_events`; the actual content lives at
  > `:670` (`/ll:verify-issues`, 2026-09-08).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_kinds.py` — `_run()` regex-scans `_MIGRATIONS` for every `CREATE TABLE` and exits 1 if a table name is neither in `_KIND_TABLE.values()` nor `_KINDLESS_TABLES`; `harness_admissions` will trip this the moment its migration lands unless registered in the same change [Agent 1 finding].
- `scripts/little_loops/session_store/queries.py:18` — imports `_KIND_TABLE`, `VALID_KINDS`; `recent()` resolves a `--kind` value to its table via `_KIND_TABLE`, so a kinded registration for `harness_admissions` flows through here automatically (no edit needed, informational) [Agent 1 finding].
- `scripts/little_loops/cli/session.py:52-70,120,132` — `VALID_KINDS` is consumed as argparse `choices=` for `ll-session search --kind` / `recent --kind`; a kinded registration makes the new kind selectable with zero code change (informational) [Agent 1 finding].
- `scripts/little_loops/cli/doctor.py` (`_schema_drift_data()`) and `scripts/little_loops/cli/artifact/dashboard.py` (schema-version stamping) both re-derive output from `_MIGRATIONS`/`SCHEMA_VERSION` at call time — no edit needed, informational [Agent 1/2 finding].

### Registrations (docs)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/verify_kinds.py` module docstring (lines 4-9) — hardcoded prose list of kindless tables (`meta`, `search_index`, `sessions`, `assistant_messages`, `summary_nodes`, `summary_spans`, `raw_events`); if `harness_admissions` is decided kindless, append it here. Not test-enforced — a missed edit won't fail CI [Agent 2 finding].
- `docs/reference/CLI.md:4408` (`### ll-verify-kinds` section) — a second, already-divergent copy of the same kindless-table prose list (includes `correction_retirements`, which the docstring above omits); update in lockstep with the docstring above if `harness_admissions` is kindless [Agent 2 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Correction (stale reference)**: `SCHEMA_VERSION` is currently `48` (not `47`) and `len(_MIGRATIONS) == 48` — a v48 migration (`FEAT-3404`, `schema.py:1339-1343`) landed after this issue was drafted. This issue's new entry is `_MIGRATIONS[48]`, stamping schema version `49`.
- **Correction (wrong citation)**: the "Fix-forward only" comment convention actually appears at `schema.py:928,946,972` — not `931,947-948,973,1011-1018`. `schema.py:1011-1018` is an unrelated `BUG-3236` migration-repair comment with no "Fix-forward" language.
- `scripts/little_loops/cli/verify_kinds.py` (`_run()` lines 54-63, `_all_migration_tables()` line 39) is the mechanical enforcer of the kinded/kindless registry: it regex-scans every `CREATE TABLE` in `_MIGRATIONS` and `ll-verify-kinds` exits 1 if a table name lands in neither `_KIND_TABLE.values()` nor `_KINDLESS_TABLES`. `harness_admissions` must resolve to one or the other or this check fails — not previously named in this issue.
- Precedent for the exact `ALTER TABLE ... ADD COLUMN` shape for the five new columns: `harness_events` already gained three columns this same way at `schema.py:952-978` (v39, ENH-141: `target_content_hash`, `target_path`, `dirty` — bare nullable columns, no `DEFAULT`, no backfill, no index added for two of the three).
- `harness_events.parent_id` (`schema.py:727`, index `idx_harness_parent` at `schema.py:737`) is the existing precedent for a self-referential nullable-FK column on this exact table: plain `INTEGER`, no `REFERENCES` clause, backed by a plain non-unique index — the closest existing model for `superseded_by`.
- `_EXPORT_TABLE_MAP` (`queries.py:89-134`) precedent is mixed, not uniform: `harness_events` has an entry (`"harness_event": ("harness_events", "ts")`, `queries.py:104`), but `credential_scope_events` — the exact v47 precedent this issue names for registry placement — has no `_EXPORT_TABLE_MAP` entry and is absent from `_EXPORT_DEFAULT_TABLES`. No comment in `queries.py` states a criterion distinguishing which audit tables get an entry.
- Dependent readers/writers (confirms this issue's scope boundary, no action needed here): `scripts/little_loops/history_reader/harness.py`'s `HarnessEvent` dataclass and `_HARNESS_EVENT_COLUMNS` fragment (lines 36-71) silently drop any DB column not listed as a dataclass field — the five new columns will exist in the DB but stay invisible to `recent_harness_events()`/`harness_eval_pass_rate()` until ENH-3408 explicitly adds them. `scripts/little_loops/session_store/writers.py`'s `record_harness_event()` (lines 1024-1104) has a hardcoded `INSERT` column list with no `**kwargs` passthrough, so no existing writer populates the five new columns until ENH-3407.
- Additional importers of `schema.py`, informational only (read `SCHEMA_VERSION`/re-export symbols, no code change needed for this issue): `scripts/little_loops/session_store/__init__.py:99`, `scripts/little_loops/cli/artifact/dashboard.py:42`, `scripts/tests/test_feat3304_artifact_dashboard.py:54`.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- `scripts/little_loops/observability/schema.py`'s `HarnessEventVariant(DESVariant)` (line 731) is a bare type-discriminator tag class for the durable event stream — `type: Literal["harness_event"] = "harness_event"` with a one-line docstring, no field list mirroring `harness_events` columns. Confirmed no action needed here: this issue's five new columns require no corresponding change to this class.
- `scripts/little_loops/queue_store.py` has its own structurally similar but fully independent migration system (own `SCHEMA_VERSION = 2`, own `_apply_migrations()` at line 170, own `ensure_db()`) — its docstring (lines 5-9) states it copies rather than shares `session_store`'s migration bodies. Confirmed out of scope: it does not call or share `session_store.schema._apply_migrations` and has no `harness_events`/`harness_admissions` reference.

## Tests

- `scripts/tests/test_session_store_schema.py` — follow the existing `harness_events`
  migration coverage shape (`test_harness_events_columns` 1573,
  `test_harness_events_indexes_exist` 1604, `test_v30_db_upgrades_gains_harness_events`
  1621, `test_harness_is_kinded` 1635, `test_harness_events_excluded_from_rebuild_tables`
  1639): add equivalents for the new columns and a
  `test_vNN_db_upgrades_gains_harness_admissions`-style test, plus the kinded/kindless
  companion assertion.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_schema.py` — 22 existing tests hardcode
  `assert SCHEMA_VERSION == 48` (lines 650, 664, 716, 812, 1034, 1075, 1413, 1453, 1497,
  1547, 1622, 1682, 1751, 1816, 1884, 1929, 1984, 2542, 2624, 2724, 2786, 2840); all must
  become `49` when this migration lands [Agent 3 finding].
- `scripts/tests/test_session_store_writers.py` — 5 hardcoded `assert SCHEMA_VERSION ==
  48` sites (lines 470, 1153, 1283, 1622, 1864) will break and need updating to `49`
  [Agent 3 finding].
- `scripts/tests/test_assistant_messages.py:88` — hardcoded `assert SCHEMA_VERSION == 48`
  will break and needs updating to `49` [Agent 3 finding].
- `scripts/tests/test_verify_kinds.py` (`TestRun.test_clean_state_returns_zero`,
  `TestMainVerifyKinds.test_clean_state_returns_zero`) — existing gate tests that call
  `_run()`/`main_verify_kinds()` against the real, unmocked migration set; both will start
  failing the moment the `harness_admissions` `CREATE TABLE` lands unless it is registered
  in `_KIND_TABLE` or `_KINDLESS_TABLES` in the same change. This is the mechanical
  enforcement of this issue's registry-placement decision rule, not a new test to write
  [Agent 3 finding].
- Precedent class to mirror is confirmed as `TestSchemaV47CredentialScopeEvents`
  (`test_session_store_schema.py:2753-2812`), exactly 6 methods:
  `test_credential_scope_events_columns` (exact-set `==` assertion, not subset),
  `test_credential_scope_events_indexes_exist`, `test_v46_db_upgrade_gains_credential_scope_events`
  (hardcodes bootstrap version 46 and post-migration `SCHEMA_VERSION == 48`),
  `test_kind_registration`, `test_excluded_from_rebuild`, `test_not_kindless`. A new
  `TestSchemaV49HarnessAdmissions`-style class should reproduce this exact 6-method shape,
  substituting whichever of `test_not_kindless`/`test_kind_registration` applies to the
  chosen registry placement [Agent 3 finding].
- `test_harness_events_columns` (`test_session_store_schema.py:1573`) confirmed to use a
  `<=` subset assertion — no update needed for the 5 new `harness_events` columns
  [Agent 3 finding].
- **Stale citation correction**: the regen-recipe docstring and
  `test_schema_manifest_matches_checked_in_file` have moved to
  `test_session_store_schema.py:2919-2934` and `:2939` respectively in the current working
  tree (this issue's cited `2852-2865` now falls inside an unrelated `ll_version`
  NULL-preservation test) — re-locate by name (`TestSchemaManifest`) rather than by line
  number when implementing [Agent 3 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Migration test classes in this codebase follow a `TestSchemaV<NN><TableName>` grouping convention — e.g. `TestSchemaV31HarnessEvents` (`test_session_store_schema.py:1570`) and `TestSchemaV47CredentialScopeEvents` (`test_session_store_schema.py:2753`) — each bundling a columns test, an indexes test, a `test_vNN_db_upgrades_gains_<table>` upgrade-simulation test (via the `_bootstrap_schema_at()` helper, `test_session_store_schema.py:1134`), a kind-registration test, and a not-in-`_REBUILD_TABLES`/not-in-`_KINDLESS_TABLES` pair.
- Columns-assertion shape differs by whether the table is expected to gain more columns later: `test_harness_events_columns` (`:1573`) uses a subset assertion (`{...} <= cols`) with an explicit comment explaining why ("so later migrations can extend the table without breaking the original contract") — this issue's five new columns still satisfy that existing subset test unchanged, no update needed there. `test_credential_scope_events_columns` (`:2764`) instead uses an exact-set assertion (`cols == {...}`) since that table has had no later column-adding migration — a new `harness_admissions` columns test would most naturally follow the exact-set form used by its own cited precedent, absent a known future column addition.
- `ll-verify-kinds` (`cli/verify_kinds.py`) has no dedicated pytest wrapper found in `test_session_store_schema.py`; the kinded/kindless companion assertions in the `TestSchemaV<NN>` classes (e.g. `test_not_kindless`, `test_session_store_schema.py:2812`) are what actually exercises this registry in the test suite, not a direct `ll-verify-kinds` subprocess test.

## Acceptance Criteria

- `harness_events` gains `cell_key`, `repetition`, `attempt_kind` (`repetition` |
  `infra_retry`), `continuations` (nullable int) and `superseded_by` (nullable attempt
  id). Schema migration, live-write-only like the rest of the table.
- A new `harness_admissions` table exists: `attempt_id`, `superseded_id`, typed `reason`
  (`timeout` | `host_crash` | `harness_error` | `network`), `ts`.
- `schema_manifest.json` regenerated and `test_schema_manifest_matches_checked_in_file`
  passes.
- `harness_admissions` has a resolved kinded-vs-kindless registry placement with a
  companion test.

## Scope Boundaries

- **In scope**: schema/table DDL, migration tests, registry placement decision,
  schema_manifest regen, `HISTORY_SESSION_GUIDE.md`/`ARCHITECTURE.md` updates for the new
  columns/table.
- **Out of scope**: any writer function that populates these columns (ENH-3407), any
  read-path logic that consumes them (ENH-3408), the `--retry-of` CLI flag (ENH-3407), the
  "no UPDATE/DELETE path" writer test (ENH-3407 — it targets `writers.py` source, not
  `schema.py`).

## Current Behavior

`harness_events` has no columns identifying which cell (`target`/`task`/`subject`) an
attempt belongs to, its repetition index, or whether it is a fresh repetition, an
infra retry, or superseded by another attempt. There is no `harness_admissions` table,
so nothing records when an infra retry was admitted or why. This makes it impossible
for later read-path logic (ENH-3408) to distinguish intentional repeated runs from
retries of the same failed attempt when computing reported `n`.

## Expected Behavior

`harness_events` gains five new nullable columns (`cell_key`, `repetition`,
`attempt_kind`, `continuations`, `superseded_by`) and a new append-only
`harness_admissions` audit table exists with a resolved kinded/kindless registry
placement. No existing CLI command's behavior changes as a result of this issue — it
is schema-only groundwork that ENH-3407 (writers) and ENH-3408 (counting) build on.

## Impact

- **Priority**: P1 — inherited from parent; this is the foundation the anti-p-hacking gate
  depends on.
- **Effort**: Small — additive schema migration only, no behavior change.
- **Risk**: Low — additive columns/table, no existing code path reads or writes them yet.
- **Breaking Change**: No.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-08:_

- **Verdict: OUTDATED.** Every prior line-citation "Correction" already recorded by
  `/ll:refine-issue`/`/ll:wire-issue` was re-checked against the current tree and
  confirmed exact — `schema.py` anchors (`_apply_migrations` 1395, `ensure_db` 1473,
  `connect` 1514, `_split_sql_statements` 1365, `SCHEMA_VERSION`/`len(_MIGRATIONS)` both
  48, Fix-forward comments at 928/946/972, `parent_id`/`idx_harness_parent` at 727/737,
  v39 columns at 975-977, `verdict_events`/`research_triage_events` CHECK lines,
  `session_lifecycle_events`/`orchestration_runs`/`loop_runs`/`advisor_consults` no-CHECK
  precedents), all 27 hardcoded `assert SCHEMA_VERSION == 48` test-file line numbers
  (22 in `test_session_store_schema.py`, 5 in `test_session_store_writers.py`, 1 in
  `test_assistant_messages.py`), the `TestSchemaV47CredentialScopeEvents` class bounds
  (2753-2812) and its exact-set-assertion line (2764), and the `TestSchemaManifest`
  location (2916/2939) all matched precisely. Two doc citations in **Files to Modify**
  had drifted and were not previously caught — corrected in place above:
  `HISTORY_SESSION_GUIDE.md:142`→`:143` (off-by-one), and `ARCHITECTURE.md:142` (points
  at an unrelated directory-tree diagram line; the real `harness_events` prose is a full
  paragraph at `:670`, not a one-liner).
- **Decisions log**: `ll-issues decisions list --type rule --enforcement required
  --active-only` returned no active required rules — no `DECISIONS_VIOLATION`.
- **Evidence-quote check**: `ll-verify-evidence` reported `"ok": true`, 0 findings — no
  `EVIDENCE_UNVERIFIED`.
- **Proposal-vs-code check**: not reached — check 1-4's OUTDATED anchors take precedence
  per the verdict-precedence rule (claim-verdict wins over `PROPOSAL_UNSOUND` when both
  could apply).
- **Graph**: provider=`codegraph` freshness=`fresh` — not used for this issue's checks
  (all citations were doc/schema line numbers rather than named symbols eligible for
  `ll-code defines`/`callers-of`).

## Status

**Open** | Created: 2026-09-08 | Priority: P1


## Session Log
- `/ll:confidence-check` - 2026-09-08T19:15:11 - `6bb0db90-fba6-4ae0-ba6a-a7670d32c039.jsonl`
- `/ll:format-issue` - 2026-09-08T18:36:34 - `204483fb-0035-4a22-9571-7e0656ebef10.jsonl`
- `/ll:verify-issues` - 2026-09-08T15:44:36 - `f5535f57-91c7-49aa-88ab-44821536803d.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T15:38:05 - `f35fb920-2ba8-40fb-874e-61854231e6cc.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-08T15:37:56 - `f35fb920-2ba8-40fb-874e-61854231e6cc.jsonl`
- `/ll:wire-issue` - 2026-09-08T15:23:56 - `a9d54179-48d4-480f-9ee0-00e38c854350.jsonl`
- `/ll:refine-issue` - 2026-09-08T15:13:47 - `deec33e7-924a-4be1-968b-50885844293d.jsonl`
- `/ll:issue-size-review` - 2026-09-08T05:34:24 - `5401886d-ebfd-404a-b6ba-9a7d5e921ddb.jsonl`
