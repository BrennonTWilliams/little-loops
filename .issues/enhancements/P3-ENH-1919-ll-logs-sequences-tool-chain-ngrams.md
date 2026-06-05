---
id: ENH-1919
title: 'll-logs sequences: tool-chain n-gram extraction primitive'
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T02:27:34Z'
completed_at: '2026-06-05T23:46:33Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- FEAT-1309
labels:
- captured
- ll-logs
- loop-suggester
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1919: ll-logs sequences — tool-chain n-gram extraction primitive

## Summary

Add an `ll-logs sequences` subcommand that mines **tool-level** n-grams (ordered
chains of ll skill/command/tool invocations) from the extracted log corpus, with
occurrence counts and transition frequencies. This is the reusable extraction
primitive that `loop-suggester` and FEAT-1309's passive-scan UX can consume.

## Current Behavior

`loop-suggester` and `analyze-workflows` source candidate workflows from
`ll-messages` (user *text*). The actual sequence of skill/command invocations —
e.g. `refine-issue → wire-issue → ready-issue` — is visible in the JSONL tool-use
records but is never extracted as structured sequence data.

## Expected Behavior

`ll-logs sequences [--project DIR|--all] [--min-len N] [--min-count M] [--top N] [--window-days D] [--json]`
walks the extracted `logs/**/*.jsonl` (or raw `~/.claude/projects/`) and emits
ranked n-grams of ll invocations: the chain, occurrence count, and per-edge
transition frequency. Default `--min-len 2`. `--top N` limits output to the
top N chains by frequency.

## Motivation

n-grams over *real tool chains* give `loop-suggester` ground truth about what
users actually do, not what they say. It also factors the n-gram logic out of
FEAT-1309 (which currently inlines mining into a `--passive-scan` flag) into a
single reusable primitive.

## Proposed Solution

Add `sequences` to `cli/logs.py` (`main_logs()`), reusing the project
enumeration that `extract` already shares with `discover`. Parse tool-use records
for ll skill/command/`ll-*` Bash invocations into an ordered per-session event
stream, then count n-grams within `--window-days`. Emit text + `--json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architecture**: The subcommand plugs into the existing `main_logs()` dispatch (line 406) and `_build_parser()` subparser registry (line 347). It reuses three shared infrastructure layers already present:

| Layer | Reusable Component | Location |
|-------|-------------------|----------|
| **Tool-use detection** | `_is_ll_relevant()` type (c) — detects `assistant` records with `Bash` tool-use blocks matching `\bll-\w+` | `logs.py:59-72` |
| **Command extraction** | `_parse_command_record()` — iterates `message.content[]` for `tool_use` blocks, extracts `input.command` | `user_messages.py:566-636` |
| **Project enumeration** | `discover_all_projects()` + `get_project_folder()` — shared by `discover`/`extract` | `logs.py:126` / `user_messages.py:356` |
| **Output conventions** | `add_json_arg()` + `print_json()` + `configure_output()` | `cli_args.py:197` / `cli/output.py:146` / `cli/output.py:88` |
| **Telemetry** | `cli_event_context()` already wraps `main_logs()` — no additional wiring needed | `session_store.py:567` |

**Detection scope**: The existing `_is_ll_relevant()` detects three signal types. For `sequences`, all three are relevant for building complete invocation chains:
1. `queue-operation` with `content.startswith("/ll:")` — records when a `/ll:` slash command is enqueued
2. `user` records with `<command-name>/ll:` in message content — records when user invokes an ll command
3. `assistant` records with `Bash` tool-use containing `ll-\w+` — records when the assistant invokes `ll-*` CLI tools (e.g., `ll-issues list`, `ll-history sessions`)

A per-session event stream should merge all three types in timestamp order to capture the full invocation chain — from slash-command enqueue through intermediate CLI tool calls.

**n-gram approach**: Use `collections.Counter` with a sliding window over the ordered event stream. The codebase has no existing sliding-window n-gram utility; `Counter` is the standard library choice. For `--window-days`, filter records by `timestamp` field (ISO 8601 strings, comparable lexicographically) before windowing.

**Output schema** matches the issue spec: `[{chain: [str], count: int, edges: [{from, to, freq}]}]`, where `edges` are per-transition frequencies within each chain, and `freq` is the proportion of times `from → to` appears out of all transitions out of `from`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `sequences` subcommand to `main_logs()`, reusing project enumeration from `extract`/`discover`
  - `_build_parser():347` — register `sequences` subparser with `--project`/`--all` group, `--min-len`, `--min-count`, `--top`, `--window-days`, and `--json` (via `add_json_arg()` from `cli_args.py:197`)
  - `main_logs():406` — add `elif args.command == "sequences":` dispatch branch
  - `_is_ll_relevant():26` — reuse existing ll-* Bash command detection for filtering records to relevant tool-use blocks
  - `_cmd_matches():185` — reuse pattern for matching specific CLI tools in Bash tool-use blocks

### Dependent Files (Callers/Importers)
- `skills/ll-loop-suggester/` — consume `sequences --json` output as history-independent sequence source alongside `ll-messages`
- FEAT-1309 implementation — re-point `--passive-scan` mining logic at this primitive instead of inlining
- FEAT-1925 (`ll-logs telemetry digest loop`) — planned FSM loop consuming `ll-logs sequences` as an orchestration state

### Similar Patterns
- `discover` and `extract` subcommands in `cli/logs.py` — reuse their project enumeration and JSONL-walking patterns
- `ll-messages` CLI (`cli/messages.py:13`) — parallel extraction primitive; follow same `--json` output convention, `cli_event_context()` wrapping, and project-folder resolution via `get_project_folder()` (`user_messages.py:356`)
- `extract_commands()` in `user_messages.py:502` — JSONL walking + tool-use extraction pattern; `_parse_command_record():566` extracts command strings from `assistant` records with `tool_use` blocks
- `workflow_sequence/analysis.py` — existing category-template matching and workflow boundary detection; `sequences` is a simpler n-gram primitive that this module (and others) can consume

### Tests
- `scripts/tests/test_ll_logs.py` — add `TestSequences` class following existing `TestDiscover`/`TestExtract` fixture patterns (temp dirs, mock JSONL records, capsys output capture, `--json` schema validation)
  - Cover: n-gram counting, `--min-len`/`--min-count`/`--window-days` filtering, `--top` limit, `--json` output schema (`[{chain: [str], count: int, edges: [{from, to, freq}]}]`), `--project` vs `--all` source selection, empty/no-match edge cases
- `scripts/tests/test_ll_logs_wiring.py` — add wiring check that `sequences` appears in `commands/help.md` ll-logs entry (following existing pattern at line 14-47)

### Documentation
- `docs/reference/API.md#little_loopscli` — document `sequences` subcommand signature and JSON schema (alongside `discover`/`extract`/`tail` entries at line 3525-3539)
- `commands/help.md:280` — update ll-logs description to include `sequences`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:1707-1743` — add `sequences` to subcommands table (currently lists `discover`/`tail`/`extract`), flag table for its arguments (`--project`/`--all`, `--min-len`, `--min-count`, `--top`, `--window-days`, `--json`), and examples following existing format [Agent 2 finding]
- `.claude/CLAUDE.md:184` — add `sequences` to the ll-logs subcommand parenthetical list (currently reads `discover` / `extract` / `tail`; update to `discover` / `extract` / `sequences` / `tail`) [Agent 2 finding]
- `docs/ARCHITECTURE.md:250` — add `sequences` to the `logs.py` file description comment (currently reads `discover/extract/tail subcommands`) [Agent 2 finding]
- `skills/init/SKILL.md:411,447` — update ll-logs descriptions in two boilerplate blocks to include "sequence" capability; follows pattern of other multi-subcommand CLI descriptions [Agent 2 finding]
- `CHANGELOG.md` — add entry for new `sequences` subcommand following conventional commit format [Agent 2 finding]

### Configuration
- N/A (no new config keys; reuses existing host resolution from `LL_HOOK_HOST` env var and `orchestration.host_cli` in `ll-config.json`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reusable detection**: `_is_ll_relevant():26` already detects ll-* Bash tool-uses via `re.search(r"\bll-\w+", cmd)` (type (c) detection). The `sequences` subcommand can reuse this pattern directly — no new detection logic needed for identifying ll-invocation records.
- **Tool-use extraction**: `_parse_command_record()` at `user_messages.py:566` extracts `CommandRecord` objects from assistant `tool_use` blocks with `name == "Bash"`. Follow this pattern but emit ordered per-session event streams instead of flat command lists.
- **Project enumeration**: `_cmd_extract():256` already handles both `--project` (single) and `--all` (multi-project) modes via `get_project_folder()` + `discover_all_projects()`. The `sequences` subcommand should mirror this exactly.
- **No existing n-gram utility**: The codebase has dict-based frequency counting (`doc_synthesis.py:88`) and log-scale frequency scoring (`next_loop.py:119`), but no sliding-window n-gram extraction. `collections.Counter` is the natural choice for n-gram counting in this subcommand.
- **JSONL line format**: Each line is `json.loads(line)`; records have `type` (user/assistant/queue-operation), `sessionId` (UUID), `timestamp` (ISO 8601), `message.content` (array of blocks including `{type: "tool_use", name: "Bash", input: {command: "..."}}`). `_extract_cwd_from_project():99` resolves project paths from the `cwd` field in JSONL records, preferring it over the lossy directory-name decode.

## Implementation Steps

1. **Define the per-session ll-invocation event-stream extractor** (shared helper in `cli/logs.py`).
   - Walk JSONL files in a project folder following `_cmd_extract():256` and `extract_commands():502` patterns (glob `*.jsonl`, skip `agent-*`, `json.loads()` per line).
   - Filter to `assistant` records containing `tool_use` blocks with `name == "Bash"` where `input.command` matches `\bll-\w+` (reuse `_is_ll_relevant():59-72` type (c) detection).
   - Also detect slash-command invocations from `user` records with `<command-name>/ll:` patterns and `queue-operation` enqueue records (types (a) and (b) from `_is_ll_relevant()`).
   - Bucket by `sessionId`, sort by `timestamp`, emit ordered list of `(tool_name, timestamp, session_id)` tuples per session.

2. **Add `sequences` subcommand + arg parsing** in `_build_parser():347`.
   - Register `sequences_parser = subparsers.add_parser("sequences", help="...")` following the `discover`/`extract` pattern.
   - Add `--project`/`--all` mutually exclusive group (mirror `_cmd_extract():376`).
   - Add `--min-len` (int, default 2), `--min-count` (int, default 1), `--top` (int, optional), `--window-days` (int, optional, for time-windowed filtering).
   - Call `add_json_arg(sequences_parser)` for `--json` flag.
   - Add `elif args.command == "sequences":` dispatch in `main_logs():406`.

3. **n-gram counting with filters** — implement `_cmd_sequences()` following `_cmd_extract()` structure.
   - Resolve project folder(s) via `get_project_folder()` + `discover_all_projects()` pattern.
   - Extract per-session event streams using the helper from step 1.
   - Build n-grams using a sliding window of `--min-len`+ across each session's ordered event stream, counting with `collections.Counter`. Filter by `--min-count`.
   - If `--window-days` is set, filter records by `timestamp` before n-gram extraction.
   - If `--top` is set, return the top N chains by frequency.

4. **Text + JSON output** — human-readable ranked list (default) and `--json` structured output.
   - Default: print ranked table of chains with count and per-edge transition frequencies.
   - `--json`: use `print_json()` from `cli/output.py:146` with schema `[{chain: [str], count: int, edges: [{from, to, freq}]}]`.
   - `cli_event_context()` already wraps `main_logs()` — no additional wiring needed.

5. **Tests** in `scripts/tests/test_ll_logs.py`.
   - Add `TestSequences` class following existing `TestExtract` fixture patterns: `_make_project_dir()`, `_assistant_bash_record()`, `tempfile.TemporaryDirectory()`, `patch("sys.argv", ...)`, `capsys.readouterr()`.
   - Cover: n-gram counting correctness, `--min-len`/`--min-count`/`--window-days` filtering, `--top` limit, `--json` schema validation, `--project` vs `--all`, empty corpora, no-match edge cases.
   - Add wiring check in `test_ll_logs_wiring.py` that `sequences` appears in `commands/help.md`.
   - Add `test_sequences_subcommand` to `TestArgumentParsing` following the existing pattern at `test_ll_logs.py:23-27` [Agent 3 finding].

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. **Documentation updates** — reflect the new `sequences` subcommand across all doc surfaces.
   - `docs/reference/CLI.md:1707-1743` — add `sequences` to subcommands table, flag table, and examples following the existing `discover`/`extract`/`tail` format.
   - `docs/reference/API.md:3525-3539` — add `sequences` to `main_logs` subcommands list with flags and JSON schema (already noted in Integration Map).
   - `commands/help.md:280` — update ll-logs description to include `sequences` (already noted in Integration Map).
   - `.claude/CLAUDE.md:184` — add `sequences` to `ll-logs` subcommand parenthetical list.
   - `docs/ARCHITECTURE.md:250` — add `sequences` to the `logs.py` file description comment.
   - `skills/init/SKILL.md:411,447` — update ll-logs descriptions to include "sequence" capability.
   - `CHANGELOG.md` — add entry for new `sequences` subcommand following conventional commit format.

7. **Argument parsing test** — add `test_sequences_subcommand` to `TestArgumentParsing` in `scripts/tests/test_ll_logs.py` following the pattern at `test_ll_logs.py:14-27` (patch `sys.argv`, assert `args.command == "sequences"`).

## API/Interface

`ll-logs sequences` — new subcommand; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq}]}]`. Supports `--top N` to limit output to top N chains by frequency.

## Scope Boundaries

- **In scope**: extracting ll skill/command/`ll-*` Bash invocations from JSONL logs into ordered per-session event streams; n-gram counting with CLI filters; text and `--json` output
- **Out of scope**: consuming or integrating the output into `loop-suggester` or FEAT-1309 (that's their respective issues); visualization or analysis of n-grams beyond ranked list output; real-time log monitoring; non-ll tool chains

## Impact

- **Priority**: P3 — enabling primitive for loop-suggester and FEAT-1309; not urgent but reduces duplicated mining logic
- **Effort**: Small — new subcommand reusing existing `discover`/`extract` project enumeration; no new parsing infrastructure needed
- **Risk**: Low — additive subcommand; does not modify existing `ll-logs` subcommands or shared state
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md#little_loopscli` (ll-logs)

## Labels

captured, ll-logs, loop-suggester

## Status

**Open** | Created: 2026-06-04 | Priority: P3


## Resolution

**Completed**: 2026-06-05T23:46:33Z | **Status**: done

### Changes Made

1. **`scripts/little_loops/cli/logs.py`** — Added `sequences` subcommand with:
   - `_extract_ll_event_streams()` helper — walks JSONL files, extracts per-session ordered event streams detecting assistant Bash tool-uses, queue-operation enqueues, and user command-name patterns
   - `_extract_tool_name()` — extracts normalized tool/skill names from three record types (matches `_is_ll_relevant()` detection)
   - `_parse_iso_timestamp()`, `_count_ngrams()`, `_build_chain_results()`, `_compute_edges()` — support functions for timestamp parsing, n-gram counting with sliding window, result ranking, and per-edge transition frequency computation
   - `_cmd_sequences()` — main command handler with --project/--all project resolution, --min-len/--min-count/--top/--window-days filtering, text and --json output
   - `InvocationEvent`, `Edge`, `ChainResult` dataclasses for structured data
   - Parser registration in `_build_parser()` with all flags
   - Dispatch branch in `main_logs()`

2. **`scripts/tests/test_ll_logs.py`** — Added `TestArgumentParsingSequences` (8 tests) and `TestSequences` (10 tests) covering:
   - Argument parsing defaults and overrides
   - Basic n-gram counting, --min-len/--min-count/--top/--window-days filtering
   - --json output schema validation
   - --project vs --all source selection
   - Queue-operation detection
   - Empty/no-match edge cases

3. **`scripts/tests/test_ll_logs_wiring.py`** — Added `test_sequences_in_ll_logs_description` wiring test

4. **Documentation** — Updated 7 files:
   - `commands/help.md:280` — ll-logs description includes sequences
   - `.claude/CLAUDE.md:184` — ll-logs subcommand list includes sequences
   - `docs/ARCHITECTURE.md:250` — logs.py description includes sequences
   - `docs/reference/API.md:3525-3539` — main_logs subcommands includes sequences with flags and JSON schema
   - `docs/reference/CLI.md:1701-1743` — full sequences subcommand section with flags table and examples
   - `skills/init/SKILL.md:411,447` — both boilerplate blocks include "sequences" capability
   - `CHANGELOG.md` — entry under [Unreleased] Added

### Verification

- ✅ All 50 tests in `test_ll_logs.py` pass (including 18 new sequences tests)
- ✅ All 6 wiring tests pass (including new sequences wiring test)
- ✅ `ruff check` passes on modified file
- ✅ `mypy` type checking passes on modified file
- ✅ Full test suite: 10,754 passed (no regressions)

## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:ready-issue` - 2026-06-05T23:31:29 - `a03c517d-b7a6-4a52-a7e0-d0bcc85a3f31.jsonl`
- `/ll:wire-issue` - 2026-06-05T23:22:41 - `0c70f56b-0c84-4dfe-a2c7-7fa2122dcc4a.jsonl`
- `/ll:refine-issue` - 2026-06-05T23:15:53 - `06348717-ce29-461a-8eec-684550f7cdb4.jsonl`
- `/ll:confidence-check` - 2026-06-05T23:45:00 - `2941edf8-31dc-4377-86b4-04f33244b7a5.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:16 - `cd123288-5c07-482f-b424-1eebfea29b6e.jsonl`
- `/ll:format-issue` - 2026-06-04T03:07:47 - `f957d413-8388-4582-b04a-6c037cc6e22e.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
- `/ll:manage-issue` - 2026-06-05T23:46:33Z - `ecdf5f1c-ad5e-40f1-b948-0f09a3fe5f0f.jsonl`
