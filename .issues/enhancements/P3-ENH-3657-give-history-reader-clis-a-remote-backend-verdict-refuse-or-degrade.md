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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py:_build_parser` — epilog "Exit codes" lists only `0`/`1 - No data found`; add the remote-refusal cause to exit 1 if `main_ctx_stats` refuses [Agent 2 finding]
- `scripts/little_loops/cli/harness.py:_parse_harness_args` — epilog "Exit codes" (`0` pass, `1` fail, `2`, `3` abstain) does not mention a refusal; a refusal returning 1 is indistinguishable from a graded FAIL, so document it or pick a distinct return [Agent 2 finding]
- `scripts/little_loops/cli/messages.py:main_messages` — `--reader` help text ("auto (DB first, JSONL fallback), db (DB only, error if unavailable)") already matches the degrade/refuse split; verify wording only [Agent 2 finding]
- `scripts/little_loops/loops/lib/cli.yaml` (`ll_history_summary` description) — the description tells callers to redirect stderr; extend it for the refusal exit 1 if item 5 lands a fallback or documents the exit [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `cli/messages.py:main_messages` (sole caller of `extract_conversation_turns`), `cli/issues/decisions.py:cmd_decisions` (sole caller of `generate_from_completed`); `issue_history/parsing.py` and `issue_history/evolution.py` gate on `.exists()`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_history`, `main_harness`, `main_logs`, `main_ctx_stats`; entry points in `scripts/pyproject.toml` (`ll-history`, `ll-harness`, `ll-logs`, `ll-ctx-stats`). **Boundary shape**: `main_history()` and `main_logs()` take **no `argv`** (read `sys.argv[1:]`), while `main_harness(argv=None)` and `main_ctx_stats(argv=None)` do; each body runs inside `cli_event_context(DEFAULT_DB_PATH, ...)`, so a `try/except HistoryUnsupported` must sit inside the `with` to return 1 without the context seeing an exception (unverified whether the exit-1 CLI event row is still written) [Agent 2 finding]
- `scripts/little_loops/loops/sft-corpus.yaml` state `stage` — `ll-messages --sft-format ... --reader db ... 2>/dev/null || touch "$OUTPUT"`: this is the `reader=db` refuse path, so the new exit 1 is swallowed, `stage` emits an empty `raw.jsonl` and routes to `enrich` as success with the refusal text hidden. Decide whether `sft-corpus` should use `--reader auto` or fail loudly [Agent 1 + Agent 2 finding]
- `.loops/ll-logs-telemetry-digest.yaml` state `run_stats` — branches on `grep -q "No history.db found" "$ERR"` against `logger.warning(...)` in `cli/logs.py` (stats aggregator, ~`:1556`); a new `ll-logs` degrade notice must **add** a stderr line, never reword that string, or `STATS_NO_DATA` flips to `STATS_OK` [Agent 2 finding]
- `scripts/little_loops/loops/lib/common.yaml` fragment `harness_exit` — describes `ll-harness` exit codes only; no YAML currently invokes `ll-harness`, so a refusal exit 1 reaches only prose gates [Agent 2 finding]
- `skills/analyze-history/SKILL.md` — runs `ll-history summary` / `analyze` interactively with no fallback; a refusal surfaces as a stderr line + exit 1 [Agent 2 finding]
- `skills/create-eval-from-issues/SKILL.md` — tells users to run `ll-harness dsl evals/dsl/<source>/` (`cmd_dsl`, one of the five pre-resolve sites) with no fallback [Agent 2 finding]
- `skills/improve-claude-md/SKILL.md` Step CT-0 — top of `--consume-triggers` mode; empty stdout currently reads as "No open Evolution Trigger candidates found", so the invisible failure masquerades as "no candidates". SKILL.md is 344 lines, so the guard fits under the 500-line cap without a companion extraction [Agent 2 finding]
- `scripts/little_loops/cli/doctor.py`, `cli/issues/set_status.py`, `cli/issues/research_triage.py`, `cli/parallel.py`, `cli/sprint/run.py`, `cli/loop/run.py`, `work_verification.py`, `transport.py`, `runner_spec.py`, `parallel/{orchestrator,merge_coordinator,worker_pool}.py`, `fsm/{executor,continuity}.py` — also call `resolve_history_db()` but are writers/runtime, not reader verdict sites; confirm they belong to BUG-3652 (not this issue), and check `cli/doctor.py` (ENH-3525 history-DB check) specifically, since it is user-invoked and reads [Agent 1 finding]
- `scripts/little_loops/issue_history/workspace_quality.py` — already handles `HistoryUnsupported` for the `attach` refusal and gates `activity` via `_gate_member`; `activity --workspace` members use per-member non-default paths, so a subcommand-entry `refuse_on_remote(None, ...)` applies to cwd config only [Agent 1 + Agent 3 finding]
- `scripts/little_loops/history_reader/_base.py:_connect_readonly` — shared read chokepoint (`open_history_readonly(db_path, ensure=True)`) for `history_reader/{summary_dag,usage,runs,search,context,formatting}.py`; also reached by `cli/history_context.py:main_history_context` (separate CLI, callers wrap in `2>/dev/null || true`) [Agent 1 finding]

### Similar Patterns
- `refuse_on_remote` callers in `session_store/lifecycle.py` and `session_store/queries.py`; CLI boundary handling in `cli/backfill_worker.py:main` and `cli/session.py:_main_migrate`.

### Tests
- `scripts/tests/test_remote_operation_matrix.py` (`_REJECTED`), `test_remote_hooks.py` (fixture shape), `test_decisions.py`, `test_cli_decisions.py`, `test_cli_harness.py`, `test_improve_claude_md_skill.py`.

_Wiring pass added by `/ll:wire-issue`:_

No test under `scripts/tests/` asserts that a reader CLI refuses or degrades under `provider: libsql`, and none of the reader-CLI test files use `HranaStub`/`libsql`; every verdict test is new. New tests reuse the `remote` fixture (duplicated in `test_remote_operation_matrix.py`, `test_remote_hooks.py`, `test_libsql_backend.py`; must `monkeypatch.delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`) — hoist it into `conftest.py` or a shared helper rather than copying it into six more files.

- `scripts/tests/test_cli_history.py` (`TestHistoryRootSubcommand`, `TestHistoryReworkSubcommand`, `TestHistoryQualitySubcommand`, `TestHistoryActivity`, `TestHistorySessionsJson`, `TestHistoryAnalyzeDbPath`) — new per-subcommand refuse tests; follow the `patch.object(sys, "argv", ...)` + `patch("pathlib.Path.cwd", ...)` shape. `TestHistoryActivity` already uses `delenv("LL_HISTORY_DB")` and stays safe if the refusal is scoped to cwd config [Agent 3 finding]
- `scripts/tests/test_issue_history_cli.py` (`test_main_history_summary_empty`, `test_main_history_summary_json`, `test_main_history_summary_text`) and `scripts/tests/test_cli.py` `TestHistory*` — local `summary`/`analyze` coverage that must stay green; add the `summary` refuse test beside them [Agent 3 finding]
- `scripts/tests/test_ll_logs.py` (`TestDiff` ~`:4193`, `TestEvalExport` ~`:4475`, `TestStats::test_stats_no_db_returns_0` ~`:2347`) — new `_cmd_diff`/`_cmd_eval_export` remote tests; assert stderr notice and unchanged stdout (Pattern: `capsys.readouterr().err` vs `.out`) [Agent 3 finding]
- `scripts/tests/test_cli_ctx_stats.py` (`test_env_var_overrides_default_db_location` ~`:537`) — new `main_ctx_stats` remote notice test; uses `monkeypatch.chdir(tmp_path)` + `patch("sys.argv", ...)` [Agent 3 finding]
- `scripts/tests/test_user_messages.py` (`test_extract_conversation_turns_basic`, ENH-3428 `reader="jsonl"` test ~`:2624`) and `scripts/tests/test_cli_messages.py` — no existing test exercises `reader="auto"` or `reader="db"`; add both remote cases (auto → JSONL, db → refuse) [Agent 3 finding]
- `scripts/tests/test_mcp_server.py` (`test_history_search_tool_empty_db_returns_empty_list` ~`:227`, `test_call_unknown_tool_returns_error_not_exception` ~`:264` as the `is_error` shape) and `test_enh_3171_mcp_project_root.py::test_history_search_reads_db_under_explicit_root_from_foreign_cwd` (~`:179`) — **design hazard**: `refuse_on_remote(db, operation)` has no `root=` and reads config from cwd, so `refuse_on_remote(None, "history_search")` reads the wrong config when the MCP `project_root` differs from cwd; no test covers a remote config at `project_root` with a foreign cwd — write one [Agent 3 finding]
- `scripts/tests/test_cli_harness.py` (`TestMainHarness`; ~13 direct `resolve_history_db(DEFAULT_DB_PATH)` calls at ~`:1359`, `:2982`, `:4094`, `:4149`, `:5180`–`:5315`) — many tests call `cmd_cmd(args)`/`cmd_skill(args)` directly, so a catch only in `main_harness` does not cover them; new remote tests must call `main_harness([...])`. Existing local tests are unaffected [Agent 3 finding]
- `scripts/tests/test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (~`:137`) and `TestSchemaSeam::test_ensure_db_refuses_a_remote_target_before_any_mutation` (~`:322`), `test_session_store_backend.py::test_backend_not_local_is_an_unsupported_error` — pin that `resolve_history_db` still raises `HistoryBackendNotLocal` and that it subclasses `HistoryUnsupported`; the fix must stay at call sites, not change `resolve_history_db` [Agent 3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — AST gate failing on `sqlite3.connect(` outside `session_store/backend.py`; degrade paths must not add a raw connect [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT` (~`:217`) requires `skills/improve-claude-md/SKILL.md` to keep `[ -f .ll/decisions.yaml ]` (BUG-2423) and `DOC_STRINGS_ABSENT` (~`:387`–`:391`) requires `decisions list --type rule 2>/dev/null | grep`; edit CT-0 only, leave CT-1 intact [Agent 3 finding]
- `scripts/tests/test_enh494_skill_companions.py` (500-line cap; SKILL.md is 344) and `scripts/tests/test_fsm_fragments.py::test_all_cli_yaml_fragments_have_description` (keep the `ll_history_summary` description non-empty) [Agent 3 finding]
- Docs gates to keep green: `scripts/tests/test_wiring_reference_docs.py` (`DOC_STRINGS_PRESENT`: `CONFIGURATION.md` must keep `history.backend.provider`, `history.backend.project_id`, `Remote history backend`; `CLI.md` must keep `ll-session migrate`) and `scripts/tests/test_docs_audience_gate.py` [Agent 3 finding]
- Local-behavior regressions to guard: `test_cli_decisions.py::TestDecisionsCLIGenerate::test_generate_from_completed_writes_entries` and `test_decisions.py::TestGenerateFromCompleted::test_honors_ll_history_db_env_override` (ENH-3525) pin the local DB-vs-scan branch; the remote degrade branch must not re-gate the local path onto the file scan [Agent 3 finding]
- Rejected-operation matrix: add one `_REJECTED` row per new operation name (`(operation, lambda)` calling `refuse_on_remote(None, "<op>")`); no test asserts the `_REMOTE_REFUSALS` key set or the default why-clause `"it is a local-file operation"`, so a key-per-operation test is new [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md`, `docs/reference/CONFIGURATION.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md:758`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md` — no remote/libsql mention at all; `ll-history summary|analyze|export|root` (~`:389`–`:423`), `rework|quality|activity` (~`:457`–`:514`), and `eval-export` "degrades gracefully to `{}` if `history.db` is missing" (~`:565`) need a remote note [Agent 2 finding]
- `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125` — `--reader SOURCE` (`auto`/`db`/`jsonl`) row is where the auto→JSONL degrade vs `db` refuse is stated [Agent 2 finding]
- `docs/guides/EVALUATION_GUIDE.md:481` — "Every `ll-harness` invocation writes a row to `harness_events` in `.ll/history.db`"; clarify against the refusal [Agent 2 finding]
- `docs/reference/loops.md:493` — `sft-corpus` step "`ll-messages --sft-format --reader db` for DB-first transcript ingestion"; note it refuses under a remote backend [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` (`:316` `ll-ctx-stats` reader, `:502` `ll-harness` CLI-support row, `:606` session store row) — mention the remote-backend reader verdicts [Agent 2 finding]
- `docs/reference/COMMANDS.md:586` and `docs/guides/MCP_SERVER_GUIDE.md` (`history_search` read-tools table) — `analyze-history` skill delegation and MCP `history_search` refusal [Agent 1 + Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md:3662` — `ll_messages` fragment with the `--sft-format` override note (adjacent to the known `:3660` `ll_history_summary` entry) [Agent 2 finding]
- `docs/reference/API.md` — one stale-phrase check: BUG-3652 cites `API.md:9946` "SQLite-only prerequisite" (different from ARCHITECTURE.md's "SQLite-only chokepoint"); confirm whether it is in scope [Agent 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Place the `except HistoryUnsupported` inside each `cli_event_context(...)` block (`main_history()` and `main_logs()` take no `argv`; `main_harness(argv=None)` and `main_ctx_stats(argv=None)` do), and test `main_harness([...])` rather than the `cmd_*` handlers, which existing tests call directly
- Thread `root=project_root` for MCP `_tool_history_search`: `refuse_on_remote` has no `root=` and reads cwd config, so either resolve the backend against `project_root` first or accept cwd-only semantics and record it; add a remote-config-at-`project_root` + foreign-cwd test beside `test_enh_3171_mcp_project_root.py`
- Keep `cli/logs.py`'s `"No history.db found"` warning string unchanged; add the degrade notice as a separate stderr line (`.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps it)
- Decide `loops/sft-corpus.yaml` `stage` (`--reader db ... 2>/dev/null || touch`): switch to `--reader auto` or surface the refusal, since the swallowed exit 1 currently yields an empty corpus routed to `enrich` as success
- Update `cli/ctx_stats.py` and `cli/harness.py` epilog "Exit codes" text, and `loops/lib/cli.yaml` `ll_history_summary` description, for the new refusal exit 1
- Update `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125`, `docs/guides/EVALUATION_GUIDE.md:481`, `docs/reference/loops.md:493`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/COMMANDS.md:586`, `docs/guides/MCP_SERVER_GUIDE.md` alongside the four reference docs already listed
- Update `skills/analyze-history/SKILL.md` and `skills/create-eval-from-issues/SKILL.md` to tell the model what a remote-refusal exit 1 means (no fallback exists in either today)
- In `skills/improve-claude-md/SKILL.md`, edit CT-0 only (keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`); no checked-in `ll-adapt` host mirror of this skill was found, so run `ll-adapt --apply` and confirm whether it changes anything before treating step 2 as a mirror update
- Hoist the `remote` fixture (currently copied in three test files) into `scripts/tests/conftest.py` or a shared helper before adding reader-CLI remote tests; add `_REJECTED` rows per new operation in `test_remote_operation_matrix.py`

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
- `/ll:wire-issue` - 2026-09-29T06:08:54 - `6853b72a-3d36-49af-862a-88cc681f2623.jsonl`
- `/ll:refine-issue` - 2026-09-29T06:01:38 - `fce6088f-c5fa-4a10-a502-c439e3fca2a1.jsonl`
