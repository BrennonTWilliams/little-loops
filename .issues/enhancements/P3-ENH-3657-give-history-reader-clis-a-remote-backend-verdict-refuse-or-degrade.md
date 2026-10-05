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
- ENH-3700
- ENH-3658
- ENH-3682
blocked_by:
- ENH-3677
blocks:
- ENH-3700
- ENH-3728
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3657: Give history reader CLIs a remote-backend verdict (refuse or degrade)

> **Split 2026-10-02** (Opus review of EPIC-3693's children). This issue is now **3657a, the refuse-boundary slice**: one boundary helper plus every refuse site that already fails on the pre-resolve's `HistoryBackendNotLocal`. It makes **no contract change** to `_connect_readonly`. The risky seam (central guard, `HistoryRemoteRefused` re-raise across ~67 callers, exhaustive caller audit, read-mode ensure, `ll-harness` serve, degrade sites, CT-0, `sft-corpus`) moved to **ENH-3700 (3657b)**, which is `blocked_by` this issue. The earlier "two slices inside one issue" plan is dropped. Scores were cleared because the scope changed; re-run `/ll:confidence-check` after ENH-3677 lands (the confidence gate is enabled, so an unscored issue stalls automation). Pre-split text is in git history.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), user-invoked history reader commands raise an unhandled `HistoryBackendNotLocal` traceback. This issue gives those sites a clean, named refusal ("not supported with a remote backend", exit 1) through one boundary helper, and documents the support matrix. Remote read serving for `ll-history` subcommands and MCP `history_search` is **not planned**; docs must say "not supported with a remote backend" and promise no follow-up (ENH-3668/3684/3685 are deferred indefinitely). The central guard, degrade sites and `ll-harness` serve are ENH-3700.

## Current Behavior

These sites pre-resolve through `resolve_history_db()` and raise `HistoryBackendNotLocal` (a `HistoryUnsupported`) unhandled, so the CLI shows a traceback:

- `cli/history.py:main_history` (8 sites: `summary`, `analyze`, `rework`, `quality`, `activity`, `audit-issue-collisions`, `sessions`, `root`), `cli/logs.py` (`_cmd_diff`, `_cmd_eval_export`), `cli/ctx_stats.py`, `cli/messages.py:main_messages` for explicit DB-backed SFT output, and `mcp_server/tools.py:_tool_history_search` (converted to `is_error` by `handle_call_tool`).
- `cli/logs.py` `_cmd_stats` / `_cmd_dead_skills` build `<project>/.ll/history.db` by hand (ENH-3658 defers them here); they can `ensure_schema`-create an empty shadow DB, so under remote they must refuse before touching the path.
- The `except HistoryError` handlers in `logs.py`/`history.py`/`ctx_stats.py` wrap only connect/query calls; the pre-resolves sit outside them.

## Expected Behavior

### Verdicts (this issue)

| Site | Under remote | Notes |
|---|---|---|
| `history analyze`, `activity`, `rework`, `quality`, `audit-issue-collisions`, `sessions`, `root` | **refuse** | boundary helper turns the pre-resolve's `HistoryBackendNotLocal` into `<prog> <sub>: <safe reason>`, exit 1 |
| `logs` `_cmd_diff`, `_cmd_eval_export`, `_cmd_stats`, `_cmd_dead_skills` | **refuse** | keep the literal `"No history.db found"` warning for local-missing (the digest loop greps it); the refusal is a separate line |
| `ctx_stats` | **refuse** | explicit `--db` skips the pre-resolve and still runs locally; no extra guard needed |
| `ll-messages --sft-format --reader db` | **refuse** | clean CLI error; `reader=auto` degrade is ENH-3728 |
| MCP `history_search` | **refuse** as a structured `is_error` naming the operation | its pre-resolve already takes `root=project_root`; verify the message names the operation |

`history summary`, `decisions generate`, `reader=auto`, CT-0 and the `sft-corpus` reader flag/enrich passthrough are **ENH-3728**; `sft-corpus` failure routing is **ENH-3729**; `ll-harness` serve and the central guard are **ENH-3700**.

### One boundary helper

One helper maps `HistoryUnsupported` to `<prog> <sub>: <safe reason>` on stderr and exit 1, used inside `cli_event_context` by `main_history`, `main_logs`, `main_ctx_stats`, and `main_messages` for explicit DB-backed SFT reads. Use a fixed safe reason naming `libsql` and the operation; do not stringify raw exceptions containing endpoint/host/token/SQL. It replaces ~20 per-site catch blocks. Catch `HistoryUnsupported`, never bare `HistoryError` (which would swallow real store errors). `main_history()` and `main_logs()` take no `argv`; `main_ctx_stats(argv=None)` does. Name this shared classifier `history_error_verdict` so deferred ENH-3668 extends it rather than creating a second mapping.

### Docs and exit codes

- Update the `ll-ctx-stats` epilog and `ll-history` CLI reference "Exit codes" text, and tell the model what a refusal exit 1 means in `skills/analyze-history/SKILL.md` and `skills/create-eval-from-issues/SKILL.md`; regenerate the `.gemini/`, `.qwen/`, `.kimi-code/` mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. ENH-3700 owns all `ll-harness` wording, including its existing retry/baseline validation failures.
- Create the single reader-support table in `docs/reference/CONFIGURATION.md` "Remote history backend", linked from `docs/reference/CLI.md`. Refused rows say **"not supported with a remote backend"** with no promise of a follow-up. Add one sentence: "context-pressure and handoff rows are not recorded under a remote backend." ENH-3700 adds its serve/degrade rows to the same table.
- Keep `loops/lib/cli.yaml` `ll_history_summary` description non-empty. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths. Reader text is a first mention everywhere and must not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Motivation

Remote-backend users hit an unhandled traceback from `ll-history`, `ll-logs` and other readers. A clean, named refusal is the achievable fix and needs no change to the reader seam, so it can ship first and independently of the risky guard work.

## Scope Boundaries

- **In scope**: the boundary helper, the refuse sites in the table (including `logs` `_cmd_stats`/`_cmd_dead_skills`, deferred here by ENH-3658), epilog and skill exit-code wording, the single support table in `CONFIGURATION.md`, the parametrized refusal test.
- **Out of scope**: the central guard and `ll-harness` serve (ENH-3700); all degrade sites, CT-0 and the `sft-corpus` reader flag (ENH-3728); `sft-corpus` failure routing (ENH-3729); startup/write-path sites (BUG-3652, done); artifact hand-built paths (ENH-3658); `context-monitor.sh` (ENH-3680 cancelled, documented no-op); remote read serving for `ll-history` subcommands/MCP (ENH-3668/3684/3685, deferred indefinitely); `ll-session search --fts` (passes the caller's own `--db`; confirm no unhandled `HistoryBackendNotLocal` path); `ll-doctor` (already handles `HistoryError`; confirm); writers/runtime callers of `resolve_history_db` (`cli/parallel.py`, `fsm/*`, `hooks/*`).

## Proposed Solution

1. **Boundary helper** (one function, wired into `main_history`, `main_logs`, `main_ctx_stats`, `main_messages`), catching `HistoryUnsupported` only.
2. **Refuse sites** per the verdict table; they rely on the existing pre-resolve's `HistoryBackendNotLocal`. For `_cmd_stats`/`_cmd_dead_skills`, resolve before building the hand-made path so a remote target refuses instead of creating a shadow DB.
3. **MCP `history_search`**: map the unsupported pre-resolve to the shared fixed safe reason naming `history_search`, before `handle_call_tool`'s generic `str(exc)` serialization. The resolver's current operation is `resolve_history_db`, which does not identify the requested tool. Preserve structured `is_error` and use `project_root`.
4. **Docs, epilog and skill wording, mirrors** as above.

### Project-root and entry-point contract

Every default read uses the root selected by the command: thread `root=project_root` through `main_history`'s pre-resolves (including the summary branch prepared for ENH-3700), and use the selected `--cwd` root for logs eval-export. A default-shaped absolute path alone does not supply resolver root context. Test remote owning root/local foreign cwd and local owning root/remote foreign cwd; preserve `history.db_path` and `LL_HISTORY_DB` local overrides. These changes do not alter `_resolve_once` or the reader opener contract.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/messages.py`, `mcp_server/tools.py`, the shared boundary helper module, `skills/analyze-history/SKILL.md`, `skills/create-eval-from-issues/SKILL.md` (+ regenerated mirrors).
- Anchors drift: re-grep every `resolve_history_db(` site before editing (`cli/history.py` ~`:501–797`, `cli/logs.py` ~`:1718/1962`, `cli/ctx_stats.py` ~`:1188`, `mcp_server/tools.py:172`).

### Loop / digest invariants
- `.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps `"No history.db found"`; keep the string verbatim and add remote notices as separate stderr lines (all its states capture `2> "$ERR"`).
- `evaluation-quality.yaml` and `backlog-flow-optimizer.yaml` (inline `ll-history summary 2>/dev/null || echo`) need no edit; `fleet-loop-improve` `fleet-review | tail -n 1` is unaffected by a stderr notice.

### Tests
- New: one **parametrized** refusal test over the refused sites, including `main_messages` under `--sft-format --reader db` (exit 1, `<prog> <sub>:` prefix, `libsql` in stderr, `"Traceback" not in err`, no reader requests) plus a local twin. Disable CLI analytics capture for the request-count assertion (`LL_ANALYTICS_CAPTURE=0`), or separate reader requests from legitimate remote `cli_events` writes. `_cmd_stats`/`_cmd_dead_skills` refuse without creating a local `.ll/history.db` (assert absence). Where a CLI defines `--db` (`ll-ctx-stats`), that explicit path stays local; `LL_HISTORY_DB` keeps its local override. MCP refusal names the operation and resolves config against `project_root` (remote config at `project_root` + foreign cwd).
- Use the hoisted `remote` fixture from ENH-3677 (must `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`). Test the public boundary: `main_history()`, `main_logs()` and `main_messages()` take no `argv`, so monkeypatch `sys.argv`; `main_ctx_stats(argv=None)` accepts a list. Seed sessions/transcripts for eval-export and SFT so discovery actually reaches the DB read. Assert the named refusal, not merely exit 1 from an earlier missing-session branch. Exercise the registered MCP `handle_call_tool`, not only `_tool_history_search`.
- Keep green: `test_enh3549_codex_stored_ctx_stats.py` (`err == ""`), `test_enh3656_stored_cache_rate.py`, `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_feat3410_workspace_quality.py`/`test_feat3445_workspace_activity.py` (literal `"history.db not found"`), `test_ll_logs.py` index-sensitive stderr tests, `test_cli_messages.py`, `test_bug_3216_telemetry_digest_invocations.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (support table), `docs/reference/CLI.md` (link + `ll-history`/`ll-ctx-stats`/`ll-harness` exit notes), `docs/reference/API.md` (`main_ctx_stats` signature is missing `argv=None`), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125`, `docs/reference/loops.md:493`.

## Program Design

### Types

- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.

### Signatures

- `main_history() -> int`, `main_logs() -> int`, `main_messages() -> int` — zero-argument CLI boundaries; `main_ctx_stats(argv=None) -> int` accepts argv. Map `HistoryUnsupported` to the program/operation's fixed safe reason on stderr and return 1. `ll-messages` and `ll-ctx-stats` have no subcommand: use `ll-messages sft` and `ll-ctx-stats` respectively as stable operation labels rather than inventing a parsed subcommand.

### Call Path

- `main_history` -> `resolve_history_db` -> `HistoryBackendNotLocal` -> boundary helper -> stderr + `return 1` (refuse verdict).
- `main_logs` -> `_cmd_stats` / `_cmd_dead_skills` -> remote classification before the hand-built path -> boundary helper.
- `mcp_server.tools._tool_history_search` -> `resolve_history_db` -> `HistoryBackendNotLocal` -> `is_error` naming the operation.

### Decision Rules

- Catch class is `HistoryUnsupported`, never bare `HistoryError`; `"No history.db found"` stays verbatim for local-missing; the refusal is a separate stderr line.
- Escape hatch: `LL_HISTORY_DB` set, or an explicit `--db` (only `ll-ctx-stats` and `ll-session refresh` define one), runs locally.
- A refusal never exits with a code that a graded loop could read as success.

## Implementation Steps

Prerequisite: ENH-3677 landed (hoisted `remote` fixture). BUG-3652 is done.

1. Add the boundary helper; wire it into `main_history`, `main_logs`, `main_ctx_stats`, `main_messages`.
2. Convert the refuse sites (respect `ll-ctx-stats --db`); make `_cmd_stats`/`_cmd_dead_skills` refuse before the hand-built path; confirm MCP `is_error` wording.
3. Epilog exit-code text, skill wording, `ll-adapt` mirrors, support table and docs.
4. Tests per the Integration Map. Run `python -m pytest scripts/tests/`, `ruff check`, `mypy` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium - one helper, ~15 refuse sites, docs and a skill mirror pass; no seam change.
- **Risk**: Low-Medium - refusals exit 1 and can trip loop gates; local behavior unchanged.
- **Breaking Change**: No (local behavior unchanged).

## Acceptance Criteria

- [ ] Every refuse site in the verdict table, including `ll-messages --sft-format --reader db`, is covered by one parametrized remote-stub test (exit 1, `<prog> <sub>:` prefix, `libsql` in stderr, `"Traceback" not in err`, no reader requests when analytics capture is disabled) plus a local twin.
- [ ] The boundary helper catches `HistoryUnsupported` only, never bare `HistoryError`, and no endpoint token appears in any refusal.
- [ ] `logs` `_cmd_stats`/`_cmd_dead_skills` refuse under remote without creating a local `.ll/history.db`; `"No history.db found"` is unchanged (invariant test).
- [ ] MCP `history_search` refusal names the operation and resolves config against `project_root`; the registered handler returns `is_error` with a fixed safe reason even when the caught exception contains endpoint/token/SQL canaries.
- [ ] `ll-history --config` and logs eval-export's selected `--cwd` use their owning root with a foreign cwd in both directions; config/env local overrides are preserved and no foreign `.ll/history.db` is created.
- [ ] Where a CLI defines `--db`, that explicit path remains local; `LL_HISTORY_DB` keeps its local override at applicable sites.
- [ ] The support table exists in `CONFIGURATION.md`, refused rows read "not supported with a remote backend" (no follow-up promised), and it includes "context-pressure and handoff rows are not recorded under a remote backend"; epilog exit codes and the two skills describe the refusal exit 1; mirrors regenerated.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3700 (3657b, central guard + serve/degrade; `blocks`, lands after this), ENH-3677 (shared `remote` fixture; `blocked_by`, land first), BUG-3652 (startup/write-path audit; **done**, `62ac0fc89`), ENH-3658 (hand-built paths; `logs` sites deferred here), ENH-3682 (prepatch read budget; independent), FEAT-3535 (remote libSQL backend).
- ENH-3668 / ENH-3684 / ENH-3685 (remote read serving) are deferred indefinitely; no follow-up is promised in docs.
- Consequence to record: remote users lose `ll-history` reader subcommands and MCP `history_search` ("not supported with a remote backend"); `summary` and `ll-harness` are addressed in ENH-3700.

## Status

**Open** | Created: 2026-09-29 | Priority: P3 | Split to 3657a 2026-10-02

## Confidence Check Notes

_Cleared 2026-10-02 after the split into 3657a (this issue) and ENH-3700 (3657b). Prior scores (70/48) no longer apply. Re-run `/ll:confidence-check` once ENH-3677 lands._

---

## Scope Boundary

**Ownership:** epilog and CLI.md "Exit codes" edits here cover `ll-ctx-stats` and `ll-history` only. ENH-3700 owns `ll-harness` serving and its existing fail-closed retry/baseline validation behavior; this issue adds no remote-backend refusal there.

## Session Log
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - root propagation, public-boundary tests and safe MCP refusal amended; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:04 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
- `/ll:advise` (Opus, EPIC-3693 children review) + split into ENH-3657 / ENH-3700 - 2026-10-02
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:25 - `813546cd-0058-4cf8-a1bc-da17040cac6b.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:50 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
- `/ll:confidence-check` - 2026-09-30T01:08:15 - `d09a5e0e-2f2f-4d02-a2fb-345fcc5b2f01.jsonl`
- `/ll:advise` (Opus, placement-bug review) + reconcile rewrite - 2026-09-30
- `/ll:confidence-check` - 2026-09-29T22:09:09 - `c419efbf-94bc-4735-80cf-772ead8ae35e.jsonl` (scores since cleared; re-run)
- `/ll:verify-issues` - 2026-09-29T22:05:34 - `b6e9a962-45bc-4981-a31d-f5f911dc70c3.jsonl`
- `/ll:refine-issue` - 2026-09-29T15:53:17 - `38b577b2-a780-4f13-a766-2b3309027fb9.jsonl`
