---
id: FEAT-2315
title: 'll-logs summary: user-facing per-project work digest for target projects'
type: FEAT
priority: P3
status: deferred
captured_at: '2026-06-26T22:05:51Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- EPIC-1918
- ENH-1921
- FEAT-1925
- FEAT-2316
- ENH-2318
labels:
- captured
- ll-logs
- target-project
- digest
depends_on:
- ENH-2317
confidence_score: 91
outcome_confidence: 75
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 22
parent: EPIC-2369
---

# FEAT-2315: `ll-logs summary` — user-facing per-project work digest

## Summary

Add a `ll-logs summary [--window-days N] [--json]` subcommand that produces a
human-readable digest of what the user actually worked on in **their own
project** over a window: sessions, issues touched, files churned, test
pass/fail trend, loops run, and recurring corrections. This is the first
`ll-logs` surface aimed at *target-project users* rather than little-loops
maintainers.

## Current Behavior

`ll-logs` has no user-facing "what happened in my project" view. Every existing
subcommand is either raw plumbing (`extract`, `tail`) or maintainer-meta
introspection on the ll catalog itself (`stats` = ll-skill frequency/error/
correction, `dead-skills`, `scan-failures` against the plugin, `eval-export`).
A developer who installed little-loops in their own repo has no single command
that answers "what did I do this week here?"

## Expected Behavior

`ll-logs summary` (defaulting to the current project — see [FEAT-2316] / [ENH-2317])
prints a compact digest, e.g.:

```
little-loops digest — myproject (last 7 days)
  Sessions:      12 (3 today)
  Issues:        touched BUG-14, FEAT-22; closed FEAT-19
  Files:         48 edits across 9 files (top: src/api.py ×11)
  Tests:         run 31× — 27 pass / 4 fail (last: pass)
  Loops:         rn-remediate ×2, docs-sync ×1
  Corrections:   2 recurring ("use the v2 client", seen 4×)
```

`--json` emits the same data structured for tooling. `--window-days` controls
the window (default from `history.session_digest.days`, currently 7).

## Motivation

`ll-logs` lands flat in target projects because nothing speaks to the user's own
work. A standalone digest gives day-one value with no extra setup and is the
natural at-a-glance complement to `/ll:handoff` / `/ll:resume`. It reuses the
per-project `.ll/history.db` (already populated by the `analytics.capture`
config: `skills`, `cli_commands`, `corrections`, `file_events`) rather than
scanning the global `~/.claude/projects/` corpus, so it is local, portable, and
privacy-safe by default.

## Proposed Solution

- Add `_cmd_summary()` in `scripts/little_loops/cli/logs.py` plus a `summary`
  subparser in `_build_parser()`.
- Source data primarily from `.ll/history.db` (see `session_store.py`) — reuse
  `_aggregate_skill_stats()` for the skill/loop counts and the existing session
  digest config (`history.session_digest`).
- Pull "recurring corrections" the same way the SessionStart hook already
  surfaces them in project context.
- Render a human table by default; gate structured output behind `--json` via
  `add_json_arg`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Data source per digest field** (all from `.ll/history.db`, `SCHEMA_VERSION = 14`
in `scripts/little_loops/session_store.py`):

| Digest field | Source table / helper | Notes |
|---|---|---|
| Sessions (count, today) | `sessions` (`started_at`, `project_path`) | `WHERE started_at >= cutoff`; "today" = count where date == today |
| Issues touched/closed | `issue_events` (`issue_id`, `transition`) or the `issue_sessions` view | closed = transition to the terminal `done` value |
| Files churned | `file_events` (`path`, `op`) | count rows; top file = `GROUP BY path ORDER BY COUNT(*) DESC` |
| Tests run / pass-fail | ⚠ **no `test_events` table** — derive from `cli_events` (`binary`, `args`, `exit_code`); `exit_code == 0` = pass | **Open decision** — see UNKNOWN below |
| Loops run | `loop_events` (`loop_name`, `transition`) — **NOT** `_aggregate_skill_stats()` | the issue's "reuse `_aggregate_skill_stats()` for skill/loop counts" is half-right; that helper reads `skill_events` only, so loops need a separate `GROUP BY loop_name` query |
| Recurring corrections | `history_reader._query_recurring_corrections()` (`history_reader.py:926`) | the same `GROUP BY content … ORDER BY seen_count DESC` query SessionStart uses; reuse via `project_digest(db_path, days=N, sections=["recurring_corrections"])` |

**Config read** — `BRConfig(Path.cwd()).history.session_digest.days` (default `7`,
`scripts/little_loops/config/features.py:712` `SessionDigestConfig`), or
`HistoryConfig.from_dict(merged.get("history", {})).session_digest` against the raw
merged `.ll/ll-config.json` (the path `hooks/session_start.py` uses, lines ~171–184).

**UNKNOWN — test pass/fail data source:** the history schema has no dedicated
test-result table. The implementer must decide whether to (a) parse
`cli_events.exit_code` for rows whose `args` match the configured
`project.test_cmd`, (b) parse `tool_events` Bash invocations, or (c) defer the
"Tests" row until a test-capture mechanism exists. The Expected Behavior sample
("run 31× — 27 pass / 4 fail (last: pass)") assumes this data exists; resolve the
source before building the renderer.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `_cmd_summary(args, logger)` (model after
  `_cmd_stats()`, lines 1169–1233); register a `summary` subparser in
  `_build_parser()` (line 1663, alongside the `stats` block at lines 1763–1792); add
  the `if args.command == "summary": return _cmd_summary(args, logger)` branch in
  `main_logs()` (line 1915).
- `docs/reference/CLI.md` — add a `summary` entry to the `ll-logs` subcommand list
  (section begins ~line 1969).
- `commands/help.md` — extend the one-line `ll-logs` help (~line 293) to mention `summary`.
- `.claude/CLAUDE.md` — add `summary` to the `ll-logs` subcommand inventory in the CLI
  Tools list (~line 227).

### Reused (read-only — no changes needed)
- `scripts/little_loops/cli/logs.py:_aggregate_skill_stats()` (line 698) — returns
  `{skill_name: {"invocations": N, "corrections": M}}` from `skill_events` with a
  `cutoff` filter. Reuse verbatim for the **skill** counts only (see loop caveat above).
- `scripts/little_loops/history_reader.py` — `project_digest()` (line 981),
  `render_project_context()` (line 1018), `_query_recurring_corrections()` (line 926).
- `scripts/little_loops/session_store.py` — `.ll/history.db` schema; `ensure_db()`,
  `connect()`. Tables the digest reads: `sessions`, `issue_events` (+ `issue_sessions`
  view), `file_events`, `loop_events`, `skill_events`, `user_corrections`, `cli_events`.
- `scripts/little_loops/config/features.py` — `SessionDigestConfig` (line 712),
  `HistoryConfig` (line 838).
- `scripts/little_loops/cli_args.py:add_json_arg()` (line 234) — adds `-j/--json`.
- `scripts/little_loops/cli/output.py` — `print_json(data)` and
  `table(headers, rows)` (every cell must be a `str`).

### Dependent / sibling integration
- `scripts/little_loops/hooks/session_start.py` (lines ~171–184) — the canonical
  config-read + `project_digest()` + `render_project_context()` chain to mirror.
- **ENH-2317** (CWD default) — `_cmd_stats` uses a `required=True` mutually-exclusive
  `--project`/`--all` group, so it cannot "default to the current project" as the
  Expected Behavior promises. Either depend on ENH-2317 (CWD defaulting across all
  `ll-logs` subcommands) or have `summary` resolve `Path.cwd()/.ll/history.db` when
  neither flag is supplied.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py` (line 20) — co-imports `_aggregate_skill_stats`
  from `cli/logs.py`. Read-only for this issue (no change needed), but it is the **other
  consumer** of that helper: if the wiring tempts you to alter `_aggregate_skill_stats`'s
  signature for the loop/skill split, this caller must be checked too. Per the issue's
  data-source table, reuse it verbatim for skill counts only and query `loop_events`
  separately — which keeps `ctx_stats.py` untouched. [Agent 1 finding]
- `.loops/ll-logs-telemetry-digest.yaml` — runs `ll-logs` subcommands (`discover`,
  `extract`, `stats`, `scan-failures`, `sequences`, `dead-skills`) as the EPIC-1918
  **maintainer** dogfooding loop. **Do NOT add a `summary` state here.** FEAT-2315 is
  the orthogonal *target-project* surface (see "Relationship to existing issues"); the
  digest is an interactive end-user command, not part of the maintainer telemetry set.
  Noted to forestall scope creep. [Agent 2 finding — scope guard]
- `scripts/pyproject.toml` (line 75) and `.claude-plugin/plugin.json` — the
  `ll-logs = "little_loops.cli:main_logs"` console-script entry point and plugin
  manifest need **no changes**; adding a subparser is internal to `main_logs`.
  Confirmed by Agent 1 — recorded so a future reviewer doesn't re-investigate.

### Tests
- `scripts/tests/test_ll_logs.py` — add `_cmd_summary` tests. Reuse fixture helpers
  `_populate_skill_events()` (~line 1437) and `_insert_correction()` (~line 1458) to
  seed `skill_events`/`user_corrections`; for the other tables, insert via `sqlite3`
  after `ensure_db()`. Tests invoke `main_logs()` directly under
  `patch("sys.argv", [...])`; capture human output with `capsys`, JSON via a
  `builtins.print` side-effect collector then `json.loads("\n".join(captured))`.
- Cover: populated digest (human + `--json`) and the empty-window "no activity" path.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs.py` — for the `file_events`/`issue_events` rows (the
  "insert via `sqlite3`" note above), copy the exact INSERT shape from
  `test_history_reader.py`'s `TestProjectDigest._insert_file_event()` (~line 406:
  `INSERT INTO file_events(ts, session_id, path, op, issue_id, git_sha)`) and
  `_insert_issue_event()` (~line 422:
  `INSERT INTO issue_events(ts, issue_id, transition, issue_type, priority)`).
  Note: `loop_events` has **no `session_id` column** (per `test_history_reader.py`),
  so seed it with only its own columns. [Agent 3 finding]
- `scripts/tests/test_ll_logs.py` — add a no-regression guard test mirroring
  `TestEvalExport.test_no_regression_extract` (~line 3025): run
  `ll-logs extract --help` (or `stats --help`) under `pytest.raises(SystemExit)` and
  assert exit code 0, confirming the new `summary` subparser doesn't break sibling
  subcommands. This is the established convention each time an `ll-logs` subcommand is
  added (`eval-export` did it). [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — add a `DOC_STRINGS_PRESENT` tuple
  (list at line 20, alongside the existing `("commands/help.md", "ll-logs", "ll-logs")`
  at line 45) such as `("commands/help.md", "summary", "FEAT-2315")` so the
  doc-coupling below is *enforced* — without it nothing fails if `summary` is dropped
  from the help one-liner. [Agent 2 finding]
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` exercises `ll-logs discover`,
  `stats --all`, `scan-failures --all` via `from little_loops.cli import main_logs`.
  Optional: add a `ll-logs summary` smoke case here for end-to-end dispatch coverage
  (the primary coverage stays in `test_ll_logs.py`). [Agent 2/3 finding — advisory]

### Documentation
- `docs/reference/CLI.md`, `commands/help.md`, `.claude/CLAUDE.md` (see Files to Modify).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — the `### main_logs` entry (~line 3698) describes the
  subcommand set in its one-line summary; add `summary`. [Agent 2 finding]
- `scripts/little_loops/cli/__init__.py` — module-level docstring (line 15) carries
  the canonical one-line `ll-logs` description; update it to mention `summary`. This
  is the docstring read when the package loads, so it should not drift. [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — `## Session Log Tooling (ll-logs)` section
  (~line 289) lists usage examples (`stats`, `scan-failures`, `dead-skills`); add a
  `summary` example. **Also fix line ~291**, which currently asserts "`ll-logs`
  operates directly on the host's session JSONL files rather than history.db" —
  `summary` is the **first** `ll-logs` subcommand that reads `.ll/history.db`, so that
  blanket framing becomes inaccurate and needs a carve-out. [Agent 2 finding]
- `docs/reference/CLI.md` (~line 2020) — the mutual-exclusion note ("`--all` and
  `--project` are mutually exclusive for `extract`, `sequences`, `stats`,
  `dead-skills`, `scan-failures`, and `eval-export`") must be updated to include
  `summary` **iff** `summary` adopts the same `--project`/`--all` group (see the
  ENH-2317 decision in Dependent / sibling integration). [Agent 2 finding]

## Implementation Steps

1. Define the digest data shape (sessions, issues, files, tests, loops,
   corrections) sourced from the per-project store.
2. Implement `_cmd_summary()` + subparser; default window from config.
3. Human renderer + `--json` renderer; wire into `main_logs()` dispatch.
4. Tests in `scripts/tests/` against a seeded `history.db` fixture.
5. Docs: `docs/reference/CLI.md`, `/ll:help`, CLAUDE.md CLI list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors per step:_

1. **Digest shape** — fields map to the source tables in the data-source table
   above; resolve the test pass/fail source (UNKNOWN) before fixing the shape.
2. **`_cmd_summary()` + subparser** — copy the `_cmd_stats()` body
   (`logs.py:1169–1233`) and the `stats` subparser block (`logs.py:1763–1792`),
   swapping the skill aggregation for the per-field queries.
3. **Renderers + dispatch** — `print_json(...)`/`table(...)` from
   `cli/output.py`; add the `summary` branch to `main_logs()` (`logs.py:1915`).
4. **Tests** — `scripts/tests/test_ll_logs.py`, reusing `_populate_skill_events()`
   / `_insert_correction()` and the `main_logs()` + `capsys`/`print`-collector
   invocation pattern.
5. **Docs** — `docs/reference/CLI.md` (~line 1969), `commands/help.md` (~line 293),
   `.claude/CLAUDE.md` (~line 227).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Extend the **docs set** beyond the three already listed — also update
   `docs/reference/API.md` (`### main_logs` line), `scripts/little_loops/cli/__init__.py`
   (module docstring, line 15), and `docs/guides/HISTORY_SESSION_GUIDE.md`
   (`## Session Log Tooling` section + the "operates directly on session JSONL rather
   than history.db" caveat at ~line 291, which `summary` invalidates).
7. Add a **doc-coupling guard** to `scripts/tests/test_wiring_cli_registry.py`
   (`DOC_STRINGS_PRESENT`, line 20) so `summary` staying documented in `commands/help.md`
   is enforced.
8. Add a **no-regression guard test** in `scripts/tests/test_ll_logs.py` mirroring
   `TestEvalExport.test_no_regression_extract` (~line 3025) — confirms the new subparser
   doesn't break sibling `ll-logs` subcommands.
9. When seeding `file_events`/`issue_events` in tests, copy the INSERT shapes from
   `test_history_reader.py` (`_insert_file_event` / `_insert_issue_event`); remember
   `loop_events` has no `session_id` column.
10. If `summary` adopts the shared `--project`/`--all` group (per the ENH-2317 decision),
    update the mutual-exclusion note in `docs/reference/CLI.md` (~line 2020) to list it.

## Use Case

A developer using little-loops in their app repo runs `ll-logs summary` on Monday
to reconstruct where they left off: which issues moved, which files churned, and
that 4 tests are still red — without grepping logs or opening the issue tracker.

## Acceptance Criteria

- `ll-logs summary` prints a compact, human-readable digest for the current
  project covering: session count (with today's count), issues touched/closed,
  file-edit churn (count + top file), test runs with pass/fail split and last
  result, loops run with counts, and recurring corrections.
- `--window-days N` controls the lookback window; default is read from
  `history.session_digest.days` (currently 7).
- `--json` emits the same data as a structured object (identical fields to the
  human digest) suitable for tooling, gated via `add_json_arg`.
- Data is sourced from the per-project `.ll/history.db` (via `session_store.py`),
  not the global `~/.claude/projects/` corpus.
- The subcommand is wired into both `_build_parser()` and the `main_logs()`
  dispatch.
- Tests in `scripts/tests/` exercise both the human and `--json` renderers
  against a seeded `history.db` fixture.
- An empty window (no sessions in range) renders a graceful "no activity"
  digest rather than erroring.

## Impact

- **Priority**: P3 — User-facing convenience surface with high day-one value for
  target-project users, but not blocking and nothing else depends on it.
- **Effort**: Medium — New subcommand, but reuses existing infrastructure
  (`.ll/history.db`, `_aggregate_skill_stats()`, `add_json_arg`, session-digest
  config) rather than new data plumbing; the work is the digest shape, the two
  renderers, and fixture-based tests.
- **Risk**: Low — Read-only, additive subcommand over an already-populated store;
  no changes to existing `ll-logs` behavior or to the DB schema.
- **Breaking Change**: No.

## Relationship to existing issues

- **EPIC-1918** frames ll-logs telemetry as dogfooding for *ll's own* features
  (skill quality, eval fixtures, dead skills). This issue is the orthogonal
  *target-project* angle — telemetry about the **user's** project — and could
  anchor a sibling epic ("ll-logs for target projects") alongside [FEAT-2316] /
  [ENH-2317].
- **ENH-1921** (`ll-logs stats`, done) aggregates *ll-skill* freq/error/
  correction — a maintainer catalog dashboard. This digest is about the user's
  project activity, not ll-catalog quality. Avoid duplicating; the digest may
  reuse `_aggregate_skill_stats()` internals.
- **FEAT-1925** (done) is an FSM *loop* that composes EPIC-1918 subcommands into
  a periodic maintainer digest. This is an interactive `summary` subcommand for
  end users, not a loop.
- Mind the boundary with `ll-session` (raw SQLite queries) and `ll-history`
  (completed-issue stats) — `summary` is the curated human roll-up across them.


## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The "Dependent / sibling integration" note in this issue's Integration Map leaves open a fork: either depend on ENH-2317 for the `summary` subcommand's CWD default, or implement a bespoke `Path.cwd()/.ll/history.db` resolver. This fork is now closed: this issue adopts ENH-2317's shared three-way resolver (`--project` | `--all` | CWD-default) rather than a bespoke DB-path resolver, ensuring `summary` behaves consistently with the other `ll-logs` subcommands. Implement ENH-2317 first (hence `depends_on: ENH-2317`). The `summary` subcommand should also appear in ENH-2317's `docs/reference/CLI.md` mutual-exclusion note update (~line 2020). Related issue: ENH-2317.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:57 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:confidence-check` - 2026-06-26T23:30:00Z - `bbbde623-e8a1-44fe-8766-f891d466029d.jsonl`
- `/ll:wire-issue` - 2026-06-26T22:48:52 - `5abe280f-1381-4870-967b-c1984b8aafbb.jsonl`
- `/ll:refine-issue` - 2026-06-26T22:39:10 - `0738aae2-208f-4800-b6cb-aef4cfec50d1.jsonl`
- `/ll:format-issue` - 2026-06-26T22:26:51 - `603866f5-8095-4955-b453-410ab44be55e.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:05:51Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afe96ddb-ff74-49fc-b0a9-7bd525432c1d.jsonl`

---

## Status

- [ ] open
