---
id: ENH-1907
type: ENH
priority: P3
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T19:54:05Z'
completed_at: '2026-06-04T00:47:01Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- ENH-1752
- ENH-1846
- ENH-1847
- FEAT-1263
- ENH-1830
- ENH-1905
- ENH-1909
- ENH-1911
blocked_by:
- ENH-1913
labels:
- captured
- history-db
- configurability
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1907: Project-Context Snapshot at Session Start

## Summary

Inject a small, project-level "recent state" digest into Claude's context at
session start, sourced from `.ll/history.db`. The digest answers *"what has been
happening in this project lately?"* — recently touched files (last ~7 days),
recently completed/closed issues, and recurring `user_corrections` themes — as
distinct from the per-session *personal handoff* of "what I was doing" that
FEAT-1263 already injects.

This is a new **consumer** under EPIC-1707 (history.db as Agent Context Layer):
the producer side and the read primitives already exist; the missing pieces are
a project-wide aggregation query and the `session_start` wiring.

## Current Behavior

`scripts/little_loops/hooks/session_start.py` (`handle()`) injects the merged
`ll-config.json` as `additionalContext` and kicks off a background
`backfill_incremental` (ENH-1830). It does **not** surface any project-state
summary. The only history-derived context an agent sees today is:

- **Personal handoff** (FEAT-1263, done): `ll-continue-prompt.md` → "what *I*
  was doing last session" (continuation of in-flight work).
- **Issue-scoped lookups** (ENH-1846/ENH-1847, done): `ll-history-context
  <ISSUE_ID>` renders corrections + FTS matches for *one issue the agent is
  already working on* — pulled on demand by `refine-issue` / `ready-issue` /
  `confidence-check`, not at session start.

Neither gives a fresh session a project-wide "here's the recent state" picture,
so `history.db`'s `file_events`, `issue_events`, and `user_corrections` tables go
unused for ambient session framing.

## Expected Behavior

On session start (for initialized projects with a non-empty `history.db`), Claude
receives a compact `<project_context>` block, e.g.:

```
<project_context>
## Recently touched (last 7 days)
- scripts/little_loops/host_runner.py (12 edits)
- scripts/little_loops/session_store.py (5 edits)
...
## Recently completed issues
- ENH-1847 — Wire ll-history-context into refine/ready/confidence (2d ago)
- BUG-1881 — post_tool_use python handler not wired (4d ago)
## Recurring corrections
- "don't add Co-Authored-By trailers" (seen 3x)
- "commands/*.md are commands, not docs" (seen 2x)
</project_context>
```

When the DB is missing, empty, or all rows are stale, the hook injects nothing
(no empty block, no error) and session start is unaffected.

## Motivation

EPIC-1707's goal is for ll components to read `history.db` so prior context
informs outputs "without the user having to manually surface that context." A
session-start project digest is the single highest-leverage *ambient* consumer:
it benefits **every** session (not just issue-scoped skills), it reuses the
already-built read API (ENH-1752), and it directly exercises the
`user_corrections` → fewer-repeated-corrections success metric the EPIC tracks.

## Success Metrics

- Gate-off (default): no `<project_context>` block injected; `session_start` timing unaffected.
- Gate-on + populated DB: `<project_context>` block present in session context and under hard `char_cap`.
- Gate-on + missing/stale DB: no block injected, no error, exit 0 (graceful degradation verified).
- **Config-driven composition**: reordering `sections` reorders the rendered blocks; omitting a section removes it; `sections: []` injects nothing — all verified without editing code.
- **Inspectability**: `ll-history-context --project` prints exactly what the hook would inject for the current config.
- Reduction in repeated `user_corrections` across sessions (EPIC-1707 primary metric).

## Scope Boundaries

- **In scope**: `project_digest()` aggregation + **section-provider registry** + bounded formatter in `history_reader.py`; gated wiring in `session_start.py`; ordered `history.session_digest.sections` config block in `config-schema.json`; a `ll-history-context --project` inspection dry-run (prints what would be injected, for config tuning); unit and integration tests; docs sweep (ARCHITECTURE / API / CONFIGURATION).
- **Out of scope**: Per-session personal handoff (FEAT-1263), issue-scoped history lookups (ENH-1846/1847), backfill behavior changes (ENH-1830), real-time within-session digest refresh (digest reflects previous-session rows only by design), user-supplied output **templates** / arbitrary external data sources (deliberately deferred — they conflict with the fixed `char_cap` on the every-session hot path; the section registry covers composability safely without them).

## Proposed Solution

The guiding design principle is **"project info surfaced at session start should
be as user-configurable as possible, long-term"** — without sacrificing the
hot-path safety envelope EPIC-1707 mandates. This means the *what* (which
sections, which sources, in what order) is config-driven, while the *safety
ceiling* (gate, hard char cap, freshness window) stays fixed and is not
user-unbounded. The mechanism is a **section-provider registry**, not three
hardcoded blocks.

1. **Add a project-digest query to `history_reader.py`** — a new
   `project_digest(db_path, *, days=7, sections=...)` that aggregates across all
   paths/issues (the existing `recent_file_events` / `find_user_corrections` /
   `related_issue_events` are per-path / per-topic / per-issue and don't roll
   up). Returns a typed dataclass; returns an empty/sentinel result on
   missing/empty/stale DB, mirroring the degradation contract the other readers
   already follow.

2. **Build the digest from a registry of named section providers**, NOT three
   hardcoded blocks. Each provider is a small record:

   ```python
   SectionProvider(
       name="touched_files",      # config-addressable key
       query=_touched_files,      # (conn, *, days, cap) -> list[Row]
       default_cap=10,
       render=_render_touched,    # rows -> markdown lines
   )
   ```

   The three v1 providers (`touched_files`, `completed_issues`,
   `recurring_corrections`) register into a `SECTION_PROVIDERS` table. The
   digest renders providers **in the order the config `sections` list names
   them**; a section omitted from the list is suppressed. This is the single
   change that makes "as configurable as possible" cheap now and expensive
   later: future history-derived signals — effort/velocity (ENH-1905),
   quantified evolution triggers (ENH-1911) — land as a *new provider + a config
   entry*, with **no formatter rewrite and no schema migration**. (This mirrors
   how ENH-1909 turns ENH-1905's hardcoded skill set into a config list — same
   "registry + config-or-default" contract, same `history.*` namespace.)

3. **Render a bounded block** — a formatter that walks the configured providers
   in order, applies each provider's cap, and concatenates their markdown into
   the `<project_context>` block, enforcing a **global hard character cap**
   (`char_cap`) so the block can never bloat the every-session hot path
   regardless of how many sections a user enables (truncate with a "+N more"
   tail). `char_cap` and `enabled` are the fixed safety ceiling — deliberately
   NOT "as configurable as possible," because full template/source freedom on
   the every-session path conflicts with EPIC-1707's primary risk.

4. **Wire into `session_start.py`** — behind an **opt-in config gate**, call the
   digest + formatter and emit the block via `additionalContext`
   (`hookSpecificOutput.additionalContext` envelope — see FEAT-1263's format
   correction note). All errors suppressed; never blocks startup. Note the
   ordering subtlety: `backfill_incremental` runs in a background daemon thread,
   so the digest reflects the *previous* session's already-persisted rows, not
   this session's backfill — acceptable, but document it.

5. **Add an inspection dry-run** — a `ll-history-context --project` mode (or
   equivalent) that prints exactly what *would* be injected for the current
   config, without starting a session. This is the mechanism by which a user
   iterates on their `sections` config; without it, tuning means starting
   sessions and eyeballing the result. Reuses the same `project_digest()` +
   formatter, so it costs little beyond an argparse branch.

6. **Config + schema** — add a gate flag (`history.session_digest.enabled`,
   default `false` while it bakes), the global tunables (`days`, `char_cap`),
   and the **ordered `sections` list** (each entry `{name, max}`) to
   `config-schema.json` (`additionalProperties: false`, so the schema MUST be
   updated). Note `history` is not yet a top-level schema key — coordinate the
   parent-object definition with ENH-1905 / ENH-1909, whichever lands first.

### Critical design constraints

EPIC-1707 names its **primary risk** as prompt bloat + stale context misleading
agents, and `session_start` is on the hot path of *every* session. Therefore:

- **Opt-in gate** (default off until validated).
- **Hard size cap** on the injected block (truncate with a "+N more" tail).
- **Recency/freshness window** (default 7 days; stale rows excluded).
- **Graceful degradation** on missing/empty/stale DB — inject nothing, never
  error, never block startup.

## API/Interface

```python
@dataclass(frozen=True)
class SectionProvider:
    name: str                                   # config-addressable key
    query: Callable[..., list]                  # (conn, *, days, cap) -> rows
    default_cap: int
    render: Callable[[list], list[str]]         # rows -> markdown lines

SECTION_PROVIDERS: dict[str, SectionProvider]   # registry; v1 = 3 entries

def project_digest(
    db_path: Path,
    *,
    days: int = 7,
    sections: list[SectionSpec] | None = None,   # ordered; None -> all providers
) -> ProjectDigest: ...

def render_project_context(
    digest: ProjectDigest,
    *,
    char_cap: int = 1200,
) -> str: ...   # "" when digest is empty (no block injected)
```

Config keys added to `config-schema.json` under `history.session_digest`:
- `enabled` (bool, default `false`) — fixed safety gate
- `days` (int, default `7`) — global freshness window
- `char_cap` (int, default `1200`) — fixed hot-path safety ceiling
- `sections` (array of **string**, ordered) — each entry is the section-name
  key (e.g. `"touched_files"`); render order = list order; omit a section to
  suppress it; default = `[]` (all providers at their `default_cap`).
  **Note**: ENH-1913 landed the schema as `array[string]` (not `array[{name,
  max}]`). Per-section `max` is not config-tunable in v1 — it comes from
  `SectionProvider.default_cap`. The Python API (`list[str] | None`) matches
  the landed schema.

```jsonc
"history": {
  "session_digest": {
    "enabled": false,
    "days": 7,
    "char_cap": 1200,
    "sections": [
      { "name": "touched_files",         "max": 10 },
      { "name": "completed_issues",      "max": 5  },
      { "name": "recurring_corrections", "max": 5  }
    ]
  }
}
```

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader.py` — add the `SECTION_PROVIDERS`
  registry (3 v1 providers), `project_digest()` aggregation, and the
  order-aware bounded `render_project_context()` formatter; reuse the
  `_connect_readonly` / `_stale_cutoff` helpers.
- `scripts/little_loops/hooks/session_start.py` — in `handle()`, after config
  composition, append the rendered block to the stdout/`additionalContext`
  payload behind the gate (best-effort, suppressed).
- `ll-history-context` CLI (entry point in `scripts/`) — add a `--project`
  mode that prints the rendered digest for the current config and exits
  (inspection / config-tuning surface).
- ~~`config-schema.json`~~ — **owned by ENH-1913** (history namespace foundation). The `history.session_digest` object (`enabled`, `days`, `char_cap`, ordered `sections`) is declared in ENH-1913. This issue wires runtime reads and the gated session-start call only after ENH-1913 lands.

### Tests

- `scripts/tests/test_history_reader.py` — add class `TestProjectDigest`: populated DB,
  empty tables, stale-only rows (>window), `char_cap` truncation, **section
  selection/ordering** (custom `sections` list reorders blocks; omitted section
  is absent; `sections: []` → empty digest), and per-section `max` capping.
- `scripts/tests/test_hook_session_start.py` — add class `TestSessionStartProjectDigest`: extend session-start coverage:
  gate off → no block; gate on + populated DB → `<project_context>` present and
  under the cap; gate on + missing/empty DB → no block, exit 0; digest error does not block startup.
- `scripts/tests/test_history_context_cli.py` — add class `TestProjectMode`: `--project` prints the same block
  the hook would inject for a given config (nothing on empty/stale DB, exit 0); mutual-exclusion cases
  (`--project` + `issue_id` = error; no args = error).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_history_context_cli.py::TestArgumentParsing.test_missing_issue_id_exits` — **will break** when
  `issue_id` becomes `nargs="?"`: once `issue_id` is optional, bare `ll-history-context` no longer exits via argparse.
  The CLI must add a mutual-exclusion guard (`parser.error()` when neither `--project` nor `issue_id` is given) so
  this test still asserts `SystemExit`. Update the test to cover the new guard semantics. [Agent 2 + 3 finding]

### Documentation

- `docs/ARCHITECTURE.md` — add the session-start digest to the history.db
  producer→consumer flow (coordinate with ENH-1753).
- `docs/reference/API.md` — document `project_digest`, `render_project_context`, `SectionProvider`, `SECTION_PROVIDERS`, `ProjectDigest` in the `## little_loops.history_reader` section and the module overview table.
- `docs/reference/CONFIGURATION.md` — document `history.session_digest.*`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-history-context` section (line ~1785) currently documents `ISSUE_ID` as a
  **required** positional argument and shows no `--project` flag. After this change `ISSUE_ID` becomes optional
  and `--project` is a new flag; update the flag table and description accordingly. [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/__init__.py` — dispatch table registers `session_start.handle` (line ~84); no change needed, but confirms the hook wiring path. [Agent 1 finding]
- `scripts/little_loops/config/features.py` — defines `SessionDigestConfig`, `HistoryConfig`, and `feature_enabled()`; `session_start.py` currently imports only from `config.core` — a new import (`feature_enabled` or `HistoryConfig`) must be added to `session_start.py` as part of Step 3. [Agent 2 finding]
- `scripts/little_loops/cli/__init__.py` — exports `main_history_context` (line 54); already wired, no change needed. [Agent 1 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Config infrastructure (ENH-1913 complete — already in place):**
- `scripts/little_loops/config/features.py` — `SessionDigestConfig` (lines ~652–668) and `HistoryConfig` (lines ~716–751) are fully implemented. Access in `session_start.py` via either:
  - `feature_enabled(merged_config, "history.session_digest.enabled")` from `little_loops.config.features` (existing dict-path gate pattern used by `user_prompt_submit.py` and `post_tool_use.py`)
  - `HistoryConfig.from_dict(merged_config.get("history", {}))` to get a typed `HistoryConfig` object with `.session_digest.enabled`, `.session_digest.days`, etc.
- `scripts/little_loops/config/core.py` — `BRConfig.history` property returns `HistoryConfig`; `_history` field initialized in `_parse_config()`

**`history_reader.py` helpers to reuse:**
- `_connect_readonly(db_path: Path) -> sqlite3.Connection | None` — opens read-only URI connection, `PRAGMA query_only = ON`; returns `None` on any `sqlite3.Error` — callers must check `if conn is None: return []`
- `_stale_cutoff(days: int) -> str` — returns ISO-8601 string; note: `STALE_DAYS_DEFAULT = 30` is the module constant but `project_digest()` should accept `days` from config (default 7, not 30)
- `_row_to_dataclass(row, dc)` — maps `sqlite3.Row` → dataclass by field name intersection

**Schema discrepancy — critical for `project_digest()` API:**
- The landed `config-schema.json` (ENH-1913) defines `history.session_digest.sections` as `"array" of "string"` items (plain section-name keys like `"touched_files"`), NOT the `{ "name": str, "max": int }` object shape proposed in this issue's API section.
- Consequence: the `sections` parameter in `project_digest(db_path, *, days, sections)` should be `list[str] | None` (section name keys), and per-section `max` must come from `SectionProvider.default_cap` only (not config-tunable per-section in v1). The `SectionSpec` alias in the issue's API spec collapses to `str`.
- `SessionDigestConfig.sections: list[str]` (default `[]`) reflects this — the dataclass is already correct for the landed schema.

**`session_start.py::handle()` wiring location:**
- Insert the project digest call after Phase 3b (backfill daemon thread start, lines ~114–137) and before Phase 4 (stdout payload composition). This ordering ensures the digest reads already-persisted rows from the previous session (before this session's backfill writes new rows).
- Gate check: `if not feature_enabled(merged_config, "history.session_digest.enabled"): pass` — already follows the `contextlib.suppress(Exception)` best-effort pattern used by Phase 3b.
- Output wiring: append the rendered `<project_context>` block to `stdout_payload` before the `LLHookResult` is built. Plain stdout is the established pattern (no JSON `hookSpecificOutput` wrapper needed — Claude Code ingests plain stdout as session context at `SessionStart`).

**`ll-history-context` CLI restructuring for `--project` mode:**
- `scripts/little_loops/cli/history_context.py::_build_parser()` — `issue_id` is currently a positional required argument (`parser.add_argument("issue_id", ...)`). Adding `--project` requires making it optional: change to `parser.add_argument("issue_id", nargs="?", default=None, ...)` and add mutually exclusive validation (`--project` requires no `issue_id`; no `--project` requires `issue_id`).
- Existing test patterns for the `--project` mode live in `scripts/tests/test_history_context_cli.py` (classes `TestHistoryContextDBMissing`, `TestHistoryContextStaleRows`, `TestDeduplication` as models for the new `TestProjectMode` class).

**Existing `issue_events` data available for `completed_issues` section:**
- `related_issue_events(issue_id, ...)` is per-issue (exact `issue_id =` match). The project-wide `completed_issues` section needs a new query: `SELECT ts, issue_id, transition, issue_type, priority FROM issue_events WHERE transition IN ('done', 'cancelled') AND ts >= ? ORDER BY ts DESC LIMIT ?` — no `WHERE issue_id = ?` filter.

## Implementation Steps

1. Implement the `SECTION_PROVIDERS` registry (3 v1 providers), `project_digest()`,
   and order-aware `render_project_context()` in `history_reader.py` with
   degradation + cap; unit-test in isolation (incl. section ordering/omission).
2. ~~Add the `history.session_digest` config block to `config-schema.json`.~~ **Deferred to ENH-1913** (history namespace owner). The `history.session_digest` schema object is declared in ENH-1913; after it lands, wire runtime reads of these keys here using `ll-config.json` defaults.
3. Wire the gated call into `session_start.py::handle()` — insert after Phase 3b (backfill daemon thread start) and before Phase 4 (stdout payload composition); gate via `feature_enabled(merged_config, "history.session_digest.enabled")`; wrap in `contextlib.suppress(Exception)`; append rendered block to the string that becomes `stdout_payload` (plain stdout pattern — no JSON envelope needed).
4. Add the `ll-history-context --project` inspection mode + its test.
5. Add session-start integration tests (gate on/off, populated/empty/stale) in `test_hook_session_start.py::TestSessionStartProjectDigest`.
6. Doc sweep (ARCHITECTURE / API / CONFIGURATION) — document the section
   registry as the extension point future history-derived consumers register
   into.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add mutual-exclusion guard to `_build_parser()` in `history_context.py`: after `nargs="?"` change, call `parser.error()` when neither `--project` nor `issue_id` is provided — preserves existing `test_missing_issue_id_exits` semantics with updated intent.
8. Update `test_history_context_cli.py::TestArgumentParsing.test_missing_issue_id_exits` to cover the new mutual-exclusion guard (bare invocation still raises `SystemExit`, but via guard not argparse).
9. Update `docs/reference/CLI.md` § `### ll-history-context` — mark `ISSUE_ID` as optional, add `--project` flag row to the flag table.
10. Add new import to `session_start.py`: `feature_enabled` from `little_loops.config.features` (or `HistoryConfig` — pick one consistent with Step 3).

## Impact

- **Priority**: P3 — high-leverage ambient consumer, but not blocking; default-off
  gate means zero risk to existing sessions until explicitly enabled.
- **Effort**: Medium — one aggregation query + formatter + a guarded wiring point;
  read API and degradation pattern already exist.
- **Risk**: Medium — prompt bloat / stale-context on the every-session hot path is
  the explicit EPIC-1707 risk; mitigated by opt-in gate, hard cap, and freshness
  window.
- **Breaking Change**: No — additive, gated, degrades to no-op.

## Related Key Documentation

- EPIC-1707 — history.db as Agent Context Layer (parent)
- ENH-1752 — `history_reader.py` read API + graceful degradation (foundation)
- ENH-1846 / ENH-1847 — `ll-history-context` (issue-scoped sibling consumer)
- FEAT-1263 — SessionStart Context Injector (personal handoff; distinct concern)
- ENH-1830 — background backfill at session start (ordering interaction)
- ENH-1905 — wire effort/velocity history reads into planning skills (a future
  section provider; establishes the `history.*` "config-or-default" pattern)
- ENH-1909 — make planning-skill history injection configurable (sibling
  `history.*` configurability issue; same registry-vs-hardcoded reframe)
- ENH-1911 — quantified evolution triggers from history (a future section
  provider)

## Labels

`captured`, `history-db`

## Resolution

Implemented via workflow:

1. **`history_reader.py`**: Added `SectionProvider` (frozen dataclass), `ProjectDigest` dataclass, three v1 section providers (`touched_files`, `completed_issues`, `recurring_corrections`) with query + render functions, `SECTION_PROVIDERS` registry, `project_digest()` aggregation, and `render_project_context()` with hard char-cap truncation.
2. **`session_start.py`**: Added `feature_enabled` import; gated `project_digest` + `render_project_context` call after Phase 3b (backfill thread launch), wrapped in `contextlib.suppress(Exception)`; appended rendered block to `stdout_payload`.
3. **`cli/history_context.py`**: Made `issue_id` optional (`nargs="?"`), added `--project` flag, mutual-exclusion guard, and `--project` branch calling `project_digest` + `render_project_context` for dry-run inspection.
4. **Tests**: 13 tests in `TestProjectDigest`, 5 in `TestSessionStartProjectDigest`, 4 in `TestProjectMode`, updated `test_missing_issue_id_exits` comment.
5. **Docs**: Updated `ARCHITECTURE.md` (read-path flowchart + components table), `API.md` (new types/functions), `CONFIGURATION.md` (`history.session_digest.*`), `CLI.md` (`--project` flag).

## Session Log
- `/ll:manage-issue` - 2026-06-04T00:47:01 - `auto`
- `/ll:ready-issue` - 2026-06-04T00:28:31 - `8a3dbce6-fa16-4468-9201-91655b6a471f.jsonl`
- `/ll:confidence-check` - 2026-06-03T00:00:00 - `a96a647c-4a09-47e3-b299-433c3979600a.jsonl`
- `/ll:wire-issue` - 2026-06-04T00:00:00 - `auto`
- `/ll:refine-issue` - 2026-06-04T00:17:25 - `783a6b2a-5259-46fe-b4d0-26a6a354c40d.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T21:52:58 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T19:57:40 - `eac7b3fc-572a-4d81-b23d-2d9c91efa16d.jsonl`
- `/ll:capture-issue` - 2026-06-03T19:54:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ada31840-370b-4650-bda9-261f3422cc4a.jsonl`

---

**Open** | Created: 2026-06-03 | Priority: P3
