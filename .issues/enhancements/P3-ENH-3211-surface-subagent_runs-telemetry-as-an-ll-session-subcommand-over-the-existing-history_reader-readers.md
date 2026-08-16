---
id: ENH-3211
type: ENH
title: Surface subagent_runs telemetry as an ll-session subcommand over the existing
  history_reader readers
priority: P3
status: blocked
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:42Z'
relates_to:
- ENH-3210
- FEAT-3183
depends_on:
- ENH-3210
blocked_by:
- FEAT-3183
confidence_score: 95
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3211: Surface subagent_runs telemetry as an `ll-session` subcommand over the existing history_reader readers

## Summary

ENH-2505 added `subagent_runs` plus three readers in `history_reader.py` —
`subagent_tree` (`:1573`), `subagent_retries` (`:1604`), and `subagent_budget`
(`:1638`) — but nothing consumes them. A repo-wide search finds the only callers in
`scripts/tests/test_enh_2505_subagent_runs.py`; no CLI exposes them, and neither
`ll-auto` nor the FSM executor reads the table. The data is write-only telemetry.

Consequence: answering "how many subagents did this run spawn, and did they all
finish?" requires a manual `sqlite3 .ll/history.db` query. Orphan rate (see the
companion stale-row reconciliation issue) is invisible, as is per-agent retry churn
and time budget — all three of which the readers already compute.

Proposed solution: a read-only CLI view over the existing readers.

**Host — settled: `ll-session`, not `ll-logs`/`ll-history`.** The capture-time sketch
named `ll-logs`/`ll-history`; refinement showed neither fits. `ll-history` is
issue-analytics domain (`issue_history` functions), unrelated to session telemetry. Every
existing `ll-logs` subcommand aggregates a JSONL corpus over `--all`/`--project`/
`--window-days`, so a single-session SQL lookup would break its flag convention. Neither
imports `history_reader.py` at all. `ll-session` (`cli/session.py`) is the only CLI that
wraps `history_reader` readers end-to-end, and it already exposes raw rows from this very
table via `ll-session recent --kind subagent_run` (`docs/reference/CLI.md:3359,3441`).
Leaving the host open adds review risk with no upside — it is fixed here.

**Argument shape — settled: positional, not `--session`/`--agent` flags.** This codebase
uses a required positional for single-target lookups (`cli/session.py:105`;
`ll-history sessions ISSUE_ID`). No `--session`/`--agent`/`--budget` flag exists anywhere
in this CLI surface. Sketch:

- `ll-session subagents <SESSION_ID>` — spawn tree (`subagent_tree`): agent_type,
  duration, status
- `ll-session subagents <SESSION_ID> --budget` — spawn count + summed duration
  (`subagent_budget`)
- `ll-session subagent-retries <AGENT_TYPE> [--since ...]` — repeat-spawn rollup
  (`subagent_retries`; its existing `since` kwarg is currently unsurfaced)
- `--json` via the shared `add_json_arg()` helper, matching sibling subcommands

**Delta vs. what already exists** (state this explicitly so it isn't re-litigated at
review): `ll-session recent --kind subagent_run` dumps raw recent rows with no session
scoping, no tree grouping, no duration/count rollup, and no retry aggregation. The three
readers already compute all four; this issue surfaces them. If the delta is judged too
thin, the honest alternative is to close this and fold the need into FEAT-3183 — see
Scope Boundaries.

Scope note: surface only — it must not change the writers, the hooks, or the schema.


## Current Behavior

Reader line numbers throughout this issue were re-verified 2026-08-15 against
`history_reader.py` (`subagent_tree` :1573, `subagent_retries` :1604,
`subagent_budget` :1638) — the capture-time citations had drifted and are corrected.

`subagent_tree(session_id, *, db=DEFAULT_DB_PATH) -> list[SubagentRun]` returns only
direct-child spawns (no grandchild recursion — a subagent's own spawns live in its
nested transcript, not a joinable `sessions` row). `subagent_retries(agent_type, *,
since=None, db=...) -> list[dict]` returns one `{"parent_session_id", "spawn_count"}`
dict per session that spawned that `agent_type` more than once — it already accepts an
optional `since` bound nothing currently surfaces as a flag. `subagent_budget(session_id,
*, db=...) -> dict | None` returns `{"spawn_count", "total_duration_s"}` or `None` when
the session has no subagent rows; duration only sums rows with both `started_at` and
`ended_at` set, so still-running/orphaned rows are excluded from the sum but counted in
`spawn_count`. All three flow through `_connect_readonly()` (`:420`) and degrade to
`[]`/`None` on a missing DB or `sqlite3.Error` rather than raising.

Neither `ll-logs` (`cli/logs.py`) nor `ll-history` (`cli/history.py`) currently imports
`history_reader.py` at all — `ll-logs`'s existing subcommands query `history.db` via raw
hand-written SQL or parse JSONL logs directly, and `ll-history` is issue-analytics
domain (`issue_history` functions), unrelated to session/event telemetry. The actual
reader-wrapping pattern lives in `ll-session` (`cli/session.py`), which is not named in
the issue's `ll-logs`/`ll-history` sketch.

## Expected Behavior

An operator can answer "how many subagents did this run spawn, and did they all
finish?" from a CLI command instead of a manual `sqlite3` query, using the data the
three existing readers already compute.

## Motivation

The readers are fully implemented and tested (`test_enh_2505_subagent_runs.py`) but have
exactly one caller — the test file itself. Orphan rate (ENH-3210), retry churn, and
time budget are all invisible today despite the query logic existing.

## Proposed Solution

Wrap the three readers using the pattern `ll-session`'s `related`/`recent` subcommands
already establish end-to-end (`cli/session.py`): reader call → `if args.json:
print_json(...)` (via `dataclasses.asdict` for `SubagentRun` rows; `subagent_retries`/
`subagent_budget` are already plain dicts, so no `asdict` needed there) → else a
human-readable fallback.

**Required display rule (do not omit).** `subagent_budget` sums duration only over rows
having *both* `started_at` and `ended_at`, but counts every row in `spawn_count`. So any
`running`/`orphaned` row silently understates the reported duration. The output must show
the excluded-row count alongside the total — e.g.
`spawn_count=12  total_duration_s=430.2  (2 rows excluded: no ended_at)`. Post-ENH-3210
those excluded rows are exactly the `orphaned` ones, which makes this the operationally
interesting number, not a footnote.

Remaining shape: the fallback carries an explicit "No subagent runs found" message on empty
results (the established empty-result convention — `cli/session.py`'s `related`
subcommand, `cli/history.py`'s `sessions` subcommand), in the exact two-part template
`print(f"No {noun} found for {id}.")` — so `"No subagent runs found for {session_id}."`,
with the `for …` suffix, not the bare string from the capture-time sketch.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/session.py` — closest existing end-to-end wrapping
  pattern to extend or model a new subcommand after: `--db` arg (:94-100),
  `related`/`recent` subparsers and dispatch (:158-163/:445-462, :120-156/:464-516)
- `scripts/little_loops/cli/logs.py` / `cli/history.py` — **not modified**; both were
  rejected as hosts (see Summary). Retained here only as the `_cmd_*`-per-subcommand
  convention reference (`logs.py:_build_parser()` :2065, `main_logs()` dispatch
  :2295-2351).

### Dependent Files (Confirmed Sole Caller)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh_2505_subagent_runs.py:16` — confirmed via repo-wide search as
  the only current importer of `subagent_tree`/`subagent_retries`/`subagent_budget`; no
  other CLI, hook, or automation code reads `subagent_runs` today [Agent 1 finding]

### Dependent Files (Existing Readers to Wrap)
- `scripts/little_loops/history_reader.py` — `subagent_tree()` (:1573),
  `subagent_retries()` (:1604), `subagent_budget()` (:1638), `SubagentRun` dataclass
  (:289), `_row_to_dataclass()` (:437), `_connect_readonly()` (:420)
- `scripts/little_loops/cli_args.py` — `add_json_arg()` (:324), `add_window_args()`
  (:289) — shared flag-registration helpers used across both `ll-logs` and `ll-history`
- `scripts/little_loops/cli/output.py` — `print_json()` (:227), `table()` (:299)
- `scripts/pyproject.toml` — entry-point registrations: `ll-history` (:79), `ll-logs`
  (:95)

### Conventions in Force
- `--json`/`-j` is added via the shared `add_json_arg()` helper on every subcommand that
  supports it, not a hand-rolled `add_argument` (one exception: `ll-history summary`
  predates the helper and still hand-rolls it — not a pattern to copy).
- Single-target lookups (a session ID, an issue ID) use a required **positional**
  argument, not a `--flag <value>` — evidence: `cli/session.py:105`
  (`session_id`, positional), `ll-history sessions ISSUE_ID`. No `--session`/`--agent`/
  `--budget` flag exists anywhere in `ll-logs`/`ll-history` today.
- JSON output: `print_json([asdict(r) for r in rows])` when the reader returns
  dataclasses (`sessions_for_issue`/`subagent_tree` both do); `print_json(rows)` directly
  when it already returns plain dicts (`subagent_retries`/`subagent_budget` both do —
  no `asdict` call needed for those two).
- Text output for row-oriented multi-record results uses either `table()` (`ll-logs
  stats`) or plain `key=value` `print()` lines (`ll-session related`/`recent`) — both
  conventions coexist; neither is exclusively "the" pattern.
- Empty-result text output is always an explicit one-line message ("No sessions found
  for X.") before any populated-loop branch, never a silent empty print.
- Reader imports in `main_history()`/`main_logs()` are function-local (inside the
  dispatching `if args.command == ...` branch), not module-top — `test_cli_history.py`'s
  docstring notes this is deliberate so test mocks target the source module
  (`little_loops.history_reader.*`), not the CLI module.

### Tests
- `scripts/tests/test_cli_history.py` — direct `main_history()` invocation via
  `patch.object(sys, "argv", [...])` + `patch("pathlib.Path.cwd", ...)`, `capsys` for
  text assertions, `json.loads(captured.out)` for `--json` assertions; no
  CliRunner/subprocess harness anywhere in this codebase's CLI tests
- `scripts/tests/test_enh_2505_subagent_runs.py` — the only current caller of the three
  readers; a new CLI test would sit alongside this, seeding via
  `record_subagent_run_start`/`record_subagent_run_stop` against a `tmp_path` db

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_session.py` — the actual closest test file if `cli/session.py`
  is the chosen host (more likely than `ll-history`/`ll-logs` per the issue's own refined
  analysis): `TestArgumentParsing::test_related_arg_parsing` (:446, argparse-only) and
  `TestMainSession::test_related_outputs_events`/`test_related_no_match`/
  `test_related_json_output` (:452/:464/:471, integration via `patch("sys.argv", ...)` +
  `capsys`) are the exact shape to mirror for a new `subagent`-style subcommand
  [Agent 3 finding]
- Exact empty-result convention confirmed: `print(f"No {noun} found for {id}.")` —
  e.g. `cli/session.py:476` (`"No sessions found for {issue_filter}."`),
  `cli/history.py:412` (`"No sessions found for {args.issue_id}."`); the issue's own
  Proposed Solution sketch ("No subagent runs found") needs the `for {session_id}` suffix
  to match this established two-part template [Agent 2 + Agent 3 finding]
- Confirmed no test in `test_cli_history.py`, `test_ll_logs.py`, or `test_ll_session.py`
  enumerates the full subcommand set for any host — adding a new subcommand anywhere is
  purely additive, no existing test breaks [Agent 3 finding]
- `ll-session recent --kind subagent_run` (`docs/reference/CLI.md:3359,3441`) already
  exposes raw `subagent_runs` rows via the generic `recent` dispatcher (ENH-2505); the new
  subcommand's naming should stay consistent with this established `subagent_run`
  vocabulary already live in the same CLI surface [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` — the new subcommand is documented under `### ll-session`
  (`:3294-3482`): a row in the subcommand table (`:3306-3321`), a flags table modeled on
  ``**`recent` flags:**`` (`:3355-3363`), and entries in the Examples block
  (`:3431-3471`). The host is settled; the `ll-logs`-vs-`ll-history` question this line
  previously deferred is closed.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — exact section locations, by candidate host: `### ll-history`
  (`:2752-2896`, new subcommand would slot after `#### ll-history sessions <ISSUE_ID>`
  `:2850-2864`, plus the consolidated `**Examples (all subcommands):**` block
  `:2865-2876`); `### ll-session` (`:3294-3482`, subcommand table `:3306-3321`, a
  dedicated flags table like `**`recent` flags:**` `:3355-3363`, Examples block
  `:3431-3471`); `### ll-logs` (`:3113-3292`) is flagged as a poor structural fit — every
  existing `ll-logs` subcommand aggregates a JSONL log corpus (`--all`/`--project`/
  `--window-days`), not a single-session SQL lookup, so a `subagents` subcommand there
  would break that flag convention [Agent 2 finding]
- `skills/analyze-history/SKILL.md:36-108` — the one skill documenting `ll-history`
  subcommands in a `| "question" | command |` table; if the new subcommand lands under
  `ll-history`, this is the sibling convention for adding a row (optional — its scope is
  issue-history analytics, not session/event telemetry, so not a hard requirement)
  [Agent 2 finding]
- `docs/reference/API.md:7825-7846` — documents `SubagentRun`'s field shape and the three
  reader signatures in prose; optional one-line addition noting the new CLI consumer
  (reader contract itself is unchanged) [Agent 2 finding]

### Configuration
- N/A — read-only surface, no config knob

## Program Design

### Types
No new dataclass. `SubagentRun` (`history_reader.py:289-305`) already carries every
field a `--session` tree view needs; `subagent_retries`/`subagent_budget` already
return plain dicts.

### Signatures
`subagent_tree(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> list[SubagentRun]`

The other two readers this issue wraps share the same `db`-keyword shape:
`subagent_retries(agent_type: str, *, since: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> list[dict]`
and `subagent_budget(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> dict | None`.

### Call Path
`main_session()` subcommand dispatch (`cli/session.py`, alongside the existing
`related`/`recent` branches) `->` one of the three `history_reader.py` readers above
`->` `print_json()`/`table()`/plain `print()` (`cli/output.py`).

(Corrected 2026-08-15: this previously named `main_logs()`/`main_history()`, contradicting
the Summary's settled decision that `ll-session` is the host. Both of those CLIs are
explicitly **not** modified — see Files to Modify.)

### Decision Rules
N/A — no new gate, threshold, or classification rule; this issue wires existing
read-only queries to a CLI surface, it does not introduce new decision logic.

## Impact

- **Priority**: P3 — operator convenience over data that already exists and is already
  partly reachable via `ll-session recent --kind subagent_run`. See the FEAT-3183 overlap
  question in Scope Boundaries before scheduling.
- **Effort**: Small — three reader calls wrapped in an existing CLI's established
  subparser/dispatch pattern; no new queries, no schema, no writers.
- **Risk**: Low — purely additive read-only subcommand. Sequencing is the real risk:
  shipped before ENH-3210, it prints 40 orphaned rows as `running`.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Blocked** | Created: 2026-08-16 | Priority: P3 | Blocked on: FEAT-3183 (overlap call);
depends on ENH-3210 (`orphaned` status must exist first)

## Current Pain Point

`subagent_tree`, `subagent_retries`, and `subagent_budget` are fully implemented and
tested but have exactly one caller each: `test_enh_2505_subagent_runs.py`. Answering a
basic operational question about a session's subagent spawns requires a manual
`sqlite3 .ll/history.db` query today.

## Success Metrics

A CLI command exists that answers "how many subagents did session X spawn, and did they
all finish?" without a manual sqlite query, using the existing readers unmodified.

## Scope Boundaries

Per the Summary's own scope note: surface only. Does not touch
`record_subagent_run_start`/`record_subagent_run_stop`, the `SubagentStart`/
`SubagentStop` hooks, or the `subagent_runs` schema.

**Blocking overlap with FEAT-3183 — status set to `blocked` 2026-08-15.** FEAT-3183
(P1, `open`, "Local agent quality report over history.db") already plans to consume
`subagent_runs.status`/`started_at`/`ended_at` as a retry-inflation signal (~line 130 of
that issue). That is two surfaces over the same table, one P1 and one P3. The options
are:

1. Ship this as the low-level per-session inspector; FEAT-3183 remains the aggregate
   quality report. Both survive, with this issue explicitly *not* doing rollup analytics.
2. Fold this into FEAT-3183 and cancel this issue (`cancelled` + `supersedes: [ENH-3211]`
   on FEAT-3183), if FEAT-3183's report already answers the operator question.

**Resolution: defer the call until FEAT-3183 lands, rather than making it now.** The
choice turns entirely on what FEAT-3183's report actually outputs, which does not exist
yet — deciding now means guessing at a P1's eventual surface in order to schedule a P3.
Once FEAT-3183 is implemented, the question answers itself in minutes: run its report and
check whether "how many subagents did session X spawn, and did they all finish?" is
already answerable. Hence `blocked_by: FEAT-3183` (a scheduling block, not a technical
dependency — nothing here needs FEAT-3183's code).

Do not implement before this is answered — option 2 makes the whole issue wasted work.

## Backwards Compatibility

No breaking change — this is a new, additive CLI subcommand. No existing `ll-logs` or
`ll-history` subcommand's behavior changes.

## API/Interface

`subagent_tree(session_id: str, *, db: Path | str = DEFAULT_DB_PATH) -> list[SubagentRun]`

## Implementation Steps

0. The FEAT-3183 overlap question in Scope Boundaries is answered. If option 2, stop —
   cancel this issue rather than implementing it.
1. ENH-3210 has landed (`depends_on`), so the `orphaned` status exists and the command
   does not report orphaned spawns as `running`.
2. The subcommand lands in `ll-session` (`cli/session.py`) — settled, not an implementer
   choice — and its session/agent-type lookup argument is a **positional**, following
   `cli/session.py:105`, not a `--session`/`--agent` flag pair.
3. `--json` output uses `print_json([asdict(r) for r in rows])` for `subagent_tree`
   (dataclass rows) and `print_json(rows)` directly for `subagent_retries`/
   `subagent_budget` (already plain dicts) — matching the asdict-only-for-dataclasses
   convention observed across `cli/session.py`/`cli/history.py`.
4. The `--budget` output reports the count of rows excluded from `total_duration_s`
   (those with no `ended_at`) alongside the total, so the duration is never silently
   understated — post-ENH-3210 those are exactly the `orphaned` rows.
5. `python -m pytest scripts/tests/test_enh_2505_subagent_runs.py scripts/tests/test_ll_session.py -v`
   and the new CLI test all pass, including an empty-result case that prints
   `"No subagent runs found for {session_id}."` rather than nothing, and a case with an
   `ended_at IS NULL` row asserting the excluded-count is shown.


## Session Log
- `/ll:wire-issue` - 2026-08-16T02:33:17 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:24:46 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:52 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
