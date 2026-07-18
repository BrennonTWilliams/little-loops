---
id: FEAT-2665
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T02:50:02Z'
completed_at: '2026-07-18T04:04:15Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
parent: EPIC-2663
relates_to:
- ENH-2664
- ENH-2666
- ENH-2533
- FEAT-1680
blocked_by:
- ENH-2664
labels:
- loops
- issue-lifecycle
- observability
confidence_score: 96
outcome_confidence: 83
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 22
---

# FEAT-2665: Cross-run resurfacing/triage for automation-deferred issues

## Summary

Provide a cross-run mechanism that surfaces automation-deferred issues back to a
human for triage, so issues that fail an automated readiness/remediation gate
don't disappear from the backlog. This is the direct fix for the ENH-2464 /
ENH-2465 / ENH-2466 drop.

## Use Case

After `rn-implement-20260717T165621` deferred ENH-2464, ENH-2465, and ENH-2466,
they vanished from every default view and no run ever brought them back. A
maintainer wants a single command (and/or an end-of-run + session-end report)
that answers: *"what did automation set aside, why, and how long ago?"* — so they
can re-open, re-scope, or intentionally close each one.

## Current Behavior

- `deferred` is excluded from active selection (`sprint.py:15` — active is
  `{open, in_progress, blocked}`) and from default listings
  (`issue_parser.py:1250` skips `done/cancelled/deferred`).
- The only auto-resurfacing, `re_enqueue_unblocked` (rn-implement.yaml:782),
  runs *within a single run* and only for `blocked_by` reasons.
- The sole manual path is `ll-issues list --status deferred`, which does not
  distinguish automation from human deferral and has no staleness/aging view.

## Expected Behavior

- A triage surface listing `deferred_by: automation` issues (from ENH-2664) with
  `deferred_reason` and age, sorted so the "remediation stalled" class ranks
  highest.
- Delivery options (decide during refinement): a dedicated CLI
  (`ll-issues deferred-triage` or a `list` flag), a session-end sweep/report
  (precedent: FEAT-1680's session-end status sweep), and/or an rn-implement
  end-of-run callout referencing the parked set.

## Acceptance Criteria

- `ll-issues deferred-triage` (or equivalent report path) lists every issue
  with `status: deferred` and `deferred_by: automation`, showing
  `deferred_reason` and age-since-`deferred_date`, with `remediation_stalled`
  entries ranked above `blocked_by_unmet` entries.
- Issues with `deferred_by: human` (or no `deferred_by` at all) are excluded
  from the triage output.
- The rn-implement end-of-run report names any issues it parked during that
  run (Step 3), and `summary.json` gains a `deferred_automation` breakdown
  without dropping any existing keys.
- A test fixture with `deferred_by: automation` appears in the triage output;
  an otherwise-identical `deferred_by: human` fixture does not.

## API/Interface

- New read-only reporting command or flag; no change to selection semantics.
- Consumes the frontmatter fields defined by ENH-2664.

## Implementation Steps

1. Query issues with `status: deferred` + `deferred_by: automation`, joining reason + age.
2. Render a triage report (CLI + optional session-end hook).
3. Wire an rn-implement end-of-run callout naming the parked issues (complements ENH-2533's summary.json).
4. Tests: a deferred-by-automation fixture appears in the triage output; human-deferred does not.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 query gap**: `find_issues()`'s default filter (`issue_parser.py:1249-1251`) skips
  `deferred` issues entirely — the triage query must call `find_issues(config,
  status_filter={"deferred"})` to bypass that exclusion. `IssueInfo`
  (`issue_parser.py`, class at line 551) does **not** carry `deferred_by` /
  `deferred_reason` / `deferred_date` as dataclass fields, so the triage code must
  re-parse frontmatter per-file the same way `show.py` does (`show.py:202-205`
  reads `deferred_reason`/`deferred_date` via `frontmatter.get(...)` — note
  `show.py` never reads `deferred_by`, so this triage command would be the first
  consumer of that field).
- **Age computation**: reuse the existing idiom rather than writing a new one —
  `issue_progress.py:_issue_age_days()` (lines 51-64) backed by
  `cli/issues/search.py:_parse_discovered_date()` (lines 21-54) already implements
  ISO-datetime-with-`Z`-strip parsing + mtime fallback for `captured_at` /
  `discovered_date`. The "age since deferred" metric should parse `deferred_date`
  the same way.
- **Step 2 CLI shape**: the established pattern for a new `ll-issues` report
  subcommand is `add_<name>_parser(subs)` + `cmd_<name>(config, args)` in its own
  file under `scripts/little_loops/cli/issues/`, wired into
  `cli/issues/__init__.py` (see `add_epic_progress_parser` registration at line
  827, dispatch at lines 891-892). `epic_progress.py`/`impact_effort.py` also show
  the `--format text/json/markdown` (or `--json`) convention, `colorize()` +
  `TYPE_COLOR` for issue-ID coloring, and `print_json()` for the JSON branch — all
  from `cli/output.py`. `impact_effort.py:_render_quadrant_lines()` shows a
  per-group capped table with `"… +N more"` truncation, directly reusable for
  grouping by `deferred_reason`.
- **Step 2 session-end hook (optional path)**: precedent is
  `hooks/sweep_stale_refs.py:handle()` (lines 141-205) — registered via
  `hooks/__init__.py:_dispatch_table()` (`"session_end": sweep_stale_refs.handle`,
  line 92) and `hooks/hooks.json`. Note this handler is actually registered under
  the `SessionStart` array (not `SessionEnd`) because Claude Code enforces a hard
  ~1.5s kill ceiling on `SessionEnd` hooks that a full-tree `.issues/` scan can
  exceed (upstream bug anthropics/claude-code#32712, #41577) — any new
  session-hook variant of this triage report inherits the same constraint and
  should follow the same `SessionStart`-registration workaround. Handler always
  returns `exit_code=0` (advisory-only, wrapped in `try/except Exception:
  return LLHookResult(exit_code=0)`); never blocks.
- **Step 3 rn-implement callout**: `mark_deferred`
  (`loops/rn-implement.yaml:1330-1362`) already stamps the fields this step reads
  — its comment at lines 1356-1359 explicitly names FEAT-2665 as the intended
  consumer. The end-of-run `report` state (lines 1423-1631) currently writes
  `summary.json` (assembled lines 1587-1606, written at line 1608) with only an
  aggregate `"deferred": DEFERRED` count, no per-issue `deferred_by`/`deferred_reason`
  breakdown or listing — the new callout should extend this state (or add a new
  pre-`done` state with the same `action_type: shell` + Python heredoc shape) to
  read parked-issue frontmatter and print/emit the named list, complementing
  rather than duplicating the existing count.
- **Cross-run gap this closes**: the only existing re-surfacing mechanism,
  `re_enqueue_unblocked` (`rn-implement.yaml:782`), operates purely on a
  run-scoped `deferred.txt`/`queue.txt` pair under `${context.run_dir}` and never
  touches issue frontmatter to un-defer — once a run ends, anything still in
  `deferred.txt` (`remediation_stalled`, or unresolved `blocked_by_unmet`) is
  discoverable only via its persisted `status: deferred` frontmatter, with no
  cross-run scan bringing it back to attention. This is the exact gap FEAT-2665
  targets.
- **Test patterns**: `test_issues_cli.py`'s `TestIssuesCLIEpicProgress` (~lines
  5812-5989) shows the CLI-report test shape (`sys.argv` patch + `main_issues()`,
  `capsys` assertions, text + JSON variants). `test_sweep_stale_refs.py` shows the
  session-hook test shape (direct `LLHookEvent` invocation, baseline/detection
  test-class split) for the optional Step 2 hook path.

_Wiring pass added by `/ll:wire-issue`:_
- **`summary.json` extension is additive-safe**: `test_rn_implement.py`'s
  `test_report_preserves_existing_scalar_keys` (~line 516) is a *subset* check
  (`missing = expected_keys - set(summary.keys())`), not an exact-equality
  check — no test in the suite asserts `set(summary.keys()) == {...}`. Adding a
  new top-level key (e.g. `deferred_automation`) for the Step 3 end-of-run
  callout will not break existing `report`-state coverage.
- **`find_issues()` needs no signature change**: it already accepts
  `status_filter: set[str] | None = None`
  (`issue_parser.py`) — `find_issues(config, status_filter={"deferred"})` is
  directly usable as-is; the triage command still filters the returned
  `IssueInfo` list in Python for `deferred_by == "automation"` post-call, since
  `find_issues()` has no `deferred_by` query param.
- **`deferred_by` enum lives in `issue_lifecycle.py`**: `DeferBy` (with
  `AUTOMATION = "automation"`) is the enum backing the `--by` stamping the
  triage command reads — not previously named in this issue's Integration Map.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/deferred_triage.py` (new) — the triage
  report subcommand (`add_deferred_triage_parser` + `cmd_deferred_triage`),
  following the `epic_progress.py` shape.
- `scripts/little_loops/cli/issues/__init__.py` — register the new subparser
  (pattern: `add_epic_progress_parser(subs)` call at line 827) and dispatch
  branch (pattern: lines 891-892).
- `scripts/little_loops/loops/rn-implement.yaml` — extend the `report` state
  (lines 1423-1631) to add the parked-issues end-of-run callout alongside the
  existing `summary.json` write at line 1608.
- `scripts/little_loops/hooks/` (optional) — new session-hook handler
  mirroring `sweep_stale_refs.py`, if the session-end delivery option is
  implemented; would need registration in `hooks/hooks.json` and
  `hooks/__init__.py:_dispatch_table()`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:1249-1251` — `find_issues()` default
  filter excludes `deferred`; triage query must pass `status_filter={"deferred"}`.
- `scripts/little_loops/sprint.py:15` — `_ACTIVE_STATUSES` excludes `deferred`;
  unaffected by this read-only feature.
- `scripts/little_loops/cli/issues/show.py:202-205,390,393,515-516` — reads
  `deferred_reason`/`deferred_date` but not `deferred_by`; the triage command is
  the first consumer of `deferred_by`.
- `scripts/little_loops/loops/rn-implement.yaml:1330-1362` (`mark_deferred`) —
  the write-side counterpart; its comment at lines 1356-1359 already names
  FEAT-2665 as the intended reader of these fields.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — defines the `DeferBy` enum
  (`AUTOMATION = "automation"`) that backs the `deferred_by` value the triage
  query filters on.

### Similar Patterns
- `scripts/little_loops/cli/issues/epic_progress.py` — canonical `ll-issues`
  report-subcommand shape (`add_epic_progress_parser` + `cmd_epic_progress`,
  `--format text/json/markdown`).
- `scripts/little_loops/issue_progress.py:_issue_age_days()` (51-64) +
  `cli/issues/search.py:_parse_discovered_date()` (21-54) — reusable
  age-computation idiom to compute "days since deferred" from `deferred_date`.
- `scripts/little_loops/cli/issues/impact_effort.py:_render_quadrant_lines()` —
  per-group capped table rendering with `"… +N more"` truncation, reusable for
  grouping rows by `deferred_reason`.
- `scripts/little_loops/hooks/sweep_stale_refs.py:handle()` (141-205) —
  session-hook precedent (FEAT-1680), including the `SessionStart`-registration
  workaround for the `SessionEnd` kill-ceiling bug.

### Tests
- `scripts/tests/test_issues_cli.py::TestIssuesCLIEpicProgress` (~5812-5989) —
  CLI report test pattern to model the new triage command's tests after.
- `scripts/tests/test_sweep_stale_refs.py` — session-hook test pattern
  (baseline/detection test-class split) for the optional hook path.
- `scripts/tests/test_set_status_cli.py` — deferred-stamping fixture patterns.
- `scripts/tests/test_rn_implement.py` — existing `mark_deferred` coverage to
  extend for the new end-of-run callout.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py` — existing coverage of `find_issues()`'s
  default deferred-exclusion filter; model for a `status_filter={"deferred"}`
  test case backing the Step 1 query gap.
- `scripts/tests/test_issue_lifecycle.py` — covers the `DeferBy` enum; relevant
  if the triage command validates/normalizes `deferred_by` values.

### Documentation
- `docs/reference/CLI.md` — documents `set-status --by/--reason`; needs a new
  `#### \`ll-issues deferred-triage\`` entry for the triage subcommand once
  implemented.
- `.claude/CLAUDE.md` § Issue File Format — already documents
  `deferred_by`/`deferred_reason`/`deferred_date` semantics (ENH-2664).

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` § CLI Tools — a *separate* location from § Issue File
  Format: the `ll-issues` bullet's parenthetical subcommand list needs
  `deferred-triage` added, following the existing pattern for other listed
  subcommands.
- `docs/reference/API.md` — has two listings needing a new entry: the
  `main_issues` **Sub-commands** summary table, and a matching
  `#### deferred-triage` per-command detail section (pattern: `#### next-issue`).
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (optional) — documents the
  `deferred` status under "Frontmatter `status` Values" but doesn't currently
  mention `deferred_by`/automation-vs-human deferral or triage; a note near
  that section would keep it in sync.

## Impact

- **Priority**: P2 — closes the loop that silently dropped real backlog issues.
- **Effort**: Medium.
- **Risk**: Low — read-only surfacing; depends on ENH-2664's fields.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented per the plan (skipped the optional session-end hook delivery path — not in
Acceptance Criteria, and every `mark_deferred` deferral is automation-deferred by
construction so no cross-run frontmatter re-read was needed for Step 3):

- `scripts/little_loops/cli/issues/deferred_triage.py` (new): `ll-issues deferred-triage`
  (alias `dt`), `--format text/json/markdown`. Reads `deferred_by`/`deferred_reason`/
  `deferred_date` frontmatter directly (via `parse_frontmatter`, matching `show.py`'s
  idiom), filters to `deferred_by: automation`, sorts `remediation_stalled` before
  `blocked_by_unmet` (then oldest-first).
- `scripts/little_loops/cli/issues/__init__.py`: registered the new subcommand.
- `scripts/little_loops/loops/rn-implement.yaml`: `mark_deferred` now writes a
  `deferred_reason_<ID>.txt` sidecar; `report` aggregates those sidecars into
  `summary.json["deferred_automation"]` (`count`, `by_reason`, `issues`) and prints an
  end-of-run callout naming parked issues, pointing at `ll-issues deferred-triage`.
- Tests: `TestIssuesCLIDeferredTriage` (5 cases: automation-only listing, ranking, age
  rendering, JSON shape, empty state) and 3 new `test_rn_implement.py` cases (sidecar
  write, breakdown aggregation, empty-sidecar case).
- Docs: `docs/reference/CLI.md`, `docs/reference/API.md`, `.claude/CLAUDE.md` § CLI
  Tools, `docs/guides/ISSUE_MANAGEMENT_GUIDE.md`.

Verification: full suite (`python -m pytest scripts/tests/`) — 15222 passed, 37 skipped;
`ruff check scripts/` clean; `python -m mypy scripts/little_loops/` clean (252 files);
`ll-loop validate rn-implement` valid.

## Session Log
- `/ll:manage-issue` - 2026-07-18T04:03:33Z - `6b279910-6e61-4e9e-8fab-6e6304df8cc2.jsonl`
- `/ll:ready-issue` - 2026-07-18T03:47:15 - `79f00b68-1a38-4353-8f1f-3dded249ab3a.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `c156078d-6ee4-4f97-bbe5-872d4b271587.jsonl`
- `/ll:wire-issue` - 2026-07-18T03:42:20 - `09d49d43-1ae4-4daf-b4e0-b02aa5eaa028.jsonl`
- `/ll:refine-issue` - 2026-07-18T03:34:03 - `476fbc25-0568-4edf-a4f4-a9566f6182c3.jsonl`
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18
