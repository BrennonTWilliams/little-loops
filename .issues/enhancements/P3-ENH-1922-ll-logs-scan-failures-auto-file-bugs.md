---
id: ENH-1922
title: 'll-logs scan-failures: mine failed ll-* calls to auto-file bugs'
type: ENH
priority: P3
status: open
captured_at: '2026-06-04T02:27:34Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- ENH-1904
- ENH-1921
labels:
- captured
- ll-logs
- bugs
- automation
confidence_score: 94
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 18
decision_needed: false
---

# ENH-1922: ll-logs scan-failures — mine failed ll-* calls to auto-file bugs

## Summary

Add `ll-logs scan-failures` to find `ll-*` Bash invocations in **interactive**
session logs that returned a nonzero exit or emitted a traceback, and propose
issue files (create/reopen) for them — generalizing the `analyze_log` skill from
ll-parallel/ll-auto runs to all sessions.

## Current Behavior

The `analyze_log` skill only inspects ll-parallel/ll-auto log files. Failures of
`ll-*` tools during ordinary interactive Claude Code sessions — captured in the
log corpus — are never mined, so tool bugs that surface in real use go unfiled.

## Expected Behavior

`ll-logs scan-failures [--project DIR|--all] [--window-days D] [--json]` scans
tool-use results for `ll-*` Bash calls with nonzero exit codes or Python
tracebacks, clusters them by tool + error signature, and emits candidate issues
(or feeds `/ll:capture-issue`). Distinct from ENH-1904, which mines user-*text*
corrections into history.db; this mines *tool failures*.

## Motivation

Real tool failures are the highest-signal bug source and currently leak away.
Closing this turns the log corpus into a passive bug detector for ll's own CLIs.

## Proposed Solution

Add `scan-failures` to `cli/logs.py` reusing the shared extractor (ENH-1919).
Detect nonzero exit / traceback in tool-use result records; cluster by
`(tool, normalized-error-signature)`; emit candidates. Optionally pipe into
`/ll:capture-issue` for file creation with duplicate detection.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**JSONL record pairing**: Claude Code session logs store Bash tool-use blocks in `assistant`-type records (field path `message.content[].type == "tool_use" and name == "Bash"`, with `id` key), and tool results in subsequent `user`-type records (field path `message.content[0].type == "tool_result"`, with `tool_use_id` matching the `assistant` block's `id`). ENH-1922 must walk records in order and pair them by `tool_use_id` to correlate which `ll-*` command produced which result. `user_messages.py:_parse_user_message()` skips tool_result records (they are not real user messages); the pairing must happen in a new walker.

**Failure signals**: Two signal types in `tool_result` content — `is_error: True` on the result block (set when exit code ≠ 0) and `"Traceback (most recent call last)"` substring in the result text (Python exception). Both must be checked.

**Error normalization**: `issue_lifecycle.py:classify_failure()` already strips transient signals (API quota, rate limit, network errors, context window overflow) from error text, returning `FailureType.TRANSIENT` for those. Suppressing transient failures prevents noisy candidates. After transient suppression, normalize the remaining error text by stripping stack frame line numbers and file paths to produce a stable cluster key.

**Clustering**: `workflow_sequence/analysis.py:_cluster_by_entities()` provides the Jaccard entity-overlap clustering shape; adapt for `(tool_name, normalized_signature)` key-based grouping (simpler than Jaccard for exact-signature matching, but Jaccard useful for fuzzy grouping of similar tracebacks).

**`--capture` implementation**: `issue_lifecycle.py:create_issue_from_failure()` writes a BUG issue from error text using `get_next_issue_number()` and the standard frontmatter template. For the `--capture` flag, call this function per unique cluster (one issue per `(tool, signature)` pair), then check for duplicates using the same Jaccard + FTS5 approach as `skills/capture-issue/SKILL.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `_cmd_scan_failures()` handler and `scan-failures` subparser in `_build_parser()`; reuses `_is_ll_relevant()`, `_extract_tool_name()`, `_extract_ll_event_streams()`, `InvocationEvent` already present
- `scripts/tests/test_ll_logs.py` — add `TestScanFailures` class; extend `_assistant_bash_record()` fixture with a `_user_tool_result_record()` counterpart for seeding failure records
- `docs/reference/API.md` — add `scan-failures` to the `main_logs` subcommands section
- `docs/reference/CLI.md` — add `scan-failures` row to the `ll-logs` subcommands table

### Dependent Files (Callers/Importers)
- `.claude/commands/analyze_log.md` — failure-pattern table and dedup logic to generalize; this is the text-log variant (operates on `.log` files from ll-parallel/ll-auto runs); ENH-1922 adapts the same clustering idea for structured JSONL `tool_result` records
- `scripts/little_loops/issue_lifecycle.py:classify_failure()` — existing error normalization (TRANSIENT vs REAL, regex-based categories for quota/network/timeout/context errors); reuse to suppress expected-transient failures from candidates; also `create_issue_from_failure()` as pattern for `--capture` sink
- `scripts/little_loops/user_messages.py:_parse_user_message()` — shows how `tool_result` blocks appear in `user`-type records and how to detect them; the `tool_use_id` field pairs each result to the preceding `assistant` `Bash` `tool_use` block via its `id`
- `/ll:capture-issue` (skill) — candidate sink; reuses Jaccard + FTS5 dup detection and the reopen flow from `skills/capture-issue/SKILL.md`
- `session_store` correction path (ENH-1904) — sibling, not overlap

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — module-level docstring at line 15 describes `ll-logs` capabilities; needs `scan-failures` appended after implementation [Agent 2 finding]
- `scripts/tests/test_cli.py` — `TestMainLogsIntegration` class covers `main_logs()` dispatch; add `test_scan_failures_returns_0` smoke test matching the `test_stats_returns_0` pattern [Agent 3 finding]
- `scripts/tests/test_issue_lifecycle.py` — `TestClassifyFailure` (line 551, 5 methods) and `TestCreateIssueFromFailure` (line 413, 6 methods) and `TestEventEmission` (lines 1284 and 1317) directly test the reused functions; if `create_issue_from_failure()` signature changes to allow `parent_info: IssueInfo | None`, all 8 direct-call sites require updating [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — 3 `mock.patch("little_loops.issue_manager.create_issue_from_failure")` calls at lines 2008/2016/2058 would silently break if the import path or signature changes [Agent 3 finding]

### Similar Patterns
- `.claude/commands/analyze_log.md` — failure pattern table and priority-bumping/dedup logic; reference only (text-log variant)
- `scripts/little_loops/cli/logs.py:_extract_ll_event_streams()` — ENH-1919 shared extractor (already implemented); walks JSONL files, extracts per-session ordered `InvocationEvent` streams; reuse directly
- `scripts/little_loops/cli/logs.py:_cmd_sequences()` — canonical subcommand following the `--project`/`--all`/`--window-days`/`--json` parser pattern to model after
- `scripts/little_loops/issue_lifecycle.py:classify_failure()` — error normalization pattern; strips line numbers and volatile paths from error text; returns `(FailureType, description)` tuple
- `scripts/little_loops/workflow_sequence/analysis.py:_cluster_by_entities()` — Jaccard entity-overlap clustering pattern for grouping similar failure messages into clusters
- `scripts/little_loops/cli_args.py:add_json_arg()` — standard `--json` / `-j` flag registration

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestScanFailures` class following `TestSequences` fixture pattern; use existing `_make_project_dir()` and `_assistant_bash_record()` helpers; add `_user_tool_result_record(tool_use_id, content, is_error=True)` factory for tool result records; cover: nonzero exit detection (`is_error: True`), traceback text detection, `(tool, signature)` clustering, false-positive suppression for expected-nonzero gates (`ll-verify-*` exit 1), `--json` output schema

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py` — add `test_scan_failures_returns_0` to `TestMainLogsIntegration` (line ~2921) following the `test_stats_returns_0` pattern; covers happy-path dispatch through `main_logs()` [Agent 3 finding]
- `scripts/tests/test_issue_lifecycle.py` — **update if signature changes**: `TestCreateIssueFromFailure` (6 methods, line 413) and `TestEventEmission.test_create_issue_from_failure_emits_event` (line 1284) call `create_issue_from_failure()` directly with `parent_info=IssueInfo(...)` — all 8 call sites need updating if `parent_info` becomes `Optional` [Agent 3 finding]
- `scripts/tests/test_issue_manager.py` — **update if signature changes**: 3 `mock.patch` targets at lines 2008/2016/2058 would silently fail if `create_issue_from_failure` import path changes [Agent 3 finding]

### Documentation
- `docs/reference/API.md` — update `ll-logs` section with new subcommand; also remove the "pending ENH-1922" qualifier on `errors`/`error_rate` fields in the `stats` bullet (line ~3539) once implemented

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — `## CLI Tools` section `ll-logs` bullet (line ~184): parenthetical subcommand list `(discover / extract / sequences / stats / tail)` needs `scan-failures` appended [Agent 2 finding]
- `commands/help.md` — `CLI TOOLS` → `ll-logs` row (line ~281): description paragraph needs `scan-failures` capability added [Agent 2 finding]
- `docs/ARCHITECTURE.md` — file tree inline comment for `logs.py` (line ~250): inline subcommand list needs `scan-failures` appended after `stats` [Agent 2 finding]
- `CHANGELOG.md` — `stats` bullet (lines ~12–13) contains "pending ENH-1922" note to resolve; add `scan-failures` as a new `### Added` entry [Agent 2 finding]
- `skills/init/SKILL.md` — two identical `ll-logs` description blocks (lines ~411 and ~447, inside Step 11 CLAUDE.md template) need `scan-failures` in capability text [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Register subcommand** in `_build_parser()` (`logs.py`): add `scan-failures` subparser with `--project`/`--all` exclusive group (required), `--window-days` (int, default None), `add_json_arg()` from `cli_args.py`, and `--capture` (store_true); add dispatch branch in `main_logs()`.
2. **Implement `_cmd_scan_failures(args, logger)`** in `logs.py`:
   - Resolve project folder(s) via `get_project_folder()` (for `--project`) or `discover_all_projects()` (for `--all`).
   - Walk JSONL files using the standard `project_folder.glob("*.jsonl")` loop (exclude `agent-*`), reading records in order.
   - Build a `pending: dict[tool_use_id, tool_name]` map: for each `assistant` record, iterate `message.content` for `Bash` `tool_use` blocks whose `input.command` matches `\bll-\w+`; store `{block["id"]: ll_tool_name}`.
   - For each `user` record whose `message.content[0].type == "tool_result"`: if `tool_use_id` is in `pending`, check for failure: `block.get("is_error") is True` OR `"Traceback (most recent call last)"` in the content text.
3. **Normalize and cluster** (`logs.py`): pass each failure's error text through `classify_failure()` from `issue_lifecycle.py`; discard `FailureType.TRANSIENT`; strip stack-frame line numbers and absolute paths from the remainder to form a stable `normalized_sig`; cluster by `(tool_name, normalized_sig)` using a `dict` keyed on that tuple.
4. **Emit candidates** (`logs.py`): text mode prints one block per cluster (tool, count, sample error, session IDs); `--json` mode calls `print_json()` from `cli/output.py` with a list of cluster dicts; `--capture` mode calls `create_issue_from_failure()` from `issue_lifecycle.py` for each cluster (one BUG per `(tool, sig)` pair), preceded by a Jaccard dup check mirroring `capture-issue`'s dedup logic.
5. **Tests** in `test_ll_logs.py`: add `TestScanFailures` class; add `_user_tool_result_record(tool_use_id, content, is_error=True)` factory alongside existing `_assistant_bash_record()`; seed a fixture corpus via `_make_project_dir()` with paired `assistant`+`user` records; assert: (a) nonzero-exit failures are detected, (b) traceback-text failures are detected, (c) multiple occurrences of same error collapse to one cluster, (d) transient errors (`rate limit`) are suppressed, (e) `ll-verify-*` expected-exit-1 calls are excluded.
6. **Update docs**: add `scan-failures` to `docs/reference/API.md` (main_logs section) and `docs/reference/CLI.md` (ll-logs subcommands table).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Resolve `create_issue_from_failure()` signature gap**: the function currently requires `parent_info: IssueInfo` as a required positional arg; the `--capture` flow in `scan-failures` has no parent issue. **Selected: construct a minimal stub `IssueInfo` from the failing `ll-*` command name** to satisfy the existing signature without a breaking change. This avoids the cascading update to 8 direct-call sites in `test_issue_lifecycle.py` and 3 `mock.patch` targets in `test_issue_manager.py` that making `parent_info` optional would require.
8. **Update `scripts/tests/test_cli.py`** — add `test_scan_failures_returns_0` to `TestMainLogsIntegration` (line ~2921) following the `test_stats_returns_0` shape: patch `sys.argv` to `["ll-logs", "scan-failures", "--all"]`, invoke `main_logs()`, assert return 0.
9. **Update prose documentation** — after implementation, update the following to add `scan-failures` to the subcommand lists: `.claude/CLAUDE.md` (line ~184), `commands/help.md` (line ~281), `docs/ARCHITECTURE.md` (line ~250), `scripts/little_loops/cli/__init__.py` docstring (line ~15), and both blocks in `skills/init/SKILL.md` (lines ~411 and ~447).
10. **Update `CHANGELOG.md`** — resolve the "pending ENH-1922" note in the `stats` subcommand bullet; add a `### Added` entry for `scan-failures`.

## Success Metrics

- Re-running over historical logs surfaces ≥1 real, previously-unfiled tool failure.
- No false-positive issue for an expected nonzero (e.g. `ll-verify-* exit 1` gates).

## Scope Boundaries

- In: failures of `ll-*` CLIs in interactive logs.
- Out: user-text correction mining (ENH-1904); ll-parallel/ll-auto logs (analyze_log).

## API/Interface

```bash
ll-logs scan-failures [--project DIR | --all] [--window-days D] [--json] [--capture]
```

- `--project DIR` — restrict scan to a specific project's logs
- `--all` — scan all project logs
- `--window-days D` — limit to logs from last D days (default: all)
- `--json` — emit structured JSON candidates instead of human-readable text
- `--capture` — pipe candidates into `/ll:capture-issue` for automatic issue filing with duplicate detection

Output (text mode): one candidate block per `(tool, normalized-error-signature)` cluster.

## Impact

- **Priority**: P3 — Real tool failures currently leak undetected; not blocking but high signal value
- **Effort**: Medium — New subcommand reuses shared extractor (ENH-1919) and analyze_log clustering logic; new parts are error-signature normalization and the `--capture` sink
- **Risk**: Low — Additive new subcommand; no changes to existing `ll-logs` behavior or shared code paths
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/` analyze_log

## Labels

`captured`, `ll-logs`, `bugs`, `automation`

## Status

**Open** | Created: 2026-06-04 | Priority: P3



---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-1922 owns the per-invocation failure-classification layer (detection of nonzero exits, tracebacks, and correction signals) atop ENH-1919's shared extractor. ENH-1921 aggregates failure/correction rates from ENH-1922's classified output rather than re-implementing failure detection. ENH-1919's shared extractor provides the raw event stream without classification.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 92/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **Open decision — `create_issue_from_failure()` signature (Step 7)**: The `--capture` path requires calling this function, but it takes `parent_info: IssueInfo` as a required positional arg. Step 7 presents two options without choosing one: (a) make `parent_info` optional — cascades to 8 direct-call sites in `test_issue_lifecycle.py` + 3 `mock.patch` targets in `test_issue_manager.py`; or (b) construct a minimal stub `IssueInfo` from the tool name, avoiding all cascading changes. Resolve this open decision before starting `--capture` implementation. Option B is lower-risk and likely sufficient.
- **Broad doc/wiring surface (11 files)**: Seven of eleven touchpoints are mechanical doc/string updates (`.claude/CLAUDE.md`, `commands/help.md`, `docs/ARCHITECTURE.md`, `cli/__init__.py`, `skills/init/SKILL.md` ×2, `CHANGELOG.md`). None will break functionality if missed, but a verification pass is needed to avoid incomplete wiring at PR time.

## Session Log
- `/ll:confidence-check` - 2026-06-05T02:00:00 - `96c87ebe-6aa2-4e31-9f6e-048c63d3f1da.jsonl`
- `/ll:decide-issue` - 2026-06-06T02:07:09 - `886c31c7-0954-45fb-848f-1d2c6cb35941.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `ebab5302-4a33-4ea6-bbbf-a199ce5df87d.jsonl`
- `/ll:wire-issue` - 2026-06-06T02:02:01 - `4a91fe55-6469-496e-af97-a69c0e2d2af2.jsonl`
- `/ll:refine-issue` - 2026-06-06T01:56:20 - `ca84d26f-26ba-4062-b6de-19cdd5c32aa4.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:22 - `8b34820d-ae67-4c39-b57a-ea2b07021501.jsonl`
- `/ll:format-issue` - 2026-06-04T03:11:09 - `52fea084-ccde-40de-a423-8dea32d03fdb.jsonl`
- `/ll:format-issue` - 2026-06-04T03:10:04 - `9b934de1-4aab-4e21-b930-1823687cb2b1.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`

## Verification Notes (2026-06-05)

- **Path correction needed**: Issue references `skills/analyze_log/` (lines 56, 61) but the actual
  command is at `.claude/commands/analyze_log.md`, not a skill directory.
- **Dependent Files** section references `skills/analyze_log/` — should be `.claude/commands/analyze_log.md`.
- All other references accurate; feature not yet implemented.
- `/ll:verify-issues` - 2026-06-05 - Feature still not implemented. Prior note about `skills/analyze_log/` vs `commands/analyze_log.md` path error remains uncorrected in issue body. The Integration Map and references to `skills/analyze_log/` should be updated to point to the command file at `.claude/commands/analyze_log.md`.
