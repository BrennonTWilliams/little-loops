---
id: ENH-1922
title: "ll-logs scan-failures: mine failed ll-* calls to auto-file bugs"
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, ENH-1904, ENH-1921]
labels: [captured, ll-logs, bugs, automation]
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

### Similar Patterns
- `.claude/commands/analyze_log.md` — failure pattern table and priority-bumping/dedup logic; reference only (text-log variant)
- `scripts/little_loops/cli/logs.py:_extract_ll_event_streams()` — ENH-1919 shared extractor (already implemented); walks JSONL files, extracts per-session ordered `InvocationEvent` streams; reuse directly
- `scripts/little_loops/cli/logs.py:_cmd_sequences()` — canonical subcommand following the `--project`/`--all`/`--window-days`/`--json` parser pattern to model after
- `scripts/little_loops/issue_lifecycle.py:classify_failure()` — error normalization pattern; strips line numbers and volatile paths from error text; returns `(FailureType, description)` tuple
- `scripts/little_loops/workflow_sequence/analysis.py:_cluster_by_entities()` — Jaccard entity-overlap clustering pattern for grouping similar failure messages into clusters
- `scripts/little_loops/cli_args.py:add_json_arg()` — standard `--json` / `-j` flag registration

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestScanFailures` class following `TestSequences` fixture pattern; use existing `_make_project_dir()` and `_assistant_bash_record()` helpers; add `_user_tool_result_record(tool_use_id, content, is_error=True)` factory for tool result records; cover: nonzero exit detection (`is_error: True`), traceback text detection, `(tool, signature)` clustering, false-positive suppression for expected-nonzero gates (`ll-verify-*` exit 1), `--json` output schema

### Documentation
- `docs/reference/API.md` — update `ll-logs` section with new subcommand

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

## Session Log
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
