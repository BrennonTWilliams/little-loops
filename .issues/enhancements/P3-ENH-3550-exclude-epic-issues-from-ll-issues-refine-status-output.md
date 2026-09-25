---
id: ENH-3550
type: ENH
title: Exclude EPIC issues from ll-issues refine-status output
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:17:10Z'
completed_at: '2026-09-25T00:23:04Z'
confidence_score: 100
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3550: Exclude EPIC issues from ll-issues refine-status output

## Summary

`ll-issues refine-status` should exclude EPIC issues from its output (table, `--json`, `--format json`). EPICs are containers decomposed into child BUG/FEAT/ENH issues; they are not refined through the per-issue refinement pipeline, so their rows (and command-touch counts) are noise in a refinement-depth table.

## Current Behavior

- `cmd_refine_status` (`little_loops.cli.issues.refine_status`) loads every active issue via `find_issues`, EPICs included. The full list then drives:
  - the dynamic per-command columns (`:301-315`);
  - the ID column width (`:324`);
  - both JSON outputs (`:329-375`);
  - the row count and scored count (`:527-529`);
  - the Key legend (`_print_key(all_cmds)`, `:532`).

  An EPIC whose Session Log carries a command no other issue has (e.g. `/ll:scope-epic`) adds a column of its own. This was reproduced.
- The empty-result branch (`:297-299`) prints the prose line `No active issues found.` and exits 0 even under `--json` and `--format json`, so JSON consumers get invalid output. This already happens today; EPIC filtering makes it more common (for example, a project whose only active issues are EPICs).
- `--type` explicitly accepts `EPIC` (`cli/issues/__init__.py:595-596`). The positional `ISSUE-ID` resolves via `_resolve_issue_id` (`:292`), including bare numbers (`1867` → EPIC-1867; the number is matched literally against the filename's anchored number, so `001` resolves only to a file named `…-EPIC-001-…`).
- With an ID and `--json`, the code prints `records[0]` (`:351`). Filtering an EPIC out *after* the lookup would leave `records` empty and raise `IndexError`.

## Expected Behavior

**The filter runs early.** EPICs are dropped right after loading (after `find_issues` / the single-ID lookup, around `:295`), before columns, width, totals, scored counts, JSON records or the Key legend are derived. An EPIC's unique commands produce no column and no Key entry.

**Default listing where nothing is left.** Exit 0 in every format:
- table, when active issues existed but all were EPICs: the prose line `No refinable issues found (EPICs are excluded from refine-status).`
- table, when a project has no active issues at all: keep the existing `No active issues found.` (asserted by `scripts/tests/test_refine_status.py:98`).
- `--json`: exactly `[]` in both cases
- `--format json`: zero NDJSON records (empty stdout) in both cases

The JSON half of this contract also fixes the existing invalid-JSON bug for a genuinely empty project.

**How an EPIC is identified.** `IssueInfo.issue_type` holds directory-style categories (`"bugs"`, `"features"`, `issue_parser.py:3728`), not `EPIC`. Filter with the same ID-prefix test `find_issues` applies for `type_prefixes` (`issue_parser.py:4452-4454`): an issue is an EPIC when the prefix of `issue.issue_id` is `EPIC`. Factor it into a small helper so the listing filter and the single-ID check share one definition. Optional: if the prefix extraction in `find_issues` is already a named helper (or can be lifted into one cheaply), have `_is_epic` call it so the two definitions cannot drift; `find_issues`' behavior stays unchanged either way.

**Explicit EPIC requests** fail with a clear diagnostic on stderr and **exit 1**, matching the command's existing "not found" exit code. This covers `--type EPIC`, `refine-status EPIC-NNN`, and a bare number that resolves to an EPIC. The message: `Error: EPICs are not tracked by refine-status; use 'll-issues epic-progress <ID>' instead.` Stdout stays empty in all formats. The single-ID check happens before records are built, so the `records[0]` path is never reached with an empty list.

Keep `EPIC` in the `--type` choices so existing invocations get the explanatory message rather than an argparse usage error.

**The filter is local to `cmd_refine_status`.** `find_issues` (`issue_parser.py:4399`) is shared by about 30 modules (29 files under `scripts/little_loops/` besides `issue_parser.py`), several of which need EPICs (`epic_progress`, `link_epics`, `epic_consistency`, `sprint`, `deps`, `parallel/orchestrator`). It must not change.

## Motivation

`cmd_refine_status` in `scripts/little_loops/cli/issues/refine_status.py` lists every active issue, including EPIC-typed ones. EPICs never accumulate refinement commands the way BUG/FEAT/ENH do, so they sink to the bottom of the "sorted by commands touched" view and distort the picture of what still needs refinement.

## Proposed Solution

In `cmd_refine_status`:

1. On the explicit-request paths, return the stderr diagnostic with exit 1:
   - `args.type == "EPIC"`: before loading.
   - single-ID path: right after `_resolve_issue_id` + `parse_file`, when the parsed issue's type is EPIC.
2. On the listing path, run `issues = [i for i in issues if not _is_epic(i)]` immediately after `find_issues`, remembering whether the pre-filter list was non-empty (it selects which table prose to print).
3. Replace the empty-result branch with a format-aware one: table prose, `[]` for `--json`, nothing for `--format json`, all exit 0.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/refine_status.py`: `cmd_refine_status` (lookup at `:286-295`, empty branch at `:297-299`; the derivations at `:301-375` and `:527-532` need no change once the list is filtered).
- `scripts/little_loops/cli/issues/__init__.py`: `refine-status` `--help` text and the `--type` help (`:590-623`); add a note to the `refine-status --type BUG` usage example (`:180`).

### Dependent Files (Callers/Importers)
- `find_issues` stays untouched (see Expected Behavior).
- Consumers of `refine-status` output; confirm none can pass an EPIC ID or depend on EPIC rows (no code change expected):
  - `scripts/little_loops/loops/refine-to-ready-issue.yaml:217`: `refine-status "<id>" --json` on the issue being refined. It already handles a failing call (`:234`); an EPIC ID reaching it would now exit 1.
  - `scripts/little_loops/loops/evaluation-quality.yaml:30`: pipes `refine-status --json` into Python; must tolerate `[]`.
  - `commands/create-sprint.md:375`: `refine-status --json` for sprint candidate data; EPICs vanishing from it is intended.

### Tests
- `scripts/tests/test_refine_status.py` has no EPIC coverage today. Add cases for every acceptance criterion below; `:98` (`No active issues found` on an empty project) keeps passing unchanged.
- `scripts/tests/test_issue_parser.py:4834-4836` (`TestPriorityRegexCompletenessAllowlist._ALLOWLIST`) keys a `P[0-5]` regex-shape allowlist entry to **line 541** of `refine_status.py` (the `norm` line in `_print_key`). Adding `_is_epic`, the diagnostics and the empty branch above it shifts that line, so this test fails until the key is re-derived to the line's new number (the test's own comment at `:4819-4823` says to re-run the scan and update it). Update it in the same change.

### Documentation
- `docs/reference/CLI.md` (`refine-status` section): EPICs excluded; the explicit-request exit code; the empty JSON contract.

### Configuration
- N/A

## Program Design

### Types
- No new types.

### Signatures
- `cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int` — gains the explicit-EPIC diagnostics, the early filter, and the format-aware empty branch (`refine_status.py:265`).
- `_is_epic(issue: IssueInfo) -> bool` (new, `refine_status.py`) — true when the `issue_id` prefix is `EPIC`; shared by the listing filter and the single-ID check.

### Call Path
`cmd_refine_status` -> `_resolve_issue_id` / `find_issues` -> `_is_epic` filter -> column, width, JSON and table derivations

### Decision Rules
- An explicit EPIC request (`--type EPIC`, an EPIC ID, a bare number resolving to an EPIC) exits 1 with the stderr diagnostic and empty stdout.
- An implicit EPIC (in the default listing) is dropped silently before any derivation.
- Empty result: exit 0; `[]` for `--json`, no records for `--format json`; table prose depends on whether EPIC filtering caused the emptiness.

## Implementation Steps

1. Write failing tests: a mixed project with an EPIC carrying a unique command, an EPIC-only project, an empty project, `--type EPIC`, `EPIC-NNN`, and a bare numeric EPIC ID.
2. Add the early filter and the explicit-request diagnostics.
3. Add the format-aware empty branch.
4. Re-key the `cli/issues/refine_status.py` entry in `scripts/tests/test_issue_parser.py` `TestPriorityRegexCompletenessAllowlist._ALLOWLIST` (currently `541`) to the shifted line of the `norm` Key line.
5. Update help text and `docs/reference/CLI.md`; run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — cosmetic noise in the default view, plus an existing invalid-JSON bug on empty results.
- **Effort**: Small — one function, early filter plus the empty branch.
- **Risk**: Low — local to one command; `find_issues` untouched.
- **Breaking Change**: Minor. `--type EPIC` and EPIC IDs change from exit 0 with rows to exit 1 with a diagnostic, and empty `--json` output changes from prose to `[]`.

## Scope Boundaries

- **In scope**: EPIC filtering, explicit-EPIC diagnostics, and the format-aware empty-result contract in `cmd_refine_status`; help text and CLI reference.
- **Out of scope**: `find_issues` and every other `ll-issues` subcommand; refine-status colorization (ENH-596); showing done issues through the single-ID path. That path currently skips the active-status filter; this issue does not change it.

## Acceptance Criteria

- [ ] Default `ll-issues refine-status` output (table, `--json`, `--format json`) contains no EPIC rows or entries.
- [ ] An EPIC whose Session Log has a command no other issue has adds no column and no Key legend entry, and doesn't change row or scored counts.
- [ ] An EPIC-only project gives the `No refinable issues found …` prose and an empty project keeps `No active issues found.`, both exit 0; in both, `--json` prints exactly `[]` and exits 0, and `--format json` prints no records and exits 0.
- [ ] `--type EPIC`, `refine-status EPIC-NNN`, and a bare numeric ID that resolves to an EPIC each print the diagnostic on stderr, nothing on stdout, and exit 1 in every format, with no `IndexError`.
- [ ] Regression: a non-EPIC single-ID call with `--json` still prints one JSON object (not an array), and when both `--json` and `--format json` are given, `--json` still takes precedence (`use_json_array`, `refine_status.py:326`).
- [ ] `find_issues` behavior is unchanged; other `ll-issues` subcommands still list EPICs.
- [ ] `--help` and `docs/reference/CLI.md` document the exclusion, the exit code and the empty-JSON contract.

## Related

- ENH-596 (colorize refine-status output) touches the same command; no overlap in behavior.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **PROPOSAL_UNSOUND** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

Checked 2026-09-24 against the working tree.

- **Confirmed**: every `refine_status.py` anchor (`:265`, `:286-295`, `:292`, `:295`, `:297-299`, `:301-315`, `:324`, `:326`, `:329-375`, `:351`, `:527-529`, `:532`); `cli/issues/__init__.py:180`, `:590-623` and `:595-596` (`--type` choices include `EPIC`); `issue_parser.py:3728`, `:4399`, `:4452-4454`; `test_refine_status.py:98` (no EPIC coverage there); consumer anchors `refine-to-ready-issue.yaml:217/:234`, `evaluation-quality.yaml:30`, `create-sprint.md:375`.
- **Behavior reproduced**: `ll-issues refine-status --json` currently emits EPIC rows (EPIC-1867, EPIC-1918, …); `/ll:scope-epic` appears only on EPIC rows and gets its own column and Key entry; an empty project prints `No active issues found.` with exit 0 under both `--json` and `--format json`.
- **Proposal consequence (fixed)**: `scripts/tests/test_issue_parser.py:4834-4836` keys a line-number allowlist entry to `refine_status.py:541`. Implementing the proposal shifts that line and fails the test. Added it to Tests and Implementation Steps (step 4).
- **Minor corrections**: `find_issues` has about 30 importers (29 files), not about 25. The bare-number claim was reworded, because matching is literal: `01867` does not resolve to EPIC-1867.
- `ll-verify-evidence`: clean (0 findings). No `## Blocked By` dependencies.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-25T00:23:03 - `f51f0560-5252-48a7-8a81-10d11331e067.jsonl`
- `/ll:ready-issue` - 2026-09-25T00:14:53 - `e5100a72-3fea-40ab-9997-b71ac9c315e8.jsonl`
- `/ll:confidence-check` - 2026-09-24T23:44:27 - `01d913d6-09f5-4671-9f2f-afb2a136b503.jsonl`
- `/ll:verify-issues` - 2026-09-24T23:40:13 - `ce8bec5b-7632-4ff9-a3da-7cdd35c70217.jsonl`
- `/ll:verify-issues` - 2026-09-24T22:56:16 - `4279401a-9acc-474c-b872-fd398cd78a8e.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:35:10 - `193eb57f-e9f6-4072-bd61-43000a1d97b1.jsonl`
- `/ll:confidence-check` - 2026-09-24T22:09:50 - `b03f0e56-e701-4b6d-bb94-8f4cb425b852.jsonl`
- `/ll:capture-issue` - 2026-09-24T18:17:16 - `12e7e1d6-d62f-431d-b8e0-a48dad1b4619.jsonl`
