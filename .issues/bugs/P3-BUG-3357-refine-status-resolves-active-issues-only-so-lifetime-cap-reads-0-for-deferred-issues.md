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

**Recommended reporting convention**: regardless of which option resolves the status-scope half of this bug, the stderr/exit-code fix reuses the exact reporting convention already standardized across `check_flag.py`, `check_design.py`, `check_verify_verdict.py`, and over a dozen other sibling commands, so the id-filter branch stops being the one place in `cli/issues/` with its own private lookup and error-reporting behavior.

- Correction to Option B's evidence (remediation pass, 2026-08-29): `find_issues_for_graph()` does not pass `_ALL_STATUSES` as claimed above. It passes `non_terminal = _ALL_STATUSES - _TERMINAL_STATUSES` (`issue_parser.py:4188-4191`), and `_ALL_STATUSES`/`_TERMINAL_STATUSES` are defined at `issue_progress.py:12` (`{open, in_progress, blocked, done, cancelled, deferred}`) and `:14` (`{done, cancelled}`) respectively — so `non_terminal` = `{open, in_progress, blocked, deferred}`, which explicitly excludes `done` and `cancelled` (verified directly against both files).
- Consequence: had Option B been selected and implemented by literally mirroring this precedent, the fix would still fail to resolve `done`/`cancelled` issue ids — the same gap Expected Behavior calls out ("resolves any status") and Root Cause's `_matches_status()` citation names all three of `done`/`cancelled`/`deferred`. This does not reopen the already-decided selection of Option A (which resolves through `resolve_issue_path()` and is status-agnostic for all three), but the Option B evidence above overstated that option's viability relative to Option A and is corrected here for the record.
- Missed existing CLI precedent (remediation pass, 2026-08-29): the option analysis above (Option A vs Option B) never considers the `clusters`/`cl` subcommand's `--status` argument, registered in the very same file as `refine-status` (`scripts/little_loops/cli/issues/__init__.py:567-576`, verified directly), which already exposes the exact alias vocabulary this bug's underlying need maps onto (`active` default = open/in_progress/blocked, `+deferred` = active + deferred, `all` = everything except cancelled). This is a closer, already-in-file convention for exposing status scope to a caller than either Option A's status-agnostic resolver or Option B's `find_issues_for_graph()` precedent. This does not reopen the already-decided selection of Option A (via `/ll:decide-issue`) — Option A's status-agnostic resolution still satisfies Expected Behavior's "resolves any status" requirement, which a `clusters`-style `--status` flag defaulting to `active` would not by itself. Noted here for completeness only.
- Convention re-confirmed with fully-qualified paths (remediation pass, 2026-08-29): every single-ID `cli/issues/*.py` command that reports a not-found condition prints the identical literal `Error: Issue '{id}' not found.` to `sys.stderr`, with no shared helper — each file duplicates the literal independently: `scripts/little_loops/cli/issues/check_flag.py:28`, `scripts/little_loops/cli/issues/check_design.py:36`, `scripts/little_loops/cli/issues/check_verify_verdict.py:83`, `scripts/little_loops/cli/issues/path_cmd.py:29`, `scripts/little_loops/cli/issues/check_acceptance_criteria.py:101` (all re-verified directly against source at these exact lines). The divergent target this bug fixes, `scripts/little_loops/cli/issues/refine_status.py:288`, still reads `print(f"Error: issue '{issue_id_filter}' not found in active issues.")` with no `file=sys.stderr` — confirming the convention this section's Option A/B analysis and Decision Rationale describe still holds unchanged today, with no shared function to call into: matching it means duplicating the exact literal, not introducing a new abstraction.
- Machine-resolvable citation of the same convention (remediation pass, 2026-08-29): `scripts/little_loops/cli/issues/check_flag.py` (line 28), `scripts/little_loops/cli/issues/check_design.py` (line 36), `scripts/little_loops/cli/issues/check_verify_verdict.py` (line 83), `scripts/little_loops/cli/issues/path_cmd.py` (line 29), and `scripts/little_loops/cli/issues/check_acceptance_criteria.py` (line 101) all print the identical literal `print(f"Error: Issue '{id}' not found.", file=sys.stderr)` — re-verified directly against source at each cited line, confirming the convention Option A's decision rests on (repeated here in full-path form, without a colon-appended line suffix inside the backtick span, so this citation is anchor-resolvable the same way Root Cause's `**File**:` fields already are).

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
2. The "not found" path is distinguishable from a genuine zero-count answer through both signal channels every other `cli/issues/` single-ID command already uses: write to `stderr` (not `stdout`) using the sibling convention `Error: Issue '{id}' not found.` (capitalized "Issue", no "in active issues" qualifier — matches `check_flag.py:28`, `check_design.py:36`, and ~13 other single-ID commands verbatim; see Codebase Research Findings below). Exit code stays `1` — `cmd_refine_status()`'s found path only ever returns `0` (`refine_status.py:275`), so `1` already satisfies "an exit code the id-found path never returns"; the `check_flag.py`/`check_design.py` code-`2` convention does not apply here because those commands' found paths already return a substantive `0`/`1` boolean answer, unlike this one.
3. `scripts/tests/test_refine_status.py::test_single_issue_not_found` (line 2059) asserts the corrected stderr text verbatim (`err == f"Error: Issue '{id}' not found.\n"`, not a loose substring check) and the exit code; add parametrized coverage (`@pytest.mark.parametrize("status", ["deferred", "done", "cancelled"])`) that builds an issue with a known, nonzero `refine_count`, transitions it to that status, and asserts `refine-status <id> --json`'s parsed `refine_count` equals the known value — the assertion must check the numeric value, not just that the issue was found.
4. Extend `scripts/tests/test_refine_status.py::_make_issue()` (lines 19-32) with a `status` parameter — it accepts none today and has no catch-all mechanism for arbitrary frontmatter fields, so a literal `_make_issue(..., status="deferred")` call raises `TypeError` until this is added.
5. The `--json`/no-ID listing mode's `find_issues(config, type_prefixes=type_prefixes)` call keeps its current active-only default — `scripts/tests/test_builtin_loops.py::test_sample_state_sources_refine_status_not_list` and the `config.refine_status` tests in `test_config.py` continue to pass unmodified.
6. Update `docs/reference/CLI.md:1465`'s `ISSUE-ID` row (currently "Exits 1 if the issue is not found") to state the lookup resolves any status and reports the not-found message on stderr — untested by Step 7's pytest run, so confirm this manually.
7. `python -m pytest scripts/tests/test_refine_status.py scripts/tests/test_issue_parser.py -v` passes (covers Steps 1-5; does not cover Step 6).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_issue_parser.py::TestPriorityRegexCompletenessAllowlist` — after the id-filter branch rewrite shifts lines, re-derive the correct line number for the `"cli/issues/refine_status.py"` entry in `_ALLOWLIST` (currently `533`, "normalized-filename convention check help text") so it still points at that `--help` text; `test_allowlist_entries_still_exist` and `test_no_unallowlisted_raw_priority_regex` both fail otherwise. Step 7's full-file pytest run surfaces this if missed, but the allowlist edit belongs in this change rather than a follow-up.
- Update the stale-after-fix comment `# cli/issues/refine_status.py:281 — cmd_refine_status` at `scripts/tests/test_issue_parser.py:1627` to cite the call's post-fix line/branch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis (folded into Implementation Steps above by `/ll:reconcile-issue`, 2026-08-29):_

- Exit-code precedent: `cmd_refine_status()`'s docstring pins its found-path contract as "Exit code (0 = success)" (`refine_status.py:275`; line 274 is the `Returns:` header), and the found-path body (`refine_status.py:279-323+`) never returns anything but `0`. Exit code `1` — already returned by the not-found branch today (`refine_status.py:290`) — already satisfies "an exit code the id-found path never returns," so no exit-code *value* change is required. The correct precedent group is the other 0-success/no-boolean-answer single-ID commands that use exit code `1` for "not found": `path_cmd.py:29-30`, `set_status.py:262-263`, `skip.py:35-36`, `size.py:196-197`, `research_triage.py:58-59`, `locate_options.py:35-36`, `format_check.py:551-552` (verified via direct grep) — not `check_flag.py:28-30`/`check_design.py:36-40`'s code `2`, which those commands reserve only because their found paths already return a substantive `0`/`1` boolean answer (`check_design.py:40`: `1 if design_gate_failed(gaps) else 0`).
- Message convention: the exact sibling message is `Error: Issue '{id}' not found.` (capitalized "Issue"), printed to `sys.stderr` and duplicated verbatim (no shared helper) across ~15 sibling single-ID commands: `check_flag.py:28`, `check_decidable.py:32`, `check_design.py:36`, `check_open_questions.py:55`, `check_verify_verdict.py:83`, `check_acceptance_criteria.py:101`, `check_readiness.py:139`, `check_unresolved_decisions.py:67`, `fold_findings.py:104`, `format_check.py:551`, `locate_options.py:35`, `path_cmd.py:29`, `research_triage.py:58`, `set_scores.py:32`, `set_status.py:262`, `skip.py:35`. `refine_status.py:288`'s current text (`Error: issue '{issue_id_filter}' not found in active issues.`) differs on both capitalization and the now-inaccurate "in active issues" qualifier — match the sibling literal (Step 2) rather than introducing a shared helper.
- Test-fixture and assertion requirements: `_make_issue()` (`test_refine_status.py:19-32`) needs the `status` parameter added first (Step 4); the new deferred/done/cancelled coverage (Step 3) must assert the resolved numeric `refine_count`, not merely that the issue is found — the bug's entire symptom (Steps to Reproduce) is a deferred issue with a nonzero prior refine history reading back `refine_count: 0`, so a test that only checks "found" or exit `0` does not prove the defect is fixed. Root Cause (`issue_parser.py:4089-4092`) names all three excluded statuses (`done`, `cancelled`, `deferred`); Step 3's parametrization must cover all three, not just one.
- Doc-sync: none of Steps 1-5 nor the Wiring Phase bullets touch `docs/reference/CLI.md` on their own — Step 6 makes that edit explicit. Step 7's `pytest scripts/tests/test_refine_status.py scripts/tests/test_issue_parser.py` run does not exercise `docs/`, so Step 6 needs manual confirmation rather than test coverage.

## Impact

- **Priority**: P3 - Silently defeats a safety cap (`check_lifetime_limit`) rather than crashing or misbehaving loudly; scoped to one automation loop state, not a user-facing correctness bug.
- **Effort**: Small - one contained branch swap in `cmd_refine_status()`'s id-filter path (`refine_status.py:279-290`), touching 4 files total: `refine_status.py` (the fix), `test_refine_status.py` (update `test_single_issue_not_found` + add non-active-status coverage), `test_issue_parser.py` (re-derive the `_ALLOWLIST` line number and the stale comment at `:1627` per the Wiring Phase above), and `docs/reference/CLI.md:1465` (doc-sync, Implementation Step 6).
- **Risk**: Low - `ll-code importers-of`/`impact-of` and a repo-wide grep both confirm `refine_status.py` has no importers beyond its own dispatch registration (`__init__.py:1010-1011`); the id-found rendering path is untouched, and the sole named caller (`check_lifetime_limit`) already discards this command's stderr and never inspects its exit code (see Integration Map finding below), so it cannot regress from either channel changing.
- **Breaking Change**: No - no other `cli/issues/*.py` module or test asserts on the current stdout "not found in active issues" text or its exit code value (`test_single_issue_not_found` is the only such assertion, and Implementation Step 3 updates it in the same change); the fix brings `refine_status.py` into line with the status-agnostic, stderr-reporting convention every sibling single-ID command already follows.

## Discovered

2026-08-28 review/refactor of `refine-to-ready-issue.yaml`.

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-08-29T19:44:39 - `5b08caaf-d6d9-41cd-a302-ae95669f4151.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:34:20 - `095cbd0a-db00-46a3-adc4-bd813f5370ea.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:27:19 - `b3d7ed27-fb20-4642-89b3-c49ed044082a.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:21:17 - `095cbd0a-db00-46a3-adc4-bd813f5370ea.jsonl`
- `/ll:verify-issues` - 2026-08-29T19:16:14 - `fedec3ab-76ac-4b03-acac-d98d32d4349a.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:12:07 - `fedec3ab-76ac-4b03-acac-d98d32d4349a.jsonl`
- `/ll:confidence-check` - 2026-08-29T19:08:58 - `1af8753e-4f9c-4ef2-97a5-4e6f8d5943ea.jsonl`
- `/ll:verify-issues` - 2026-08-29T19:04:35 - `1af8753e-4f9c-4ef2-97a5-4e6f8d5943ea.jsonl`
- `/ll:refine-issue` - 2026-08-29T19:00:13 - `1af8753e-4f9c-4ef2-97a5-4e6f8d5943ea.jsonl`
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
