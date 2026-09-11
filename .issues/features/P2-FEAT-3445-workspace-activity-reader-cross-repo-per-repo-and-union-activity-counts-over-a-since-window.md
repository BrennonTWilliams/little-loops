---
id: FEAT-3445
type: FEAT
title: 'Workspace activity reader: cross-repo per-repo and union activity counts over
  a since window'
priority: P2
status: open
blocks:
- FEAT-3446
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T23:53:04Z'
---

# FEAT-3445: Workspace activity reader: cross-repo per-repo and union activity counts over a since window

## Summary

New reusable cross-repo reader `aggregate_workspace_activity()` that returns per-repo and workspace-total activity counts — loops run, loops completed, issues completed, issues deferred, plus an `instrumented` flag per member — over a `since` window. A **sibling** to `aggregate_history_dbs()` in a new module, not a generalization of it.

## Context

Identified from a design review of a private downstream consumer's requirements. 1.162.0 shipped cross-repo history.db aggregation (FEAT-3399/3409/3410/3418) scoped exclusively to agent-quality regression detection (`ll-history quality --workspace`). A downstream consumer (a private plugin's briefing/portfolio tools) needs a single cross-repo activity/event read; today it shells out per project (`ll-loop list --running --json`, `ll-issues list --json`) and opens each project's `.ll/history.db` with its own sqlite3, once per project, every sync.

## Current Behavior

No cross-repo activity read exists. Workspace aggregation is quality-only: `aggregate_history_dbs()` (workspace_quality.py:196) takes quality-shaped kwargs (`min_sample`, `sensitivity`, `baseline_windows`, `latest_only`) and runs issue analysis per member; its `skipped: list[tuple[str, str]]` string pairs cannot distinguish "no history" (uninstrumented) from "history present but unreadable". A consumer wanting activity counts shells out per project (`ll-loop list --running --json`, `ll-issues list --json`) and opens each project's `.ll/history.db` with its own sqlite3, every sync.

## Expected Behavior

`aggregate_workspace_activity(members, since=...)` returns one structured `RepoActivity` per member — counts, `instrumented` flag, machine-readable status — plus Python-side workspace totals over `ok` members, using read-only connections and no ATTACH/union machinery. Consumers (a downstream briefing/portfolio plugin, then `ll-history activity` via FEAT-3446) make one call instead of N subprocess spawns + N direct sqlite connections.

## Motivation

- Per-project shelling + per-project sqlite is O(members) subprocess/connection cost every sync, and the consumer re-implements discovery and skip semantics that already exist here.
- `aggregate_history_dbs()` cannot serve this: its kwargs are quality-shaped (`min_sample`, `sensitivity`, `baseline_windows`, `latest_only`) and it runs `find_issues(BRConfig(member.repo_path))` per member, which activity counts don't need.
- Quality's `skipped: list[tuple[str, str]]` string pairs can't distinguish "no history" (uninstrumented) from "history present but unreadable" (schema skew) — the exact distinction a briefing consumer needs.

## Proposed Solution

New module `scripts/little_loops/issue_history/workspace_activity.py`:

```python
aggregate_workspace_activity(members: list[WorkspaceMember], *, since: str | None) -> WorkspaceActivityResult
```

**Metric definitions** (single-db read-only SQL per `ok` member):

| Metric | Source | Predicate |
|---|---|---|
| `loops_run` | `loop_runs` | `started_at >= since` |
| `loops_completed` | `loop_runs` | `ended_at IS NOT NULL AND ended_at >= since` (running loops have NULL `ended_at` — schema.py:577-578 — and must not count) |
| `issues_completed` | `issue_events` | `transition = 'done' AND ts >= since` |
| `issues_deferred` | `issue_events` | `transition = 'deferred' AND ts >= since` |
| `instrumented` | — | member status is `ok` (db present, readable, schema current); NOT a count — absence stays distinguishable from zero |

`since` accepts a full ISO-8601 **timestamp** (datetime granularity, e.g. `2026-08-10T14:00:00Z`) as an inclusive (`>=`) lower bound — the consumer's windows are rolling (now−7d) and not date-aligned, so date-only granularity is insufficient. `since is None` = unbounded (all history).

**Transition values (grounded):** the `issue_events` predicates rest on values all write paths actually produce — `_ISSUE_TRANSITION_MAP` (writers.py:2774-2786) maps `issue.completed`/`issue.closed` → `'done'` and `issue.deferred` → `'deferred'`; backfill writes frontmatter `status` verbatim over the six valid statuses (writers.py:3161); `record_issue_event`'s transition is the caller-supplied new status (cli/issues/set_status.py:167-177). No CHECK constraint exists on the column, and `transition = 'deferred'` has no existing reader in `issue_history/` (readers query only `'done'` — agent_quality.py:240, parsing.py:466/:500) — a novel read, but over values with three grounded writers.

**Timestamp caveat (must handle, not ignore):** formats are mixed per writer (confirmed against source):
- `loop_runs.started_at` — `+00:00` with microseconds (`_iso_now()` executor.py:167-169, set at executor.py:621, passed by `_finish()` executor.py:4295-4307).
- `loop_runs.ended_at` — `Z`-suffix, second precision (`_now()` writers.py:128-130, defaulted at writers.py:1780).
- `issue_events.ts` — **writer-dependent, not uniformly `Z`**: `record_issue_event` (cli/issues/set_status.py:167-177 path) writes `Z` (writers.py:447); EventBus `SQLiteTransport.send` rows from `issue_lifecycle` producers write `+00:00`-with-microseconds (`ts = str(event.get("ts") or _now())` writers.py:2820; producers emit `_iso_now()` issue_lifecycle.py:35-37, :1200-1210, :1301-1312); backfill rows carry frontmatter dates verbatim (writers.py:3165).

Because `since` is datetime-granular, **raw lexicographic comparison is not acceptable**: `2026-09-10T22:48:17.151663+00:00` string-compares as *before* `2026-09-10T22:48:17Z` while temporally being *after* it. Existing `ts >= ?` sites (issue_history/evolution.py:115, history_reader/events.py:245) survive only because their `ts` columns happen to be uniformly `Z`-formatted — neither counted column here is. Two acceptable implementations (AC 5's "or equivalent" is the binding contract): SQLite `datetime()` on both sides (normalizes `Z` and `+00:00`, truncates sub-second precision → ≤1s boundary tolerance — accepted and documented), **or** the repo's established mixed-format convention, Python-side `datetime.fromisoformat(x.replace("Z", "+00:00"))` (session_store/lifecycle.py:1178/:1338, workflow_sequence/analysis.py:230, fsm/persistence.py:271), fetching rows and filtering in Python as `count_loop_runs_in_window` does. Note: SQL-side `datetime()` has **zero precedent in-repo** (all `datetime(` hits are Python) — Python-side is the convention; format-dependent misordering is a failure under either.

**Counting semantics (decision, resolved):** an issue counts **once per repo it appears in** — workspace totals are the sum of per-repo counts. Do NOT dedupe on bare `issue_id` across repos: every little-loops repo numbers issues from 1, so same-ID issues in different repos are usually *different* logical issues colliding (this is FEAT-3418's own rationale for the `#r{i}` discriminator). If a future consumer truly has mirrored issues needing cross-repo merge, that requires a workspace-canonical id, not bare `issue_id` — explicitly out of scope.

**No ATTACH union (decision, resolved):** under per-(repo, issue) counting every metric is exactly sum-decomposable — run_ids are UUIDs unique to one member db, and each member db already enforces row uniqueness on both counted tables: `loop_runs.run_id UNIQUE` written with `INSERT OR IGNORE` (writers.py:1783-1805) means a resumed-then-completed run contributes exactly one row, and `idx_issue_events_dedup` is, on a migrated v50 db, the **partial unique on `(issue_num, transition) WHERE issue_num IS NOT NULL`** recreated by v36/ENH-2771 (schema.py:896-898, replacing v3's `(issue_id, transition)` form at schema.py:197-199) — type-blind by design; `_warn_on_dedup_collision` (writers.py:304-351) logs when a suppressed insert belonged to a different issue id. The ATTACH/union machinery (`_open_union`, `_union_view_sql`, `_attach_limit`) earns its keep only for SQL-level joins/analytics over combined rows; for counts it adds a `SQLITE_LIMIT_ATTACHED` member ceiling and discriminator bookkeeping for zero semantic gain. Sum in Python instead.

**Member gating:** extract the per-member gate from `aggregate_history_dbs()` (workspace_quality.py:217-252: missing db → open `file:...?mode=ro` → `read_schema_version` check → skip-and-report) into a shared private helper used by both callers. Helper contract: return the opened conn or a skip reason, and own the close (quality's `try/finally` at :251-252 already guarantees close on every skip path); each caller keeps its success-path work (quality: `find_issues` + `analyze_agent_quality` at :241-250; activity: count SQL). Facts to preserve verbatim in the extraction: `_open_member_readonly` (workspace_quality.py:108-120 — `mode=ro` URI, `row_factory=sqlite3.Row`, `PRAGMA query_only=ON`) deliberately bypasses `history_reader/_base.py::_connect_readonly()` (:60-84) because that calls `ensure_db()` and would migrate a stale member before the gate could see it; and corrupt files open lazily, failing only on first query (docstring :109-116), so `read_schema_version` (queries.py:203-216 — maps `sqlite3.OperationalError` → `None` → "schema_version missing") must stay inside the same try as the open. Skew compares against `SCHEMA_VERSION = 50` (schema.py:25), report-and-skip in both directions, nothing raises. Placement note: the repo has no cross-module shared sqlite opener (11 `mode=ro` sites, 8 modules, each private with "modeled on" docstring chains) — this share is intra-subsystem (the workspace aggregation pair), so keep the helper private to the pair (live in `workspace_quality.py`, imported by `workspace_activity.py`, or hoist to a small private module); do not promote it to a public shared opener. The activity reader upgrades the skip record from a reason string to a structured status; reuse quality's exact reason wording for `db_missing` (`f"history.db not found at {db_path}"`, :220) — the sibling suites assert these strings verbatim, and cross-command output stays greppable.

**Known limitation (document, do not solve):** FSM signals (stalls, cycles, rate-limits) are webhook-only and not stored in history.db; a history.db read cannot cover them.

## Program Design

### Types

See `## API/Interface` for the full contract: `MemberActivityStatus` (**plain `Enum` with string values, not `(str, Enum)`/`StrEnum`** — zero `(str, Enum)` definitions exist in `scripts/little_loops/` (repo-wide grep, confirmed); the plain-`Enum` convention is established by issue_lifecycle.py's five enums, whose `CompletionResult` docstring at :124-125 argues against `StrEnum` specifically (not the `(str, Enum)` tuple form) — the `(str, Enum)` avoidance rests on the grep, not that docstring; values `ok`/`db_missing`/`schema_skew`/`unreadable` with an inline `#` comment per member), `RepoActivity` (frozen dataclass; counts `None` iff status != OK; `to_dict()`), `WorkspaceActivityResult` (`per_repo` + `totals: WorkspaceTotals | None`, `to_dict()`). Every serializable result container gets a `to_dict() -> dict[str, Any]` that recursively delegates (the `agent_quality.py` quartet + `AggregationResult` pattern), so `WorkspaceActivityResult.to_dict()` builds each array element via `RepoActivity.to_dict()`.

### Signatures

- `aggregate_workspace_activity(members: list[WorkspaceMember], *, since: str | None) -> WorkspaceActivityResult` — the only public entry; module sibling to `aggregate_history_dbs()` in `scripts/little_loops/issue_history/workspace_activity.py` (new file).

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
- NEW `scripts/tests/test_feat3445_workspace_activity.py` (sibling naming; plain `test_workspace.py` also exists in-tree for FEAT-3409, but the two aggregation siblings use the `test_featNNNN_` form) — mixed timestamp formats, NULL `ended_at`, missing/skewed/unreadable members, zero-ok workspace, unbounded `since`. Follow the sibling suites' conventions:
  - **Fixtures**: build `WorkspaceMember` objects over `tmp_path` dirs; healthy dbs via the real write API (`record_issue_event`, test_feat3410.py:28-43); skewed members via hand-rolled `meta` table (`_skewed_member`, :65-76); garbage via `write_text("not a database")` (:176). Name test dbs `<name>-history.db`, NOT default-shaped `.ll/history.db`, to dodge the autouse `_isolate_history_db` fixture (conftest.py:915-949) that routes default-shaped paths through one shared `LL_HISTORY_DB` env var.
  - **Untouched-source**: sha256 the member db before/after every skip case (test_feat3410.py:79-80/:122-129; test_feat3418.py:396-413).
  - **Source-inspection**: mirror `test_never_uses_migrating_opener` (test_feat3410.py:215-231) — assert `"ensure_db(" not in code`, `"_connect_readonly(" not in code`, `"mode=ro" in code` over the new module's source.
  - **Timestamp control**: the write API's `_now()` controls `ts`, so window tests overwrite it post-write via direct UPDATE (`_stamp_ts`/`_close`/`_reopen`, test_feat3418.py:69-88); for `+00:00`-micros `started_at` rows, set them the way executor does (or UPDATE directly) so both formats are exercised.
  - One `class TestX:` per AC group, docstring citing the AC.
- `scripts/tests/test_feat3410_workspace_quality.py` + `test_feat3418_workspace_quality.py` — must pass unmodified after the gate-helper extraction.
  > ⚠ Superseded — breaks if gate helper is hoisted elsewhere

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat3410_workspace_quality.py:215-231` (`test_never_uses_migrating_opener`) — source-inspects `workspace_quality.py`'s own file text for the literal string `def _open_member_readonly`; if the gate extraction hoists `_open_member_readonly` out of `workspace_quality.py` into a separate module, `text.index(...)` raises `ValueError` (substring not found) and this test breaks. If the helper stays resident in `workspace_quality.py` (one of the two placements this issue's own placement note allows), no change is needed — but the implementer must verify which placement was chosen and update the test's source-inspection target if hoisted. [Agent 1 + Agent 2 finding, confirmed]
- `scripts/tests/test_feat3418_workspace_quality.py:24-32` — imports private ATTACH/union symbols directly (`_UNION_RELATIONS`, `_discriminate_issues`, `_discriminator`, `_open_union`, `aggregate_history_dbs`) from `workspace_quality`. These belong to the union machinery, explicitly out of scope for the gate extraction — do not relocate or rename them; only the per-member gate helper moves. [Agent 1 + Agent 2 finding, confirmed]

### Documentation
- `docs/reference/API.md` — issue_history submodules do **not** get their own `##` sections: fold into the existing `## little_loops.issue_history` section as function-table rows (the `aggregate_history_dbs` row at API.md:2389 is the pattern), with `WorkspaceActivityResult`/`RepoActivity` appearing via formatter/result rows as `AggregationResult` does (:2402). Note the gate extraction under `workspace_quality`'s row.
- `docs/ARCHITECTURE.md` — one sentence appended to the "History DB: Producer→Consumer Flow" section's workspace-manifest prose (line ~714), not a new section; the module tree keeps `issue_history/` collapsed.

### Configuration
- N/A — reads only `WorkspaceMember` inputs + per-member history.db; no new config keys.

## Implementation Steps

1. Extract the member gate from `workspace_quality.aggregate_history_dbs()` into a shared helper; re-run the quality test suite unchanged.
   > ⚠ Superseded — breaks if gate helper is hoisted elsewhere
2. Create `workspace_activity.py` with the enums/dataclasses above. Module docstring follows the sibling convention: one-line purpose + FEAT number first (`"""Cross-repo activity counts over a declared workspace (FEAT-3445)."""`), narrate the mechanism with "modeled on" cross-references and explicit anti-references (never `_connect_readonly()` — it migrates), restate resolved decisions from this issue verbatim, close with accepted limitations (FSM-signals, ≤1s `datetime()` tolerance if SQL-side normalization is chosen).
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
    UNREADABLE = "unreadable"      # sqlite3.Error on open/read -> instrumented: True

@dataclass(frozen=True)            # frozen: crosses the producer/consumer boundary (WorkspaceMember convention)
class RepoActivity:
    repo_path: str                               # absolute, resolved
    role: str
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
class WorkspaceActivityResult:
    since: str | None
    per_repo: dict[str, RepoActivity]            # keyed by repo_path for lookup
    totals: WorkspaceTotals | None               # None iff no ok members
    def to_dict(self) -> dict[str, Any]: ...     # serializes per_repo as an ARRAY via RepoActivity.to_dict()
```

`WorkspaceTotals` sums each count over `ok` members only, plus `members: int`, `instrumented_members: int`, and `instrumented: bool` (OR over members). Schema-skewed/unreadable members are excluded from totals (matching quality's gate) — stated so an implementer doesn't have to re-derive it.

**Canonical serialization rules (consumer contract):**
- Each serialized member object carries `repo_path`, `role`, `label` (`"{repo_path.name} ({role})"`, display only), `status`, `ok` (`status == "ok"`), `error` (`reason`), and `instrumented`. `ok`/`error` are the canonical consumer-facing fields; `status` rides along as the finer-grained discriminator.
- Metrics unavailable from history.db serialize as `null`, **never `0`**. Two named cases: `issues_closed` is emitted as an explicit always-`null` reserved key (history.db collapses issue closed→completed into transition `'done'`, so the split cannot be made today — null keeps "unavailable" distinguishable from "measured zero" if the schema ever records it distinctly), and the three FSM signals (stalls / cycles / rate-limits — webhook-only) are deliberately absent from the output; consumers must model them as unavailable, not zero.

## Use Case

A downstream briefing/portfolio sync calls `aggregate_workspace_activity(members, since=last_sync)` once per sync instead of N subprocess spawns + N direct sqlite connections, and branches on `instrumented`/status to report "not instrumented" vs "history present but unreadable" per repo — the distinction the current string-pair skip record cannot express.

## Acceptance Criteria

1. `aggregate_workspace_activity(members, since=...)` returns one `RepoActivity` per member carrying `repo_path`/`role`; non-ok members carry `None` counts, never `0`, plus `ok: False` and a populated `error`.
2. `instrumented` is False only for `db_missing`; True for `schema_skew`/`unreadable` (both report `reason`).
3. Totals equal the sum of `ok` members' counts; zero `ok` members yields `totals=None`, no exception.
4. Running loops (NULL `ended_at`) never count as completed; loops started before `since` but ended after do.
5. Timestamp comparison is format-safe at datetime granularity across `+00:00`-micros and `Z` forms (via `datetime()` normalization or equivalent); raw lexicographic comparison of unnormalized strings is a test-visible failure.
6. Member databases are opened read-only (`file:...?mode=ro`, `PRAGMA query_only`), never migrated — same contract as workspace_quality.
7. The shared member-gate helper is used by both `aggregate_history_dbs()` and the new reader; quality's behavior is byte-identical after extraction (existing tests pass unmodified).
8. The module docstring documents the FSM-signals limitation verbatim.
9. Serialized output follows the canonical rules above: member objects carry `repo_path`/`role`/`ok`/`error`/`instrumented`; `issues_closed` is always `null`; unavailable metrics are `null` or absent, never `0`; `totals.instrumented` is the OR over members.

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design; where the workspace aggregation layer sits |
| architecture | docs/reference/API.md | Python module reference — new public module + `workspace_quality` gate extraction land here |

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

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

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-11T00:47:45 - `e2289526-f05e-4914-b7bb-dee1a954062a.jsonl`
- `/ll:wire-issue` - 2026-09-11T00:38:37 - `2e842a0e-c20b-4811-ac47-806369f06e2c.jsonl`
- `/ll:format-issue` - 2026-09-10T23:59:04 - `977177b4-c924-4eb0-8524-717b55725bed.jsonl`
- `/ll:capture-issue` - 2026-09-10T23:53:43 - `98b64441-1d76-4822-ab69-c295348ddfd6.jsonl`
