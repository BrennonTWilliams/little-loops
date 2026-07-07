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
decision_needed: true
labels:
  - enhancement
  - decisions
  - history-db
  - captured
---

# ENH-2464: Backlink .ll/decisions.yaml entries to issuing session_id and issue_id

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

## Session Log
- `/ll:refine-issue` - 2026-07-07T00:14:46 - `a2f712f0-e5cb-481f-b11e-ebec85b401f1.jsonl`
- audit - 2026-07-06 - Fixed Sources ref: `correction_retirements` is a table in `session_store.py` (v13, ENH-2046), not a module. Verified the three capture-bridge skills (`decide-issue`, `tradeoff-review-issues`, `go-no-go`) and `scripts/little_loops/decisions.py` exist.
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
