---
id: ENH-3657
type: ENH
title: Give history reader CLIs a remote-backend verdict (refuse or degrade)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-29'
captured_at: '2026-09-29T05:29:43Z'
reconcile_attempted: true
relates_to:
- BUG-3652
- ENH-3668
- ENH-3658
blocked_by:
- BUG-3652
confidence_score: 65
outcome_confidence: 51
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3657: Give history reader CLIs a remote-backend verdict (refuse or degrade)

> **Re-scoped 2026-09-29** after the `/ll:advise` (Opus) review: this issue now only *stops the tracebacks* (refuse / degrade, plus serving `ll-harness`). Real remote reads for `ll-history` reader subcommands and MCP `history_search` moved to **ENH-3668**. The earlier plan to "serve" ~11 sites by dropping the pre-resolve was unsafe (see Decision Rules) and is superseded throughout.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), user-invoked history reader commands pre-resolve through `resolve_history_db()` and raise an unhandled `HistoryBackendNotLocal`. This issue gives each reader site an explicit verdict: **refuse** cleanly with a named `HistoryUnsupported`, **degrade** to a correct fallback, or (for `ll-harness` only) **serve** the read from the remote store. Split out of BUG-3652, which covers the startup/write path; real remote reads for the remaining `ll-history` subcommands and MCP are ENH-3668.

## Current Behavior

These sites raise `HistoryBackendNotLocal` (or exit via a traceback) under a remote backend with `LL_HISTORY_DB` unset:

- `cli/history.py:main_history` (8 sites, including the `summary` and `analyze` paths)
- `cli/harness.py` (5 sites)
- `cli/logs.py` (2), `cli/ctx_stats.py` (1)
- `decisions.py:generate_from_completed` (`:596`), `user_messages.py:extract_conversation_turns` (`:1198`)
- `mcp_server/tools.py:_tool_history_search` (`:172`; `call_tool` converts to `is_error`)
- `skills/improve-claude-md/SKILL.md` Step CT-0 (`python3 -c` block calling `resolve_history_db()` then `detect_recurring_feedback`)

Correction (gap analysis): the `except HistoryError` handlers in `cli/logs.py` (`:869/877/902/1611/1621`), `cli/history.py:807` and `cli/ctx_stats.py` wrap only the connect/query calls; the `resolve_history_db()` pre-resolves (`logs.py:1718/1962`, `ctx_stats.py:1188`, `history.py:797`) sit **outside** them, so those sites raise today rather than degrade silently. Also unowned until now: `cli/logs.py` `_cmd_stats` (`:1535/1539`) and `_cmd_dead_skills` (`:997/1002`) build `<project>/.ll/history.db` by hand (ENH-3658 defers them here).

## Expected Behavior

One verdict per site. Refusals come from `refuse_on_remote(<own db arg>, "<op>")` at subcommand entry (before the pre-resolve), the CLI boundary catches `HistoryUnsupported`, prints `<prog> <sub>: <exc>` to stderr and returns 1, no traceback.

| Site | Under remote | Notes |
|---|---|---|
| `cli/history.py` `summary` | **degrade** to the file scan, exit 0 | fallback already exists (`issues = scan_completed_issues(issues_dir)`); one `note:` line on stderr |
| `cli/history.py` `analyze`, `activity` | **refuse** | `evolution._open_db` / `workspace_quality._gate_member` are sqlite-only; degrade instead only if a file fallback exists (verify) |
| `cli/history.py` `rework`, `quality`, `audit-issue-collisions`, `sessions`, `root` | **refuse** (interim) | absolute path ⇒ `LocalTarget` ⇒ dropping the pre-resolve would create an empty shadow DB; real reads are ENH-3668 |
| `cli/harness.py` ×5 | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend`; needs the read-mode ensure fix (Step 1) and verification against `HranaStub`; harness never refuses with exit 1 (indistinguishable from a graded FAIL) |
| `cli/logs.py` `_cmd_diff`, `_cmd_eval_export`, `_cmd_stats`, `_cmd_dead_skills` | **refuse** | keep the literal `"No history.db found"` warning for the local-missing case (digest loop greps it); add the refusal as a separate line |
| `cli/ctx_stats.py` | **refuse** via `refuse_on_remote(args.db, ...)` | pass `args.db` so explicit `--db` still runs locally; gate on `RemoteTarget` so `err == ""` local tests stay green |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first |
| `user_messages.extract_conversation_turns` | `reader=auto` → **degrade** to JSONL; `reader=db` → **refuse** | |
| `skills/improve-claude-md` CT-0 | **degrade**: skip with a one-line note | empty stdout must no longer read as "no candidates" |
| MCP `history_search` | **refuse** as a structured `is_error` result naming the operation | resolve config against `project_root` (`refuse_on_remote` gains `root=`) |

Reader refusals share one why-clause, added as one `_REMOTE_REFUSALS` key per refused operation name (`session_store/backend.py`).

**Convention (decided):** catch `HistoryUnsupported` (never bare `HistoryError`, which would swallow real store errors) at the CLI boundary; message `<prog> <sub>: <exc>`; degrade notices are a single `note:` line via `print(..., file=sys.stderr)` (not `logger.warning`, which is level-filtered and only reaches stderr through `logging.lastResort`), emitted only under a `RemoteTarget`, never on stdout, and never echoing an endpoint token.

## Motivation

Remote-backend users hit an unhandled traceback from `ll-history`, `ll-harness` and other readers, and the reader layer cannot yet take a `RemoteTarget`. A clean, named refusal (or a correct degrade) is the achievable fix now, and it removes the ambiguity that held BUG-3652's outcome confidence at 56. Serving the remaining readers safely needs typed-target plumbing (ENH-3668), not a call-site edit.

## Scope Boundaries

- In scope: the reader sites in the Expected Behavior table (including `cli/logs.py` `_cmd_stats` / `_cmd_dead_skills`, which ENH-3658 defers here), the `improve-claude-md` CT-0 block, the `sft-corpus.yaml` `stage` fix, the read-mode remote ensure fix needed to serve `ll-harness`, `refuse_on_remote(..., root=)`, and reader-facing docs.
- Out of scope: startup and write-path sites (BUG-3652), hand-built `.ll/history.db` paths and `context-monitor.sh` (ENH-3658), and `HistoryTarget`-aware readers that serve `ll-history` subcommands / MCP from the remote store (ENH-3668).

## Proposed Solution

1. **Session-store seams** (`session_store/`): (a) add one `_REMOTE_REFUSALS` key per refused reader operation (shared reader why-clause) and matching `_REJECTED` rows in `test_remote_operation_matrix.py::TestRejectedOperations`; (b) give `refuse_on_remote` an optional `root=` so MCP resolves config against `project_root`; (c) make the ensure step of `open_history_readonly(ensure=True)` for a `RemoteTarget` a read-mode check (a reader must not require a write-current schema), verified against `HranaStub`. Without (c), `ll-harness` serve reads fail on a behind/ahead store and surface as "no data".
2. **Per-site edits per the Expected Behavior table.** Refusals call `refuse_on_remote(<own db arg>, "<op>")` before the pre-resolve; boundaries catch `HistoryUnsupported` inside `cli_event_context`.
3. **`skills/improve-claude-md/SKILL.md`**: guard the CT-0 block (edit CT-0 only; SKILL.md is 344 lines, cap 500), then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and re-run `test_improve_claude_md_skill.py`.
4. **`loops/sft-corpus.yaml` `stage`**: switch to `--reader auto` (degrade to JSONL) so a refusal is not swallowed into an empty corpus routed to `enrich` as success.
5. **Docs**: `docs/reference/CLI.md` per-CLI remote notes, `CONFIGURATION.md` "Remote history backend", `API.md`, `ARCHITECTURE.md:758`, plus the guide/reference files under Wiring Phase. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose.
6. **`loops/lib/cli.yaml` `ll_history_summary` (resolved):** `ll-history summary` now degrades to exit 0 under remote, so no `|| echo` fallback is needed; just keep the fragment description non-empty (`test_all_cli_yaml_fragments_have_description`).

**Premise check (resolved 2026-09-29, `/ll:advise` Opus):** dropping the `resolve_history_db()` pre-resolve does **not** make a site read remotely when it passes an absolute path — `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), and `_connect_readonly`'s `ensure=True` then runs `ensure_schema` on a local path and **creates an empty shadow `.ll/history.db`**. Only `cli/harness.py` (relative `DEFAULT_DB_PATH`) qualifies for "serve" here; every other former "serve" site refuses in this issue and is served by ENH-3668.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Constraint from `refuse_on_remote`**: signature is `refuse_on_remote(db: Path | str | HistoryTarget | None, operation: str) -> None`; it resolves with no `root=`, so `None` reads backend config from cwd, and it raises only for a `RemoteTarget` — an explicit non-default path or `LL_HISTORY_DB` passes. An operation missing from `_REMOTE_REFUSALS` (a plain `dict[str, str]`: operation → why-clause) gets the default why `"it is a local-file operation"`, so the shared reader reason must be added as one key per operation name, not one key overall (the message format is `f"{operation} is not supported under history.backend provider {provider!r}: {why}"`, with `operation=` set on the exception).
- **Constraint from the exception hierarchy**: `HistoryUnsupported(HistoryError)`; `HistoryBackendNotLocal(HistoryUnsupported)`. A boundary `except HistoryUnsupported` therefore also catches the unhandled `HistoryBackendNotLocal` raised by any remaining pre-resolve, but a bare `except HistoryError` at `history.py:807`/`logs.py` would additionally swallow real store errors. Only `HistoryUnsupported` is exported from `session_store/__init__.py`; `HistoryBackendNotLocal` and `refuse_on_remote` are imported from `session_store.backend`.
- **Premise check result** (**superseded** by the resolved premise check under Proposed Solution: only the relative-path `harness.py` sites are safely servable here): the premise "reader layer cannot take a `RemoteTarget`" is *partly* false. `history_reader.*` takes `Path | str` (never a `HistoryTarget`), but reaches the remote store when handed `None` or the relative `DEFAULT_DB_PATH`; the sites in Integration Map → "Remote-capable if the pre-resolve is dropped" qualify. The `.exists()`/sqlite-only sites do not. So the verdict set is mixed: some rows can *serve* remote reads instead of refusing, which would change the Expected Behavior table and the "Consequence to record" in Related.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py`, `cli/harness.py`, `cli/logs.py`, `cli/ctx_stats.py`, `decisions.py`, `user_messages.py`, `mcp_server/tools.py`, `session_store/backend.py` (`_REMOTE_REFUSALS`), `skills/improve-claude-md/SKILL.md`; sites and line numbers are in BUG-3652's caller table. Only `cli/harness.py` ×5 is a serve site (edits only the pre-resolve, plus the read-mode ensure seam); every other site — including `history.py` `rework`/`quality`/`audit-issue-collisions`/`sessions`/`root` and MCP `history_search` — refuses or degrades by adding `refuse_on_remote` and the boundary catch or fallback, and is served later by ENH-3668. `issue_history/evolution.py:_open_db` (sqlite-only choke point shared by `analyze` and CT-0) changes only if made remote-aware.

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

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/evaluation-quality.yaml` state `sample` (`:46`) and `loops/backlog-flow-optimizer.yaml` (`:35`) — inline `ll-history summary 2>/dev/null || echo "(no history available)"`; the refusal exit 1 is already absorbed, so they need no edit, but they are the precedent for item 5's `cli.yaml` fallback. `test_builtin_loops.py:1114` regexes the `evaluation-quality` action text, so its layout is pinned [Agent 1 + Agent 2 finding]
- `scripts/little_loops/loops/examples-miner.yaml:38` and `loops/lib/cli.yaml` fragment `ll_messages` (`:93`) — `ll-messages` with no `--reader`, i.e. `auto`: takes the JSONL degrade path, not a refusal; no edit [Agent 1 finding]
- `scripts/little_loops/loops/fleet-loop-improve.yaml:78-80` — `ll-logs fleet-review ... | tail -n 1`; `fleet-review` is not a listed reader site, and a stderr notice does not disturb the stdout `tail -n 1` capture; no edit [Agent 1 + Agent 2 finding]
- `scripts/little_loops/loops/{test-coverage-improvement:141,incremental-refactor:109,dead-code-cleanup:123,autodev:708}.yaml` — consume `fragment: harness_exit`; none invokes `ll-harness` directly, so a refusal exit 1 reaches them only through the fragment's exit-code space [Agent 1 finding]
- `commands/loop-suggester.md` (`:31`, `:49`, `:309`), `skills/ll-loop-suggester/SKILL.md`, `commands/analyze-workflows.md:79` — `ll-messages` (default `auto` reader) and `ll-logs sequences`; unaffected unless the `ll-messages` default changes [Agent 1 + Agent 2 finding]
- `scripts/little_loops/issue_history/analysis.py:calculate_analysis` (`:144`, `:147`) — calls `detect_recurring_feedback` / `detect_skill_bypass`; the `analyze` path into `evolution._open_db`, reached from `cli/history.py:565` [Agent 1 finding]
- `scripts/little_loops/cli/session.py` (`ll-session search --fts`, ~`:570`) — calls `history_search(..., db=args.db)`; a same-shape reader outside this issue's list, decide whether it belongs to this issue or BUG-3652 [Agent 2 finding]
- `.loops/ll-logs-telemetry-digest.yaml` states `scan-failures` (~`:61`), `sequences` (~`:124`), `dead-skills` (~`:142`) — each captures `2> "$ERR"` beside `run_stats`, so a new `ll-logs` degrade line lands in `$ERR` for all of them, not just `run_stats` [Agent 2 finding]

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

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_enh3549_codex_stored_ctx_stats.py` (`test_codex_cli_uses_latest_selected_stored_session_and_clean_json` ~`:101`–`:122`, asserts `output.err == ""`; `test_codex_missing_store_keeps_json_parseable` ~`:134`) and `test_enh3656_stored_cache_rate.py` (`test_current_session_json_reads_store_with_as_of`, `test_json_stderr_distinguishes_four_store_absences`) — call `main_ctx_stats(["--db", ...])`; break if the ctx_stats refusal ignores `args.db` or the notice prints on a local path. Gate any notice on a `RemoteTarget` and pass `args.db` [Agent 2 + Agent 3 finding]
- `scripts/tests/test_ll_logs.py` (`~:1294`, `~:1898` project-not-found tests index `err_lines[0]`/`err_lines[1]`; `~:344` `test_stale_worktree_path_emits_no_warning` asserts no WARNING records on `little_loops.cli.logs`) and `test_cli_messages.py::TestMessagesZeroHandlesNamesCause` (~`:347`–`:368`) — index-sensitive stderr contracts; a new remote notice must not precede those lines or fire on the local/stale-path cases [Agent 2 finding]
- `scripts/tests/test_feat3410_workspace_quality.py` (~`:118`) and `test_feat3445_workspace_activity.py` (~`:576`) — pin the literal `"history.db not found"` reason in `workspace_quality._gate_member`; leave unchanged for `ll-history activity` [Agent 2 finding]
- `scripts/tests/test_doc_synthesis.py` (four `main_history()` tests, ~`:388`–`:484`, `ll-history export`) and `conformance/test_session_reader_fakes.py::test_ll_messages_cli_reads_both_fake_hosts` (~`:168`, `main_messages() == 0` via `--sft-format`) — local-path regressions to keep green; the latter guards the `reader=auto` degrade [Agent 3 finding]
- `scripts/tests/test_bug_3216_telemetry_digest_invocations.py` (`EXPECTED_TARGETS`) — pins the digest loop's `ll-logs` invocations; add a new test that the `"No history.db found"` string is unchanged (no test asserts the grep today) [Agent 3 finding]
- `scripts/tests/test_loops_sft_corpus.py` — no class covers the `stage` state; add a test asserting the chosen `--reader` flag (or surfaced refusal). `test_builtin_loops.py` (sft-corpus in the builtin set, `:252`; ENH-3358 context-key check) may break if the `stage` edit adds a `${...}` [Agent 3 finding]
- `scripts/tests/test_remote_doctor.py` (fixture ~`:34`; user-invoked CLI reader under a remote backend with `capsys` stderr, ~`:133`–`:148`) — closest structural sibling for the reader-CLI verdict tests; a hoisted `remote` fixture must also reconcile this copy and `test_remote_ingestion_telemetry.py:57` [Agent 3 finding]
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` (~`:397`) and `test_verify_skill_prose.py` (`BASELINE_COUNT = 17`, ~`:219`) — gates over the real `skills/*/SKILL.md`; a CT-0 note must not touch frontmatter or add algorithm-as-prose markers [Agent 3 finding]
- `scripts/tests/test_evolution_triggers.py` — covers `detect_recurring_feedback` / `detect_skill_bypass` (`evolution._open_db`, CT-0); stays green unless `_open_db` is made remote-aware [Agent 1 finding]

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

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — three more anchors beyond the per-CLI notes: `ll-history summary` (~`:3611`) and `analyze` (~`:3639`) subsection bodies, and the MCP tools table `history_search` row (~`:5993`, `ll-mcp` section) [Agent 2 finding]
- `docs/reference/API.md` — `extract_conversation_turns` "Relationship" paragraph (~`:9253`–`:9255`, "DB-first, `reader="auto"` ... falls back to JSONL") needs the remote qualifier (auto → JSONL, db → refuse); `issue_history` function table rows for `scan_completed_issues_from_db` and `detect_recurring_feedback` (~`:2370`–`:2372`); `detect_recurring_feedback()` "existing `_open_db()` path" sentence (~`:10605`) [Agent 2 finding]
- `docs/reference/COMMANDS.md` (~`:695`, `create-eval-from-issues --dsl`) — `ll-harness dsl evals/dsl/<source-name>/` instruction, separate from the `:586` entry already listed [Agent 2 finding]
- `docs/ARCHITECTURE.md` (~`:705`–`:716`, `:858`, `history.db` section) — check for more "SQLite-only" wording while editing `:758` [Agent 2 finding]
- `.gemini/skills/create-eval-from-issues/SKILL.md`, `.qwen/skills/create-eval-from-issues/SKILL.md`, `.kimi-code/skills/create-eval-from-issues/SKILL.md` — committed host mirrors of a skill this issue edits (the `ll-harness dsl` note); regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` (`test_wiring_skills_and_commands.py::test_generated_mirrors_do_not_ship_claude_model_aliases` globs them). `skills/analyze-history` and `skills/improve-claude-md` have no committed mirror; `skills/improve-claude-md/agents/openai.yaml` is the only adapt output and has no history text [Agent 1 + Agent 2 finding]
- Low-priority check only, no edit implied: `docs/reference/OUTPUT_STYLING.md` (~`:465`), `docs/reference/CONFIGURATION.md` (~`:568`, `analytics.capture.file_events`), `README.md:188` / `scripts/README.md:188` (if either is edited, copy to the other — `test_packaging_duplicate_files.py`) [Agent 2 finding]

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

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Anchor drift since the last pass** (re-grepped 2026-09-29, after commit `9cb4467d6`): `cli/ctx_stats.py` pre-resolve is now `:1188` (was `:1074`; `main_ctx_stats` starts `:1175`); `cli/logs.py` `_cmd_diff` `:1718` and `_cmd_eval_export` `:1962` (were `:1721`/`:1965`); `user_messages.py` `extract_conversation_turns` pre-resolve `:1227` (was `:1198`); `docs/reference/API.md` "SQLite-only prerequisite" `:9968` under the `Backend chokepoint` heading `:9965` (was `:9949`), `main_ctx_stats` `:5178`, `generate_from_completed` `:13461`. Unchanged: all eight `cli/history.py` sites, all five `cli/harness.py` sites, `decisions.py:596`, `mcp_server/tools.py:172`, `docs/ARCHITECTURE.md:758`, `loops/lib/cli.yaml` `ll_history_summary` (`:59`–`:66`).
- **New history.db readers in `cli/ctx_stats.py`** (ENH-3651 stored-usage cutover): `_compute_cache_rate_from_usage` (`:445`, called from `main_ctx_stats` `:1204`) gates on `db_path.exists()` (`:457`), opens with `connect_readonly` (`:460`), runs SQL against `raw_events` (`:465`) and `select_usage_coverage` (`:477`), and maps `(HistoryError, sqlite3.Error)` to a `(None, "unreadable_store")` diagnostic; `_aggregate_usage_events` (`:226`, called `:1226`) has the same `.exists()` gate. `_aggregate_mcp_health` and `_aggregate_waste` reach remote-capable `history_reader` openers but are blocked by the same `.exists()` gate. All of them stay behind the single pre-resolve, so the ctx_stats verdict is still one entry-level decision, not per helper. The file's `import sqlite3` is used only for `sqlite3.Error`; there is no `sqlite3.connect(`, so `test_history_store_chokepoint_gate.py` stays satisfied.
- **ctx_stats `--db` edge**: an explicit `--db` skips the pre-resolve (`args.db if args.db is not None`). A relative, default-shaped `--db .ll/history.db` is treated as a remote-capable path by `_resolve_once` after the `.exists()` gate, so it can reach `LibsqlBackend` — unconfirmed by any test (`test_cli_ctx_stats.py` has no libsql reference).
- **No non-raising stand-in for `db_path`** exists in `main_ctx_stats`: every helper takes a `Path` and calls `.exists()`. The existing non-DB fallback (`_load_fallback_state` → `_render_fallback`, exit 0 when a fallback exists) is only taken when the summary is `None`, so a "keep degrading" verdict for ctx_stats needs the pre-resolve to stop raising *and* a value that makes every helper return `None`; a refusal at entry avoids that.
- **Same-shape sites outside this issue's list**: `cli/session.py:755` (`refresh`) already calls `refuse_on_remote(args.db, "refresh_raw_events")` (`:754`) inside an `except HistoryError` (`:756`–`:758`), so it is handled, not a traceback site; `ll-session rebuild`/`compact`/`prune` call refusing functions with no boundary catch (a BUG-3652-class gap, not reader verdicts); `hooks/scripts/context-monitor.sh:58,84` and `fsm/continuity.py:52` call `resolve_history_db` as runtime/hook sites (BUG-3652 territory); `issue_history/workspace_quality._open_union` (`:218`) raises `HistoryUnsupported` with no `operation=` and no CLI catch, which matters for `ll-history activity --workspace`.
- **`history_reader/sessions.py` `.exists()` gates** at `:358` (`lookup_session_metadata`) and `:443` (`conversation_turns`) confirm those two readers cannot serve a remote store, matching the refuse/degrade classification for `cli/logs.py` `_cmd_eval_export` and `extract_conversation_turns`.
- **Conventions in Force — boundary catch**: a CLI turns a remote refusal into one stderr line that embeds `{exc}` and returns 1, and the message text comes from the exception (evidence: `cli/backfill_worker.py:main`, `cli/session.py` `refresh` branch). The examples **disagree on the catch class and prefix**: `backfill_worker` catches `HistoryUnsupported` and prints `backfill_worker: <exc>`; `session.py` `refresh`/`_main_migrate` and `cli/doctor.py` catch the parent `HistoryError` with per-site wording (`Cannot refresh source rows:`, `migrate failed:`, `unreachable:`). `cli/history.py`'s only stderr prints are un-prefixed `print(str(exc), ...)` at `:656`/`:708`. The choice of catch class and prefix for four different CLIs is a decision the implementer makes knowingly; a bare `HistoryError` catch would also swallow real store errors.
- **Conventions in Force — `refuse_on_remote` call shape**: every existing call (`session_store/lifecycle.py`, `queries.py`, `usage_refresh.py`, `cli/session.py:754`) passes the function's or subcommand's **own `db` argument**, as the first statement before any I/O, with one operation name per call site; none passes a literal `None`. Passing `None` makes the refusal ignore an explicit `--db` (`None` is always default-shaped), which contradicts this issue's own Decision Rules escape hatch ("explicit non-default `--db` bypasses the refusal"). Three existing operation names (`backfill_usage_incremental`, `refresh_usage_source`, `refresh_raw_events`) have no `_REMOTE_REFUSALS` key and get the default why-clause, so a shared reader reason requires an explicit key per reader operation name.
- **Conventions in Force — refusal wording**: `resolve_history_db` raises `HistoryBackendNotLocal` with `operation="resolve_history_db"` and the text "history.backend provider 'libsql' has no local database path" (`session_store/db.py:152`–`:159`), which names neither the subcommand nor the `<op> is not supported under history.backend provider` format that `refuse_on_remote` emits. The acceptance criterion "operation name plus `libsql` in stderr" therefore cannot be met by catching the pre-resolve's exception alone; the refusal must originate from `refuse_on_remote` (or be re-raised with the subcommand's name) before the pre-resolve runs.
- **Conventions in Force — degrade notice**: no CLI in the tree prints a stderr line keyed on a `RemoteTarget`; `RemoteTarget` appears outside `session_store/` only in `worktree_utils.py`, `hooks/session_start.py`, `cli/session.py` and `cli/doctor.py`. Existing degrade notices use four different channels — `logger.warning` (`cli/logs.py:1556`, `user_messages.py` JSONL fallback, `libsql.py` `warn_once`), stdout (`cli/session.py` `path`), data fields (`workspace_quality._gate_member`, `_STORED_USAGE_DIAGNOSTICS` in `cli/ctx_stats.py`), and shell `echo` in loop YAML. The Decision Rules' "one line on stderr, never stdout" is a new convention; whether `logger.warning` reaches stderr in each CLI must be checked before using it as the channel.
- **Conventions in Force — docs**: remote behavior is documented per feature area, not per CLI: `docs/reference/CLI.md` (`ll-session` section, refusal paragraph ~`:4412`: "refused with an error that names the operation, before any network call") and `docs/reference/CONFIGURATION.md` "Remote history backend" (`Not supported remotely`, ~`:736`: "before any change"). The two lists disagree (CLI.md includes `refresh`, CONFIGURATION.md includes `VACUUM`/`ATTACH`). No remote text exists yet in the `ll-history`/`ll-history-context` sections of CLI.md, in `docs/guides/`, `HOST_COMPATIBILITY.md`, `COMMANDS.md`, `loops.md` or `MCP_SERVER_GUIDE.md` — every doc edit listed for this issue is a first mention, not an amendment. `API.md` documents `main_ctx_stats` as `def main_ctx_stats() -> int` (`:5181`), missing the `argv=None` the source takes.
- **Conventions in Force — tests**: refusal tests assert `pytest.raises(HistoryUnsupported)`, `ei.value.operation == operation`, `"libsql" in str(ei.value)` and an unchanged `len(remote.requests)` (`test_remote_operation_matrix.py::TestRejectedOperations`); CLI-boundary tests assert `== 1`, operation and `libsql` in stderr, and `"Traceback" not in err` (`test_remote_hooks.py:165`). The `remote` fixture is copied in **five** test files, not three — `test_remote_operation_matrix.py:29`, `test_remote_hooks.py:27`, `test_libsql_backend.py:66`, `test_remote_doctor.py:34`, `test_remote_ingestion_telemetry.py:57` — and the copies differ (telemetry reset via `remote_telemetry.reset_for_tests()`, `LL_NON_INTERACTIVE` handling, a separate `stub` fixture in `test_libsql_backend.py`); `conftest.py` has none, and `tests/hrana_stub.py` provides only `HranaStub`. A hoisted fixture must reconcile those differences. No reader-CLI test file is among the ten libsql-using test files.

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Gap-analysis re-check after commit `32043a206` (BUG-3659, write-side only)**: every source anchor in this issue still resolves unchanged — all eight `cli/history.py` `resolve_history_db(` sites, all five `cli/harness.py` sites, `cli/logs.py:1718`/`:1962`, `cli/ctx_stats.py:1188`, `decisions.py:596`, `user_messages.py:1227`, `mcp_server/tools.py:172`, and the `API.md` anchors (`main_ctx_stats` `:5178`, `Backend chokepoint` `:9965`, "SQLite-only prerequisite" `:9968`, `generate_from_completed` `:13461`). The commit added no reader-side caller and no new user-invoked history-reading site. `skills/improve-claude-md/SKILL.md` is still 344 lines.
- **Stale test anchors in the findings above**: the `remote` fixture in `test_remote_hooks.py` is at `:29` (cited `:27`), `test_remote_doctor.py:35`, and `TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` is at `:305` with assertions at `:312`–`:315` (cited `test_remote_hooks.py:165`). The fixture is still copied in exactly five files; no sixth copy and no shared helper exists, and `conftest.py` has none. `warn_once` is defined in `session_store/remote_telemetry.py:163` and only *called* from `libsql.py:198` (the earlier text attributes it to `libsql.py`).
- **Docs: the commit added write-side remote wording only.** `docs/reference/CONFIGURATION.md` `#### Remote history backend` (`:723`) gained the "Never stalls a hook" bullet (`:738`) beside the unchanged "Not supported remotely" bullet (`:736`) and a "Diagnostics" bullet (`:739`); `docs/reference/API.md` gained write-side notes at `:10202` (`skill_event_context`), `:10218` (`hook_event_context`), `:10239` (`record_hook_event`) and a `_DEGRADE_ERRORS` sentence at `:9991` inside the `Backend chokepoint` section this issue also edits. No reader-verdict wording exists yet in any of these — reader text is still a first mention, and it must not contradict the "telemetry is skipped silently" wording at `CONFIGURATION.md:738`, which describes writers, not readers.

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
`main_history` -> `refuse_on_remote(<own db arg>, "<op>")` -> `HistoryUnsupported` -> boundary `except HistoryUnsupported` -> stderr + `return 1` (refuse verdict)
`cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade verdict, replaces `scan_completed_issues_from_db`)
`main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade verdict; `reader="db"` refuses)
`handle_call_tool` -> `_tool_history_search` -> refusal surfaced as `is_error` text naming the operation

### Decision Rules
- **Refuse / degrade / serve classification** per the Expected Behavior table. Serve only where the caller passes a relative/default-shaped path (`ll-harness`); an absolute path is a `LocalTarget` and must never be handed to `ensure=True` under a remote provider.
- **Refuse inputs**: pass the caller's **own `db` argument** to `refuse_on_remote` (`args.db` for `ll-ctx-stats`, the only reader CLI with a `--db` flag; `None` for `history`/`harness`/`logs`, where the escape hatch reduces to `LL_HISTORY_DB`). Operation name is the subcommand's own name; the reason text is the shared reader why-clause. For MCP, pass `root=project_root`.
- **Escape hatch**: `LL_HISTORY_DB` set, or an explicit non-default `--db` (ctx_stats), bypasses the refusal and runs against the local file.
- **Catch / message / notice convention**: `except HistoryUnsupported` inside each `cli_event_context(...)` block; `<prog> <sub>: <exc>` to stderr; exit 1 (never for `ll-harness`, which serves); degrade notice = one `note:` line via `print(file=sys.stderr)`, only under a `RemoteTarget`, never stdout, never echoing an endpoint token.
- **`"No history.db found"`** (`cli/logs.py:~1556`) stays verbatim for the local-missing case; a remote refusal is a separate line.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Signature correction (gap-analysis)**: the `generate_from_completed(project_root, config, ...)` signature above is stale — the current definition is `generate_from_completed(config: BRConfig) -> int` (`decisions.py:578`). It derives `project_root = Path(config.project_root)` internally and pre-resolves with `resolve_history_db(root=project_root)` (`:596`), which is the line that raises `HistoryBackendNotLocal` under a remote target.
- **Degrade branch already exists**: `generate_from_completed` already imports `scan_completed_issues`, `scan_completed_issues_from_db` and `HistoryDbUnavailable` (`issue_history/parsing.py:339`, `:469`) and only takes the DB branch when `db_path.exists()`. The remote degrade is therefore a matter of keeping the pre-resolve from raising and routing to the existing scan branch — not adding a new scan path. The "replaces `scan_completed_issues_from_db`" wording in the Call Path describes the remote case only; the local branch must stay DB-first (`test_honors_ll_history_db_env_override`).
- **Pre-resolve shapes differ per site** (relevant to which sites are "default-shaped"): `user_messages.py:1198` passes the *relative* `DEFAULT_DB_PATH`; `cli/logs.py:1721` passes nothing; `cli/logs.py:1965` passes an absolute `cwd_path / ".ll" / "history.db"`; `cli/ctx_stats.py:1074` passes `cwd / DEFAULT_DB_RELPATH` unless `--db` is given (an explicit `--db` already bypasses the pre-resolve); `mcp_server/tools.py:172` passes `project_root / DEFAULT_DB_PATH` with `root=project_root`; the eight `cli/history.py` sites (`:501`, `:551`, `:592`, `:628`, `:731`, `:755`, `:780`, `:797`) all pass an absolute `project_root / DEFAULT_DB_PATH`.
- **Anchor drift**: `docs/reference/API.md` now carries the "SQLite-only prerequisite" phrase at `:9949` (BUG-3652 cites `:9946`); `docs/ARCHITECTURE.md:758` ("SQLite-only chokepoint") still resolves. `loops/lib/cli.yaml` `ll_history_summary` begins at `:59` with the `description` at `:60`–`:64`; the `:66` cited in Proposed Solution item 5 lands on the `action_type`/`action` lines of that fragment.

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Signature/type corrections (2026-09-29)**: `_REMOTE_REFUSALS` is an unannotated module-level dict literal (`session_store/backend.py:94`–`:101`, `refuse_on_remote` at `:104`, default why-clause fetched via `.get` at `:112`), not a declared `dict[str, str]`; `resolve_history_db` raises `HistoryBackendNotLocal(..., operation="resolve_history_db")`, so an operation-naming boundary message must come from `refuse_on_remote`, not from the pre-resolve's exception. `main_ctx_stats(argv: list[str] | None = None) -> int` is at `cli/ctx_stats.py:1175` and its pre-resolve is `:1188`.
- **Call Path addition**: `main_ctx_stats` -> `resolve_history_db` (`:1188`, unhandled today) -> `_compute_cache_rate_from_usage` / `_aggregate_*` (each `.exists()`-gated). A refusal placed ahead of `:1188` and taking `args.db` covers the whole helper set with one call.
- **Decision Rules correction**: the "Refuse inputs" rule reads "`db=None` to `refuse_on_remote`". Existing call sites pass the caller's own `db`; of the CLIs in this issue only `ll-ctx-stats` (`cli/ctx_stats.py:88`) defines a `--db` flag (as does `ll-session refresh`, `cli/session.py:114`, the precedent), so passing `args.db` is what keeps the "explicit non-default `--db` runs locally" escape hatch true there. `cli/history.py`, `cli/harness.py` and `cli/logs.py` define no `"--db"` argument, so for them `None` is the only available value and the escape hatch reduces to `LL_HISTORY_DB`.

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Conventions in Force — degrade signalling (from `32043a206`)**: a degrade under a remote or dead-remote endpoint is signalled through `logging`, not a `print(..., file=sys.stderr)`: `writers._log_degraded(message, name, exc)` (`session_store/writers.py:57`) logs `debug` for `HistorySuppressed` and `warning` otherwise, with wording `<function>: <step> failed for <name> (<ExcClass>: <exc>)`. Warnings reach stderr only via `logging.lastResort` (documented in the `cli_event_context` docstring, `writers.py:552`–`:556`); the package configures no handler. The only once-per-process channel is `remote_telemetry.warn_once(key, message)` (`remote_telemetry.py:163`), whose one caller is `libsql.py:198`. This sits beside the Decision Rules' "one line on stderr" degrade notice as a second, contested channel: a `logger.warning` is level-filtered and not guaranteed to be a single un-prefixed stderr line, while a `print` is. The choice per CLI is the implementer's call and must be checked against each CLI's logging setup.
- **Conventions in Force — catch class**: the new write-side degrade catches the parent `HistoryError` through `_DEGRADE_ERRORS = (sqlite3.Error, HistoryError)` (`writers.py:54`) at inner steps and a broad `except Exception` at outer boundaries (`writers.py:613`, `hooks/__init__.py:256`–`:261`); no new exception class. This is a third example on the catch-class disagreement already recorded (`HistoryUnsupported` in `backfill_worker`, `HistoryError` in `session.py`/`doctor.py`), and it also catches the unhandled `HistoryBackendNotLocal`. A reader boundary that catches `HistoryError` swallows real store errors as well as refusals.
- **Constraint — `HistoryUnsupported` on the telemetry path**: `libsql.py:195`–`:199` converts a `HistoryUnsupported` into `HistorySuppressed` after `warn_once` only on the telemetry path; on a non-telemetry path it re-raises unchanged. Reader CLIs are non-telemetry, so a refusal from them stays a `HistoryUnsupported` and reaches the boundary.
- **Constraint — dead endpoint on serve sites**: a serve site drops the local-file gate and so gains a network dependency. `history_reader._connect_readonly` maps `HistoryError` (which includes `HranaUnavailable`/`HistorySuppressed`) to `None`, so an unreachable endpoint reads as "no data", not as a refusal or an error; no verdict in this issue currently distinguishes "remote store empty" from "remote store unreachable".

## Implementation Steps

Prerequisite: BUG-3652 landed (it hoists/reconciles the shared `remote` fixture and edits the same `_REMOTE_REFUSALS`/`_REJECTED`).

1. **Seams** (see Proposed Solution 1): per-operation `_REMOTE_REFUSALS` keys + `_REJECTED` rows; `refuse_on_remote(..., root=)`; read-mode remote ensure in `open_history_readonly`. Hoist the `remote` fixture into `conftest.py` if BUG-3652 did not.
2. **Serve** `cli/harness.py` (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`): drop the pre-resolve, pass the relative default; verify rows round-trip through `HranaStub` and that no local `.ll/history.db` is created.
3. **Degrade**: `history summary` (file scan, exit 0, `note:` line), `decisions.generate_from_completed` (keep the pre-resolve from raising, route to the existing scan branch; local stays DB-first), `extract_conversation_turns` (`auto` → JSONL), CT-0 (skip + note), `sft-corpus.yaml` `stage` → `--reader auto`.
4. **Refuse** with boundary catch inside `cli_event_context`: `history` `analyze`/`activity`/`rework`/`quality`/`audit-issue-collisions`/`sessions`/`root`; `logs` `_cmd_diff`/`_cmd_eval_export`/`_cmd_stats`/`_cmd_dead_skills`; `ctx_stats` (`args.db`); `extract_conversation_turns(reader="db")`; MCP `history_search` (`is_error`, `root=project_root`). Update `ll-ctx-stats` / `ll-harness` epilog "Exit codes" text.
5. **Skills/mirrors/docs**: guard CT-0, `ll-adapt --host <gemini|kimi-code|qwen> --apply` (also regenerates the `create-eval-from-issues` mirrors), update `skills/analyze-history` and `skills/create-eval-from-issues`, and the docs listed under Documentation / Wiring Phase.
6. **Tests**: remote-stub test per site plus local twin; refusals assert exit 1, operation name + `libsql` in stderr, `"Traceback" not in err`, zero stub requests; degrade tests assert stdout unchanged and the `note:` line on stderr with no token; harness serve asserts data from the stub and **no local `.ll/history.db` created**; a remote-config-at-`project_root` + foreign-cwd MCP test; `"No history.db found"` invariant test; `sft-corpus` `stage` reader-flag test. Run `python -m pytest scripts/tests/`, `ruff check`, `mypy`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Place the `except HistoryUnsupported` inside each `cli_event_context(...)` block (`main_history()` and `main_logs()` take no `argv`; `main_harness(argv=None)` and `main_ctx_stats(argv=None)` do), and test `main_harness([...])` rather than the `cmd_*` handlers, which existing tests call directly
- Thread `root=project_root` for MCP `_tool_history_search` (**decided:** add `root=` to `refuse_on_remote`); add a remote-config-at-`project_root` + foreign-cwd test beside `test_enh_3171_mcp_project_root.py`
- Keep `cli/logs.py`'s `"No history.db found"` warning string unchanged; add the degrade notice as a separate stderr line (`.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps it)
- `loops/sft-corpus.yaml` `stage` (`--reader db ... 2>/dev/null || touch`) (**decided:** switch to `--reader auto`), since the swallowed exit 1 currently yields an empty corpus routed to `enrich` as success
- Update `cli/ctx_stats.py` and `cli/harness.py` epilog "Exit codes" text, and `loops/lib/cli.yaml` `ll_history_summary` description, for the new refusal exit 1
- Update `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125`, `docs/guides/EVALUATION_GUIDE.md:481`, `docs/reference/loops.md:493`, `docs/reference/HOST_COMPATIBILITY.md`, `docs/reference/COMMANDS.md:586`, `docs/guides/MCP_SERVER_GUIDE.md` alongside the four reference docs already listed
- Update `skills/analyze-history/SKILL.md` and `skills/create-eval-from-issues/SKILL.md` to tell the model what a remote-refusal exit 1 means (no fallback exists in either today)
- In `skills/improve-claude-md/SKILL.md`, edit CT-0 only (keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`); no checked-in `ll-adapt` host mirror of this skill was found, so run `ll-adapt --apply` and confirm whether it changes anything before treating step 2 as a mirror update
- Hoist the `remote` fixture (currently copied in three test files) into `scripts/tests/conftest.py` or a shared helper before adding reader-CLI remote tests; add `_REJECTED` rows per new operation in `test_remote_operation_matrix.py`
  > ⚠ Superseded — copies are in five files; BUG-3652 (landing first) owns the hoist and reconciliation; see Integration Map findings
- Regenerate the committed `create-eval-from-issues` host mirrors (`.gemini/`, `.qwen/`, `.kimi-code/`) via `ll-adapt --host <gemini|kimi-code|qwen> --apply` after the `ll-harness dsl` note edit
- Gate any `ll-ctx-stats` refusal/notice on a `RemoteTarget` and pass `args.db` to `refuse_on_remote`, so `test_enh3549_codex_stored_ctx_stats.py` (`err == ""`) and the `--db` tests in `test_enh3656_stored_cache_rate.py` stay green
- Add tests: `run_stats` `"No history.db found"` string invariant (`test_bug_3216_telemetry_digest_invocations.py`), `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`)
- Extend the docs edits with `docs/reference/CLI.md` (`ll-history summary`/`analyze` sections, MCP `history_search` row), `docs/reference/API.md` (`extract_conversation_turns` Relationship paragraph, `issue_history` table rows), `docs/reference/COMMANDS.md:~695`
- `cli/session.py` `ll-session search --fts` (`history_search(..., db=args.db)`): **decided** it follows ENH-3668 (a `history_reader` caller; passes the caller's own `--db`, so no traceback in this issue's scope) — confirm no unhandled `HistoryBackendNotLocal` path when implementing

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- Ordering check: if BUG-3652 lands after this issue, both edit `_REMOTE_REFUSALS` in `session_store/backend.py` and both want the shared `remote` test fixture hoisted into `conftest.py`, so the second to land must reconcile those two edits; neither mechanism fails to work. Recorded as `relates_to`, not `blocked_by`.

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage is handled by BUG-3652.
- **Effort**: Large - about 20 reader sites across four verdict kinds, three seam edits, ~12 doc files, a skill mirror pass and a loop fix; every verdict test is new.
- **Risk**: Low - local behavior unchanged; reader refusals exit 1 and can trip loop gates such as `ll-history summary`.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Every reader site in the Expected Behavior table has its verdict (serve, refuse, or degrade) implemented and covered by a remote-stub test (`HranaStub`) plus a local twin.
- [ ] No reader CLI surfaces a bare `HistoryBackendNotLocal` traceback under a remote backend; refusals assert exit 1, `<prog> <sub>:` prefix, operation name plus `libsql` in stderr, `"Traceback" not in err`, and zero stub requests.
- [ ] `ll-harness` serve sites return data from the stub and create **no** local `.ll/history.db` (assert absence); a behind/ahead remote schema is still readable (read-mode ensure).
- [ ] Degrade sites (`history summary`, `decisions generate`, `--reader auto`, CT-0) keep stdout unchanged, exit 0, and print exactly one `note:` line on stderr only under a remote target; no endpoint token appears in any notice or refusal.
- [ ] MCP `history_search` refusal resolves config against `project_root` (remote config at `project_root` + foreign cwd test).
- [ ] `sft-corpus.yaml` `stage` no longer turns a remote refusal into an empty-success corpus; `"No history.db found"` is unchanged (invariant test).
- [ ] With an explicit `--db` / `LL_HISTORY_DB`, every refused site still runs locally; with the default local store, `python -m pytest scripts/tests/` passes unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-29 — based on codebase analysis:_

- **Edge not covered by the criteria above (low)**: behavior of a serve site under an *unreachable* remote endpoint (`_connect_readonly` returns `None`, so output is indistinguishable from an empty store). `test_remote_hooks.py::TestDeadEndpointDegrades` (`:155`; class-local `dead` fixture `:158`–`:166`; `_assert_intact` `:185`–`:191` checks `"Traceback" not in err` and `TOKEN not in err`) is the closest existing shape for a dead-endpoint test; stderr and log assertions there go through `caplog`, not `capsys`. Resolved: for `ll-harness` serve, an unreachable endpoint reading as "no data" is accepted here (same as today's fail-soft harness gates) and recorded in docs; distinguishing it is ENH-3668's second acceptance criterion.
- **Edge not covered (low)**: no criterion says a degrade notice must not leak the endpoint token (the existing dead-endpoint tests assert `TOKEN not in err` and no token in log records); a reader notice that echoes `{exc}` from a `HranaUnavailable` should hold the same property (now an acceptance criterion).

## Related

- BUG-3652 (startup/write-path audit; `blocked_by`, land first).
- FEAT-3535 (remote libSQL history backend).
- ENH-3668 (`HistoryTarget`-aware readers; serves the `ll-history` subcommands and MCP `history_search` this issue refuses in the interim).
- ENH-3658 (hand-built paths; shares `_REMOTE_REFUSALS`/`_REJECTED` edits: merge, don't overwrite).
- Consequence to record: remote users lose `ll-history` reader subcommands (except `summary`, which degrades) and MCP `history_search` until ENH-3668; `ll-harness` reads work.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-29 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-09-29 (graph: provider=`codegraph`, freshness=`fresh`; anchors were confirmed by grep/Read, not by graph results)_

Verdict at time of check: **DEP_ISSUES** (no content edits were needed; the finding below is not fixed by this pass)

- Confirmed: all eight `cli/history.py` `resolve_history_db(` sites (`:501`–`:797`), five `cli/harness.py` sites (`:245`, `:1089`, `:1994`, `:2027`, `:3613`), `cli/logs.py:1718`/`:1962`, `cli/ctx_stats.py:1188`, `decisions.py:596`, `user_messages.py:1227`, `mcp_server/tools.py:172`, the hand-built `logs.py` paths (`:997/1002`, `:1535/1539`), the `"No history.db found"` warning (`logs.py:1556`), the `except HistoryError` handlers, `sft-corpus.yaml` `--reader db … || touch`, `cli.yaml` `ll_history_summary`, `skills/improve-claude-md/SKILL.md` (344 lines), and `_REJECTED` (8 rows).
- Load-bearing premise probed directly (`session_store/backend.py:_resolve_once`, `:353`–`:355`): an absolute path is returned as a `LocalTarget` verbatim, while `None`/relative goes through `resolve_history_target`; `open_history_readonly(ensure=True)` then calls `ensure_schema` on that path. So the serve-vs-refuse split (only relative-path `cli/harness.py` can serve) holds. `LibsqlBackend.ensure_schema` does run `check_access(..., write=True)` (`libsql.py:286`), which is what Proposed Solution 1(c) targets. `history_reader/harness.py` readers have no `.exists()` gate.
- `ll-verify-evidence` and `ll-issues format-check` are clean; no active required decision rule conflicts (proposal-vs-code check found no exception-handler, fixture or AC-coverage gap beyond what the issue already lists).
- Remaining: `blocked_by: BUG-3652` is unsatisfied (BUG-3652 is `open`), but BUG-3652 has no `## Blocks` section naming ENH-3657 (MISSING_BACKLINK; it mentions the split only in prose). Not auto-fixed because it edits an issue outside this run's scope.

_Re-verified by `/ll:verify-issues --auto` on 2026-09-29 (graph: provider=`codegraph`, freshness=`fresh`; anchors confirmed by grep/Read, not graph results)_

Verdict at time of check: **VALID** (no content edits needed; this section is a record, not an outstanding action item)

- The `DEP_ISSUES` finding above is resolved: BUG-3652's `## Blocks` section now lists ENH-3657 and ENH-3658 (`efc7f735d`). `blocked_by: BUG-3652` stays an unsatisfied, legitimate blocker (BUG-3652 is `open`); its own `blocked_by: BUG-3659` is satisfied (done). No cycle.
- Anchors re-confirmed: all eight `cli/history.py` sites (`:501`–`:797`), five `cli/harness.py` sites, `cli/logs.py:1718`/`:1962`, `cli/ctx_stats.py:1188`, `decisions.py:596`, `user_messages.py:1227`, `mcp_server/tools.py:172`, `"No history.db found"` at `logs.py:1556`, `logs.py` hand-built paths (`:997/1002`, `:1535/1539`), `_REMOTE_REFUSALS` keys (`session_store/backend.py:94`–`:101`), `sft-corpus.yaml` `--reader db` (`:54`), CT-0 SKILL.md at 344 lines. Older anchors in the first refinement bullets (e.g. `logs.py:1721/1965`) are superseded by the "Anchor drift" bullet. `ll-verify-evidence` and `ll-issues format-check` are clean; no active required decision rule.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 51/100 → LOW

_Re-scored after the ENH-3668 re-scope. Program Design, learning-test, claim/parity/structure and decision gates are clean; the readiness score is held down by the unresolved `blocked_by: BUG-3652` edge (Dependencies Hard Override), not by structure._

### Concerns
- Proposed Solution 1(c) (read-mode remote ensure in `open_history_readonly`) is the one shared-seam edit `ll-harness` serve depends on, and is not yet verified against `HranaStub`; every other new mechanism is a call-site edit on existing seams. Verify first when implementing.
- `ll-session search --fts` is deferred to ENH-3668 on the argument that it passes the caller's own `--db`; confirm no unhandled `HistoryBackendNotLocal` path while implementing.

### Gaps to Address
- **Unresolved dependency**: `blocked_by` BUG-3652 is `open` (its own blocker BUG-3659 is done). It hoists the shared `remote` fixture and edits the same `_REMOTE_REFUSALS` / `_REJECTED` — land it first, or drop the edge if the fixture hoist is split out.

### Outcome Risk Factors
- Broad enumeration across ~20 code sites (8 `cli/history.py`, 5 `cli/harness.py`, `logs`, `ctx_stats`, `decisions`, `user_messages`, MCP, CT-0) plus ~12 doc files; per-site depth is moderate (boundary catch inside `cli_event_context`), not a uniform Pattern B substitution.
- Every verdict test is new and the `remote` fixture is copied in five files until BUG-3652 hoists it; `test_cli_harness.py` calls `cmd_*` directly, so the boundary catch is not covered by existing tests.
- New refusal exit 1 can trip loop gates (`ll_history_summary`, `sft-corpus`, `ll-logs-telemetry-digest` `run_stats` greps `"No history.db found"`).
- Serve sites cannot tell an unreachable remote from an empty store (`_connect_readonly` maps `HistoryError` to `None`); accepted for `ll-harness`, distinguished in ENH-3668.

## Resolved Concerns

- [resolved 2026-09-29 by /ll:confidence-check follow-up] Integration Map "Serve sites" line contradicted the re-scoped table — reworded so only `cli/harness.py` serves; all other reader sites refuse or degrade.

## Session Log
- `/ll:confidence-check` - 2026-09-29T22:09:09 - `c419efbf-94bc-4735-80cf-772ead8ae35e.jsonl`
- `/ll:verify-issues` - 2026-09-29T22:05:34 - `b6e9a962-45bc-4981-a31d-f5f911dc70c3.jsonl`
- `/ll:verify-issues` - 2026-09-29T21:59:39 - `f8adf1da-5f55-4437-ac1b-3cda2eb8384a.jsonl`
- `/ll:confidence-check` - 2026-09-29T17:10:54 - `bd506705-1a67-435c-95c6-e7a6cced7523.jsonl`
- `/ll:verify-issues` - 2026-09-29T16:04:55 - `d2886606-137b-4448-b1f0-22d8e796de6d.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-29T16:03:21 - `b2df855d-9a45-4710-92a2-763b4f73c99e.jsonl`
- `/ll:verify-issues` - 2026-09-29T15:59:32 - `dec2cde6-1a0c-4895-8a02-4d69f3488107.jsonl`
- `/ll:wire-issue` - 2026-09-29T15:58:08 - `33ac0072-4acd-418a-a128-a0122044ca57.jsonl`
- `/ll:refine-issue` - 2026-09-29T15:53:17 - `38b577b2-a780-4f13-a766-2b3309027fb9.jsonl`
- `/ll:reconcile-issue` - 2026-09-29T06:17:02 - `5f8d5762-5341-43fe-88c8-0e9ad90d90b3.jsonl`
- `/ll:confidence-check` - 2026-09-29T06:15:37 - `64ee27e7-98c4-4210-b976-65275ac000b0.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-29T06:11:37 - `236872ac-1b8a-494a-8a4f-024f9ae7329e.jsonl`
- `/ll:wire-issue` - 2026-09-29T06:08:54 - `6853b72a-3d36-49af-862a-88cc681f2623.jsonl`
- `/ll:refine-issue` - 2026-09-29T06:01:38 - `fce6088f-c5fa-4a10-a502-c439e3fca2a1.jsonl`
