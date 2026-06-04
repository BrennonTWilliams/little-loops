---
id: ENH-1905
title: Wire history.db effort/velocity reads into planning skills
type: ENH
priority: P3
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T19:50:05Z'
completed_at: '2026-06-04T01:10:09Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1752
- ENH-1846
- ENH-1847
- ENH-1888
- ENH-1711
- ENH-1909
labels:
- captured
- history-db
confidence_score: 96
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 18
implementation_order_risk: true
decision_needed: false
blocked_by: []
---

# ENH-1905: Wire history.db effort/velocity reads into planning skills

## Summary

Every current `.ll/history.db` consumer is an issue-refinement or gating skill
(`refine-issue`, `ready-issue`, `confidence-check`, `go-no-go`,
`capture-issue`). Planning skills — `create-sprint`, `scope-epic`,
`manage-issue`, `review-epic` — do not read history, even though the
`issue_sessions` view (ENH-1711) plus `ll-ctx-stats` already hold per-issue
session counts and token/effort data. Planning decisions remain inference-based
rather than grounded in actual historical effort.

## Current Behavior

- `prioritize-issues` and `manage-release` reference history (precedent), but
  `create-sprint`, `scope-epic`, `manage-issue`, and `review-epic` do not.
- Sprint sizing, epic decomposition, and per-issue effort estimates are made
  without consulting how long comparable past issues actually took.

## Expected Behavior

- A planning-oriented read surface (per-issue session count, cumulative token
  cost, wall-clock cycle time from first→last session) is exposed via
  `history_reader.py` / `ll-history-context`.
- `create-sprint`, `scope-epic`, `manage-issue`, and `review-epic` consult it
  to inform sizing/velocity, degrading gracefully when the DB is empty or stale.

## Motivation

The user's intent for EPIC-1707 explicitly includes **planning**, not just issue
refinement. Historical effort data is the highest-signal input for sprint
sizing and epic decomposition, and it already exists in the DB — it just isn't
surfaced to the skills that would benefit.

## Success Metrics

- All four planning skills (`create-sprint`, `scope-epic`, `manage-issue`, `review-epic`) invoke the effort/velocity read when the DB has ≥1 matching session.
- Sprint/epic sizing output cites historical session counts or cycle times when data is available.
- When DB is absent or has no matching data, no exception is raised and the skill proceeds without effort context (graceful degradation verified by empty-DB test).

## Proposed Solution

1. Add a read (e.g. `issue_effort(issue_id)` / `recent_issue_velocity()`) to
   `history_reader.py`, backed by `issue_sessions` + ctx-stats data.
2. Expose it through `ll-history-context` (or a sibling CLI) for skill
   invocation.
3. Wire it into the four planning skills with the same graceful-degradation
   guard used by existing consumers.

## API/Interface

```python
# history_reader.py additions
def issue_effort(issue_id: str) -> dict | None:
    """Per-issue effort: session_count, total_tokens, cycle_time_days (first→last session)."""

def recent_issue_velocity(limit: int = 10) -> list[dict]:
    """Effort data for recently completed issues; empty list when DB has no data."""
```

CLI addition:
```
ll-history-context <issue_id> --effort
```

> **Note on `total_tokens`**: The `issue_sessions` VIEW does not include token counts — only session timestamps. Computing `total_tokens` requires joining `tool_events` on `session_id`, which no existing `history_reader.py` function does. The initial implementation should omit `total_tokens` (return `None` or exclude the key) and document this as a future enhancement. The dict shape should be `{"session_count": int, "cycle_time_days": float | None}` for the MVP.

> **Config keys (user configurability)**: `limit` in `recent_issue_velocity` and the set of surfaced metric fields should be read from `ll-config.json` rather than hardcoded. Suggested keys under a `history:` namespace:
> - `history.velocity_window` (int, default `10`) — controls how many recent issues `recent_issue_velocity` returns
> - `history.effort_fields` (list[str], default `["session_count", "cycle_time_days"]`) — controls which fields are printed by `ll-history-context <issue_id> --effort`
> - `history.max_age_days` (int | null, default `null`) — when set, sessions older than this many days are excluded from effort computation; `null` disables staleness filtering
>
> The MVP may fall back to these defaults when the keys are absent, but the implementation must read from config if present so users can tune behavior without code changes. This keeps the rubric extensible as the `issue_sessions` schema grows (e.g. adding `total_tokens` later).
>
> **`effort_fields` validation**: unknown field names in `history.effort_fields` must be logged as a warning and skipped — they must never raise an exception or abort the skill. This ensures forward compatibility when users reference a field (e.g. `total_tokens`) before the backing code lands.

> **Graceful-degradation guard pattern** (verbatim from `skills/confidence-check/SKILL.md § Phase 1` and `skills/go-no-go/SKILL.md § Step 3a`):
> ```bash
> EFFORT=$(ll-history-context {{issue_id}} --effort 2>/dev/null || true)
> ```
> `|| true` ensures a non-zero exit never aborts the skill. `allowed-tools` entry: `Bash(ll-history-context:*)`.
>
> **Design clarification (verified against `cli/history_context.py`)**: `issue_id` is a positional arg in the current CLI (`_build_parser()` line 51); `--file` is an optional flag that takes a PATH. `--effort` must be implemented as a **boolean flag** (no argument) reusing the existing positional `issue_id` — not as `--effort <issue_id>`, which would require making the positional arg optional. Usage: `ll-history-context <issue_id> --effort`. The guard above is already corrected to this form.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py`
- `scripts/little_loops/cli/history_context.py`
- ~~`config-schema.json`~~ — **owned by ENH-1913** (history namespace foundation); the three keys (`history.velocity_window`, `history.effort_fields`, `history.max_age_days`) are declared there. This issue wires runtime reads only after ENH-1913 lands.
- `commands/create-sprint.md`
- `skills/scope-epic/SKILL.md`
- `skills/manage-issue/SKILL.md`
- `skills/review-epic/SKILL.md`

_Wiring pass added by `/ll:wire-issue`:_
- `skills/ll-create-sprint/SKILL.md` — Codex bridge stub; add `Bash(ll-history-context:*)` to `allowed-tools` frontmatter to mirror ENH-1847 pattern for `ll-refine-issue` / `ll-ready-issue` stubs
- `.claude/CLAUDE.md` — `ll-history-context` bullet description must mention the new `--effort` flag

### Dependent Files (Callers/Importers)
- `commands/create-sprint.md` — will call `ll-history-context <issue_id> --effort` for per-issue sizing
- `skills/scope-epic/SKILL.md` — will call `recent_issue_velocity()` for epic decomposition guidance
- `skills/manage-issue/SKILL.md` — will call `issue_effort()` before generating implementation plan
- `skills/review-epic/SKILL.md` — will call velocity read during epic review

### Similar Patterns
- `skills/refine-issue/SKILL.md` — uses `ll-history-context` with graceful-degradation guard; mirror this pattern
- `skills/confidence-check/SKILL.md` — same guard pattern
- `skills/go-no-go/SKILL.md` — same guard pattern

### Tests
- `scripts/tests/test_history_reader.py` — effort/velocity read + empty-DB
  degradation.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_context_cli.py` — primary CLI test file for `main_history_context()`; extend with a new `TestHistoryContextEffortFlag` class covering: `--effort` accepted without error, output includes `## Effort Context` when sessions exist, empty stdout when no sessions, exit 0 when DB missing. Uses `patch("sys.argv", [..., "--effort", ...])` + `capsys` pattern matching existing `TestHistoryContextWithMatches`.
- `scripts/tests/test_enh1905_doc_wiring.py` — beyond `allowed-tools` frontmatter checks, add `test_api_documents_issue_effort` and `test_api_documents_recent_issue_velocity` methods asserting `docs/reference/API.md` contains those function names; follow `test_enh1753_doc_wiring.py` precedent (which gates `sessions_for_issue` API docs)

### Documentation
- `docs/reference/API.md` — update `history_reader` module docs with new functions; add `### issue_effort` and `### recent_issue_velocity` subsections at line 5964+; update module-overview table inline exports description (line 52); add `--effort` flag row to `### main_history_context` Flags table (line 3519–3529)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-history-context` flags table (line 1789–1795): add `--effort ISSUE_ID` flag row and `## Effort Context` output description
- `docs/ARCHITECTURE.md` — Read Path flowchart `SK` node (line 622): expand to include `create-sprint`, `scope-epic`, `manage-issue`, `review-epic` alongside existing refinement skills; Components table `history_reader.py` row (line 636): update function count from 5 to 7
- `CHANGELOG.md` — add release entry documenting `--effort` flag in `ll-history-context` and the four planning skill wirings (release-time update; via `ll:manage-release`)

### Configuration
- N/A — no new configuration required

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**All referenced files confirmed to exist.** Additional files identified:

- `scripts/little_loops/history_reader.py` — `sessions_for_issue()` (anchor) is the closest existing function; `_connect_readonly()` (anchor) is the shared graceful-degradation helper all new functions must reuse
- `scripts/little_loops/session_store.py` — no modification needed; read-only reference for `issue_sessions` VIEW schema (defined in `_MIGRATIONS` index 4, v5 migration)
- `scripts/tests/test_enh1905_doc_wiring.py` — **new file to create**; validates that all four planning skills have `Bash(ll-history-context:*)` in `allowed-tools`; follow pattern in `scripts/tests/test_enh1888_doc_wiring.py`

**Data source clarification:** `ll-ctx-stats` is project-wide (no per-issue breakdown) and is NOT a valid data source for per-issue effort. The `issue_sessions` VIEW provides `session_count` (row count) and `cycle_time_days` (derived from `MIN(first_message_ts)` → `MAX(last_message_ts)` across all rows for an issue). Token totals would require joining `tool_events`, which no existing function does — see API note below.

## Implementation Steps

1. Define the planning read API and back it with `issue_sessions`/ctx-stats.
2. Surface via CLI.
3. Wire each planning skill, mirroring the existing consumer guard pattern.
4. Add degradation tests.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file references from codebase analysis:_

1. **`scripts/little_loops/history_reader.py`** — add two functions below `sessions_for_issue()`:
   - `issue_effort(issue_id, *, db)` — call `sessions_for_issue()` or query `issue_sessions` directly; count rows → `session_count`; compute `cycle_time_days` from `min(first_message_ts)` to `max(last_message_ts)`; return `{"session_count": int, "cycle_time_days": float | None}` or `None` when no rows. Use `_connect_readonly()` helper for graceful degradation.
   - `recent_issue_velocity(limit=10, *, db)` — query `issue_events` for recently-completed issues (non-NULL `completed_at`), call `issue_effort()` for each; return `list[dict]`; return `[]` when DB absent or empty.

2. **`scripts/little_loops/cli/history_context.py:main_history_context()`** — add `--effort` flag to `argparse`; when passed, call `issue_effort(args.issue_id)` and print a `## Effort Context` block; exit 0 silently when no data. Mirror the existing `--file` flag pattern.

3. **`commands/create-sprint.md`** — add `Bash(ll-history-context:*)` to `allowed-tools` frontmatter (currently has `Bash(mkdir:*)` and `Bash(ll-issues:*)`); inject `EFFORT=$(ll-history-context {{issue_id}} --effort 2>/dev/null || true)` guard in `### Step 1.5.1: Scan Active Issues` or `### 4. Validate Issues Exist`; include non-empty `$EFFORT` in per-issue sizing context.

4. **`skills/scope-epic/SKILL.md`** — add `Bash(ll-history-context:*)` to `allowed-tools` (currently has `Read`, `Write`, `Edit`, `Glob`, `Grep`, `AskUserQuestion`, `Bash(ll-issues:*, git:*)`); inject guard in `### Phase 2: Decompose Theme into EPIC + Children`; use velocity output to calibrate child-issue size estimates.

5. **`skills/manage-issue/SKILL.md`** — add `Bash(ll-history-context:*)` to `allowed-tools` (currently has only `Bash(git:*)`); inject guard in `## Phase 1.5: Deep Research`, alongside the three existing parallel `Task` calls; include non-empty `$EFFORT` in the implementation plan preamble.

6. **`skills/review-epic/SKILL.md`** — add `Bash(ll-history-context:*)` to `allowed-tools` (currently has `Read`, `Bash(ll-issues:*)`, `Bash(git:*)`); inject guard in `## Step 2: Load EPIC and Resolve Children` or `## Step 3: Compute Progress Aggregates`; surface session counts and cycle times in the health report.

7. ~~**`config-schema.json`**~~ — **ENH-1913 has landed** (`status: done`, `completed_at: 2026-06-04T00:05:41Z`). The three config keys are live. In `main_history_context()`, read them via:
   ```python
   from little_loops.config import BRConfig
   cfg = BRConfig()
   limit = cfg.history.velocity_window  # default 10
   fields = cfg.history.effort_fields   # default ["session_count", "cycle_time_days"]
   ```
   When formatting `## Effort Context`, iterate over `fields`; for any field not in `{"session_count", "cycle_time_days"}`, call `logger.warning("history_context: unknown effort field %r — skipping", f)` and skip it. No schema edit needed in this issue.

8. **`scripts/tests/test_history_reader.py`** — add test cases for `issue_effort()` and `recent_issue_velocity()`: empty-DB returns `None`/`[]`; single-session returns `cycle_time_days=0.0`; multi-session returns correct day delta.

9. **`scripts/tests/test_enh1905_doc_wiring.py`** (new file) — create following `scripts/tests/test_enh1888_doc_wiring.py`; validate `commands/create-sprint.md`, `skills/scope-epic/SKILL.md`, `skills/manage-issue/SKILL.md`, `skills/review-epic/SKILL.md` each contain `Bash(ll-history-context:*)` in `allowed-tools`.

### Codebase Research Findings (Second Pass)

_Added by `/ll:refine-issue` — direct code inspection; resolves ambiguity in pass 1 guidance:_

**`issue_effort()` must NOT reuse `sessions_for_issue()`** — that helper applies `LIMIT=20`. For issues with >20 sessions, the top-20 rows would miss the oldest session, producing an incorrect `cycle_time_days`. Use a direct aggregate query:

```sql
SELECT COUNT(*) AS session_count,
       MIN(first_message_ts) AS first_ts,
       MAX(last_message_ts) AS last_ts
FROM issue_sessions WHERE issue_id = ?
```

Return `None` when `session_count == 0`. Compute `cycle_time_days` as `(last_ts - first_ts).total_seconds() / 86400` after parsing ISO-8601 strings via `datetime.fromisoformat()`. Full skeleton (mirrors `sessions_for_issue()` at line 265):

```python
def issue_effort(issue_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> dict | None:
    db_path = Path(db)
    conn = _connect_readonly(db_path)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS session_count, MIN(first_message_ts) AS first_ts, "
            "MAX(last_message_ts) AS last_ts FROM issue_sessions WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()
    except sqlite3.Error:
        logger.warning("history_reader: issue_effort query failed", exc_info=True)
        return None
    finally:
        conn.close()
    if row is None or row["session_count"] == 0:
        return None
    cycle: float | None = None
    if row["first_ts"] and row["last_ts"]:
        delta = datetime.fromisoformat(row["last_ts"]) - datetime.fromisoformat(row["first_ts"])
        cycle = delta.total_seconds() / 86400
    return {"session_count": row["session_count"], "cycle_time_days": cycle}
```

**`recent_issue_velocity()` outer SQL** — query `issue_events` for the completion filter, then call `issue_effort()` per issue:

```sql
SELECT DISTINCT issue_id FROM issue_events
WHERE completed_at IS NOT NULL
ORDER BY completed_at DESC LIMIT ?
```

Use `_connect_readonly()` for this outer query; `issue_effort()` manages its own connection.

**`--effort` argparse pattern** — add after `--db` in `_build_parser()` (`history_context.py` line 59):

```python
parser.add_argument(
    "--effort",
    action="store_true",
    default=False,
    help="Include effort/velocity context (session count and cycle time)",
)
```

Usage: positional arg first — `ll-history-context ENH-1905 --effort`.

**Test argv for `TestHistoryContextEffortFlag`** (model after `TestHistoryContextWithMatches`):

```python
with patch("sys.argv", ["ll-history-context", "--db", str(db), "ENH-1905", "--effort"]):
    result = main_history_context()
assert result == 0
assert "## Effort Context" in capsys.readouterr().out
```

**`skills/ll-create-sprint/SKILL.md` currently has NO `allowed-tools` key** — step 13 must create the entire section, not append to an existing one. Model the addition after `skills/ll-go-no-go/SKILL.md` frontmatter (which similarly was a stub that received `allowed-tools` in the ENH-1888 wiring pass).

### Codebase Research Findings (Third Pass)

_Added by `/ll:refine-issue` — ENH-1913 status verification and config read path:_

**ENH-1913 is `done` (`completed_at: 2026-06-04T00:05:41Z`)** — `blocked_by` cleared. All three config keys (`history.velocity_window`, `history.effort_fields`, `history.max_age_days`) are live in `config-schema.json:1406–1503` and `scripts/little_loops/config/features.py:HistoryConfig` (line 716).

**`BRConfig().history` read path** (unblocked; ready for `history_context.py`):
- Import: `from little_loops.config import BRConfig` (re-exported at `config/__init__.py:28`)
- `BRConfig().history.velocity_window` → `int`, default `10`
- `BRConfig().history.effort_fields` → `list[str]`, default `["session_count", "cycle_time_days"]`
- `BRConfig().history.max_age_days` → `int | None`, default `None`

**`effort_fields` validation location**: validate in `main_history_context()`, NOT in `history_reader.py`. Known valid MVP fields: `{"session_count", "cycle_time_days"}`. For any unknown field, log `logger.warning("history_context: unknown effort field %r — skipping", f)` and continue. This matches the forward-compatibility requirement in the API/Interface section.

**`issue_sessions` VIEW columns confirmed** (`session_store.py:229`): `issue_id`, `session_id`, `jsonl_path`, `first_message_ts`, `last_message_ts` — one row per `(issue_id, session_id)`. `MIN(first_message_ts)` / `MAX(last_message_ts)` across all rows for an issue gives earliest session start → latest session end, which is the correct cycle-time window.

**`history.planning_skills` config key** exists in schema at `config-schema.json:1406`, default `["create-sprint", "scope-epic", "manage-issue", "review-epic"]`. ENH-1905 does NOT read this key — it is ENH-1909's config gate for skill-selection. Hard-wire the four skills in this issue.

**`skills/ll-create-sprint/SKILL.md` confirmed**: has no `allowed-tools` block (only `name`, `description`, `metadata` in frontmatter). Step 13 must create the entire `allowed-tools` section, modeled after `skills/ll-go-no-go/SKILL.md:1–20`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `scripts/tests/test_history_context_cli.py` — add `TestHistoryContextEffortFlag` class covering `--effort` with data, empty DB, and no-match cases; use `patch("sys.argv", [..., "--effort", ...])` + `capsys` pattern from `TestHistoryContextWithMatches`
10. Update `docs/reference/CLI.md` — add `--effort ISSUE_ID` flag row to `### ll-history-context` flags table; describe `## Effort Context` output block
11. Update `docs/ARCHITECTURE.md` — expand Read Path flowchart `SK` node to include planning skills (`create-sprint`, `scope-epic`, `manage-issue`, `review-epic`); update Components table `history_reader.py` row function count from 5 to 7
12. Update `.claude/CLAUDE.md` — update `ll-history-context` bullet in `## CLI Tools` section to mention `--effort` flag
13. Update `skills/ll-create-sprint/SKILL.md` — add `allowed-tools` frontmatter with `Bash(ll-history-context:*)` to match ENH-1847 mirror pattern for Codex bridge stubs
14. Extend `test_enh1905_doc_wiring.py` — add `test_api_documents_issue_effort` and `test_api_documents_recent_issue_velocity` methods asserting those function names appear in `docs/reference/API.md`; follow `test_enh1753_doc_wiring.py` pattern
15. Update `CHANGELOG.md` at release time — add entry for `--effort` flag in `ll-history-context` and planning skill history context wiring (via `ll:manage-release`)

## Scope Boundaries

- **In scope**: Adding `issue_effort()` / `recent_issue_velocity()` reads to `history_reader.py`; CLI exposure via `ll-history-context`; wiring the four planning skills with graceful-degradation guards; reading the `history.velocity_window`, `history.effort_fields`, and `history.max_age_days` config keys via `BRConfig().history` (added to `config-schema.json` by ENH-1913, which has landed).
- **Out of scope**: New session data collection (handled by ENH-1904); UI/visualization of effort data; changes to how `issue_sessions` view is populated; backfilling historical data; configuring which skills receive history context (tracked in ENH-1909).

## Impact

- **Priority**: P3 — high-value but not blocking; depends on the corpus being
  populated (ENH-1904 improves signal quality).
- **Effort**: Medium.
- **Risk**: Medium — stale/wrong effort data could mislead planning; needs a
  staleness guard and clear "no data" fallback.
- **Breaking Change**: No.

## Labels

`captured`, `history-db`

## Confidence Check Notes

_Last updated by `/ll:confidence-check` on 2026-06-03 (confirmed post-wire-issue; ENH-1913 + ENH-1904 both done)_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Broad file surface across 15 sites (wire-issue pass added Codex bridge stub, CLI.md, ARCHITECTURE.md, CLAUDE.md to the original 11 sites) — use `test_enh1905_doc_wiring.py` assertions as a completeness gate; tick off sites in sequence rather than all at once
- Implementation ordering: Python backend (`history_reader.py` + `history_context.py`) must be complete and tested before skill wiring can be end-to-end verified; recommended sequence: Python functions → CLI `--effort` flag → config reads via `BRConfig().history` → skill wiring (4 skills + Codex stub) → doc updates

## Session Log
- `/ll:ready-issue` - 2026-06-04T00:52:22 - `3ce6b5fc-b012-4951-b3ab-bb878fcf9d39.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00Z - `4995fa04-e682-4d6b-abb1-22c65bd6ef20.jsonl`
- `/ll:wire-issue` - 2026-06-04T00:22:03 - `d1eaa95b-b80b-42c6-b2d9-258fd9ca6ff0.jsonl`
- `/ll:refine-issue` - 2026-06-04T00:16:06 - `27d9ab17-d520-4d96-8957-0da168836cea.jsonl`
- `/ll:refine-issue` - 2026-06-03T23:55:28 - `aa87de99-5965-418d-b42c-7afc5a40e2f3.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T21:52:58 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:confidence-check` - 2026-06-03T21:30:00Z - `05f0b8cd-d4c6-444a-8f99-5505d4cea6e9.jsonl`
- `/ll:refine-issue` - 2026-06-03T20:56:43 - `d1a065c6-71ae-4747-b229-4d42ac65cacd.jsonl`
- `/ll:confidence-check` - 2026-06-03T20:30:00Z - `31b2bc85-a0b5-413e-94f6-06c7a9e7124c.jsonl`
- `/ll:wire-issue` - 2026-06-03T20:19:04 - `c1a5f52d-2382-47ae-be05-cfb663438f44.jsonl`
- `/ll:refine-issue` - 2026-06-03T20:12:40 - `5cfac3fd-69b5-4992-849b-b3e21aecf055.jsonl`
- `/ll:format-issue` - 2026-06-03T20:07:08 - `0ecffd0e-287b-4cbc-aeee-94a176efb0b2.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:50:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/13a13638-9030-4da6-94ba-939418824572.jsonl`

---

**Open** | Created: 2026-06-03 | Priority: P3
