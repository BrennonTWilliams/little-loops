---
id: FEAT-3445
type: FEAT
title: 'Workspace activity reader: cross-repo per-repo and union activity counts over
  a since window'
priority: P2
status: done
verify_verdict: VALID
blocks:
- FEAT-3446
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:04Z'
completed_at: '2026-09-11T02:20:09Z'
confidence_score: 90
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3445: Workspace activity reader: cross-repo per-repo and union activity counts over a since window

## Summary

New reusable cross-repo reader `aggregate_workspace_activity()` that returns per-repo and workspace-total activity counts — loops run, loops completed, issues completed, issues deferred, plus an `instrumented` flag per member — over a `since` window. A **sibling** to `aggregate_history_dbs()` in a new module, not a generalization of it.

## Context

Identified from a design review of a private downstream consumer's requirements. 1.162.0 shipped cross-repo history.db aggregation (FEAT-3399/3409/3410/3418) scoped exclusively to agent-quality regression detection (`ll-history quality --workspace`). A downstream consumer (a private plugin's briefing/portfolio tools) needs a single cross-repo activity/event read; today it shells out per project (`ll-loop list --running --json`, `ll-issues list --json`) and opens each project's `.ll/history.db` with its own sqlite3, once per project, every sync.

## Current Behavior

No cross-repo activity read exists. Workspace aggregation is quality-only: `aggregate_history_dbs()` (workspace_quality.py:196) takes quality-shaped kwargs (`min_sample`, `sensitivity`, `baseline_windows`, `latest_only`) and runs issue analysis per member; its `skipped: list[tuple[str, str]]` string pairs cannot distinguish "no history" (uninstrumented) from "history present but unreadable". A consumer wanting activity counts shells out per project (`ll-loop list --running --json`, `ll-issues list --json`) and opens each project's `.ll/history.db` with its own sqlite3, every sync.

## Expected Behavior

`aggregate_workspace_activity(members, since=...)` returns one structured `RepoActivity` per member — counts, `instrumented` flag, machine-readable status — plus Python-side workspace totals (always present; count fields `None` when no member is `ok`) over `ok` members, using read-only connections and no ATTACH/union machinery. Consumers (a downstream briefing/portfolio plugin, then `ll-history activity` via FEAT-3446) make one call instead of N subprocess spawns + N direct sqlite connections.

## Motivation

- Per-project shelling + per-project sqlite is O(members) subprocess/connection cost every sync, and the consumer re-implements discovery and skip semantics that already exist here.
- `aggregate_history_dbs()` cannot serve this: its kwargs are quality-shaped (`min_sample`, `sensitivity`, `baseline_windows`, `latest_only`) and it runs `find_issues(BRConfig(member.repo_path))` per member, which activity counts don't need.
- Quality's `skipped: list[tuple[str, str]]` string pairs can't distinguish "no history" (uninstrumented) from "history present but unreadable" (schema skew) — the exact distinction a briefing consumer needs.

## Proposed Solution

New module `scripts/little_loops/issue_history/workspace_activity.py`:

```python
aggregate_workspace_activity(
    members: list[WorkspaceMember], *, since: str | None, until: str | None = None
) -> WorkspaceActivityResult
```

**Metric definitions** (single-db read-only SQL per `ok` member; `<window>` = `>= since` when `since` is set AND `<= until` when `until` is set):

| Metric | Source | Predicate |
|---|---|---|
| `loops_run` | `loop_runs` | `started_at <window>` |
| `loops_completed` | `loop_runs` | `ended_at IS NOT NULL AND ended_at <window>` (running loops have NULL `ended_at` — schema.py:577-578 — and must not count) |
| `issues_completed` | `issue_events` | `transition = 'done' AND ts <window>` |
| `issues_deferred` | `issue_events` | `transition = 'deferred' AND ts <window>` |
| `instrumented` | — | member status is `ok` (db present, readable, schema current); NOT a count — absence stays distinguishable from zero |

`since` / `until` accept a full ISO-8601 **timestamp** (datetime granularity, e.g. `2026-08-10T14:00:00Z`) as inclusive (`>=` / `<=`) bounds — the consumer's windows are rolling (now−7d) and not date-aligned, so date-only granularity is insufficient. `None` = unbounded on that side. `until` exists because FEAT-3446 exposes `--until` and emits an `"until"` key in its JSON contract; the reader must accept it rather than have the CLI post-filter.

**Malformed / naive / NULL timestamps (must handle, not ignore):** the counted columns are not uniformly well-formed. `loop_runs.started_at` is nullable (schema.py:577). Backfill writes `issue_events.ts = str(completed_at or captured_at or discovered_date or "")` (writers.py:3165), so `ts` can be the **empty string** or a **date-only** value such as `2026-09-10` (frontmatter `discovered_date`). A naive Python-side `datetime.fromisoformat(x.replace("Z", "+00:00"))` raises `ValueError` on `""` and yields a *naive* datetime on date-only input, and comparing naive with aware raises `TypeError`. FEAT-3446 also accepts date-only `--since`, so the bound itself can be naive. Rules:
- NULL, empty, or unparseable timestamps are **excluded** from windowed counts (either bound set) and **included** in unbounded counts (`since is None and until is None`) — an unbounded count is a row count, a windowed count requires a comparable timestamp.
- Naive timestamps (no offset), on either the row or the bound, are treated as **UTC**.
- The parse is wrapped (`ValueError` → `None` → excluded) and `tzinfo=UTC` is attached explicitly when missing, on both row values and the bounds.

**Transition values (grounded):** the `issue_events` predicates rest on values all write paths actually produce — `_ISSUE_TRANSITION_MAP` (writers.py:2774-2786) maps `issue.completed`/`issue.closed` → `'done'` and `issue.deferred` → `'deferred'`; backfill writes frontmatter `status` verbatim over the six valid statuses (writers.py:3161); `record_issue_event`'s transition is the caller-supplied new status (cli/issues/set_status.py:167-177). No CHECK constraint exists on the column, and `transition = 'deferred'` has no existing reader in `issue_history/` (readers query only `'done'` — agent_quality.py:240, parsing.py:466/:500) — a novel read, but over values with three grounded writers.

**Timestamp caveat (must handle, not ignore):** formats are mixed per writer (confirmed against source):
- `loop_runs.started_at` — `+00:00` with microseconds (`_iso_now()` executor.py:167-169, set at executor.py:621, passed by `_finish()` executor.py:4295-4307).
- `loop_runs.ended_at` — `Z`-suffix, second precision (`_now()` writers.py:128-130, defaulted at writers.py:1780).
- `issue_events.ts` — **writer-dependent, not uniformly `Z`**: `record_issue_event` (cli/issues/set_status.py:167-177 path) writes `Z` (writers.py:447); EventBus `SQLiteTransport.send` rows from `issue_lifecycle` producers write `+00:00`-with-microseconds (`ts = str(event.get("ts") or _now())` writers.py:2820; producers emit `_iso_now()` issue_lifecycle.py:35-37, :1200-1210, :1301-1312); backfill rows carry frontmatter dates verbatim (writers.py:3165).

Because `since` is datetime-granular, **raw lexicographic comparison is not acceptable**: `2026-09-10T22:48:17.151663+00:00` string-compares as *before* `2026-09-10T22:48:17Z` while temporally being *after* it. Existing `ts >= ?` sites (issue_history/evolution.py:115, history_reader/events.py:245) survive only because their `ts` columns happen to be uniformly `Z`-formatted — neither counted column here is. **Implementation (decision, resolved): Python-side fetch-and-filter.** SQL narrows the row set (`WHERE transition = ?`, `WHERE ended_at IS NOT NULL`) and selects only the timestamp column; a single private helper (`_parse_ts(value: str | None) -> datetime | None`) applies the NULL/empty/unparseable/naive rules above via `datetime.fromisoformat(x.replace("Z", "+00:00"))` — the repo's established mixed-format convention (session_store/lifecycle.py:1178/:1338, workflow_sequence/analysis.py:230, fsm/persistence.py:271) — and the window check runs in Python, as `count_loop_runs_in_window` does. Do **not** use SQLite `datetime()` (zero precedent in-repo; would introduce a ≤1s truncation caveat and silently coerce malformed values the rules above want handled explicitly). Unbounded counts (`since is None and until is None`) skip the fetch and use `SELECT COUNT(*)` with the same SQL predicates. Format-dependent misordering (AC 5) is a test-visible failure.

**Counting semantics (decision, resolved):** an issue counts **once per repo it appears in** — workspace totals are the sum of per-repo counts. Do NOT dedupe on bare `issue_id` across repos: every little-loops repo numbers issues from 1, so same-ID issues in different repos are usually *different* logical issues colliding (this is FEAT-3418's own rationale for the `#r{i}` discriminator). If a future consumer truly has mirrored issues needing cross-repo merge, that requires a workspace-canonical id, not bare `issue_id` — explicitly out of scope.

**No ATTACH union (decision, resolved):** under per-(repo, issue) counting every metric is exactly sum-decomposable — run_ids are UUIDs unique to one member db, and each member db already enforces row uniqueness on both counted tables: `loop_runs.run_id UNIQUE` written with `INSERT OR IGNORE` (writers.py:1783-1805) means a resumed-then-completed run contributes exactly one row, and `idx_issue_events_dedup` is, on a migrated v50 db, the **partial unique on `(issue_num, transition) WHERE issue_num IS NOT NULL`** recreated by v36/ENH-2771 (schema.py:896-898, replacing v3's `(issue_id, transition)` form at schema.py:197-199) — type-blind by design; `_warn_on_dedup_collision` (writers.py:304-351) logs when a suppressed insert belonged to a different issue id. The ATTACH/union machinery (`_open_union`, `_union_view_sql`, `_attach_limit`) earns its keep only for SQL-level joins/analytics over combined rows; for counts it adds a `SQLITE_LIMIT_ATTACHED` member ceiling and discriminator bookkeeping for zero semantic gain. Sum in Python instead.

**Member gating:** extract the per-member gate from `aggregate_history_dbs()` (workspace_quality.py:217-252: missing db → open `file:...?mode=ro` → `read_schema_version` check → skip-and-report) into a shared private helper used by both callers. Helper contract: return the opened conn or a skip reason, and own the close (quality's `try/finally` at :251-252 already guarantees close on every skip path); each caller keeps its success-path work (quality: `find_issues` + `analyze_agent_quality` at :241-250; activity: count SQL). Facts to preserve verbatim in the extraction: `_open_member_readonly` (workspace_quality.py:108-120 — `mode=ro` URI, `row_factory=sqlite3.Row`, `PRAGMA query_only=ON`) deliberately bypasses `history_reader/_base.py::_connect_readonly()` (:60-84) because that calls `ensure_db()` and would migrate a stale member before the gate could see it; and corrupt files open lazily, failing only on first query (docstring :109-116), so `read_schema_version` (queries.py:203-216 — maps `sqlite3.OperationalError` → `None` → "schema_version missing") must stay inside the same try as the open. Skew compares against `SCHEMA_VERSION = 50` (schema.py:25), report-and-skip in both directions, nothing raises. Placement note: the repo has no cross-module shared sqlite opener (11 `mode=ro` sites, 8 modules, each private with "modeled on" docstring chains) — this share is intra-subsystem (the workspace aggregation pair), so keep the helper private to the pair (live in `workspace_quality.py`, imported by `workspace_activity.py`, or hoist to a small private module); do not promote it to a public shared opener. The activity reader upgrades the skip record from a reason string to a structured status; reuse quality's exact reason wording for `db_missing` (`f"history.db not found at {db_path}"`, :220) — the sibling suites assert these strings verbatim, and cross-command output stays greppable.

**Known limitations (document, do not solve):**
- FSM signals (stalls, cycles, rate-limits) are webhook-only and not stored in history.db; a history.db read cannot cover them.
- `_ISSUE_TRANSITION_MAP` (writers.py:2774-2781) maps `issue.closed` → `'done'` but `issue.skipped` → `'cancelled'`, and backfill writes `cancelled` verbatim. So live-closed issues count as `issues_completed`, while live-skipped and backfilled-`cancelled` issues count nowhere. This is the concrete reason `issues_closed` is a reserved-`null` key rather than a count.
- No filter on `issue_events.discovered_by`: backfilled rows count the same as live `record_issue_event` / EventBus rows.
- Backfilled `done` issues with no `completed_at` frontmatter get `ts = captured_at` (writers.py:3165 fallback chain), so they count as completed at capture time, not completion time. Live `record_issue_event` rows are unaffected.
- `per_repo` is keyed by `str(member.db_path)` (not `repo_path`): `discover_workspace_members` rejects duplicate `db_path` (workspace.py:202) but not duplicate `repo_path`, so keying by repo would silently collapse two entries sharing a repo with different db paths. `RepoActivity.repo_path` remains the serialized identity field.

## Program Design

### Types

See `## API/Interface` for the full contract: `MemberActivityStatus` (**plain `Enum` with string values, not `(str, Enum)`/`StrEnum`** — zero `(str, Enum)` definitions exist in `scripts/little_loops/` (repo-wide grep, confirmed); the plain-`Enum` convention is established by issue_lifecycle.py's five enums, whose `CompletionResult` docstring at :124-125 argues against `StrEnum` specifically (not the `(str, Enum)` tuple form) — the `(str, Enum)` avoidance rests on the grep, not that docstring; values `ok`/`db_missing`/`schema_skew`/`unreadable` with an inline `#` comment per member), `RepoActivity` (frozen dataclass; counts `None` iff status != OK; `to_dict()`), `WorkspaceActivityResult` (`per_repo` + `totals: WorkspaceTotals | None`, `to_dict()`). Every serializable result container gets a `to_dict() -> dict[str, Any]` that recursively delegates (the `agent_quality.py` quartet + `AggregationResult` pattern), so `WorkspaceActivityResult.to_dict()` builds each array element via `RepoActivity.to_dict()`.

### Signatures

- `aggregate_workspace_activity(members: list[WorkspaceMember], *, since: str | None, until: str | None = None) -> WorkspaceActivityResult` — the only public entry; module sibling to `aggregate_history_dbs()` in `scripts/little_loops/issue_history/workspace_activity.py` (new file).

### Call Path

`discover_workspace_members` (workspace.py:163; manifest → members) -> `aggregate_workspace_activity` [new] -> per member: `_open_member_readonly` + `read_schema_version` (session_store/queries.py:203) gate -> count SQL -> Python-side totals. The member gate itself is extracted from `aggregate_history_dbs` (workspace_quality.py:196) into a shared private helper both callers use.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/workspace_quality.py` — extract the per-member gate (missing db → read-only open → `read_schema_version` check → skip-and-report) into a shared private helper; quality behavior byte-identical (AC 7).
- `scripts/little_loops/issue_history/workspace_activity.py` — NEW module: types, reader, `to_dict()`.
- `scripts/little_loops/issue_history/__init__.py` — three-point public registration, mirroring `aggregate_history_dbs` (docstring "Public exports" list at :57-58, import at :197, `__all__` at :276-277): register `aggregate_workspace_activity` **and** the result types (`WorkspaceActivityResult`, `RepoActivity`, `MemberActivityStatus`) — the sibling re-exports the dataclass alongside the function, not just the function.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workspace.py` — supplies `WorkspaceMember` / `discover_workspace_members()` (read-only dependency, no change).
- `scripts/little_loops/cli/history.py` — future caller via FEAT-3446 (`ll-history activity`); not wired in this issue.

### Similar Patterns
- `aggregate_history_dbs()` (workspace_quality.py:196) — the sibling aggregation whose member gating, read-only opens, and skip-and-report semantics this reader upgrades into structured statuses.
- Raw `ts >= ?` window queries (issue_history/evolution.py:115, history_reader/events.py:245) — get away with string compare only because `ts` is uniformly `Z`-formatted; this module must normalize instead (mixed `+00:00`-micros/`Z` formats).
- `count_loop_runs_in_window` (issue_history/parsing.py:552-599) — the existing both-format-tolerant precedent: fetches `started_at, ended_at` rows and filters in Python via `_parse_iso_datetime` (parsing.py:91-102 — strips trailing `Z`, drops tzinfo; API.md documents its naive-local split from lifecycle's UTC-aware convention). Date-granularity only, so insufficient here, but the fetch-and-filter shape is the fallback implementation.
- `_snapshot_select` (session_store/queries.py:219-245) — SQL-side window precedent: `COALESCE(ended_at, started_at) >= ?` on loop_runs (D13 comment at :234-236 documents the in-flight/crashed-run NULL semantics — it keeps such rows in the window rather than excluding them; this reader's `loops_completed` predicate instead requires `ended_at IS NOT NULL` by design).
- Frozen-value-object convention — `WorkspaceMember` (workspace.py:31-44) freezes with an explicit producer/consumer-boundary rationale citing `host_runner.HostInvocation`; `RepoActivity`/`WorkspaceActivityResult` follow it. Note the split: analysis containers inside `agent_quality.py` (`QualityMetric`/`QualityWindow`/`RetryWindow`/`QualityAnalysis`) stay mutable — frozen is for boundary-crossing values only.

### Tests
- NEW `scripts/tests/test_feat3445_workspace_activity.py` (sibling naming; plain `test_workspace.py` also exists in-tree for FEAT-3409, but the two aggregation siblings use the `test_featNNNN_` form) — mixed timestamp formats, NULL `ended_at`, NULL `started_at`, empty-string and date-only `issue_events.ts` (backfill shapes), naive `since`, `until` alone / `since`+`until` together, missing/skewed/unreadable members, count-SQL `sqlite3.Error` → `unreadable`, zero-ok workspace, unbounded window, `WorkspaceTotals.to_dict()` key order, all-`schema_skew` workspace (totals present, `instrumented: True`, counts `None`), `unreadable` `reason` wording. Follow the sibling suites' conventions:
  - **Fixtures**: build `WorkspaceMember` objects over `tmp_path` dirs; healthy dbs via the real write API (`record_issue_event`, test_feat3410.py:28-43); skewed members via hand-rolled `meta` table (`_skewed_member`, :65-76); garbage via `write_text("not a database")` (:176). Name test dbs `<name>-history.db`, NOT default-shaped `.ll/history.db`, to dodge the autouse `_isolate_history_db` fixture (conftest.py:915-949) that routes default-shaped paths through one shared `LL_HISTORY_DB` env var.
  - **Untouched-source**: sha256 the member db before/after every skip case (test_feat3410.py:79-80/:122-129; test_feat3418.py:396-413).
  - **Source-inspection**: mirror `test_never_uses_migrating_opener` (test_feat3410.py:215-231) — assert `"ensure_db(" not in code`, `"_connect_readonly(" not in code`, `"mode=ro" in code` over the new module's source.
  - **Timestamp control**: the write API's `_now()` controls `ts`, so window tests overwrite it post-write via direct UPDATE (`_stamp_ts`/`_close`/`_reopen`, test_feat3418.py:69-88); for `+00:00`-micros `started_at` rows, set them the way executor does (or UPDATE directly) so both formats are exercised.
  - One `class TestX:` per AC group, docstring citing the AC.
- `scripts/tests/test_feat3410_workspace_quality.py` + `test_feat3418_workspace_quality.py` — must pass unmodified after the gate-helper extraction.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3410_workspace_quality.py:215-231` (`test_never_uses_migrating_opener`) — source-inspects `workspace_quality.py`'s own file text for the literal string `def _open_member_readonly`; if the gate extraction hoists `_open_member_readonly` out of `workspace_quality.py` into a separate module, `text.index(...)` raises `ValueError` (substring not found) and this test breaks. If the helper stays resident in `workspace_quality.py` (one of the two placements this issue's own placement note allows), no change is needed — but the implementer must verify which placement was chosen and update the test's source-inspection target if hoisted. [Agent 1 + Agent 2 finding, confirmed]
- `scripts/tests/test_feat3418_workspace_quality.py:24-32` — imports private ATTACH/union symbols directly (`_UNION_RELATIONS`, `_discriminate_issues`, `_discriminator`, `_open_union`, `aggregate_history_dbs`) from `workspace_quality`. These belong to the union machinery, explicitly out of scope for the gate extraction — do not relocate or rename them; only the per-member gate helper moves. [Agent 1 + Agent 2 finding, confirmed]

### Documentation
- `docs/reference/API.md` — issue_history submodules do **not** get their own `##` sections: fold into the existing `## little_loops.issue_history` section as function-table rows (the `aggregate_history_dbs` row at API.md:2389 is the pattern), with `WorkspaceActivityResult`/`RepoActivity` appearing via formatter/result rows as `AggregationResult` does (:2402). Note the gate extraction under `workspace_quality`'s row.
- `docs/ARCHITECTURE.md` — one sentence appended to the "History DB: Producer→Consumer Flow" section's workspace-manifest prose (line ~714), not a new section; the module tree keeps `issue_history/` collapsed.

### Configuration
- N/A — reads only `WorkspaceMember` inputs + per-member history.db; no new config keys.

## Implementation Steps

1. Extract the member gate from `workspace_quality.aggregate_history_dbs()` into a shared private helper **kept resident in `workspace_quality.py`** (decision, resolved — no test change needed; see Wiring Phase); re-run the quality test suite unchanged.
2. Create `workspace_activity.py` with the enums/dataclasses above. Module docstring follows the sibling convention: one-line purpose + FEAT number first (`"""Cross-repo activity counts over a declared workspace (FEAT-3445)."""`), narrate the mechanism with "modeled on" cross-references and explicit anti-references (never `_connect_readonly()` — it migrates), restate resolved decisions from this issue verbatim, close with accepted limitations (FSM-signals, cancelled-vs-done, backfill `ts` fallback).
3. Implement per-member count SQL + Python-side totals.
4. Unit tests: mixed timestamp formats, NULL `ended_at`, missing/skewed/unreadable members, zero-ok workspace, unbounded `since`.
5. Register public exports in `issue_history/__init__.py` (docstring, import, `__all__`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- If the shared gate helper is hoisted into a new module (not kept resident in `workspace_quality.py`), update `test_never_uses_migrating_opener` (`test_feat3410_workspace_quality.py:215-231`) to source-inspect the new module instead; if kept in `workspace_quality.py`, no test change is needed.
- Do not relocate or rename `_UNION_RELATIONS`, `_discriminate_issues`, `_discriminator`, or `_open_union` in `workspace_quality.py` — `test_feat3418_workspace_quality.py:24-32` imports them directly by dotted path.

## Impact

- New public module (goes in `docs/reference/API.md`); no changes to existing behavior beyond the gate-helper extraction in `workspace_quality.py`.
- Unblocks the CLI surface issue (`ll-history activity`) and the downstream consumer.

## API/Interface

```python
class MemberActivityStatus(Enum):                # plain Enum, string values — repo convention (issue_lifecycle.py:124)
    OK = "ok"                      # counts present (possibly zero)
    DB_MISSING = "db_missing"      # no history.db -> instrumented: False
    SCHEMA_SKEW = "schema_skew"    # version mismatch -> instrumented: True, counts unreadable
    UNREADABLE = "unreadable"      # sqlite3.Error on open, version read, OR the count SQL -> instrumented: True
                                   # (the count phase sits inside the same try as the gate; reason populated)
                                   # reason wording: open/version-read failures reuse quality's exact
                                   # f"could not read read-only: {exc}"; count-phase failures use
                                   # f"count query failed: {exc}" so tests can distinguish the two phases

@dataclass(frozen=True)            # frozen: crosses the producer/consumer boundary (WorkspaceMember convention)
class RepoActivity:
    repo_path: str                               # absolute, resolved
    role: str
    label: str                                   # _label(member), computed at construction
    status: MemberActivityStatus
    instrumented: bool
    reason: str | None = None                    # serialized as `error`
    loops_run: int | None = None                 # None iff status != OK (not 0)
    loops_completed: int | None = None
    issues_completed: int | None = None
    issues_deferred: int | None = None
    issues_closed: None = None                   # reserved: always None, see below
    def to_dict(self) -> dict[str, Any]: ...     # canonical member object (below)

@dataclass(frozen=True)
class WorkspaceTotals:
    members: int                                 # len(per_repo)
    instrumented_members: int                    # count of members with instrumented == True
    instrumented: bool                           # OR over members' instrumented
    ok_members: int                              # count of status == OK members
    loops_run: int | None                        # each: sum over status == OK members only;
    loops_completed: int | None                  #   None (never 0) iff ok_members == 0
    issues_completed: int | None
    issues_deferred: int | None
    issues_closed: None = None                   # reserved: always None (same rule as RepoActivity)
    def to_dict(self) -> dict[str, Any]: ...     # keys in the declaration order above (stable order: FEAT-3446 AC 1)

@dataclass(frozen=True)
class WorkspaceActivityResult:
    since: str | None
    until: str | None
    per_repo: dict[str, RepoActivity]            # keyed by str(member.db_path) — see Known limitations
    totals: WorkspaceTotals                      # always present (decision, resolved — see below)
    def to_dict(self) -> dict[str, Any]: ...     # {"since", "until", "per_repo": [RepoActivity.to_dict()...], "totals"}
```

`WorkspaceTotals` sums each count over `ok` members only; schema-skewed/unreadable members are excluded from the count sums (matching quality's gate) but still count toward `members` / `instrumented_members`. **`totals` is always present (decision, resolved):** a workspace whose members are all `schema_skew` is instrumented yet has zero `ok` members, so `members` / `instrumented_members` / `instrumented` / `ok_members` must survive; only the four count fields become `None` when `ok_members == 0`. This also gives FEAT-3446 a stable JSON shape.

**Canonical serialization rules (consumer contract):**
- Each serialized member object carries `repo_path`, `role`, `label` (`"{Path(repo_path).name} ({role})"`, display only — `RepoActivity.repo_path` is a `str`; compute it once at construction via quality's `_label(member)` and store it, don't recompute in `to_dict()`), `status`, `ok` (`status == "ok"`), `error` (`reason`), and `instrumented`. `ok`/`error` are the canonical consumer-facing fields; `status` rides along as the finer-grained discriminator.
- Metrics unavailable from history.db serialize as `null`, **never `0`**. Two named cases: `issues_closed` is emitted as an explicit always-`null` reserved key (history.db collapses issue closed→completed into transition `'done'`, so the split cannot be made today — null keeps "unavailable" distinguishable from "measured zero" if the schema ever records it distinctly), and the three FSM signals (stalls / cycles / rate-limits — webhook-only) are deliberately absent from the output; consumers must model them as unavailable, not zero.

## Use Case

A downstream briefing/portfolio sync calls `aggregate_workspace_activity(members, since=last_sync)` once per sync instead of N subprocess spawns + N direct sqlite connections, and branches on `instrumented`/status to report "not instrumented" vs "history present but unreadable" per repo — the distinction the current string-pair skip record cannot express.

## Acceptance Criteria

1. `aggregate_workspace_activity(members, since=...)` returns one `RepoActivity` per member carrying `repo_path`/`role`; non-ok members carry `None` counts, never `0`, plus `ok: False` and a populated `error`.
2. `instrumented` is False only for `db_missing`; True for `schema_skew`/`unreadable` (both report `reason`). A `sqlite3.Error` raised by the count SQL after the gate passes maps to `unreadable`, not an exception.
3. `totals` is always present; its count fields equal the sum of `ok` members' counts and are `None` (never `0`) when `ok_members == 0`; `members`/`instrumented_members`/`instrumented`/`ok_members` are populated regardless. No exception.
4. Running loops (NULL `ended_at`) never count as completed; loops started before `since` but ended after do. `until` is an inclusive upper bound applied to the same column as `since` for each metric; `since`/`until` are independently optional.
5. Timestamp comparison is format-safe at datetime granularity across `+00:00`-micros and `Z` forms (Python-side `_parse_ts` fetch-and-filter, per Proposed Solution); raw lexicographic comparison of unnormalized strings is a test-visible failure. NULL, empty-string, and date-only timestamps (all real backfill/schema outputs) never raise: they are excluded from windowed counts and included in unbounded counts; naive values on either side are treated as UTC.
6. Member databases are opened read-only (`file:...?mode=ro`, `PRAGMA query_only`), never migrated — same contract as workspace_quality.
7. The shared member-gate helper is used by both `aggregate_history_dbs()` and the new reader; quality's behavior is byte-identical after extraction (existing tests pass unmodified).
8. The module docstring documents the FSM-signals limitation verbatim.
9. Serialized output follows the canonical rules above: member objects carry `repo_path`/`role`/`ok`/`error`/`instrumented`; `issues_closed` is always `null`; unavailable metrics are `null` or absent, never `0`; `totals.instrumented` is the OR over members.
10. `aggregate_workspace_activity`, `WorkspaceActivityResult`, `RepoActivity`, and `MemberActivityStatus` are all registered in `issue_history/__init__.py` (docstring "Public exports" list, import, and `__all__`) — mirroring `aggregate_history_dbs`'s three-point registration, not just the function.
11. `docs/reference/API.md` gains function-table rows for the new module (per the Documentation section) and `docs/ARCHITECTURE.md`'s "History DB: Producer→Consumer Flow" section gets the one-sentence addition describing the workspace-manifest read.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design; where the workspace aggregation layer sits |
| architecture | docs/reference/API.md | Python module reference — new public module + `workspace_quality` gate extraction land here |

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (citation corrections below applied
in the same pass — this section is a record of what was wrong and fixed for
those, not an outstanding action item; one item is not fixed, see Remaining)

Checked 32+ file:line citations against HEAD. Corrected:
- Motivation section's `record_issue_event` transition citation named
  `set_status.py:167-170`; the file actually lives at
  `scripts/little_loops/cli/issues/set_status.py` (line range :167-177 there
  matches the claimed content). Fixed (both occurrences).
- Program Design's `MemberActivityStatus` rationale cited
  `issue_lifecycle.py:124-125` as precedent against both `(str, Enum)` and
  `StrEnum`; that docstring (`CompletionResult`) only argues against
  `StrEnum` specifically. The broader "zero `(str, Enum)` definitions exist"
  claim is independently true (repo-wide grep, confirmed) but wasn't resting
  on the right citation. Reworded to attribute each claim to its actual
  source.
- Similar Patterns' `_snapshot_select` D13-comment citation said `:236-237`;
  the comment is at `:234-236` (session_store/queries.py). Fixed.
- Two `evolution.py:115` citations (Proposed Solution and Similar Patterns)
  omitted the module's actual parent package — the file is
  `scripts/little_loops/issue_history/evolution.py`, not
  `scripts/little_loops/evolution.py`. Fixed (both occurrences).

Also added a `blocks: [FEAT-3446]` frontmatter backlink — FEAT-3446 declares
`blocked_by: [FEAT-3445]` but this file had no reverse reference
(MISSING_BACKLINK).

Everything else checked clean: the SQL/timestamp-format claims (mixed
`+00:00`-micros vs `Z` across `loop_runs`/`issue_events` writers), the
dedup/uniqueness claims (`loop_runs.run_id UNIQUE`, `idx_issue_events_dedup`
partial-unique scope), the member-gate extraction source
(`workspace_quality.py:108-120`/`:217-252`), and the `WorkspaceMember`/
`discover_workspace_members` citations in `workspace.py` all matched current
code.

Decisions log: no active required rules found (`ll-issues decisions list
--type rule --enforcement required --active-only` returned empty).

Evidence-quote check (`ll-verify-evidence --json`): clean, 0 findings.

Proposal-vs-code consequence check (ENH-3250): no exception-handler or
test-fixture-invalidation defects found — the `test_never_uses_migrating_opener`
hoist risk is already correctly self-flagged in the Wiring Phase, including the
right failure mode (`ValueError` from a literal `text.index()` source-inspection
miss if the gate helper is hoisted out of `workspace_quality.py`).

~~Remaining: two Integration Map points had no corresponding Acceptance
Criterion~~ — closed in a follow-up pass (2026-09-11): AC10 (`__init__.py`
three-point export registration) and AC11 (API.md/ARCHITECTURE.md doc
updates) added. All findings from this issue's verification are now
resolved; no outstanding action items remain.

## Resolution

Implemented as specified:

- Extracted the shared per-member gate (`_gate_member()`) from
  `aggregate_history_dbs()` into `workspace_quality.py` (kept resident there,
  per the resolved placement decision — `test_never_uses_migrating_opener`
  needed no change). Returns `(conn, None, None)` on success or
  `(None, reason, kind)` on skip, `kind` matching
  `MemberActivityStatus`'s values without a cross-module enum dependency.
  `aggregate_history_dbs()` now calls the helper; behavior is byte-identical
  (`test_feat3410_workspace_quality.py` / `test_feat3418_workspace_quality.py`
  pass unmodified).
- New `scripts/little_loops/issue_history/workspace_activity.py`:
  `MemberActivityStatus`, `RepoActivity`, `WorkspaceTotals`,
  `WorkspaceActivityResult`, and `aggregate_workspace_activity()`. Python-side
  fetch-and-filter timestamp comparison (`_parse_ts`/`_in_window`) per the
  resolved decision — no SQLite `datetime()`, no ATTACH/union. Unbounded
  windows use `SELECT COUNT(*)`; bounded windows fetch and filter in Python.
- Registered `aggregate_workspace_activity`, `WorkspaceActivityResult`,
  `RepoActivity`, `MemberActivityStatus` in `issue_history/__init__.py`
  (docstring, import, `__all__` — three-point registration).
- `docs/reference/API.md` gained a function-table row for
  `aggregate_workspace_activity`; `docs/ARCHITECTURE.md`'s "History DB:
  Producer→Consumer Flow" section gained the one-sentence sibling mention.
- New `scripts/tests/test_feat3445_workspace_activity.py` (50 tests): running
  vs. completed loop counting, since/until independence and inclusivity,
  mixed-timestamp-format safety, NULL/empty/date-only timestamp handling,
  naive-bound-as-UTC, all four `MemberActivityStatus` branches (including a
  count-phase `sqlite3.Error` -> `unreadable`), totals (including the
  all-non-ok zero-ok-members case and the empty-workspace case), canonical
  serialization (`ok`/`error`/`issues_closed` always null), and a
  source-inspection proving no migrating opener.

Verification: `python -m pytest scripts/tests/` — 23,952 passed, 43 skipped,
5 failed. All 5 failures are pre-existing and unrelated to this change,
confirmed by isolated re-run: `test_feat3323_sse_bridge.py`'s fan-in test is a
socket-timing flake (passes alone); the other four
(`test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` x2,
`test_issue_parser.py::TestBug3295ContainmentCorpusDifferential`,
`test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`)
are repo-wide `.issues/` corpus / `mcp_server/tools.py` drift gates untouched
by this issue's files. `ruff check scripts/` and `python -m mypy` on the
touched modules are both clean.

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-11T02:19:50 - `413fd87f-60ac-4371-a3de-9c2fb3fec6c9.jsonl`
- `/ll:confidence-check` - 2026-09-11T01:55:52 - `c8678e03-b9b5-468d-a83f-076102f8e125.jsonl`
- `/ll:verify-issues` - 2026-09-11T01:52:45 - `e6b2283d-2f88-428b-aef9-912b5592580e.jsonl`
- `/ll:confidence-check` - 2026-09-11T01:30:47 - `9be5076d-2998-4a46-a8a5-490fcdb1ba9a.jsonl`
- `/ll:verify-issues` - 2026-09-11T01:26:20 - `445bd444-f9c5-4d60-bf47-1c94e4dd13b9.jsonl`
- `/ll:confidence-check` - 2026-09-11T01:14:23 - `226e3334-05f8-455d-a6d0-352e3badc359.jsonl`
- `/ll:reconcile-issue` - 2026-09-11T01:00:10 - `96fc360a-b5db-40dd-bb89-1981614713ee.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:53:16 - `74560d07-2a1c-4247-b7b2-e91055dab494.jsonl`
- `/ll:verify-issues` - 2026-09-11T00:47:45 - `e2289526-f05e-4914-b7bb-dee1a954062a.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:38:37 - `2e842a0e-c20b-4811-ac47-806369f06e2c.jsonl`
- `/ll:format-issue` - 2026-09-10T23:59:04 - `977177b4-c924-4eb0-8524-717b55725bed.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:53:43 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
