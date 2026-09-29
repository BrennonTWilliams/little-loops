---
id: ENH-3657
type: ENH
title: Give history reader CLIs a remote-backend verdict (refuse or degrade)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:43Z'
---

# ENH-3657: Give history reader CLIs a remote-backend verdict (refuse or degrade)

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), user-invoked history reader commands pre-resolve through `resolve_history_db()` and raise an unhandled `HistoryBackendNotLocal`. The reader layer (`history_reader.*`, `issue_history.parsing.*`, `decisions.generate_from_completed`) coerces with `Path(db)` and calls `.exists()`, so routing readers to the remote store is not a call-site-only change. This issue gives each reader site an explicit verdict: refuse cleanly with a named `HistoryUnsupported`, or degrade to a correct fallback. Split out of BUG-3652, which now covers only the startup/write path.

## Current Behavior

These sites raise `HistoryBackendNotLocal` (or exit via a traceback) under a remote backend with `LL_HISTORY_DB` unset:

- `cli/history.py:main_history` (8 sites, including the `summary` and `analyze` paths)
- `cli/harness.py` (5 sites)
- `cli/logs.py` (2), `cli/ctx_stats.py` (1)
- `decisions.py:generate_from_completed` (`:596`), `user_messages.py:extract_conversation_turns` (`:1198`)
- `mcp_server/tools.py:_tool_history_search` (`:172`; `call_tool` converts to `is_error`)
- `skills/improve-claude-md/SKILL.md` Step CT-0 (`python3 -c` block calling `resolve_history_db()` then `detect_recurring_feedback`)

`cli/logs.py`, `cli/ctx_stats.py` and `cli/history.py:807` already degrade silently on `HistoryError`, with no user-visible notice.

## Expected Behavior

Default verdict: a clean refusal via `refuse_on_remote(None, "<cli op>")` at subcommand entry; the CLI boundary catches `HistoryUnsupported`, prints `<prefix>: <exc>` to stderr, returns 1, no traceback. Degrade instead where a correct fallback exists:

| Site | Under remote |
|---|---|
| `decisions.generate_from_completed` | fall back to the issues-directory scan |
| `user_messages` with `reader=auto` | fall back to JSONL (`reader=db` refuses) |
| `skills/improve-claude-md` CT-0 | skip with a one-line note |
| `cli/logs.py`, `cli/ctx_stats.py`, `cli/history.py:807` | keep degrading, but print a one-line stderr notice |
| `cli/history.py` (rest), `cli/harness.py`, MCP `history_search` | refuse with a named operation |

Reader refusals share one reason string in `_REMOTE_REFUSALS` (`session_store/backend.py`).

## Motivation

Remote-backend users hit an unhandled traceback from `ll-history`, `ll-harness` and other readers, and the reader layer cannot yet take a `RemoteTarget`. A clean, named refusal (or a correct degrade) is the achievable fix now, and it removes the ambiguity that held BUG-3652's outcome confidence at 56.

## Scope Boundaries

- In scope: the reader sites, the `improve-claude-md` CT-0 block, and reader-facing docs listed above.
- Out of scope: startup and write-path sites (BUG-3652), hand-built `.ll/history.db` paths (ENH-3658), and building `HistoryTarget`-aware readers that read from the remote store (a future FEAT).

## Proposed Solution

1. Add `_REMOTE_REFUSALS` entries (one shared reader reason) and matching `_REJECTED` rows in `test_remote_operation_matrix.py::TestRejectedOperations`.
2. Per-site edits per the table above; CLI boundaries catch `HistoryUnsupported`.
3. `skills/improve-claude-md/SKILL.md`: guard the CT-0 block (SKILL.md is capped at 500 lines), then run `ll-adapt --host <gemini|kimi-code|qwen> --apply` and re-run `test_improve_claude_md_skill.py`.
4. Docs: `docs/reference/CLI.md` per-CLI remote notes (`ll-history`, `ll-harness`, `ll-logs`, `ll-ctx-stats`), `docs/reference/CONFIGURATION.md` "Remote history backend" not-supported list, `docs/reference/API.md` (`main_ctx_stats`, `generate_from_completed`, `Backend chokepoint`), `docs/ARCHITECTURE.md:758` (stale "SQLite-only chokepoint" text). Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose.
   **Re-check the "reader layer cannot take a `RemoteTarget`" premise before defaulting to refuse** (finding from BUG-3652's `/ll:advise` review, 2026-09-29): the `history_reader` entry point `_connect_readonly` already opens through `open_history_readonly`, which is remote-capable for a default-shaped `Path`. Where a reader site only fails because the CLI pre-resolves with `resolve_history_db()`, dropping the pre-resolve and passing the default path may make it read remotely — no refusal needed. Sites that gate on `.exists()` (`issue_history/parsing.py`, `evolution.py`) or coerce with `Path(db)` still need refuse/degrade. Verify per site against `HranaStub` before choosing.
5. Decide whether `loops/lib/cli.yaml:66` (`ll-history summary` gate, no `|| true`) gets an `|| echo "(no history available)"` fallback or the exit 1 is documented as intended.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Constraint from `refuse_on_remote`**: signature is `refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None`; it resolves with no `root=`, so `None` reads backend config from cwd, and it raises only for a `RemoteTarget` — an explicit non-default path or `LL_HISTORY_DB` passes. An operation missing from `_REMOTE_REFUSALS` (a plain `dict[str, str]`: operation → why-clause) gets the default why `"it is a local-file operation"`, so the shared reader reason must be added as one key per operation name, not one key overall (the message format is `f"{operation} is not supported under history.backend provider {provider!r}: {why}"`, with `operation=` set on the exception).
- **Constraint from the exception hierarchy**: `HistoryUnsupported(HistoryError)`; `HistoryBackendNotLocal(HistoryUnsupported)`. A boundary `except HistoryUnsupported` therefore also catches the unhandled `HistoryBackendNotLocal` raised by any remaining pre-resolve, but a bare `except HistoryError` at `history.py:807`/`logs.py` would additionally swallow real store errors. Only `HistoryUnsupported` is exported from `session_store/__init__.py`; `HistoryBackendNotLocal` and `refuse_on_remote` are imported from `session_store.backend`.
- **Premise check result** (the item-4 caveat): the premise "reader layer cannot take a `RemoteTarget`" is *partly* false. `history_reader.*` takes `Path | str` (never a `HistoryTarget`), but reaches the remote store when handed `None` or the relative `DEFAULT_DB_PATH`; the sites in Integration Map → "Remote-capable if the pre-resolve is dropped" qualify. The `.exists()`/sqlite-only sites do not. So the verdict set is mixed: some rows can *serve* remote reads instead of refusing, which would change the Expected Behavior table and the "Consequence to record" in Related.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py`, `cli/harness.py`, `cli/logs.py`, `cli/ctx_stats.py`, `decisions.py`, `user_messages.py`, `mcp_server/tools.py`, `session_store/backend.py` (`_REMOTE_REFUSALS`), `skills/improve-claude-md/SKILL.md`; sites and line numbers are in BUG-3652's caller table.

### Dependent Files (Callers/Importers)
- `cli/messages.py:main_messages` (sole caller of `extract_conversation_turns`), `cli/issues/decisions.py:cmd_decisions` (sole caller of `generate_from_completed`); `issue_history/parsing.py` and `issue_history/evolution.py` gate on `.exists()`.

### Similar Patterns
- `refuse_on_remote` callers in `session_store/lifecycle.py` and `session_store/queries.py`; CLI boundary handling in `cli/backfill_worker.py:main` and `cli/session.py:_main_migrate`.

### Tests
- `scripts/tests/test_remote_operation_matrix.py` (`_REJECTED`), `test_remote_hooks.py` (fixture shape), `test_decisions.py`, `test_cli_decisions.py`, `test_cli_harness.py`, `test_improve_claude_md_skill.py`.

### Documentation
- `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md:758`.

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Reader-layer remote capability is decided by path shape, not by the CLI's pre-resolve alone.** `open_history_readonly(target, *, ensure=False)` → `_resolve_once()` (`session_store/backend.py`) treats `None` / a relative path as remote-capable under libsql (`LL_HISTORY_DB` unset) but treats any **absolute** path as `LocalTarget` verbatim (BUG-3181 contract). `db._is_default_shaped()` accepts `None`, `DEFAULT_DB_PATH`, or basename `history.db` under a `.ll` parent. Every CLI site below passes an absolute `project_root / DEFAULT_DB_PATH` (or `cwd / DEFAULT_DB_RELPATH`) except `harness.py`, which passes the relative `DEFAULT_DB_PATH`.
- **Per-site remote verdict** (input to the refuse/degrade decision; verified against the reader code, not yet against `HranaStub`):
  - *Remote-capable if the pre-resolve is dropped and a relative default / `None` is passed* (readers do `Path(db)` → `_connect_readonly`, no `.exists()` gate): `cli/harness.py` `:245` `_retry_gate`, `:1089` `_read_target_history`, `:1994` `_resolve_baseline_of`, `:2027` `read_baseline`, `:3613` `cmd_dsl`; `cli/history.py` `:592` `rework`, `:628` `quality`, `:755` `audit-issue-collisions`, `:780` `sessions`, `:797` `root`; `mcp_server/tools.py:172` `_tool_history_search` (needs `root=project_root`; `_resolve_once` takes no `root`, and `history_reader.search` takes `Path`, so a root-anchored remote target cannot be threaded through today).
  - *Cannot read remote — `.exists()` gate or sqlite-only opener; needs refuse or degrade*: `cli/history.py` `:501` `summary` (`issue_history/parsing.py` `issue_events_ever_recorded`, `scan_completed_issues_from_db`, `count_loop_runs_in_window`), `:551` `analyze` (`evolution._open_db`, `detect_recurring_feedback`, `detect_skill_bypass`), `:731` `activity` (`workspace_quality._gate_member`); `cli/ctx_stats.py:1074` (every `_aggregate_*` gates on `db_path.exists()`); `cli/logs.py:1721` `_cmd_diff` (`_resolve_session_log`) and `:1965` `_cmd_eval_export` (`history_reader.lookup_session_metadata`); `decisions.py:596`; `user_messages.py:1198` (`history_reader.conversation_turns`); `skills/improve-claude-md` CT-0 (`evolution._open_db`).
- **`evolution._open_db` is the sqlite-only choke point** shared by `analyze` and CT-0: it does `.exists()` then `resolve_backend().connect_readonly(Path)` with no argument, so `resolve_backend()` is `SqliteBackend`. Making it remote-aware would resolve two verdict rows at once; leaving it refuses both.
- **Current Behavior correction for the "already degrade silently" claim**: in `cli/logs.py`, `cli/ctx_stats.py` and `cli/history.py:root`, the `except HistoryError` handlers (`logs.py:869/877/902/1611/1621`, `history.py:807`) wrap only `connect_readonly` and the queries; the `resolve_history_db()` pre-resolve (`logs.py:1721/1965`, `ctx_stats.py:1074`, `history.py:797`) sits **outside** them. Those sites therefore raise `HistoryBackendNotLocal` unhandled today, not degrade. `main_logs` has no handler and `cli_event_context` re-raises (`exit_code = 1; raise`).
- **`history_reader._connect_readonly` swallows `HistoryError` to `None`** (warning logged). Under a remote target `LibsqlBackend.ensure_schema` runs `remote_schema.check_access(..., write=True)` and raises `HistoryUnsupported` for a store that is behind, ahead, or belongs to another project — so a reader that *does* reach the remote store reports "no data" rather than a refusal for those states.
- **`skills/improve-claude-md` CT-0** already ends its `python3 -c` block with `2>/dev/null`, so under remote it emits empty stdout with the traceback hidden — the skip-with-note verdict changes an invisible failure into a visible one.
- **`loops/lib/cli.yaml:66` resolves to a different path**: the file lives at `scripts/little_loops/loops/lib/cli.yaml`; the fragment is `ll_history_summary` (`action: "ll-history summary"`, `evaluate: type: exit_code`), whose description already tells callers to redirect stderr themselves. `evaluation-quality.yaml:46` and `backlog-flow-optimizer.yaml:35` inline `ll-history summary 2>/dev/null || echo "(no history available)"` and do not use the fragment. Docs mention: `docs/guides/LOOPS_REFERENCE.md:3660`.
- `harness.py` caller fan-out (all funnel through the five pre-resolve sites, so a fix at those five covers them): `_retry_gate` ← `:2819`, `:2980`, `:3108`, `:3243`, `:3398`; `_read_target_history` ← `:2509`, `:2654`; `_resolve_baseline_of` ← `:2883`, `:3038`, `:3166`, `:3293`; `read_baseline` ← ten sites (`:2076`–`:3303`). `harness.py` has no `HistoryError`/`HistoryUnsupported` handling anywhere.
- `cmd_decisions` reaches `generate_from_completed` only in the `sub == "generate"` branch (`cli/issues/decisions.py:388`–`:390`); `main_messages` reaches `extract_conversation_turns` only in the `--sft-format` branch (`cli/messages.py:281`, passing `reader=args.reader`). With `reader="db"` and empty windows `extract_conversation_turns` already raises `RuntimeError("history.db missing or predates v11; ...")`.
- `mcp_server/tools.py` `handle_call_tool` wraps handlers in `try/except Exception` and returns `CallToolResult(..., is_error=True)` with `str(exc)`; the policy guard `check_tool_call` sits outside that `try`.
- `test_remote_operation_matrix.py::_REJECTED` is a `list[tuple[str, Callable]]` of `(operation, lambda)` (8 rows today); `TestRejectedOperations::test_raises_naming_the_operation_before_any_network_call` asserts `pytest.raises(HistoryUnsupported)`, `ei.value.operation == operation`, `"libsql" in str(ei.value)`, and `len(remote.requests)` unchanged. Sibling tests `test_local_sqlite_still_runs_the_same_operations` (sets `LL_HISTORY_DB`) and `test_explicit_local_path_is_not_rejected_under_libsql` are the local twins.
- CLI-boundary assertion shape to hold: `test_remote_hooks.py::TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` — `main([...]) == 1`, operation name and `libsql` in stderr, `"Traceback" not in err`. The `remote` fixture is duplicated in `test_remote_operation_matrix.py` and `test_remote_hooks.py` (the latter also calls `remote_telemetry.reset_for_tests()`); it exposes `HranaStub.requests`, `.db`, `.url`.
- Evidence that `history_reader` already reads remotely with a relative default: `TestSupportedOperations::test_reads_round_trip` (`open_history_readonly(ensure=True)`), `TestLlGrepWithoutCreateFunction` (`ll_grep` with default relative `db`), `test_fts5_search_round_trips`. No test asserts a reader CLI refuses, and no `except HistoryUnsupported` exists in `cli/history.py`, `cli/harness.py`, `cli/logs.py` or `cli/ctx_stats.py`.

## Program Design

### Types
- `HistoryError(Exception)` ← `HistoryUnsupported(HistoryError)` ← `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name the CLI boundary prints.
- `_REMOTE_REFUSALS: dict[str, str]` in `little_loops.session_store.backend` — operation name → why-clause; today keyed `rebuild`, `backfill`, `prune`, `compact`, `recompress`, `snapshot_export`.
- `HistoryTarget = LocalTarget | RemoteTarget` in `little_loops.session_store.targets`; no reader signature accepts it (`history_reader.*` and `issue_history.parsing.*` take `Path | str`).

### Signatures
- `refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None` — raises `HistoryUnsupported` only for a `RemoteTarget`.
- `resolve_history_db(path: Path | str | HistoryTarget | None = None, *, root: Path | None = None) -> Path` — raises `HistoryBackendNotLocal` under a remote target.
- `open_history_readonly(target=None, *, ensure: bool = False)` — the remote-capable reader opener used by `history_reader._connect_readonly`.
- `main_history(argv: list[str] | None = None) -> int`, `main_harness`, `main_logs`, `main_ctx_stats` — CLI boundaries that must map `HistoryUnsupported` to `<prefix>: <exc>` on stderr and return `1`.
- `generate_from_completed(project_root, config, ...)` in `little_loops.decisions` and `extract_conversation_turns(..., reader: str)` in `little_loops.user_messages` — the two degrade sites; both already have a non-DB fallback branch.

### Call Path
`main_history` -> `resolve_history_db` -> `HistoryBackendNotLocal` (today, unhandled)
`main_history` -> `refuse_on_remote(None, "<op>")` -> `HistoryUnsupported` -> boundary `except HistoryUnsupported` -> stderr + `return 1` (refuse verdict)
`cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade verdict, replaces `scan_completed_issues_from_db`)
`main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade verdict; `reader="db"` refuses)
`handle_call_tool` -> `_tool_history_search` -> refusal surfaced as `is_error` text naming the operation

### Decision Rules
- **Refuse / degrade / serve classification** is keyed on whether the reader can reach a non-local store, per the Integration Map findings: `.exists()`-gated or `evolution._open_db` readers cannot (refuse, or degrade where a fallback exists); `Path(db)` → `_connect_readonly` readers can when handed `None` or a relative default-shaped path.
- **Refuse inputs**: `db=None` to `refuse_on_remote`, so an explicit non-default path or `LL_HISTORY_DB` continues to run locally; operation name is the subcommand's own name (not one shared string); the reason text is the shared reader why-clause.
- **Escape hatch**: `LL_HISTORY_DB` set, or an explicit non-default `--db`, bypasses the refusal and runs against the local file.
- **Degrade notice**: one line on stderr, only under a remote target, never on stdout (stdout of `ll-history summary`, `ll-logs`, `ll-ctx-stats` is consumed by loops).

## Implementation Steps

1. Add the shared reader reason to `_REMOTE_REFUSALS` and matching `_REJECTED` rows; implement the per-site verdicts from the table (refuse at subcommand entry, or degrade).
2. Guard the `skills/improve-claude-md` CT-0 block, run `ll-adapt --host <gemini|kimi-code|qwen> --apply`, and re-run `test_improve_claude_md_skill.py`.
3. Add remote-stub tests per site plus local twins, update the reader docs, then run `python -m pytest scripts/tests/` (default local store) with `ruff check` and `mypy` clean.

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage is handled by BUG-3652.
- **Effort**: Medium - about 20 reader sites, each a small edit, plus docs and a skill mirror pass.
- **Risk**: Low - local behavior unchanged; reader refusals exit 1 and can trip loop gates such as `ll-history summary`.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Every reader site listed above has a verdict (refuse or degrade) implemented and covered by a remote-stub test.
- [ ] No reader CLI surfaces a bare `HistoryBackendNotLocal` traceback under a remote backend; refusals assert exit 1, operation name plus `libsql` in stderr, `"Traceback" not in err`, and zero stub requests.
- [ ] With the default local store, `python -m pytest scripts/tests/` passes unchanged.

## Related

- BUG-3652 (startup/write-path audit; land first).
- FEAT-3535 (remote libSQL history backend).
- Consequence to record: remote users lose `ll-history` / `ll-harness` reads until a follow-up builds `HistoryTarget`-aware readers.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-29T06:01:38 - `fce6088f-c5fa-4a10-a502-c439e3fca2a1.jsonl`
