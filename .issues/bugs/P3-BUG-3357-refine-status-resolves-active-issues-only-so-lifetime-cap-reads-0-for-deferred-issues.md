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
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-3357: refine-status resolves active issues only, so lifetime cap reads 0 for deferred issues

## Summary

`ll-issues refine-status` resolves IDs against the *active* issue set only, unlike every other `ll-issues` probe used by the refinement loops, which resolve any status.

## Current Behavior

`cli/issues/refine_status.py` uses `find_issues(config)` (active issues only) and, when the positional ID is not in that set, prints `Error: issue '<id>' not found in active issues.` — to **stdout** — and exits 1. Every sibling probe in `refine-to-ready-issue.yaml` (`check-flag`, `check-verify-verdict`, `check-open-questions`, `check-acceptance-criteria`, `check-design`, `show`) resolves via `resolve_issue_path`, which finds issues regardless of status.

Consequence in `refine-to-ready-issue.yaml` `check_lifetime_limit`: for a deferred (or otherwise non-active) issue, the `refine-status ... --json | python3 -c ...` pipeline swallows the failure and reads `refine_count: 0`, so the lifetime cap silently never fires for exactly the issues most likely to have burned refine budget before being deferred.

## Steps to Reproduce

1. Take any issue that has previously run `/ll:refine-issue` at least once (so it has a non-zero refine count).
2. Defer it: `ll-issues set-status <ID> deferred`.
3. Run `ll-issues refine-status <ID> --json`.
4. Observe stdout prints `Error: issue '<ID>' not found in active issues.` and the command exits 1 — the same exit code the found-issue path could also plausibly return — instead of reporting the issue's actual `refine_count`.
5. In `refine-to-ready-issue.yaml`'s `check_lifetime_limit` state, this failure is piped through `2>/dev/null` into a `python3 -c` block whose `except Exception: print(0)` silently reads `refine_count: 0` for the now-deferred issue.

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

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Correction to Option B's evidence (remediation pass, 2026-08-29): `find_issues_for_graph()` does not pass `_ALL_STATUSES` as claimed above. It passes `non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES` (`issue_parser.py:4188-4191`), and `_ALL_STATUSES`/`_TERMINAL_STATUSES` are defined at `issue_progress.py:12` (`{open, in_progress, blocked, done, cancelled, deferred}`) and `:14` (`{done, cancelled}`) respectively — so `non_terminal` = `{open, in_progress, blocked, deferred}`, which explicitly excludes `done` and `cancelled` (verified directly against both files).
- Consequence: had Option B been selected and implemented by literally mirroring this precedent, the fix would still fail to resolve `done`/`cancelled` issue ids — the same gap Expected Behavior calls out ("resolves any status") and Root Cause's `_matches_status()` citation names all three of `done`/`cancelled`/`deferred`. This does not reopen the already-decided selection of Option A (which resolves through `resolve_issue_path()` and is status-agnostic for all three), but the Option B evidence above overstated that option's viability relative to Option A and is corrected here for the record.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Missed existing CLI precedent (remediation pass, 2026-08-29): the option analysis above (Option A vs Option B) never considers the `clusters`/`cl` subcommand's `--status` argument, registered in the very same file as `refine-status` (`scripts/little_loops/cli/issues/__init__.py:567-576`, verified directly), which already exposes the exact alias vocabulary this bug's underlying need maps onto (`active` default = open/in_progress/blocked, `+deferred` = active + deferred, `all` = everything except cancelled). This is a closer, already-in-file convention for exposing status scope to a caller than either Option A's status-agnostic resolver or Option B's `find_issues_for_graph()` precedent. This does not reopen the already-decided selection of Option A (via `/ll:decide-issue`) — Option A's status-agnostic resolution still satisfies Expected Behavior's "resolves any status" requirement, which a `clusters`-style `--status` flag defaulting to `active` would not by itself. Noted here for completeness only.

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
- Every other single-ID `cli/issues/*.py` command resolves through `_resolve_issue_id()` (`show.py:39`, which the module's own docstring calls "the stable import path" for `check_verify_verdict.py`, `set_status.py`, `path_cmd.py`, `set_scores.py`, `cli/loop/_scaffold_core.py`, `mcp_server/tools.py`) — a thin delegation to `resolve_issue_path()` (`issue_parser.py:114`), a filename-based lookup with no status filter, so it resolves `done`/`cancelled`/`deferred` issues identically to `open` ones.
- `find_issues()` already supports resolving beyond its active-only default without touching `resolve_issue_path` at all: passing an explicit `status_filter` overrides the `None` default (`issue_parser.py:4052`, `:4089-4092`). `find_issues_for_graph()` (`issue_parser.py:4172-4191`) is a live precedent for this exact need — it calls `find_issues(config, category=category, status_filter=non_terminal)` specifically so a non-active issue isn't hidden from a caller that needs it.
- `IssueParser.parse_file(path: Path) -> IssueInfo` (`issue_parser.py:3556`) builds a single `IssueInfo` from an already-resolved path — the same per-file parse `find_issues()` uses internally during its directory walk (`issue_parser.py:4123`, `:4152`) — so a `Path` from `resolve_issue_path()` can be turned into the `IssueInfo` the table/JSON rendering needs without re-walking every category directory.

### Tests
- `scripts/tests/test_refine_status.py::test_single_issue_not_found` (line 2059) currently pins the exact behavior this bug describes: it asserts `result == 1` and `"not found" in out` where `out` is captured **stdout**. A fix that changes the exit code and/or routes the message to stderr must update this test's assertions, not just add a new test alongside it.
- `scripts/tests/test_refine_status.py::test_single_issue_table_output` (line 2013) and `test_single_issue_json_flag` (line 2083) cover the found-issue path only — no existing test exercises a `deferred`/`done`/`cancelled` issue id.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py::TestPriorityRegexCompletenessAllowlist::test_allowlist_entries_still_exist` / `::test_no_unallowlisted_raw_priority_regex` — the class's `_ALLOWLIST` dict pins `"cli/issues/refine_status.py": {533: "normalized-filename convention check help text"}`. Rewriting the id-filter branch (lines 279-290, well above line 533) shifts every line below it in the 549-line file, so line 533 will no longer hold that regex use after the fix: `test_allowlist_entries_still_exist` fails outright ("stale entries left behind after a refactor shifts lines" is its own stated purpose), and the pattern reappearing at its new line — not yet allowlisted — fails `test_no_unallowlisted_raw_priority_regex` too. The allowlist's line number must be updated to the post-fix location of that `--help` text. [Agent-equivalent finding, `ll-code` graph confirmed no other callers/importers beyond the ones already listed above.]
- `scripts/tests/test_issue_parser.py:1627` (inside `test_find_issues_skip_blocked_false_byte_identical_for_all_caller_shapes`) carries a descriptive comment `# cli/issues/refine_status.py:281 — cmd_refine_status` labeling that line as the `find_issues(config, type_prefixes=type_prefixes)` callsite. This comment is not asserted against the source (so it can't fail the test), but Option A removes/relocates that call for the id-filter path — update the comment alongside the `_ALLOWLIST` fix so it doesn't cite a stale line/branch.

### Documentation
- `docs/reference/CLI.md:1465` — the `ISSUE-ID` argument row states "Exits 1 if the issue is not found," which today means "not found in active issues"; once the id-filter branch resolves any status, this row's exit-code/scoping claim must be updated to match (the stdout→stderr channel change and the "active issues" → "any status" scoping both land on this line). No test pins this exact text (`test_wiring_reference_docs.py`/`test_wiring_cli_registry.py` don't assert on it), so nothing in CI catches drift here — it is a manual doc-sync obligation of this fix, not an N/A.
- `refine-status` is otherwise documented only via its own `--help` text (`__init__.py:125-180`), which doesn't describe active-only scoping today and needs no update either way.

### Configuration
- N/A — `config.refine_status.columns`/`elide_order` (exercised in `test_config.py:1005-1033`) control table rendering only and are unrelated to this bug.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Correction / scope clarification (remediation pass, 2026-08-29): the `check_lifetime_limit` state named above (`refine-to-ready-issue.yaml:209-217`) pipes `ll-issues refine-status ... --json 2>/dev/null` straight into a `python3 -c` block that reads only stdin/stdout JSON inside a bare `except Exception: print(0)` — it never inspects `refine-status`'s shell exit code at all, and `2>/dev/null` discards its stderr unconditionally (verified directly against the loop YAML). Adding a distinct exit code and/or moving the message to stderr therefore fixes nothing for this specific caller: the bug's stated symptom (`refine_count` reading 0 for a deferred issue) is resolved entirely by the status-agnostic *resolution* half of the fix (Option A), not by the stderr/exit-code half.
- The stderr/exit-code change (Expected Behavior, Implementation Step 2) remains worth making for consistency with every other single-ID `cli/issues/*.py` command, but it is not load-bearing for `check_lifetime_limit` and should not be represented as fixing that caller's symptom. If `check_lifetime_limit` is later wanted to *discriminate* "not found" from "count 0" via exit code/stderr, that would require also updating the loop YAML's shell pipeline to stop discarding stderr and to inspect `$?` — out of scope for this issue unless explicitly extended.

## Program Design

### Types

N/A — no new data shape. The existing `IssueInfo` record already carries the `status` field `_matches_status()` reads.
> ⚠ Superseded — `_matches_status()` is cited only to describe `find_issues()`'s existing default-exclusion behavior (Root Cause); Option A does not call `find_issues()` for the id-filter branch, so this function is not part of the fix.

### Signatures

- `find_issues(config: BRConfig, category: str | None = None, skip_ids: set[str] | None = None, only_ids: list[str] | set[str] | None = None, type_prefixes: set[str] | None = None, status_filter: set[str] | None = None, *, skip_blocked: bool = False) -> list[IssueInfo]` — existing (`issue_parser.py:4046-4054`); `status_filter=None` excludes `done`/`cancelled`/`deferred` (`:4089-4092`).
  > ⚠ Superseded — `status_filter` is `find_issues()`'s pre-existing parameter, named here only to document today's signature; Option A bypasses `find_issues()` for the id-filter branch entirely rather than passing it.
- `resolve_issue_path(config: BRConfig, user_input: str) -> Path | None` — existing, status-agnostic filename resolver (`issue_parser.py:114`).
- `IssueParser.parse_file(issue_path: Path) -> IssueInfo` — existing (`issue_parser.py:3556`).
- `cmd_refine_status(config: BRConfig, args: argparse.Namespace) -> int` — existing function this bug's fix touches (`refine_status.py:263`).

### Call Path

`main_issues` -> `cmd_refine_status` -> `find_issues` (id-filter branch, `status_filter` left at its `None` default) — the buggy path.
> ⚠ Superseded — describes today's buggy call path, not the Option A fix, which bypasses `find_issues` for this branch.

Contrast with the sibling convention: `main_issues` -> `cmd_check_flag` -> `_resolve_issue_id` -> `resolve_issue_path` (status-agnostic).

### Decision Rules

N/A — no new decision logic; this fixes the resolution scope and not-found signaling of existing control flow.

## Implementation Steps

1. The id-filter branch of `cmd_refine_status()` (`refine_status.py:279-290`) resolves a deferred/done/cancelled issue the same way `open`/`in_progress`/`blocked` ones already do — verified by exercising `refine-status <id>` and `refine-status <id> --json` against an issue at each non-active `status` value.
2. The "not found" path is distinguishable from a genuine zero-count answer through both signal channels every other `cli/issues/` single-ID command already uses: written to `stderr` (not `stdout`), and returned via an exit code the id-found path never returns — matching the `check_flag.py:28-30`/`check_design.py:36-40` convention of reserving a code for "not found" apart from the command's own true/false-shaped answers.
   > ⚠ Superseded — wrong precedent group; see Codebase Research Findings below (exit code 1 already suffices, `check_flag`/`check_design`'s code 2 doesn't apply here)
3. `scripts/tests/test_refine_status.py::test_single_issue_not_found` (line 2059) asserts against the corrected channel/exit code rather than continuing to pin the old stdout/exit-1 behavior; a new test covers the previously-uncovered case of `refine-status` given a `deferred` (or `done`/`cancelled`) issue id.
4. The `--json`/no-ID listing mode's `find_issues(config, type_prefixes=type_prefixes)` call keeps its current active-only default — `scripts/tests/test_builtin_loops.py::test_sample_state_sources_refine_status_not_list` and the `config.refine_status` tests in `test_config.py` continue to pass unmodified.
5. `python -m pytest scripts/tests/test_refine_status.py scripts/tests/test_issue_parser.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` — after the id-filter branch rewrite shifts lines, re-derive the correct line number for the `"cli/issues/refine_status.py"` entry in `_ALLOWLIST` (currently `533`, "normalized-filename convention check help text") so it still points at that `--help` text; `test_allowlist_entries_still_exist` and `test_no_unallowlisted_raw_priority_regex` both fail otherwise. Step 5's full-file pytest run surfaces this if missed, but the allowlist edit belongs in this change rather than a follow-up.
- Update the stale-after-fix comment `# cli/issues/refine_status.py:281 — cmd_refine_status` at `scripts/tests/test_issue_parser.py:1627` to cite the call's post-fix line/branch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Correction to Step 2's exit-code precedent (remediation pass, 2026-08-29): `cmd_refine_status()`'s own docstring pins its found-path contract as "Exit code (0 = success)" (`refine_status.py:274`), and the found-path body (`refine_status.py:279-323+`) never returns anything but `0`. That means exit code `1` — what the not-found branch already returns today (`refine_status.py:290`) — already satisfies "an exit code the id-found path never returns"; no exit-code *value* change is required, only the stdout→stderr channel change.
- `check_flag.py:28-30`/`check_design.py:36-40` reserve exit code `2` for a different reason that does not apply here: both commands' found-path already returns `0` *or* `1` as a substantive true/false answer (verified: `check_design.py:40` returns `1 if design_gate_failed(gaps) else 0`), so `2` is the first code left over for "not found." `refine_status.py` has no such boolean answer space on its found path, so it needs no third code.
- The correct precedent group is the other 0-success/no-boolean-answer single-ID commands, all of which use exit code `1` for "not found": `path_cmd.py:29-30`, `set_status.py:262-263`, `skip.py:35-36`, `size.py:196-197`, `research_triage.py:58-59`, `locate_options.py:35-36`, `format_check.py:551-552` (all verified via direct grep against source). Step 2 should be read against this group, not `check_flag.py`/`check_design.py`.
- Net effect: an implementation that changes only the stdout→stderr channel and leaves the exit code at `1` fully satisfies Step 2 as corrected here; adopting exit code `2` to mirror `check_flag.py`/`check_design.py` would be inconsistent with the closer analog group and is not required.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- Citation correction (remediation pass, 2026-08-29): the prior finding above cites `cmd_refine_status()`'s docstring "Exit code (0 = success)" text as `refine_status.py:274`. Verified directly against source: line 274 is the docstring's `Returns:` header; the quoted sentence itself is on line 275. The correct citation is `refine_status.py:275` (or `:274-275` to cover both the header and the quoted line).
- Test-assertion gap: neither this step nor the Tests subsection under Integration Map specifies that the new deferred/done/cancelled test must assert on the actual `refine_count` value, not just that the issue is found. The bug's entire symptom (Steps to Reproduce) is a deferred issue with a nonzero prior refine history reading back `refine_count: 0` — so the new test must construct an issue with a known, nonzero `/ll:refine-issue` Session Log count, transition it to `deferred` (or `done`/`cancelled`), then assert `refine-status <id> --json`'s parsed `refine_count` equals that known count. A test that only checks the issue is found or exits 0 in table mode does not prove the defect is fixed.
- Test-fixture prerequisite: `scripts/tests/test_refine_status.py::_make_issue()` (lines 19-32) takes no `status` parameter and has no catch-all mechanism for arbitrary frontmatter fields — its `frontmatter_lines` list only ever appends `confidence_score`/`outcome_confidence`/`score_*`/`size`. `IssueInfo.status` comes exclusively from a `status:` frontmatter key (`issue_parser.py:3608`, `frontmatter.get("status", "open")`) with no directory-based inference — placing a file under the test's existing `deferred`/`completed` dirs (already created by `_setup_dir`, `test_refine_status.py:2003-2011`) does not set status. Writing the deferred/done/cancelled test this step calls for requires first extending `_make_issue()` with a `status` parameter (or hand-writing frontmatter that includes a `status:` line) — without this, a literal `_make_issue(..., status="deferred")` call raises `TypeError`.
- Message-wording gap: once the id-filter branch resolves status-agnostically (Option A, via `resolve_issue_path()`), the not-found message's own wording — `Error: issue '{issue_id_filter}' not found in active issues.` (`refine_status.py:288`) — becomes an inaccurate description of the new behavior for an id that genuinely resolves to nothing under any status. No step here calls for revising the string itself (only its stdout->stderr channel, per the exit-code correction above), and `test_single_issue_not_found`'s loose substring check (`"not found" in out`) passes whether or not the stale "in active issues" phrase is corrected. The fix should drop or generalize that phrase (e.g. "not found") alongside the channel change.

## Impact

- **Priority**: P3 - Silently defeats a safety cap (`check_lifetime_limit`) rather than crashing or misbehaving loudly; scoped to one automation loop state, not a user-facing correctness bug.
- **Effort**: Small - one contained branch swap in `cmd_refine_status()`'s id-filter path (`refine_status.py:279-290`), touching 3 files total: `refine_status.py` (the fix), `test_refine_status.py` (update `test_single_issue_not_found` + add a non-active-status case), and `test_issue_parser.py` (re-derive the `_ALLOWLIST` line number and the stale comment at `:1627` per the Wiring Phase above).
- **Risk**: Low - `ll-code importers-of`/`impact-of` and a repo-wide grep both confirm `refine_status.py` has no importers beyond its own dispatch registration (`__init__.py:1010-1011`); the id-found rendering path is untouched, and the sole named caller (`check_lifetime_limit`) already discards this command's stderr and never inspects its exit code (see Integration Map finding below), so it cannot regress from either channel changing.
- **Breaking Change**: No - no other `cli/issues/*.py` module or test asserts on the current stdout "not found in active issues" text or its exit code value (`test_single_issue_not_found` is the only such assertion, and Implementation Step 3 updates it in the same change); the fix brings `refine_status.py` into line with the status-agnostic, stderr-reporting convention every sibling single-ID command already follows.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- File-count correction (remediation pass, 2026-08-29): the Effort estimate above enumerates "3 files total" (`refine_status.py`, `test_refine_status.py`, `test_issue_parser.py`). This omits `docs/reference/CLI.md:1465`, which the Documentation section (under Integration Map) already states "must be updated to match" the new scoping/channel behavior and calls "a manual doc-sync obligation of this fix, not an N/A." The fix therefore touches 4 files total, not 3; a fixer following only the Effort section's file list will miss the doc edit the issue itself requires elsewhere.

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml`.

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-29T18:47:00 - `237f015b-641f-4613-8e7e-3269af82a4c8.jsonl`
- `/ll:refine-issue` - 2026-08-29T18:35:51 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
- `/ll:confidence-check` - 2026-08-29T18:31:19 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
- `/ll:refine-issue` - 2026-08-29T18:21:19 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
- `/ll:format-issue` - 2026-08-29T18:20:58 - `477f6591-ae32-49d7-bc90-ee1e0759ddc3.jsonl`
- `/ll:confidence-check` - 2026-08-29T18:16:14 - `705df646-68fd-4942-88f0-15c172537d74.jsonl`
- `/ll:verify-issues` - 2026-08-29T18:09:44 - `48e9d546-94fd-4111-9bec-ae917ba67439.jsonl`
- `/ll:wire-issue` - 2026-08-29T18:04:00 - `7123d651-4594-4bf8-9409-d68bea464210.jsonl`
- `/ll:decide-issue` - 2026-08-29T17:57:49 - `7123d651-4594-4bf8-9409-d68bea464210.jsonl`
- `/ll:refine-issue` - 2026-08-29T17:51:59 - `c3e9e317-4789-4436-bd68-830408d594dc.jsonl`
