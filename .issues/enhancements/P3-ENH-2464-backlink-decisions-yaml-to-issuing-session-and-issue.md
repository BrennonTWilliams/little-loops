---
id: ENH-2464
title: Backlink .ll/decisions.yaml entries to issuing session_id and issue_id
type: ENH
priority: P3
status: open
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
decision_needed: false
labels:
  - enhancement
  - decisions
  - history-db
  - captured
---

# ENH-2464: Backlink .ll/decisions.yaml entries to issuing session_id and issue_id

> **✅ Architecture alignment (ENH-2581 `raw_events`) — read before implementing.**
> [[ENH-2581]] made `raw_events` the single ingestion point for **session-transcript
> JSONL**, with every stream-derived table produced by a `_backfill_*()` parser that
> `rebuild()` replays (the pattern [[ENH-2461]] became). **`decision_events` is NOT
> that kind of table, and correctly so.** Its canonical source of truth is the
> external file `.ll/decisions.yaml` (+ `.ll/decisions.d/*.json`); the DB row is a
> **search/join mirror**, and `source_session_id` / `source_issue_id` are threaded
> from the orchestrator's runtime context at the `ll-issues decisions add` CLI call
> site — none of this is present in, or recovered from, session-transcript JSONL.
> `decision_events` is therefore a **direct-write YAML-mirror sibling**, shaped like
> `record_issue_snapshot` (YAML+DB dual-write) and `correction_retirements`, and its
> `_backfill_decision_events()` helper walks the **YAML/JSON decision files** — NOT
> `raw_events`. It joins the "outside `raw_events`'s scope" exclusion set (NOT added
> to `_REBUILD_TABLES` / `_REBUILD_SEARCH_KINDS`). It must still register in
> `_KIND_TABLE` (never `_KINDLESS_TABLES`) so `ll-verify-kinds` stays green. No
> `raw_events`-sourced parser is needed or wanted.

## Summary

`.ll/decisions.yaml` (FEAT-948 done, ENH-2152 done for extraction) holds `rule`, `decision`, and `exception` entries with author-provided fields like `rule`, `rationale`, `issue`, `category`, `enforcement`. `correction_retirements` (a sibling table) marks corrections as "codified as a rule" but it's only a one-way link from correction → rule. The `decisions` source file itself carries no `session_id` or `issuing_session_id` — when a `decision` is appended by `/ll:decide-issue`, `/ll:tradeoff-review-issues`, or `/ll:go-no-go`, the originating session and any related issue are not recorded. Add `source_session_id` and `source_issue_id` (or restructure `issue:` to include both) so a rule/decision can be traced to the session and issue that produced it. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #7: *"when a decision is added or its outcome is recorded, write the source `session_id`/`issue_id` so `ll-session search` can trace a rule back to the incident that produced it."*

## Motivation

The current decisions log is the project's rule substrate, but it's a write-once, manual-source-of-truth ledger with no traceback:

- **Why was this rule added?** — currently the rule entry has a `rationale` field but no link to the session that discussed it.
- **Which issue prompted this rule?** — `issue:` is set when present but isn't required; some entries drift orphan.
- **No backward trace from `correction_retirements` to issuing session** — corrections are linked to rule IDs, but the rule doesn't say "this rule came from session S discussing issue I."
- **No cross-query with `skill_events`** — without `source_session_id`, `ll-session search` cannot surface "which rules were added by `/ll:decide-issue` last week?" because the rule entry has no provenance.

## Current Behavior

- `.ll/decisions.yaml` schema (per FEAT-948): each entry has `id`, `type`, `timestamp`, `category`, `labels`, `rule`, `rationale`, optional `issue`, optional `scope`, optional `outcome`, optional `enforcement`, optional `supersedes`/`rule_ref`.
- Skill-level capture bridges (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) all write `rule` and `rationale` and `issue` if available — but the current session_id and a structured `source_session_id` are not recorded.
- `correction_retirements` in `.ll/history.db` has `topic_fingerprint`, `rule_id`, `addressed_at`, `session_id` — partial traceability on the corrections side.
- `ll-session search --fts "<rationale fragment>"` returns no decisions entries because decisions live in YAML, not the DB.

## Expected Behavior

- `DecisionEntry` and `RuleEntry` (per FEAT-948 / `scripts/little_loops/decisions.py`) gain `source_session_id: str | None` and structured `source_issue_id` fields.
- Skill-level capture bridges (the three pipelines named above) populate these from the orchestrator's runtime context when adding a new entry.
- `ll-session search --fts "<decision content>"` returns decision rows via a parallel DB mirror (analogous to `issue_snapshots` per ENH-2151 — store summaries in history.db, full text in YAML).
- `ll-issues decisions list --source-session <sid>` filters by issuing session; `ll-issues decisions show <id>` shows full YAML.
- Round-trip safe: editing a YAML entry preserves any already-set `source_session_id`.

## Proposed Solution

### Schema (dataclass + YAML + DB)

**Dataclass** (`scripts/little_loops/decisions.py`):
```python
@dataclass
class DecisionEntry:
    ...
    source_session_id: Optional[str] = None
    source_issue_id: Optional[str] = None  # canonical form; existing 'issue' field remains
```

Add the same to `RuleEntry` and `ExceptionEntry` (or only `DecisionEntry` — decide by adoption cost).

**YAML schema** (backward compatible):
```yaml
- id: TOOLING-001
  type: decision
  timestamp: "2026-04-04T00:00:00Z"
  category: tooling
  rule: "..."
  rationale: "..."
  source_session_id: "abc-1234-uuid"   # NEW; nullable
  source_issue_id: "FEAT-948"           # NEW; nullable
  issue: "P3-FEAT-948-..."               # existing (kept)
  ...
```

**DB mirror** (`scripts/little_loops/session_store.py`):
```sql
CREATE TABLE IF NOT EXISTS decision_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,        -- rule | decision | exception
    category TEXT,
    rule TEXT,
    rationale TEXT,
    source_session_id TEXT,
    source_issue_id TEXT,
    issue TEXT                          -- existing
);
CREATE INDEX IF NOT EXISTS idx_decision_events_source_session ON decision_events(source_session_id);
CREATE INDEX IF NOT EXISTS idx_decision_events_source_issue ON decision_events(source_issue_id);
CREATE INDEX IF NOT EXISTS idx_decision_events_decision_id ON decision_events(decision_id);
```

Add `"decision"` to `_VALID_KINDS` and `"decision": "decision_events"` to `_KIND_TABLE`. The DB row is a search/join mirror; YAML remains the source of truth for editable detail.

### Producer wiring

- Update `/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go` skill capture bridges (per FEAT-948 / ENH-2152) to thread `session_id` (from the active orchestrator context) and the current `issue_id` if any.
- Extend `scripts/little_loops/decisions.py::add_entry()` to accept `source_session_id` and `source_issue_id` kwargs; pass through to YAML serialization and DB row insert.
- Mirror inserts to `decision_events` are best-effort (`contextlib.suppress(Exception)`); YAML remains canonical.

### Read API

Add to `history_reader.py`:
- `find_decisions_for_session(session_id)` returning `list[DecisionRecord]`.
- `find_decisions_for_issue(issue_id)` returning `list[DecisionRecord]`.

### CLI surface

- `ll-session search --fts "<rationale fragment>" --kind decision` returns matching decisions.
- `ll-session recent --kind decision` returns recent decisions.
- `ll-issues decisions show <id>` shows full YAML.
- `ll-issues decisions list --source-session <sid>` filters by issuing session.

### Codebase Research Findings

_Added by `/ll:refine-issue` — file:line anchors from codebase analysis:_

#### Dataclass round-trip pattern (model after `outcome` / `supersedes` / `enforcement`)

- `scripts/little_loops/decisions.py:50-95` `RuleEntry` — uses the `"if self.X is not None: d["X"] = self.X"` omit-when-None pattern in `to_dict()` (lines 80–95) and `data.get("X")` defaulting in `from_dict()` (lines 65–78). Same shape applies to the two new fields.
- `scripts/little_loops/decisions.py:98-148` `DecisionEntry` — uses identical pattern for `outcome: DecisionOutcome | None` (round-trip at lines 114–148) and `scope: str = "issue"`.
- `scripts/little_loops/decisions.py:151-192` `ExceptionEntry` — `issue: str = ""` (non-optional). Add the new fields as `Optional[...] = None` to preserve optionality; do not change the existing `issue` default.

#### Schema migration (model after the v13 / v17 / v18 recipe)

- v13 ENH-2046 `correction_retirements`: `scripts/little_loops/session_store.py:418-430` — minimal `CREATE TABLE` + single-column UNIQUE index for idempotency.
- v17 ENH-2458 `commit_events`: `scripts/little_loops/session_store.py:501-519` — the more elaborate 3-column-index recipe; closest precedent for the new `decision_events` table (which needs indexes on `source_session_id`, `source_issue_id`, and `decision_id`).
- v18 ENH-2459 `test_run_events`: `scripts/little_loops/session_store.py:521-544` — same recipe; the conventional block layout to copy.

#### Write/read helper shape (model after `record_retirement` + `list_retirements`)

- `scripts/little_loops/session_store.py:2735-2759` `record_retirement()` — `INSERT OR REPLACE` on a UNIQUE-indexed column yields idempotency without a separate backfill routine. Use `decision_id` (text) UNIQUE for the new table.
- `scripts/little_loops/session_store.py:2762-2783` `list_retirements()` — tolerant of missing table (returns `[]` on `sqlite3.OperationalError`); same defensive shape for any new `list_decision_events()`.
- `scripts/little_loops/session_store.py:788-813` `record_skill_event()` — full recipe: connect → `_now()` → INSERT → `_index(conn, kind="decision", ...)` → commit → close. The new `record_decision_event()` should call `_index(...)` so FTS picks it up automatically (no `_VALID_KINDS` change needed for `search` to surface decisions).
- `scripts/little_loops/session_store.py:1268-1289` `recent()` — the ONLY read-side use of `_VALID_KINDS`; `search()` (lines 1241–1265) does not consult the whitelist (FTS kind column is `UNINDEXED`). Adding `"decision"` to `_VALID_KINDS` lights up `recent(kind="decision")`; FTS5 search picks it up automatically once `_index` is called.

#### Read API history_reader.py

- `scripts/little_loops/history_reader.py:407-438` `find_session_for_issue_transition()` — exact-match one-row pattern with `try/except sqlite3.Error → return None/[]` graceful degrade. Use this template for `find_decisions_for_session`.
- `scripts/little_loops/history_reader.py:601-637` `sessions_for_issue()` — list-returning template with default `limit=20` and newest-first ordering. Use this for `find_decisions_for_issue`.
- `scripts/little_loops/history_reader.py:252-256` `_row_to_dataclass()` — auto-maps row columns to dataclass fields by intersection. After adding the `DecisionRecord` dataclass, the helper means new SELECT columns Just Work.
- `scripts/little_loops/history_reader.py:235-249` `_connect_readonly()` — opens the DB read-only (`mode=ro` + `PRAGMA query_only = ON`); all reader functions route through it.

#### CLI plumbing

- `scripts/little_loops/cli/issues/decisions.py:79-164` `add_decisions_parser` — `add_p` subparser where `--source-session` and `--source-issue-id` should land alongside `--issue` (line 98). The `--metavar="SESSION_ID"` convention matches `scripts/little_loops/cli/session.py:86`.
- `scripts/little_loops/cli/issues/decisions.py:408-499` `_cmd_add()` — constructs the dataclass per `entry_type`. After `add_entry(...)` at the end, slot `contextlib.suppress(Exception): record_decision_event(...)` (model on `record_issue_snapshot` lines 820–866 which already supports a YAML+DB dual-write).
- `scripts/little_loops/cli/issues/decisions.py:28-77` `list` subparser — `--source-session` slots at the end of the flag list; `_cmd_list()` at lines 334–382 does post-filtering via `getattr(args, "source_session", None)` as a clean integration point.
- `scripts/little_loops/cli/session.py:92-106` and `:115-128` — `--kind` argparse `choices` lists are HARDCODED (10 elements each); must be extended in BOTH places or `--kind decision` is rejected by argparse before reaching `_VALID_KINDS`.

#### Skill capture bridges (CLI invocation sites)

- `skills/decide-issue/SKILL.md:415-428`, `skills/go-no-go/SKILL.md:403-416`, `commands/tradeoff-review-issues.md:294-303` and `:346-355` — all four call `ll-issues decisions add` with the same set of flags; threading `--source-session="$SESSION_ID"` requires setting the env var at the top of each skill (no orchestrator context currently exists in skill markdown bodies).
- `skills/improve-claude-md/SKILL.md:277-282` — already captures session IDs in rationale text (`Recurred ${COUNT}x; sessions: ${SESSION_IDS}`); should be refactored to thread them via `--source-session` instead.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research (locator + analyzer + pattern-finder):_

### Files to Modify

**Dataclass + serialization (`scripts/little_loops/decisions.py`)**
- `RuleEntry` lines 50–95 — add `source_session_id: str | None = None` and `source_issue_id: str | None = None`; update `from_dict()` (65–78) to use `.get()` and `to_dict()` (80–95) to emit only when non-`None` (mirrors existing `issue` / `supersedes` round-trip)
- `DecisionEntry` lines 98–148 — same pattern (mirrors existing `outcome` / `scope`)
- `ExceptionEntry` lines 151–192 — same; note existing `issue: str = ""` (non-optional, default empty string) — keep distinct semantics
- `CouplingEntry` lines 195–250 — also carries `issue: str | None`; flagged for the decision step (not in original issue scope — see `decision_needed`)
- `add_entry()` lines 298–302 — keep signature-compatible; new fields live on the passed dataclass instance

**DB schema + migrations (`scripts/little_loops/session_store.py`)**
- Bump `SCHEMA_VERSION = 18` (line 102) → `19` (the constant is the length of `_MIGRATIONS`, so appending the v19 block is sufficient)
- Append v19 DDL block at the end of `_MIGRATIONS` (between current lines 545 and 546) — model on v17/v18 (lines 501–544) which use `CREATE TABLE IF NOT EXISTS ... ; CREATE INDEX` recipe
- `_VALID_KINDS` line 104 — append `"decision"` (else `recent(kind="decision")` raises)
- `_KIND_TABLE` line 119 — append `"decision": "decision_events"`
- New `record_decision_event()` helper, slot next to `record_retirement()` at lines 2735–2759 (apply the same `INSERT OR REPLACE` recipe for idempotency via a `decision_id UNIQUE` column)
- Optionally a `_backfill_decision_events()` helper to walk existing `.ll/decisions.yaml` on first migration — call from `backfill()` at lines 2441–2494 (add `"decisions": 0` to the `counts` dict)

**Read API (`scripts/little_loops/history_reader.py`)**
- New `DecisionRecord` dataclass slot near lines 75–123 (sibling to `FileEvent` / `IssueEvent` / `SkillEvent` / `CommitEvent` at lines 124–136)
- New `find_decisions_for_session(session_id, *, limit, db)` near lines 407–438 (model on `find_session_for_issue_transition`)
- New `find_decisions_for_issue(issue_id, *, limit, db)` near lines 370–404 (model on `related_issue_events`)
- Both queries go through `_connect_readonly()` (lines 235–249) and reuse `_row_to_dataclass()` (lines 252–256); graceful-degrade on `sqlite3.Error → []`

**CLI surface (`scripts/little_loops/cli/issues/decisions.py`)**
- `add_decisions_parser` `add` subparser lines 79–164 — register `--source-session` and `--source-issue-id` flags (slot next to `--issue` at line 98)
- `_cmd_add()` lines 408–499 — extend per-type entry construction (RuleEntry at ~420, DecisionEntry at ~450, etc.); after `add_entry()`, call `record_decision_event()` best-effort with `contextlib.suppress(Exception)` (model on `record_issue_snapshot` lines 820–866)
- `add_decisions_parser` `list` subparser lines 28–77 — register `--source-session` flag; in `_cmd_list()` lines 334–382 route to `find_decisions_for_session` when set
- `cmd_decisions` dispatch line 265 — add new `show` subcommand (currently missing — referenced in motivation as desired read path; not strictly part of `decision_needed` decision)

**CLI surface (`scripts/little_loops/cli/session.py`)**
- `search_parser` lines 92–106 and `recent_parser` lines 115–128 — append `"decision"` to the **hardcoded** `--kind` argparse `choices` lists (otherwise `--kind decision` is rejected before reaching the `_VALID_KINDS` validator)
- Module docstring line 8–11 — add `decision` to the kind list

**Skill capture bridges (markdown, executed via Claude `Bash` tool)**
- `skills/decide-issue/SKILL.md:415-428` — append `--source-session="$SESSION_ID"` to the `ll-issues decisions add` block
- `skills/go-no-go/SKILL.md:403-416` — same
- `commands/tradeoff-review-issues.md:294-303` (Close/Defer action) — same
- `commands/tradeoff-review-issues.md:346-355` (Update action) — same
- `skills/capture-issue/SKILL.md:308-319` — same (for FEAT/EPIC capture decisions)
- `skills/improve-claude-md/SKILL.md:277-282` — already captures session IDs in rationale text (`Recurred ${COUNT}x; sessions: ${SESSION_IDS}`); pass them via `--source-session`

### Dependent Files (Read-only consumers / callers)

- `scripts/little_loops/decisions_sync.py:sync_to_local_md` (line 15) — reads `RuleEntry` and writes active rules to `.ll/ll.local.md`; round-trip should preserve new fields automatically (yaml.safe_load → from_dict)
- `scripts/little_loops/cli/issues/decisions.py:_cmd_extract_from_completed` (lines 694–883) — calls `add_entry` at line 875; currently drops session context
- `scripts/little_loops/cli/issues/decisions.py:_cmd_promote` (lines 886–930) — converts `DecisionEntry` → `RuleEntry` in place, copying `target.issue` to `rule.issue` at line 920; the same copy step should propagate the two new source_* fields
- `scripts/little_loops/decisions.py:generate_from_completed` (line 382+) — constructs entries without session info today

### Tests to Add or Extend

- `scripts/tests/test_decisions.py` (700+ lines) — new `TestAddEntryWithSourceFields` next to `TestAddEntry` (line 146), `TestLegacyYamlLoadsAsNone` next to `TestLoadDecisions` (line 75)
- `scripts/tests/test_cli_decisions.py` (1500+ lines) — extend `TestDecisionsCLIAdd` (line 342) to cover `--source-session`/`--source-issue-id` plumbing; extend `TestDecisionsCLIList` (line 127) to cover `--source-session` filter
- `scripts/tests/test_session_store.py` (3620+ lines) — new `TestSchemaV19DecisionEvents` (next after `TestSchemaV18` at line 3098); new `TestRecordDecisionEvent` (sibling to `TestRecordIssueSnapshot` at line 2942); test that test classes using literal `18` (e.g. line 1190, 1691, 1806, 1858) are updated to read `SCHEMA_VERSION` symbolically or break loudly
- `scripts/tests/test_history_reader.py` (1378+ lines) — host `TestFindDecisionsForSession` / `TestFindDecisionsForIssue` under existing `TestNewEventReaders`
- `scripts/tests/test_feat1896_skill_bridges.py` (234 lines) — extend `TestDecideIssueDecisionsBridge` / `TestGoNoGoDecisionsBridge` / `TestTradeoffReviewDecisionsBridge` to verify the new flags appear in the `ll-issues decisions add` invocation
- `scripts/tests/test_correction_retirement.py` (94 lines) — direct precedent template for `TestDecisionEvent` (idempotent, optional-fields, survives-reopen, multi-row, table-existence)

### Documentation

- `docs/ARCHITECTURE.md` — schema versions table at line 628 (add v19 row); persistence-layer section
- `docs/guides/DECISIONS_LOG_GUIDE.md` — new fields section; auto-generation section (mention session provenance)
- `docs/reference/CLI.md` — add `--source-session` row in `ll-issues decisions list` flags table at line 1571–1583; add `--kind decision` row at line 2245 and 2253
- `docs/reference/API.md` — `little_loops.decisions` module section (line 46–47); extend `record_*`/`list_*` precedent section (line 7057–7089); add new `find_decisions_for_*` near `find_session_for_issue_transition` (line 6692–6800)

### Configuration

- `config-schema.json` — `decisions` block at lines 531–549 likely needs **no** new fields; new behavior is transparent (always-thread session_id when available, gracefully `None` when not)
- `scripts/little_loops/config/features.py` — `DecisionsConfig` at lines 509–523 — same; no new key needed

### Wiring Pass — Net-New Findings (added by `/ll:wire-issue`)

_3 parallel wiring-research agents (caller-tracer, side-effect-tracer, test-gap-finder) ran on 2026-07-16 against current `main`. Each entry below is anchor-specific with file:line references and `[Agent N]` attribution. Append-only._

**Files to Modify (additional):**

- `scripts/little_loops/session_store.py:60-93` — `__all__` export list; append `"record_decision_event"` (and optionally `"_backfill_decision_events"`) next to `"record_commit_event"` (line 86) for parity with sibling recorders [Agent 1 / Agent 2]
- `scripts/little_loops/session_store.py:3304-3316` — `_EXPORT_TABLE_MAP`; add `_EXPORT_TABLE_MAP["decision"] = ("decision_events", "ts")` for `ll-session export` parity with `commit`/`test_run`/`usage` [Agent 1 / Agent 2]
- `scripts/little_loops/session_store.py:3318` — `_EXPORT_DEFAULT_TABLES`; append `"decision_event"` to the default export set (referenced at lines 3362 and 3371) [Agent 2]
- `scripts/little_loops/cli/issues/decisions.py:216-247` — `extract-from-completed` subparser; **decide**: either add `--source-session` / `--source-issue-id` flags for symmetry (recommended), or document the one-shot CLI limitation (`source_session_id=None` accepted); dispatch lives at line 323 [Agent 2]
- `skills/wire-issue/static-coupling-layer.md:50-58` — CouplingEntry capture-bridge example; add `--source-session="$SESSION_ID"` for Option B parity with the 5 sibling skills (note: this is a documentation example, not a programmatic capture-bridge — no skill body runs it) [Agent 1 / Agent 2]
- `scripts/tests/test_ll_session.py:15-106` — `TestArgumentParsing`; extend with `test_recent_subcommand_decision_accepted` and `test_search_subcommand_decision_accepted` (model on `commit`/`test_run`/`usage` acceptance tests at lines 78-106) [Agent 3]

**Dependent Files (additional):**

- `scripts/little_loops/cli/verify_decisions.py:57` — `_entry_from_dict` consumer; round-trip-safe for the new fields via existing `extra` dict mechanism, no edit required but flagged for completeness [Agent 1]
- `scripts/little_loops/issue_history/parsing.py` — `scan_completed_issues_from_db` / `scan_completed_issues` return `CompletedIssue` records without `session_id`; if `generate_from_completed` (decisions.py:550) is extended to thread `source_session_id`, lookup must go via `find_session_for_issue_transition()` (history_reader.py:432) per completed issue. Otherwise auto-extracted entries remain `source_session_id=None` [Agent 2]
- `scripts/tests/test_wire_issue_static_layer.py:17-22` — `CouplingEntry` / `RuleEntry` fixtures; under Option B (4 dataclasses), `CouplingEntry` gains the new fields and the fixture constructor calls must be reviewed [Agent 1]
- `scripts/tests/test_verify_kinds.py` (full file) — `ll-verify-kinds` gate; `decision_events` MUST land in `_KIND_TABLE` (NOT `_KINDLESS_TABLES`) for the gate to remain green — registering in `_KINDLESS_TABLES` will trip the `TestRun.test_flags_unregistered_table:25` negative-control [Agent 1]

**Tests to Add or Extend (additional):**

- `scripts/tests/test_session_store.py` — new `TestSchemaV21DecisionEvents` class (slot near line 4036 alongside `TestSchemaV16IssueSessionId`, OR near line 4235 alongside `TestRecordCommitEvent`); assert `decision_events` table exists with all 9 columns, `idx_decision_events_source_session` / `_source_issue` / `_decision_id` indexes exist, v20→v21 migration runs idempotently [Agent 3]
- `scripts/tests/test_session_store.py` — new `TestBackfillDecisionEvents` (sibling to `TestBackfillCommitEvents:4286`); walks `.ll/decisions.yaml` + `.ll/decisions.d/*.json`, idempotent on re-run, `counts` dict carries `"decisions"` key [Agent 3]
- `scripts/tests/test_session_store.py:3409-3418` — extend `TestValidKindsCentralization` with `test_recent_decision_kind_does_not_raise` (model on `test_recent_snapshot_kind_does_not_raise:3415`); extends the `set(VALID_KINDS) == set(_KIND_TABLE.keys())` invariant [Agent 3]
- `scripts/tests/test_history_reader.py:1395` — new `TestFindDecisionsForSession` / `TestFindDecisionsForIssue` under existing `TestNewEventReaders` (or standalone); `list[DecisionRecord]` return shape, newest-first ordering, graceful degrade on missing DB / unknown session / unknown issue [Agent 3]
- `scripts/tests/test_cli_decisions.py:127` — extend `TestDecisionsCLIList` with `test_list_filter_source_session` and `test_list_filter_no_match_when_session_unknown` [Agent 3]
- `scripts/tests/test_cli_decisions.py:342` — extend `TestDecisionsCLIAdd` with: `test_add_rule_with_source_session_writes_db_row`, `test_add_decision_with_source_issue_id`, `test_add_rule_without_source_fields_db_row_has_nulls`, `test_add_db_write_failure_does_not_break_yaml` (last one asserts the `contextlib.suppress(Exception)` envelope) [Agent 3]
- `scripts/tests/test_cli_decisions.py` — optional `TestDecisionsCLIShow` for the new `show <id>` subcommand (referenced in motivation; not strictly part of `decision_needed` decision) [Agent 3]
- `scripts/tests/test_feat1896_skill_bridges.py:49, 89, 125, 168` — extend `TestGoNoGoDecisionsBridge`, `TestDecideIssueDecisionsBridge`, `TestTradeoffReviewDecisionsBridge`, `TestCaptureIssueDecisionsBridge` with `--source-session="$SESSION_ID"` literal-string assertions; extend `TestTradeoffReviewDecisionsBridge` to assert the Close/Defer site has the `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]` guard for sibling-skill consistency [Agent 3]

**Tests to Update (incidental breaks — schema bump at 7 sites):**

| File | Line | Current | Bump to |
|------|------|---------|---------|
| `scripts/tests/test_session_store.py` | 1372 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestBackfillIncremental.test_schema_version_is_seven`) |
| `scripts/tests/test_session_store.py` | 1817 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestCliEvents.test_schema_version_is_eight`) |
| `scripts/tests/test_session_store.py` | 1932 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestSchemaV9` upgrade test) |
| `scripts/tests/test_session_store.py` | 1984 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestSchemaV10.test_schema_version_is_ten`) |
| `scripts/tests/test_session_store.py` | 2080 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestSchemaV11.test_schema_version_is_eleven`) |
| `scripts/tests/test_session_store.py` | 3658 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestSchemaV13.test_schema_version_is_thirteen`) |
| `scripts/tests/test_session_store.py` | 3699 | `assert SCHEMA_VERSION == 20` | `== 21` (in `TestSchemaV13` upgrade test) |

_Refactor opportunity (deferred): read `SCHEMA_VERSION` symbolically rather than literal `21` to avoid drift on future bumps — the v17/v18 `commit_events` and `test_run_events` precedent used symbolic reads._

**Documentation (additional):**

- `docs/reference/API.md:4068-4108` — `ll-session` subcommand description; append `decision` to the `--kind` enumeration prose (twice, hardcoded in prose) [Agent 2]
- `docs/reference/API.md:6985` — `search()` description prose; append `decision` to the illustrative `--kind` enumeration [Agent 2]
- `docs/reference/API.md:7284-7290, 7346-7432` — `record_*` precedent section; add parallel `record_decision_event` reference and `decision_events` table row [Agent 2]
- `docs/reference/API.md:46-47` (already in Integration Map) — extend `little_loops.decisions` module section with new fields [Agent 1 / Agent 2]
- `docs/reference/CLI.md:2427, 2435` — **correct anchors** (issue's claimed 2245, 2253 are stale); append `decision` to the `search` / `recent` `--kind` prose tables [Agent 2]
- `docs/reference/CLI.md:1776` — Phase 8 `ll-issues decisions add` example; add `--source-session` example [Agent 1]
- `docs/reference/COMMANDS.md:247, 276, 363` — Decisions log sections; consider adding `--source-session` mention [Agent 1]
- `docs/guides/HISTORY_SESSION_GUIDE.md:32-42, 95-97, 170` — `--kind decision` prose enumerations [Agent 2]
- `docs/guides/DECISIONS_LOG_GUIDE.md:266, 270, 278, 285, 295, 484` — `ll-issues decisions add` examples; add `--source-session` example [Agent 1]
- `docs/ARCHITECTURE.md:769` — persistence-layer prose mentions the YAML log only; add a sentence about the DB mirror once landed [Agent 2]
- `specs/harness-optimize-rubric.md:358` — `ll-issues decisions add` example; consider adding `--source-session` example [Agent 1]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by 3-agent wiring analysis and must be included in the implementation. All anchors verified against current `main` (2026-07-16). Append after Implementation Step 11._

12. Update `scripts/little_loops/session_store.py:60-93` — append `"record_decision_event"` (and optionally `"_backfill_decision_events"`) to `__all__` next to `"record_commit_event"` (line 86).
13. Update `scripts/little_loops/session_store.py:3304-3316` and `:3318` — add `_EXPORT_TABLE_MAP["decision"] = ("decision_events", "ts")` and append `"decision_event"` to `_EXPORT_DEFAULT_TABLES` for `ll-session export` parity.
14. Decide & extend `scripts/little_loops/cli/issues/decisions.py:216-247` — `extract-from-completed` subparser: either add `--source-session` / `--source-issue-id` flags (recommended for symmetry), or document the one-shot CLI limitation (`source_session_id=None` accepted); dispatch lives at line 323.
15. Update `skills/wire-issue/static-coupling-layer.md:50-58` — CouplingEntry capture-bridge example; add `--source-session="$SESSION_ID"` for Option B parity with the 5 sibling skills.
16. Update documentation prose — append `decision` to `--kind` enumerations in:
    - `docs/reference/API.md:4068-4108, 6985, 7284-7290`
    - `docs/reference/CLI.md:2427, 2435` (NOT 2245/2253 — those anchors are stale; see Re-verified Anchors table)
    - `docs/guides/HISTORY_SESSION_GUIDE.md:32-42, 95-97, 170`
    - `docs/guides/DECISIONS_LOG_GUIDE.md:266, 270, 278, 285, 295, 484` (add `--source-session` example)
    - `docs/reference/COMMANDS.md:247, 276, 363` (Decisions log sections)
    - `docs/ARCHITECTURE.md:769` (add DB-mirror prose)
    - `specs/harness-optimize-rubric.md:358` (add `--source-session` example)
17. Tests (additional beyond Integration Map's `### Tests to Add or Extend`):
    - `scripts/tests/test_session_store.py` — new `TestSchemaV21DecisionEvents` (near line 4036 or 4235), new `TestBackfillDecisionEvents` (sibling of `TestBackfillCommitEvents:4286`), extend `TestValidKindsCentralization:3409-3418`
    - `scripts/tests/test_history_reader.py:1395` — new `TestFindDecisionsForSession` / `TestFindDecisionsForIssue`
    - `scripts/tests/test_cli_decisions.py:127` — extend `TestDecisionsCLIList` (`--source-session` filter)
    - `scripts/tests/test_cli_decisions.py:342` — extend `TestDecisionsCLIAdd` (4 new tests covering `--source-session`/`--source-issue-id` plumbing + DB-mirror + suppress-envelope)
    - `scripts/tests/test_cli_decisions.py` — optional `TestDecisionsCLIShow`
    - `scripts/tests/test_ll_session.py:15-106` — extend `TestArgumentParsing` with `test_recent_subcommand_decision_accepted` / `test_search_subcommand_decision_accepted`
    - `scripts/tests/test_feat1896_skill_bridges.py:49, 89, 125, 168` — extend 4 bridge tests with `--source-session="$SESSION_ID"` literal-string assertions; extend `TestTradeoffReviewDecisionsBridge` to assert the `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]` guard
    - `scripts/tests/test_wire_issue_static_layer.py:17-22` — `CouplingEntry` fixture review for Option B
    - `scripts/tests/test_verify_kinds.py` — confirm `decision_events` registration keeps the gate green
18. Bump `assert SCHEMA_VERSION == 20` → `== 21` at 7 sites in `scripts/tests/test_session_store.py`: lines 1372, 1817, 1932, 1984, 2080, 3658, 3699. (Refactor opportunity: read `SCHEMA_VERSION` symbolically rather than literal `21` to avoid drift on future bumps.)

## Acceptance Criteria

- New YAML fields `source_session_id` and `source_issue_id` are backward-compatible (legacy YAML without them loads as `None`).
- A new `decision` entry added via `/ll:decide-issue` carries the current `session_id` and the current `issue_id` from runtime context.
- A `decision_events` row mirrors the YAML entry in `decision_events` table.
- `ll-session recent --kind decision` returns rows; FTS search matches `rule` and `rationale` text.
- `history_reader.find_decisions_for_session(sid)` returns the decisions issued by that session.
- Round-trip safe: loading + saving YAML preserves all three of `issue`, `source_session_id`, `source_issue_id`.
- Tests cover: legacy YAML load, capture-bridge wiring, DB mirror, read API, CLI surface.

## Implementation Steps

1. Extend `DecisionEntry` / `RuleEntry` / `ExceptionEntry` dataclasses (`scripts/little_loops/decisions.py`) with the two new fields.
2. Update `to_yaml` / `from_yaml` to round-trip the new fields.
3. Schema migration for `decision_events`; bump `SCHEMA_VERSION`.
4. Add `"decision"` to `_VALID_KINDS` and `_KIND_TABLE`.
5. Implement `record_decision_event()` and `_backfill_decision_events()` in `session_store.py`.
6. Update three skill capture bridges (`/ll:decide-issue`, `/ll:tradeoff-review-issues`, `/ll:go-no-go`) to thread `session_id` and `issue_id` into `add_entry()`.
7. Mirror to DB at write time (best-effort).
8. Extend `history_reader` with `find_decisions_for_session` and `find_decisions_for_issue`.
9. CLI: ensure `--kind decision` enumerations; add `--source-session` to `ll-issues decisions list`.
10. Tests: `TestDecisionEntryNewFields`, `TestRecordDecisionEvent`, `TestSchemaV15` (or higher), skill-bridge integration test, read-API tests.
11. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md` updates, `docs/guides/DECISIONS_LOG_GUIDE.md` new fields section, `docs/reference/CLI.md` new flag.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete line anchors per step:_

1. **Dataclass extension**: `scripts/little_loops/decisions.py:50-95` (`RuleEntry`), `:98-148` (`DecisionEntry`), `:151-192` (`ExceptionEntry`); also `CouplingEntry:195-250` if the scope decision lands on "all four" — see `decision_needed`.
2. **Serialization round-trip**: `from_dict`/`to_dict` pairs at lines `65-78 / 80-95`, `114-129 / 131-148`, `165-177 / 179-192`, `213-229 / 231-250`. New fields use `.get()` + `omit-when-None` shape (matches existing `outcome` / `supersedes` / `scope`).
3. **Schema migration**: append to `_MIGRATIONS` at end of `scripts/little_loops/session_store.py:545` (line 545 → 546 becomes the new DDL string). Bumping `SCHEMA_VERSION` from `18` (line 102) → `19` happens implicitly (constant is `len(_MIGRATIONS)`). Update literal `18` assertions in `scripts/tests/test_session_store.py:1190`, `:1691`, `:1806`, `:1858` to read `SCHEMA_VERSION` symbolically.
4. **Kind registry**: `scripts/little_loops/session_store.py:104-130` — append `"decision"` to `_VALID_KINDS` and `"decision": "decision_events"` to `_KIND_TABLE`. Also extend `scripts/little_loops/cli/session.py:92-106` AND `:115-128` (both hardcoded `--kind` choices lists) — argparse rejection otherwise.
5. **Write helpers**: `record_decision_event` slots next to `record_retirement` at `scripts/little_loops/session_store.py:2735-2759` (use `INSERT OR REPLACE` with `decision_id UNIQUE` for idempotency). `_backfill_decision_events` walks `.ll/decisions.yaml` on first launch; register in `backfill()` `counts` dict at `scripts/little_loops/session_store.py:2462`.
6. **Skill capture bridges**: extend `skills/decide-issue/SKILL.md:417-428`, `skills/go-no-go/SKILL.md:405-416`, `commands/tradeoff-review-issues.md:296-305` AND `:349-358` (two call sites in tradeoff: Close/Defer action + Update action), and additionally `skills/capture-issue/SKILL.md:310-319` plus `skills/improve-claude-md/SKILL.md:279-284` for full coverage. None of them currently has `LL_SESSION_ID` plumbing — need env-var bridge from orchestrator.
7. **DB mirror at write time**: `contextlib.suppress(Exception)` envelope around `record_decision_event()` in `_cmd_add()` at `scripts/little_loops/cli/issues/decisions.py:408-499` — model on `record_issue_snapshot`'s dual-write approach at `scripts/little_loops/session_store.py:820-866`. YAML remains canonical; DB failure is silent.
8. **Read API**: new `DecisionRecord` dataclass at `scripts/little_loops/history_reader.py:75-123`; `find_decisions_for_session` at `:407-438` (model on `find_session_for_issue_transition`); `find_decisions_for_issue` at `:370-404` (model on `related_issue_events`). All readers route through `_connect_readonly()` at `:235-249` and degrade gracefully.
9. **CLI**: `--source-session` / `--source-issue-id` added at `scripts/little_loops/cli/issues/decisions.py:98` (next to `--issue`). `--source-session` filter for `list` at `:28-77` with post-filter logic in `_cmd_list()` `:334-382`. `ll-session search`/`recent` `--kind decision` choices at `scripts/little_loops/cli/session.py:92-106` AND `:115-128` (both lists). Optional `show` subcommand missing from `cmd_decisions` dispatch (`scripts/little_loops/cli/issues/decisions.py:265`) — referenced in motivation.
10. **Tests**: `scripts/tests/test_decisions.py:146` (`TestAddEntry` slot), `:75` (`TestLoadDecisions` slot); `scripts/tests/test_session_store.py:3098` (next `TestSchemaV19` after `TestSchemaV18`); `scripts/tests/test_history_reader.py` (existing `TestNewEventReaders`); `scripts/tests/test_feat1896_skill_bridges.py:234` (extend bridge tests).
11. **Docs**: `docs/ARCHITECTURE.md:628` (schema versions table); `docs/reference/CLI.md:1571-1583` (decisions list flags table) and `:2245 / 2253` (session --kind); `docs/guides/DECISIONS_LOG_GUIDE.md` (auto-generation section); `docs/reference/API.md:46-47` (decisions module) and `:7057-7089` (retirement precedent) and `:6692-6800` (find_*_for_session/issue proximity).

### Open question surfaced by research

The original issue scope lists only **3** dataclasses (`RuleEntry`, `DecisionEntry`, `ExceptionEntry`). Codebase research indicates a **4th** dataclass — `scripts/little_loops/decisions.py:195-250` `CouplingEntry` — also has `issue: str | None` and follows the same round-trip pattern. Should the new `source_session_id` / `source_issue_id` fields extend to `CouplingEntry` as well? See `decision_needed` flag — this is one of the options the `/ll:decide-issue` step should resolve.

### Codebase Research Findings — Re-verified Anchors (2026-07-07 second pass)

_Added by `/ll:refine-issue` (re-run, gap-analysis mode) — anchor reconciliation against current `main`:_

**Verified anchors (within ≤3-line drift, no action needed):**

| File | Claim | Actual | Status |
|------|-------|--------|--------|
| `scripts/little_loops/decisions.py` | `RuleEntry` 50–95 | 50–95 | ✓ exact |
| `scripts/little_loops/decisions.py` | `DecisionEntry` 98–148 | 98–148 | ✓ exact |
| `scripts/little_loops/decisions.py` | `ExceptionEntry` 151–192 | 151–192 | ✓ exact |
| `scripts/little_loops/decisions.py` | `CouplingEntry` 195–250 | 195–250 | ✓ exact |
| `scripts/little_loops/decisions.py` | `add_entry()` 298–302 | 298–302 | ✓ exact |
| `scripts/little_loops/session_store.py` | `SCHEMA_VERSION = 18` line 102 | 102 | ✓ exact |
| `scripts/little_loops/session_store.py` | `_VALID_KINDS` line 104 | 104 | ✓ exact |
| `scripts/little_loops/session_store.py` | `_KIND_TABLE` line 119 | 119 | ✓ exact |
| `scripts/little_loops/session_store.py` | v15 (ENH-2460) 451–458 | 451–458 | ✓ exact |
| `scripts/little_loops/session_store.py` | v16 (ENH-2462) 460 | 460 | ✓ exact |
| `scripts/little_loops/session_store.py` | v17 (ENH-2458) 501–519 | 501–519 | ✓ exact |
| `scripts/little_loops/session_store.py` | v18 (ENH-2459) 521–544 | 521–544 | ✓ exact |
| `scripts/little_loops/session_store.py` | end of `_MIGRATIONS` at 545 | 545 | ✓ exact |
| `scripts/little_loops/session_store.py` | `record_retirement` 2735–2759 | 2735–2759 | ✓ exact |
| `scripts/little_loops/session_store.py` | `list_retirements` 2762–2783 | 2762–2783 | ✓ exact |
| `scripts/little_loops/history_reader.py` | `related_issue_events` 370–404 | 370–404 | ✓ exact |
| `scripts/little_loops/history_reader.py` | `sessions_for_issue` 601–637 | 601–637 | ✓ exact |
| `scripts/little_loops/cli/issues/decisions.py` | `--issue` arg at 98 | 98 | ✓ exact |
| `scripts/little_loops/cli/issues/decisions.py` | `cmd_decisions` dispatch at 265 | 265 | ✓ exact |
| `scripts/little_loops/cli/session.py` | `--kind` choices 92–106 (search_parser) | 92–105 | ≈ (1-line) |
| `scripts/little_loops/cli/session.py` | `--kind` choices 115–128 (recent_parser) | 115–128 | ✓ exact |
| `scripts/tests/test_decisions.py` | `TestLoadDecisions` at 75 | 75 | ✓ exact |
| `scripts/tests/test_decisions.py` | `TestAddEntry` at 146 | 146 | ✓ exact |
| `scripts/tests/test_session_store.py` | `TestRecordIssueSnapshot` at 2942 | 2942 | ✓ exact |
| `scripts/tests/test_session_store.py` | `TestSchemaV15SkillCompletionColumns` at 3098 | 3098 | ✓ exact (see stale anchor note below) |
| `scripts/tests/test_history_reader.py` | `TestNewEventReaders` at 1378 | 1378 | ✓ exact |
| `skills/decide-issue/SKILL.md` | decisions add at 415–428 | 419 | ✓ exact |
| `skills/go-no-go/SKILL.md` | decisions add at 403–416 | 407 | ✓ exact |
| `skills/capture-issue/SKILL.md` | decisions add at 308–319 | 310 | ✓ exact |
| `skills/improve-claude-md/SKILL.md` | decisions add at 277–282 | 277 | ✓ exact |
| `commands/tradeoff-review-issues.md` | decisions add at 294–303 | 297 | ✓ exact |
| `commands/tradeoff-review-issues.md` | decisions add at 346–355 | 349 | ✓ exact |

**Drift-only anchors (≤8 lines, cosmetic):**

| File | Claim | Actual | Drift |
|------|-------|--------|-------|
| `scripts/little_loops/history_reader.py` | `find_session_for_issue_transition` 407–438 | 407–441 | +3 |
| `scripts/little_loops/history_reader.py` | `_connect_readonly` 235–249 | 235–252 | +3 |
| `scripts/little_loops/history_reader.py` | `_row_to_dataclass` 252–256 | 252–264 | +8 |
| `scripts/little_loops/cli/issues/decisions.py` | `add_decisions_parser` 79–164 | 80–164 | +1 |
| `scripts/little_loops/cli/issues/decisions.py` | `_cmd_add` 408–499 | 408–501 | +2 |
| `scripts/little_loops/cli/issues/decisions.py` | `_cmd_extract_from_completed` 694–883 | 694+ | line range wide |
| `scripts/little_loops/cli/issues/decisions.py` | `_cmd_promote` 886–930 | 886+ | line range wide |
| `scripts/little_loops/session_store.py` | `record_issue_snapshot` 820–866 | 816+ | -4 |

> Implementation note: drift under ~10 lines is acceptable for an anchor sweep; the implementer should use `Read` with `offset`/`limit` to navigate rather than trusting exact ranges.

**Stale anchor note (medium priority — correct before implementing):**

> ⚠ Anchor `scripts/tests/test_session_store.py:3098` no longer resolves to `TestSchemaV18` — line 3098 is currently `TestSchemaV15SkillCompletionColumns` (ENH-2460). The latest dedicated schema-version test is `TestSchemaV16IssueSessionId` at **line 3218** (ENH-2462). Migrations v17 (ENH-2458) and v18 (ENH-2459) do NOT have dedicated `TestSchemaV*` classes — the upgrade path is exercised indirectly via `TestRecordCommitEvent` (line 3416) and `TestRecordTestRunEvent` (line 3549). The new v19 `TestSchemaV19DecisionEvents` class should be appended AFTER `TestSchemaV16IssueSessionId` at line 3218 (or near the end of the file at line 3620+ alongside `TestLoopEventTypes`), not at line 3098.

**Additional `assert SCHEMA_VERSION == 18` sites not listed in Implementation Steps:**

The current Implementation Steps lists four assertion sites (`test_session_store.py:1190`, `:1691`, `:1806`, `:1858`). Re-verification found two MORE sites that must also be updated when bumping to v19:

| File | Line | Snippet |
|------|------|---------|
| `scripts/tests/test_session_store.py` | 1954 | `assert SCHEMA_VERSION == 18` (inside `TestSchemaV12` upgrade test) |
| `scripts/tests/test_session_store.py` | 2842 | `assert SCHEMA_VERSION == 18` (inside `TestSchemaV13` upgrade test) |

Total sites to update: **6**, not 4 (1190, 1691, 1806, 1858, 1954, 2842). Consider using `git grep -n "SCHEMA_VERSION == 18" scripts/tests/test_session_store.py` as the implementer's canonical list — and refactoring to read `SCHEMA_VERSION` symbolically rather than literal `18` to avoid this drift on future bumps (per the v17/v18 commit_events and test_run_events precedent which used symbolic reads).

**Already-existing test infrastructure (reduces scope):**

| Test class | File | Line | Notes |
|------------|------|------|-------|
| `TestCaptureIssueDecisionsBridge` | `scripts/tests/test_feat1896_skill_bridges.py` | 168 | Already covers `skills/capture-issue/SKILL.md:308-319` invocation shape — extend, do not create |
| `TestLoopSuggesterSequencesWiring` | `scripts/tests/test_feat1896_skill_bridges.py` | 214 | Adjacent; not relevant to ENH-2464 |

The implementer should EXTEND `TestCaptureIssueDecisionsBridge` (not create a new test class) to assert the new `--source-session="$SESSION_ID"` flag appears in the `ll-issues decisions add` invocation.

**`ll-session recent --kind decision` validation path:**

For the new `"decision"` kind to surface through `ll-session recent`, the kind must satisfy ALL THREE of:
1. `scripts/little_loops/session_store.py:_VALID_KINDS` (line 104) — append `"decision"` ✓ (issue correctly identifies)
2. `scripts/little_loops/session_store.py:_KIND_TABLE` (line 119) — append `"decision": "decision_events"` ✓
3. `scripts/little_loops/cli/session.py` `choices=[...]` lists at lines 92–106 (search) AND 115–128 (recent) — append `"decision"` ✓

The issue correctly identifies all three locations. Argparse rejects `--kind decision` at the parser layer before the runtime validator runs, so step 3 is mandatory.

**`decision_needed: true` confirmed:**

Frontmatter already carries `decision_needed: true` (line 11). The Proposed Solution section names **two distinct options**:
- **Option A (3 dataclasses)**: extend `RuleEntry` + `DecisionEntry` + `ExceptionEntry` only (matches original issue scope).
- **Option B (4 dataclasses)**: also extend `CouplingEntry` at `scripts/little_loops/decisions.py:195-250` because it also has `issue: str | None` and follows the same round-trip pattern.

> **Selected:** Option B (4 dataclasses) — per the stated recommendation; `CouplingEntry` shares the single `_cmd_add` write path and DB mirror, so provenance fields must extend to it to avoid accidental NULL provenance on coupling rows.

These are the two paths `/ll:decide-issue` should resolve between. The existing "Open question surfaced by research" subsection at the bottom of the Codebase Research Findings already names this choice explicitly.

### Codebase Research Findings — Re-verified Anchors (2026-07-16 third pass)

_Added by `/ll:refine-issue --auto` (gap-analysis, additive-only) — anchor reconciliation against current `main`. All 2026-07-07 line anchors have drifted; use symbolic navigation, not the literal ranges above._

**Current anchors (re-resolved against live `main`):**

| Symbol | 2026-07-07 claim | Current line | Note |
|--------|------------------|--------------|------|
| `session_store.SCHEMA_VERSION` | 102 (`= 18`) | **207 (`= 20`)** | next open slot is **v21**; read the live constant |
| `session_store.VALID_KINDS` | `_VALID_KINDS` @ 104 | **`VALID_KINDS` @ 209** | **renamed** (underscore dropped, now exported tuple) — append `"decision"` here |
| `session_store._KIND_TABLE` | 119 | **223** | append `"decision": "decision_events"` |
| `session_store.record_issue_snapshot` | 820–866 | **1001+** | dual-write model for the DB mirror |
| `session_store.record_retirement` | 2735–2759 | **3248** | `INSERT OR REPLACE` idempotency template |
| `session_store.list_retirements` | 2762–2783 | **3275** | tolerant-read template |
| `decisions.RuleEntry` | 50–95 | **89** | |
| `decisions.DecisionEntry` | 98–148 | **140** | |
| `decisions.ExceptionEntry` | 151–192 | **196** | |
| `decisions.CouplingEntry` | 195–250 | **243** | still exists → Option B (below) still live |
| `decisions.add_entry` | 298–302 | **366** | |
| `history_reader._connect_readonly` | 235–249 | **256** | |
| `history_reader._row_to_dataclass` | 252–256 | **273** | |
| `history_reader.related_issue_events` | 370–404 | **395** | template for `find_decisions_for_issue` |
| `history_reader.find_session_for_issue_transition` | 407–438 | **432** | template for `find_decisions_for_session` |
| `history_reader.sessions_for_issue` | 601–637 | **728** | |
| `cli/issues/decisions.py --issue` | 98 | **99** | slot `--source-session` / `--source-issue-id` alongside |
| `cli/issues/decisions.py cmd_decisions` | 265 | **266** | |
| `cli/issues/decisions.py _cmd_list` | 334–382 | **340** | |
| `cli/issues/decisions.py _cmd_add` | 408–499 | **414** | |

**Scope reduction (was 3 CLI edit sites, now 1) — supersedes Implementation Step 4 / 9 CLI guidance:**

> ⚠ The 2026-07-07 pass claimed `cli/session.py` has **two hardcoded** `--kind`
> `choices=[...]` lists that must both be extended. This is **no longer true.**
> Both `search_parser` (line **103**) and `recent_parser` (line **115**) now use
> `choices=list(VALID_KINDS)` — derived from the single `VALID_KINDS` tuple. So
> `--kind decision` lights up automatically once `"decision"` is appended to
> `session_store.VALID_KINDS` (line 209). **No `cli/session.py` edit is required.**
> The three-place checklist in "`ll-session recent --kind decision` validation
> path" collapses to two places (`VALID_KINDS` + `_KIND_TABLE`).

**`assert SCHEMA_VERSION == N` test sites (now 7, all `== 20`):**

`git grep -n "SCHEMA_VERSION == 20" scripts/tests/test_session_store.py` →
lines **1372, 1817, 1932, 1984, 2080, 3658, 3699**. The earlier "6 sites at
`== 18`" list is fully stale. On bump to v21, update all 7 (or refactor to a
symbolic `SCHEMA_VERSION - 1`-style assertion to end the recurring drift).

**Still-unimplemented (issue remains valid):** `grep -rn decision_events
scripts/little_loops/` returns nothing — the `decision_events` table, mirror
helper, and read API do not yet exist. Core deliverable is untouched.

**`decision_needed: true` — options unchanged:** `CouplingEntry` still present
(now line 243) and still carries `issue`, so Option A (3 dataclasses) vs
Option B (add `CouplingEntry` → 4) remains the open `/ll:decide-issue` choice.

### Codebase Research Findings — Re-verified Anchors (2026-07-16 fourth pass)

_Added by `/ll:refine-issue --auto` (gap-analysis, additive-only) — anchor reconciliation against current `main` plus new findings from `_KINDLESS_TABLES`, `update_entry`, and the runtime `recent()` validator._

**Verified anchor drift since the third pass (within ≤5 lines, no action needed):**

| File | Third-pass claim | Current line | Drift | Status |
|------|------------------|--------------|-------|--------|
| `scripts/little_loops/decisions.py` `RuleEntry` | 88 (claimed 50–95) | 89 | +1 | ✓ stable |
| `scripts/little_loops/decisions.py` `DecisionEntry` | 140 (claimed 98–148) | 140 | exact | ✓ stable |
| `scripts/little_loops/decisions.py` `ExceptionEntry` | 196 (claimed 151–192) | 196 | exact | ✓ stable |
| `scripts/little_loops/decisions.py` `CouplingEntry` | 243 (claimed 195–250) | 243 | exact | ✓ stable |
| `scripts/little_loops/decisions.py` `add_entry` | 366 | 366 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `SCHEMA_VERSION = 20` | 207 | 207 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `VALID_KINDS` (was `_VALID_KINDS`) | 209 | 209 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `_KIND_TABLE` | 223 | 223 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `_index()` | 890 | 890 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `record_issue_snapshot` | 1001+ | 1001 | exact | ✓ stable |
| `scripts/little_loops/session_store.py` `record_commit_event` | (NEW) | 1222 | — | ✓ NEW FINDING |
| `scripts/little_loops/session_store.py` `recent()` validator | (NEW) | 1462 | — | ✓ NEW FINDING |
| `scripts/little_loops/session_store.py` `SQLiteTransport` class | (NEW) | 1506 | — | ✓ NEW FINDING |
| `scripts/little_loops/session_store.py` `record_retirement` | 3248 | 3248 | exact | ✓ stable |
| `scripts/little_loops/decisions.py` `update_entry` | (NEW) | 378 | — | ✓ NEW FINDING |
| `scripts/little_loops/history_reader.py` `_connect_readonly` | 256 | 256 | exact | ✓ stable |
| `scripts/little_loops/history_reader.py` `_row_to_dataclass` | 273 | 273 | exact | ✓ stable |
| `scripts/little_loops/history_reader.py` `related_issue_events` | 395 | 395 | exact | ✓ stable |
| `scripts/little_loops/history_reader.py` `find_session_for_issue_transition` | 432 | 432 | exact | ✓ stable |
| `scripts/little_loops/cli/issues/decisions.py` `_cmd_list` | 340 | 340 | exact | ✓ stable |
| `scripts/little_loops/cli/issues/decisions.py` `_cmd_add` | 414 | 414 | exact | ✓ stable |
| `scripts/little_loops/cli/issues/decisions.py` `_cmd_extract_from_completed` | 694 | 694 | exact | ✓ stable |
| `scripts/little_loops/cli/issues/decisions.py` `_cmd_promote` | 890 | 890 | exact | ✓ stable |
| `scripts/little_loops/cli/session.py` `search_parser` `--kind choices` | 103 | 103 | exact | ✓ stable |
| `scripts/little_loops/cli/session.py` `recent_parser` `--kind choices` | 115 | 115 | exact | ✓ stable |

**New findings the third pass missed (none of these invalidate prior Implementation Steps, but each sharpens the recipe):**

1. **`_KINDLESS_TABLES` registry (lines 244-255)** — `scripts/little_loops/session_store.py` defines a `frozenset({"meta", "search_index", "sessions", "assistant_messages", "summary_nodes", "summary_spans", "raw_events", "correction_retirements"})` for tables that intentionally have no `_KIND_TABLE` entry. The block comment at lines 238-243 explicitly cites `ll-verify-kinds` (ENH-2581) as the gate that enforces "every other CREATE TABLE in `_MIGRATIONS` has a `_KIND_TABLE` entry." **Implication for ENH-2464:** `decision_events` MUST be added to `_KIND_TABLE` (line 223) — it is a queryable kind, not infrastructure. Do NOT add it to `_KINDLESS_TABLES`; doing so will cause `ll-verify-kinds` to fail post-implementation. The closest analog `correction_retirements` is intentionally kindless; `decision_events` is intentionally NOT.

2. **`record_commit_event()` is the closer FTS-indexed precedent (lines 1222-1272)** — replaces `record_retirement` as the template for `record_decision_event`. Reason: `record_commit_event` does the full write-then-FTS-index sequence (`INSERT OR IGNORE` keyed on a UNIQUE `commit_sha`, then `_index(conn, content=..., kind="commit", ref=commit_sha, anchor=..., ts=ts)`, then `conn.commit()`), where `record_retirement` does NOT call `_index` (correction_retirements is a kindless registry table — no FTS row). The new `record_decision_event` should mirror `record_commit_event`'s shape because `decision_events` IS a queryable kind (per finding 1) and the FTS row must be created so `ll-session search --fts "<rationale>"` works.

3. **`_index()` signature (line 890)** — `def _index(conn, *, content, kind, ref, anchor, ts)` — five keyword-only args. The `kind` arg goes into the `search_index.kind` column which is `UNINDEXED` (per FTS5 schema at lines 377-383) — so FTS5 does not index it, but `_KIND_TABLE` lookups still work. For `record_decision_event`, the call shape is `_index(conn, content=f"{decision_id} {rule} {rationale}".strip(), kind="decision", ref=decision_id, anchor=category or "", ts=ts)`.

4. **`recent()` runtime validator (line 1462)** — `if kind not in VALID_KINDS: raise ValueError(f"unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}")`. Confirms the third-pass claim that just appending `"decision"` to `VALID_KINDS` (line 209) is sufficient — `ll-session recent --kind decision` will pass this check, then `_KIND_TABLE["decision"]` resolves to `decision_events`, and `_connect_readonly` reads from there.

5. **`SQLiteTransport.send()` (lines 1506-...; specifically 1567-1607 region)** — the runtime path that emits `issue.*` events. It picks up `event.get("session_id") or event.get("sessionId")` and writes it to the authoritative `issue_events.session_id` column (ENH-2462, v16). For ENH-2464, this is NOT the right hook to add the decision-event write — `SQLiteTransport` only knows about FSM event types, not CLI captures. The correct producer hook is `_cmd_add()` at `scripts/little_loops/cli/issues/decisions.py:414`, called by the `add` subparser dispatch at line 293 (`cmd_decisions`). No new event-bus plumbing is needed; the DB write is a direct `record_decision_event(...)` call wrapped in `contextlib.suppress(Exception)`.

6. **`add_entry()` writes fragment files, NOT a flat-file rewrite (lines 366-375)** — per BUG-2642/BUG-2644. The path is `decisions.d/<uuid4>.json` written via `atomic_write_json`. This matters for `_cmd_extract_from_completed` (which constructs the `RuleEntry` at line 863 with `issue=issue.issue_id`) — the new `source_session_id` / `source_issue_id` fields on that constructed entry must be passed through to `add_entry()` via the dataclass instance, NOT as separate kwargs (current signature takes only `entry, path`). Confirms the third-pass Implementation Step 1 design ("new fields live on the passed dataclass instance").

7. **`update_entry()` (line 378) replaces in-place copy** — the third pass at line 209 (under "Dependent Files") describes `_cmd_promote` as "converts `DecisionEntry` → `RuleEntry` in place, copying `target.issue` to `rule.issue` at line 920." This is stale. Per BUG-2645, `_cmd_promote` now uses `update_entry()` (line 927) which rewrites the single backing fragment. The new `source_session_id` / `source_issue_id` fields are preserved automatically by the round-trip pattern (`from_dict` → mutate → `update_entry` → `to_dict`), so no special copy logic is needed. Implementation Step 6 should be updated accordingly: **no explicit field-copy step in `_cmd_promote`**; just rely on `update_entry` round-trip.

8. **`_EXPORT_TABLE_MAP["commit_event"] = ("commit_events", "ts")` (line 3313 region)** — the export-tooling table map. For `decision_events`, a parallel entry `_EXPORT_TABLE_MAP["decision"] = ("decision_events", "ts")` should be added. This keeps `ll-session export` output consistent across kinds. (Optional; not strictly required for the core deliverable.)

9. **`_backfill_sessions()` precedent (lines 2640-2668)** — `INSERT OR IGNORE` keyed on `session_id` PRIMARY KEY; the closest precedent for `_backfill_decision_events` if backfill is desired. Confirms the third-pass recipe at line 265: `_backfill_decision_events()` walks `.ll/decisions.yaml` on first migration; registered via `backfill()` `counts` dict at `scripts/little_loops/session_store.py:2951-2957`.

**`assert SCHEMA_VERSION == N` test sites — still 7, all `== 20`:**

`grep -n 'SCHEMA_VERSION == 20' scripts/tests/test_session_store.py` → lines **1372, 1817, 1932, 1984, 2080, 3658, 3699** (unchanged from third pass; verified live).

**Skill capture-bridge anchors — third pass also has stale claims, not just 2026-07-07:**

The third-pass table at lines 311-316 of this issue still lists skill-bridge anchors from the 2026-07-07 pass. Current live anchors (verified by the analyzer pass):

| File | Third-pass claim | Current line |
|------|------------------|--------------|
| `skills/decide-issue/SKILL.md` `ll-issues decisions add` block | 415–428 | **310** (block at 308) |
| `skills/go-no-go/SKILL.md` `ll-issues decisions add` block | 403–416 | **421** (block at 419) |
| `skills/capture-issue/SKILL.md` `ll-issues decisions add` block | 308–319 | **297** (block at 295) |
| `skills/improve-claude-md/SKILL.md` `ll-issues decisions add` block | 277–282 | **407** (block at 405) |
| `commands/tradeoff-review-issues.md` Close/Defer site | 294–303 | **277** (block at 276; **unconditional** — no `[ -f .ll/decisions.yaml ]` guard; regression vs. sibling skills) |
| `commands/tradeoff-review-issues.md` Update site | 346–355 | **349** (block at 348; guarded) |

> Implementation note: when extending each call site to thread `--source-session="$SESSION_ID"`, navigate by block (the `\`\`\`bash` fence + the `ll-issues decisions add` line), not by literal line number. The tradeoff-review-issues Close/Defer site is **unconditional** — when adding `--source-session`, also add the `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]` guard for consistency with the sibling skills (the existing `TestTradeoffReviewDecisionsBridge` test at `scripts/tests/test_feat1896_skill_bridges.py:125-166` does not currently assert for the guard, so this is an opportunity to extend that test class in the same pass).

**Test class line drift:**

| Class | Third-pass claim | Current line |
|-------|------------------|--------------|
| `TestLoadDecisions` (`test_decisions.py`) | 75 | 75 ✓ stable |
| `TestSaveDecisions` (`test_decisions.py`) | (NEW) | 151 |
| `TestAddEntry` (`test_decisions.py`) | 146 | **226** (+80) |
| `TestListEntries` (`test_decisions.py`) | (NEW) | 244 |
| `TestResolveActive` (`test_decisions.py`) | (NEW) | 290 |
| `TestSetOutcome` (`test_decisions.py`) | (NEW) | 317 |
| `TestSyncToLocalMd` (`test_decisions.py`) | (NEW) | 386 |
| `TestGenerateFromCompleted` (`test_decisions.py`) | (NEW) | 584 |
| `TestCouplingEntry` (`test_decisions.py`) | (NEW) | 810 |
| `TestDecisionsCLIList` (`test_cli_decisions.py`) | 127 | 127 ✓ stable |
| `TestDecisionsCLIAdd` (`test_cli_decisions.py`) | 342 | 342 ✓ stable |
| `TestDecisionsCLICoupling` (`test_cli_decisions.py`) | (NEW) | 639 |
| `TestDecisionsCLIGenerate` (`test_cli_decisions.py`) | (NEW) | 962 |
| `TestDecisionsCLINoSubcommand` (`test_cli_decisions.py`) | (NEW) | 1013 |
| `TestDecisionsCLIPromote` (`test_cli_decisions.py`) | (NEW) | 1040 |
| `TestDecisionsCLISuggestRules` (`test_cli_decisions.py`) | (NEW) | 1317 |
| `TestExtractFromCompleted` (`test_cli_decisions.py`) | (NEW) | 1553 |
| `TestRecordIssueSnapshot` (`test_session_store.py`) | 2942 | **3758** (+816) |
| `TestRecordCommitEvent` (`test_session_store.py`) | (NEW, NEW PRECEDENT) | 4235 |
| `TestSchemaV20UsageEvents` (`test_session_store.py`) | (NEW, ENH-2461) | 3221 |
| `TestSchemaV16IssueSessionId` (`test_session_store.py`) | 3218 | **4036** (+818) |
| `TestNewEventReaders` (`test_history_reader.py`) | 1378 | **1395** (+17) |
| `TestUsageEventReaders` (`test_history_reader.py`) | (NEW, ENH-2461) | 1548 |
| `TestCaptureIssueDecisionsBridge` (`test_feat1896_skill_bridges.py`) | 168 | 168 ✓ stable |
| `TestTradeoffReviewDecisionsBridge` (`test_feat1896_skill_bridges.py`) | (NEW) | 125 |

The new `TestRecordCommitEvent` at line 4235 is the closest precedent for the new `TestRecordDecisionEvent` (it covers `record` round-trip + FTS indexing + idempotency via UNIQUE column, exactly the shape needed). Use it as the model, not `TestRecordIssueSnapshot`.

**Still-unimplemented (issue remains valid):** `grep -rn decision_events scripts/little_loops/` returns nothing — confirmed live. The `decision_events` table, mirror helper, and read API do not yet exist. Core deliverable is untouched. The `_KIND_TABLE` and `_KINDLESS_TABLES` registries confirm this is a fresh gap (no partial migration has been merged).

**`decision_needed: true` confirmed (frontmatter unchanged):** `CouplingEntry` still present at line 243 and still carries `issue: str | None`. Option A (3 dataclasses) vs Option B (add `CouplingEntry` → 4) remains the open `/ll:decide-issue` choice. No frontmatter write needed (idempotency: value already correct).

> **Recommended**: Option B (4 dataclasses) — extend `source_session_id` /
> `source_issue_id` to `CouplingEntry` as well. It shares the single `_cmd_add`
> write path and DB mirror, so omitting it would leave coupling rows with NULL
> provenance by accident, not design; `wire-issue` is session/issue-scoped so
> the fields are meaningful, and the edit is the same ~4-line round-trip pattern.

**Implementation Step updates derived from new findings:**

- Step 1: confirmed — new fields on the passed dataclass instance, not as `add_entry()` kwargs.
- Step 5: replace the "model on `record_retirement`" recipe with "model on `record_commit_event` (lines 1222-1272)" — `record_decision_event` must call `_index()` for FTS visibility. Add `decision_events` row + index in the same `conn.commit()`.
- Step 5 (continued): register `"decision": "decision_events"` in `_KIND_TABLE` (line 223). Do NOT add to `_KINDLESS_TABLES` (lines 244-255) — the table IS a queryable kind.
- Step 6: the `_cmd_promote` field-copy concern is obsolete (line 920 no longer does in-place copy; `update_entry()` at line 927 round-trips all fields automatically). Drop the explicit copy step.
- Step 6 (continued): when extending `commands/tradeoff-review-issues.md` Close/Defer site (line 277) to add `--source-session`, also add the `[ -f .ll/decisions.yaml ] || [ -d .ll/decisions.d ]` guard for sibling-skill consistency. Extend `TestTradeoffReviewDecisionsBridge` to assert the guard.
- Step 8 (new, optional): add `_EXPORT_TABLE_MAP["decision"] = ("decision_events", "ts")` near line 3313 for export-tooling parity.
- Step 9 (CLI): confirmed — `--kind decision` lights up via `choices=list(VALID_KINDS)` at lines 103 and 115 of `cli/session.py`. No `cli/session.py` edit needed beyond what's already in the third-pass Implementation Step 9.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 6 ("`decisions.yaml` content — Partial"), §3 ranked recommendation #7
- `.issues/features/P3-FEAT-948-rules-and-decisions-log-for-issue-compliance.md` — decision entry schema
- `.issues/enhancements/P3-ENH-2152-extract-decisions-and-rules-from-completed-issues.md` — extraction pipeline that depends on these fields existing
- `scripts/little_loops/decisions.py` — core schema (single source of truth)
- `scripts/little_loops/session_store.py` — `correction_retirements` table (v13, ENH-2046); existing one-way linkage precedent

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; persistence layer section |
| `docs/guides/DECISIONS_LOG_GUIDE.md` | Decisions schema and CLI surface |
| `docs/reference/CLI.md` | New `--source-session` flag |

## Status

**Open** | Created: 2026-07-02 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2465, ENH-2492, ENH-2493, ENH-2494, ENH-2495, ENH-2496,
ENH-2497, ENH-2498, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Session Log
- `/ll:wire-issue` - 2026-07-16T21:05:34 - `49522429-a4f8-47fc-bf61-54cfd3e4c244.jsonl`
- `/ll:decide-issue` - 2026-07-16T18:40:25 - `610f97a0-a009-4f75-8a2c-c24b7b21105f.jsonl`
- `/ll:decide-issue` - 2026-07-16T18:32:14 - `610f97a0-a009-4f75-8a2c-c24b7b21105f.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:40:07 - `ea5d084b-1c5c-442a-875a-55dfbf608ccc.jsonl`
- `/ll:refine-issue` - 2026-07-16T14:12:00 - `0e80f55f-c0ba-48db-8154-89fc3934107b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:47 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T07:13:46 - `545040c5-e94c-459c-892a-62e85637299c.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:14:46 - `a2f712f0-e5cb-481f-b11e-ebec85b401f1.jsonl`
- audit - 2026-07-06 - Fixed Sources ref: `correction_retirements` is a table in `session_store.py` (v13, ENH-2046), not a module. Verified the three capture-bridge skills (`decide-issue`, `tradeoff-review-issues`, `go-no-go`) and `scripts/little_loops/decisions.py` exist.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
