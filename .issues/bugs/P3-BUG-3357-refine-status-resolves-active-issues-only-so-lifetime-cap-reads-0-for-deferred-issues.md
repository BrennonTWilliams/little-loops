---
id: BUG-3357
type: BUG
title: refine-status resolves active issues only, so lifetime cap reads 0 for deferred
  issues
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T23:26:59Z'
decision_needed: false
verify_verdict: VALID
confidence_score: 90
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 25
---

# BUG-3357: refine-status resolves active issues only, so lifetime cap reads 0 for deferred issues

## Summary

`ll-issues refine-status` resolves IDs against the *active* issue set only, unlike every other `ll-issues` probe used by the refinement loops, which resolve any status.

## Current Behavior

`cli/issues/refine_status.py` uses `find_issues(config)` (active issues only) and, when the positional ID is not in that set, prints `Error: issue '<id>' not found in active issues.` — to **stdout** — and exits 1. Every sibling probe in `refine-to-ready-issue.yaml` (`check-flag`, `check-verify-verdict`, `check-open-questions`, `check-acceptance-criteria`, `check-design`, `show`) resolves via `resolve_issue_path`, which finds issues regardless of status.

Consequence in `refine-to-ready-issue.yaml` `check_lifetime_limit`: for a deferred (or otherwise non-active) issue, the `refine-status ... --json | python3 -c ...` pipeline swallows the failure and reads `refine_count: 0`, so the lifetime cap silently never fires for exactly the issues most likely to have burned refine budget before being deferred.

## Expected Behavior

`refine-status <id>` resolves any status (mirror `resolve_issue_path` semantics), or at minimum exits with a distinct code and stderr (not stdout) so callers can discriminate "not found" from "count 0". The `--json` no-ID listing mode may reasonably stay active-only.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/refine_status.py`
- **Anchor**: `in function cmd_refine_status()`
- **Cause**: The single-ID lookup path (`refine_status.py:279-290`) resolves through `find_issues(config, type_prefixes=type_prefixes)` (`refine_status.py:281`) with no `status_filter` argument. `find_issues()`'s own default excludes non-active issues — `status_filter: set[str] | None = None` (`issue_parser.py:4052`) and, when `None`, `_matches_status()` returns `info.status not in ("done", "cancelled", "deferred")` (`issue_parser.py:4089-4092`). A deferred/done/cancelled issue is therefore never present in the `issues` list the id-filter then searches (`refine_status.py:284`), so the not-found branch (`refine_status.py:286-290`) fires: `print(f"Error: issue '{issue_id_filter}' not found in active issues.")` — to **stdout**, with no `file=sys.stderr` — followed by `return 1`, the same exit code the id-found path never returns for any other reason. Every other single-ID command in `cli/issues/` writes its "not found" message with `file=sys.stderr`: `check_flag.py:28`, `check_decidable.py:32`, `check_design.py:36`, `check_verify_verdict.py:83`, `check_acceptance_criteria.py:101`, `check_readiness.py:139`, `check_unresolved_decisions.py:67`, `check_open_questions.py:55`, `fold_findings.py:104`, `format_check.py:551`, `locate_options.py:35`, `path_cmd.py:29`, `research_triage.py:58`, `size.py:196`, `set_scores.py:32`, `set_status.py:262`, `skip.py:35` — `refine_status.py:288` is the sole holdout in that directory (`show.py:788` also omits `file=sys.stderr`, but that command already resolves via `_resolve_issue_id`/`resolve_issue_path` and so is unaffected by the status-scope half of this bug).

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

**Option A**: Resolve the id-filter branch through `resolve_issue_path()`/`_resolve_issue_id()` — the same status-agnostic lookup every other single-ID `cli/issues/*.py` command already uses — then build the `IssueInfo` needed for rendering via `IssueParser.parse_file()` on the resolved path, bypassing `find_issues()`'s directory walk and its active-only default entirely for this branch.

> **Selected:** Option A — reuses the exact resolver (`resolve_issue_path`/`_resolve_issue_id`) and stderr/distinct-exit-code reporting convention already standardized across a dozen-plus sibling single-ID `cli/issues/*.py` commands, so the id-filter branch stops being the one place in the directory with its own private lookup and error-reporting behavior.

**Option B**: Keep the id-filter branch on `find_issues()`, but pass an explicit `status_filter` (the `_ALL_STATUSES` set `find_issues_for_graph()` already demonstrates at `issue_parser.py:4188-4191` for the same "don't hide non-active issues" need) only when `issue_id_filter` is set, leaving the no-ID listing mode's default untouched.

**Recommended**: Option A — it reuses the exact resolver (`resolve_issue_path`) and reporting convention (stderr plus a distinct exit code) already standardized across `check_flag.py`, `check_design.py`, `check_verify_verdict.py`, and over a dozen other sibling commands, so the id-filter branch stops being the one place in `cli/issues/` with its own private lookup and error-reporting behavior. Either option resolves the status-scope half of this bug; the stderr/exit-code fix is required regardless of which is chosen.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-08-29.

**Selected**: Option A — resolve the id-filter branch through `resolve_issue_path()`/`_resolve_issue_id()`, then build the `IssueInfo` via `IssueParser.parse_file()` on the resolved path.

**Reasoning**: Option A matches the single-ID resolution convention already used by every other `cli/issues/*.py` command with an id-filter branch (`check_flag.py`, `check_design.py`, `check_verify_verdict.py`, `check_acceptance_criteria.py`, `path_cmd.py`, and over a dozen others), so `refine_status.py` stops being the sole holdout with its own private lookup and stdout-based error reporting. `resolve_issue_path()` (`issue_parser.py:114`) and `IssueParser.parse_file()` (`issue_parser.py:3556`) are both existing, independently-tested primitives — `find_issues()` already builds each `IssueInfo` via the same per-file parse internally — so Option A composes proven pieces rather than introducing a new status-filter code path. Option B is a smaller line-level diff (an added `status_filter` argument to the existing `find_issues()` call, mirroring `find_issues_for_graph()`'s precedent at `issue_parser.py:4172-4191`) but leaves the id-filter branch's error handling and lookup semantics diverging from every sibling command — the exact inconsistency this bug is about.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B | 2/3 | 3/3 | 2/3 | 3/3 | 10/12 |

**Key evidence**:
- For Option A: `resolve_issue_path()` (`issue_parser.py:114`) and `_resolve_issue_id()` (`show.py:39`) are the shared status-agnostic lookup already used by `check_flag.py:28`, `check_design.py:36`, `check_verify_verdict.py:83`, and over a dozen other single-ID commands; `IssueParser.parse_file()` (`issue_parser.py:3556`) is the same per-file parse `find_issues()` already uses internally, so the `IssueInfo` shape stays identical between paths.
- For Option B: `find_issues_for_graph()` (`issue_parser.py:4172-4191`) demonstrates the `status_filter` override pattern for a "don't hide non-active issues" need, and reusing it here is a smaller diff, but it does not by itself bring `refine_status.py`'s error-reporting (stdout, no distinct exit code) into line with sibling commands — that fix is still needed as a separate change under this option.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/refine_status.py` — `cmd_refine_status()`'s id-filter branch (lines 279-290) is where the active-only resolution and the stdout "not found" print live.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:1010-1011` — `main_issues()` dispatches `args.command == "refine-status"` to `cmd_refine_status(config, args)`; the subparser itself is registered at `__init__.py:580-584`.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:209-224` (`check_lifetime_limit` state) — the consequence path named in this issue: pipes `ll-issues refine-status "<id>" --json 2>/dev/null` into a `python3 -c` block whose `except Exception: print(0)` defaults to `refine_count: 0` on any JSON-parse failure, so today's plain-text stdout error is silently swallowed regardless of exit code.
- No other importers of `refine_status.py` exist — `ll-code importers-of`/`impact-of` both returned empty result sets for this file, and a repo-wide grep for `from little_loops.cli.issues.refine_status import` / `refine_status\.` outside the file itself confirms it.

### Similar Patterns
- Every other single-ID `cli/issues/*.py` command resolves through `_resolve_issue_id()` (`show.py:58`, which the module's own docstring calls "the stable import path" for `check_verify_verdict.py`, `set_status.py`, `path_cmd.py`, `set_scores.py`, `cli/loop/_scaffold_core.py`, `mcp_server/tools.py`) — a thin delegation to `resolve_issue_path()` (`issue_parser.py:114`), a filename-based lookup with no status filter, so it resolves `done`/`cancelled`/`deferred` issues identically to `open` ones.
- `find_issues()` already supports resolving beyond its active-only default without touching `resolve_issue_path` at all: passing an explicit `status_filter` overrides the `None` default (`issue_parser.py:4052`, `:4089-4092`). `find_issues_for_graph()` (`issue_parser.py:4172-4191`) is a live precedent for this exact need — it calls `find_issues(config, category=category, status_filter=non_terminal)` specifically so a non-active issue isn't hidden from a caller that needs it.
- `IssueParser.parse_file(path: Path) -> IssueInfo` (`issue_parser.py:3556`) builds a single `IssueInfo` from an already-resolved path — the same per-file parse `find_issues()` uses internally during its directory walk (`issue_parser.py:4123`, `:4148`) — so a `Path` from `resolve_issue_path()` can be turned into the `IssueInfo` the table/JSON rendering needs without re-walking every category directory.

### Tests
- `scripts/tests/test_refine_status.py::test_single_issue_not_found` (line 2059) currently pins the exact behavior this bug describes: it asserts `result == 1` and `"not found" in out` where `out` is captured **stdout**. A fix that changes the exit code and/or routes the message to stderr must update this test's assertions, not just add a new test alongside it.
- `scripts/tests/test_refine_status.py::test_single_issue_table_output` (line 2013) and `test_single_issue_json_flag` (line 2083) cover the found-issue path only — no existing test exercises a `deferred`/`done`/`cancelled` issue id.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py::TestPriorityRegexCompletenessAllowlist::test_allowlist_entries_still_exist` / `::test_no_unallowlisted_raw_priority_regex` — the class's `_ALLOWLIST` dict pins `"cli/issues/refine_status.py": {533: "normalized-filename convention check help text"}`. Rewriting the id-filter branch (lines 279-290, well above line 533) shifts every line below it in the 549-line file, so line 533 will no longer hold that regex use after the fix: `test_allowlist_entries_still_exist` fails outright ("stale entries left behind after a refactor shifts lines" is its own stated purpose), and the pattern reappearing at its new line — not yet allowlisted — fails `test_no_unallowlisted_raw_priority_regex` too. The allowlist's line number must be updated to the post-fix location of that `--help` text. [Agent-equivalent finding, `ll-code` graph confirmed no other callers/importers beyond the ones already listed above.]
- `scripts/tests/test_issue_parser.py:1627` (inside `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes`) carries a descriptive comment `# cli/issues/refine_status.py:281 — cmd_refine_status` labeling that line as the `find_issues(config, type_prefixes=type_prefixes)` callsite. This comment is not asserted against the source (so it can't fail the test), but Option A removes/relocates that call for the id-filter path — update the comment alongside the `_ALLOWLIST` fix so it doesn't cite a stale line/branch.

### Documentation
- N/A — `refine-status` is documented only via its own `--help` text (`__init__.py:125-180`), which doesn't describe active-only scoping today and needs no update either way.

### Configuration
- N/A — `config.refine_status.columns`/`elide_order` (exercised in `test_config.py:1005-1033`) control table rendering only and are unrelated to this bug.

## Program Design

### Types

N/A — no new data shape. The existing `IssueInfo` record already carries the `status` field `_matches_status()` reads.

### Signatures

- `find_issues(config: BRConfig, category: str | None = None, skip_ids: set[str] | None = None, only_ids: list[str] | set[str] | None = None, type_prefixes: set[str] | None = None, status_filter: set[str] | None = None, *, skip_blocked: bool = False) -> list[IssueInfo]` — existing (`issue_parser.py:4046-4054`); `status_filter=None` excludes `done`/`cancelled`/`deferred` (`:4089-4092`).
- `resolve_issue_path(config: BRConfig, user_input: str) -> Path | None` — existing, status-agnostic filename resolver (`issue_parser.py:114`).
- `IssueParser.parse_file(issue_path: Path) -> IssueInfo` — existing (`issue_parser.py:3556`).
- `cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int` — existing function this bug's fix touches (`refine_status.py:263`).

### Call Path

`main_issues` -> `cmd_refine_status` -> `find_issues` (id-filter branch, `status_filter` left at its `None` default) — the buggy path.

Contrast with the sibling convention: `main_issues` -> `cmd_check_flag` -> `_resolve_issue_id` -> `resolve_issue_path` (status-agnostic).

### Decision Rules

N/A — no new decision logic; this fixes the resolution scope and not-found signaling of existing control flow.

## Implementation Steps

1. The id-filter branch of `cmd_refine_status()` (`refine_status.py:279-290`) resolves a deferred/done/cancelled issue the same way `open`/`in_progress`/`blocked` ones already do — verified by exercising `refine-status <id>` and `refine-status <id> --json` against an issue at each non-active `status` value.
2. The "not found" path is distinguishable from a genuine zero-count answer through both signal channels every other `cli/issues/` single-ID command already uses: written to `stderr` (not `stdout`), and returned via an exit code the id-found path never returns — matching the `check_flag.py:28-30`/`check_design.py:36-40` convention of reserving a code for "not found" apart from the command's own true/false-shaped answers.
3. `scripts/tests/test_refine_status.py::test_single_issue_not_found` (line 2059) asserts against the corrected channel/exit code rather than continuing to pin the old stdout/exit-1 behavior; a new test covers the previously-uncovered case of `refine-status` given a `deferred` (or `done`/`cancelled`) issue id.
4. The `--json`/no-ID listing mode's `find_issues(config, type_prefixes=type_prefixes)` call keeps its current active-only default — `scripts/tests/test_builtin_loops.py::test_sample_state_sources_refine_status_not_list` and the `config.refine_status` tests in `test_config.py` continue to pass unmodified.
5. `python -m pytest scripts/tests/test_refine_status.py scripts/tests/test_issue_parser.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` — after the id-filter branch rewrite shifts lines, re-derive the correct line number for the `"cli/issues/refine_status.py"` entry in `_ALLOWLIST` (currently `533`, "normalized-filename convention check help text") so it still points at that `--help` text; `test_allowlist_entries_still_exist` and `test_no_unallowlisted_raw_priority_regex` both fail otherwise. Step 5's full-file pytest run surfaces this if missed, but the allowlist edit belongs in this change rather than a follow-up.
- Update the stale-after-fix comment `# cli/issues/refine_status.py:281 — cmd_refine_status` at `scripts/tests/test_issue_parser.py:1627` to cite the call's post-fix line/branch.

## Impact

- **Priority**: P3 - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml`.

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-29T18:16:14 - `705df646-68fd-4942-88f0-15c172537d74.jsonl`
- `/ll:verify-issues` - 2026-08-29T18:09:44 - `48e9d546-94fd-4111-9bec-ae917ba67439.jsonl`
- `/ll:wire-issue` - 2026-08-29T18:04:00 - `7123d651-4594-4bf8-9409-d68bea464210.jsonl`
- `/ll:decide-issue` - 2026-08-29T17:57:49 - `7123d651-4594-4bf8-9409-d68bea464210.jsonl`
- `/ll:refine-issue` - 2026-08-29T17:51:59 - `c3e9e317-4789-4436-bd68-830408d594dc.jsonl`
