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
