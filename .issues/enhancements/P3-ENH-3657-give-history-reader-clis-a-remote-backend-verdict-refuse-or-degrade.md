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

> **Current split (reviewed 2026-10-05, review #4):** this is **3657a, the refuse-boundary slice**: one boundary helper plus the refused CLI/MCP sites. It also owns the small local-target setup/provenance fix required by its selected-root tests; `_connect_readonly`'s error contract stays unchanged. **ENH-3700** owns the central guard, catch widening, narrow required harness lookups and `ll-harness` serving; **ENH-3728** owns degrade sites and CT-0; **ENH-3729** owns SFT failure routing. The universal re-raise, exhaustive caller audit and read-mode ensure/serve-behind designs were dropped on 2026-10-04. Scores remain cleared; re-run `/ll:confidence-check` after ENH-3677 lands. Pre-split plans are in git history.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), user-invoked history reader commands raise an unhandled `HistoryBackendNotLocal` traceback. This issue gives those sites a clean, named refusal ("not supported with a remote backend", exit 1) through one boundary helper, and documents the support matrix. Remote read serving for `ll-history` subcommands and MCP `history_search` is **not planned**; docs must say "not supported with a remote backend" and promise no follow-up (ENH-3668/3684/3685 are deferred indefinitely). The central guard and `ll-harness` serve are ENH-3700; the degrade sites are ENH-3728.

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
| `ctx_stats` | **refuse** | explicit `--db` skips the pre-resolve and still runs locally, including relative/absolute default-shaped paths; anchor the explicit relative path before the strict opener |
| `ll-messages --sft-format --reader db` | **refuse** | preflight against the selected `--cwd` root before discovery/empty-message returns; `reader=auto` degrade is ENH-3728 |
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

- **In scope**: the boundary helper, the refuse sites in the table (including `logs` `_cmd_stats`/`_cmd_dead_skills`, deferred here by ENH-3658), selected-local provenance through conversation reads and SQLite reader setup, epilog and skill exit-code wording, the single support table in `CONFIGURATION.md`, the parametrized refusal test.
- **Out of scope**: the central guard and `ll-harness` serve (ENH-3700); all degrade sites, CT-0 and the `sft-corpus` reader flag (ENH-3728); `sft-corpus` failure routing (ENH-3729); startup/write-path sites (BUG-3652, done); artifact hand-built paths (ENH-3658); `context-monitor.sh` (ENH-3680 cancelled, documented no-op); remote read serving for `ll-history` subcommands/MCP (ENH-3668/3684/3685, deferred indefinitely); `ll-session search --fts` (passes the caller's own `--db`; confirm no unhandled `HistoryBackendNotLocal` path); `ll-doctor` (already handles `HistoryError`; confirm); writers/runtime callers of `resolve_history_db` (`cli/parallel.py`, `fsm/*`, `hooks/*`).

## Proposed Solution

1. **Boundary helper** (one function, wired into `main_history`, `main_logs`, `main_ctx_stats`, `main_messages`), catching `HistoryUnsupported` only.
2. **Refuse sites** per the verdict table; they rely on the existing pre-resolve's `HistoryBackendNotLocal`. For `_cmd_stats`/`_cmd_dead_skills`, resolve before building the hand-made path so a remote target refuses instead of creating a shadow DB.
3. **MCP `history_search`**: map the unsupported pre-resolve to the shared fixed safe reason naming `history_search`, before `handle_call_tool`'s generic `str(exc)` serialization. The resolver's current operation is `resolve_history_db`, which does not identify the requested tool. Preserve structured `is_error` and use `project_root`.
4. **Docs, epilog and skill wording, mirrors** as above.

### Project-root and entry-point contract

Every default read uses the root selected by the command: thread `root=project_root` through `main_history`'s pre-resolves (including the summary branch prepared for ENH-3728), use the selected project root for logs eval-export, and use `args.cwd or Path.cwd()` for messages. The logs option is `--project` (with `--cwd` as an alias); resolve before discovery/empty-session returns. A default-shaped absolute path alone does not supply resolver root context. Test remote owning root/local foreign cwd and local owning root/remote foreign cwd. Preserve `history.db_path` for **local providers**; under `libsql` it stays ignored, as documented today. `LL_HISTORY_DB` and applicable explicit local paths remain overrides; do not add new precedence.

`logs stats` and `dead-skills` without `--project` enumerate multiple projects through `discover_all_projects`; checking only the ambient cwd misses remote members. Resolve each candidate with `root=its_project_root` before `_aggregate_skill_stats`, use returned local paths, and deduplicate resolved local paths (an env override can map many projects to one file). Preflight the complete selected set: any remote candidate gives the command's fixed refusal before aggregation or data stdout, rather than silently dropping that project or returning a partial total. An all-local selection retains its output and literal missing-DB warning. For `history activity --workspace`, preflight the owning default target and discovered member targets before local aggregation; a remote member cannot masquerade as a missing/empty local member. Keep explicit non-default manifest paths local under the existing resolver rules.

For explicit messages DB mode, classification precedes both the no-handles error and the `not messages and not commands` success branch. A remote refusal must not depend on finding transcripts. Thread an optional owning `root` into `extract_conversation_turns`' DB resolution so local selected-project reads also use the right store; ENH-3728 reuses this parameter for auto fallback. Automatic callers that omit it keep their current cwd resolution. These changes do not alter `_resolve_once` or the reader opener contract.

### Local-target setup must land with the boundary slice

**Review #4 evidence:** a local owning root resolved from a foreign remote cwd still fails through `open_history_readonly(..., ensure=True)` with `HistoryBackendNotLocal`. Applying only a temporary typed-local `SqliteBackend.ensure_schema` fix made that same probe succeed. The setup fix was previously assigned to ENH-3700, which is blocked by this issue; leaving it there makes this slice's foreign-cwd local tests impossible to satisfy independently.

Move the narrow setup fix here: after validating the local path, `SqliteBackend.ensure_schema` calls `schema.ensure_db(LocalTarget(path))`, so SQLite setup cannot resolve an already-selected local store again against ambient config. Ordinary `schema.connect`/`ensure_db` callers and writer/hook precedence are unchanged. This supplies ENH-3700's prerequisite; do not add a reverse dependency.

When `extract_conversation_turns` resolves a local DB against its owning root, pass that selected result as `LocalTarget` through `history_reader.sessions.conversation_turns` and `_connect_readonly`. Keep a separate Path for `exists()` and forward the typed target to the opener; do not strip intent with `Path(target)`. Widen only these reached annotations/handling, retaining the existing fallback/error contracts. ENH-3728 separately owns local provenance through the summary/decisions parsing helpers that use `schema.connect` directly.

For `ll-ctx-stats --db`, a relative `.ll/history.db` currently reaches the strict opener's default resolver and selects remote despite the explicit flag. Anchor the explicitly supplied Path at the invocation cwd before passing it to the existing filesystem/strict-read helpers; an absolute Path already has that local contract. Test actual content through both default-shaped forms, rather than accepting a fallback report as evidence that the override was read.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/messages.py`, `user_messages.py` (optional owning-root argument), `mcp_server/tools.py`, the shared boundary helper module, `skills/analyze-history/SKILL.md`, `skills/create-eval-from-issues/SKILL.md` (+ regenerated mirrors).
- `scripts/little_loops/session_store/backend.py` (`SqliteBackend.ensure_schema` only), `history_reader/sessions.py` (`conversation_turns` local-target forwarding) and `history_reader/_base.py` (target annotation/forwarding only). ENH-3682 may independently add best-effort handling to the same opener; preserve its parameters when integrating. ENH-3700 consumes this setup fix rather than implementing it later.
- Anchors drift: re-grep every `resolve_history_db(` site before editing (`cli/history.py` ~`:501–797`, `cli/logs.py` ~`:1718/1962`, `cli/ctx_stats.py` ~`:1188`, `mcp_server/tools.py:172`).

### Loop / digest invariants
- `.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps `"No history.db found"`; keep the string verbatim and add remote notices as separate stderr lines (all its states capture `2> "$ERR"`).
- `evaluation-quality.yaml` and `backlog-flow-optimizer.yaml` (inline `ll-history summary 2>/dev/null || echo`) need no edit; `fleet-loop-improve` `fleet-review | tail -n 1` is unaffected by a stderr notice.

### Tests
- New: one **parametrized** refusal test over the refused sites, including `main_messages` under `--sft-format --reader db` (exit 1, `<prog> <sub>:` prefix, `libsql` in stderr, `"Traceback" not in err`, no reader requests) plus a local twin. Disable CLI analytics capture for the request-count assertion (`LL_ANALYTICS_CAPTURE=0`), or separate reader requests from legitimate remote `cli_events` writes. `_cmd_stats`/`_cmd_dead_skills` refuse without creating a local `.ll/history.db` (assert absence). Where a CLI defines `--db` (`ll-ctx-stats`), that explicit path stays local; `LL_HISTORY_DB` keeps its local override. MCP refusal names the operation and resolves config against `project_root` (remote config at `project_root` + foreign cwd).
- Use the hoisted `remote` fixture from ENH-3677 (must `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`). Test the public boundary: `main_history()`, `main_logs()` and `main_messages()` take no `argv`, so monkeypatch `sys.argv`; `main_ctx_stats(argv=None)` accepts a list. Cover seeded and empty transcripts for eval-export/explicit SFT so a refusal is named in both cases. Exercise the registered MCP `handle_call_tool`, not only `_tool_history_search`.
- Add mixed local/remote discovery tests for logs stats/dead-skills from a local foreign cwd, all-local twins with custom `history.db_path`, and an `LL_HISTORY_DB` alias case proving one file is counted once. Workspace activity gets a local owning root plus remote member case. No selected remote path is probed or opened, including a pre-existing shadow DB.
- Prove the local selected messages root returns seeded DB conversation windows from a foreign remote cwd through the real ensure/read chain; no JSONL fallback may hide failure. Prove relative and absolute default-shaped `ll-ctx-stats --db` return seeded local metrics with zero reader requests to the remote stub. Keep explicit absolute-path precedence and ordinary writer/hook resolution tests green.
- Keep green: `test_enh3549_codex_stored_ctx_stats.py` (`err == ""`), `test_enh3656_stored_cache_rate.py`, `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_feat3410_workspace_quality.py`/`test_feat3445_workspace_activity.py` (literal `"history.db not found"`), `test_ll_logs.py` index-sensitive stderr tests, `test_cli_messages.py`, `test_bug_3216_telemetry_digest_invocations.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (support table), `docs/reference/CLI.md` (link + `ll-history`/`ll-ctx-stats`/`ll-harness` exit notes), `docs/reference/API.md` (`main_ctx_stats` signature is missing `argv=None`), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125`, `docs/reference/loops.md:493`.

## Program Design

### Types

- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.

### Signatures

- `history_error_verdict(exc: HistoryUnsupported, *, program: str, operation: str | None = None) -> int` — planned shared helper; print the fixed safe reason and return 1. Use the caller's fixed operation label, never arbitrary exception text.
- `main_history() -> int`, `main_logs() -> int`, `main_messages() -> int` are zero-argument boundaries; `main_ctx_stats(argv=None) -> int` accepts argv. Messages and ctx-stats have no subcommand: their prefixes are `ll-messages:` and `ll-ctx-stats:`; name the SFT operation in the reason without inventing a CLI subcommand.
- `extract_conversation_turns(..., reader: str = "auto", *, root: Path | None = None) -> list[list[tuple[str, str]]]` — add the optional root to the existing signature without changing other argument calling conventions; only DB resolution consumes it.
- `conversation_turns(db_path: Path | str | LocalTarget, since=None, context_window=3)` — retain its existing calling convention and empty fallback; unwrap only for filesystem probes and preserve the typed argument for the reader opener.
- `_connect_readonly(db_path: Path | LocalTarget, ...)` — target forwarding/annotation change only; preserve ENH-3682's best-effort keyword if it has landed. The guard/required/error-contract changes remain ENH-3700.
- `SqliteBackend.ensure_schema(target: Path | HistoryTarget) -> None` — existing signature; pass validated local intent to `schema.ensure_db` rather than a plain default-shaped Path.

### Call Path

- `main_history` -> `resolve_history_db` -> `HistoryBackendNotLocal` -> boundary helper -> stderr + `return 1` (refuse verdict).
- `main_logs` -> `_cmd_stats` / `_cmd_dead_skills` -> remote classification before the hand-built path -> boundary helper.
- `mcp_server.tools._tool_history_search` -> `resolve_history_db` -> `HistoryBackendNotLocal` -> `is_error` naming the operation.

### Decision Rules

- Catch class is `HistoryUnsupported`, never bare `HistoryError`; `"No history.db found"` stays verbatim for local-missing; the refusal is a separate stderr line.
- Escape hatch: `LL_HISTORY_DB` set, or an explicit `--db` where supported, runs locally. Among this slice's refused CLIs only ctx-stats defines that flag; session/history-context provenance belongs to ENH-3700.
- A refusal never exits with a code that a graded loop could read as success.

## Implementation Steps

Prerequisite: ENH-3677 landed (hoisted `remote` fixture). BUG-3652 is done.

1. Add the boundary helper; wire it into `main_history`, `main_logs`, `main_ctx_stats`, `main_messages`.
2. Convert the refuse sites (anchor explicit `ll-ctx-stats --db`); make `_cmd_stats`/`_cmd_dead_skills` refuse before the hand-built path; confirm MCP `is_error` wording. Land the narrow typed-local SQLite setup fix and selected conversation-target forwarding here so foreign-cwd local tests pass before ENH-3700.
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
- [ ] `ll-history --config`, logs eval-export's selected project and messages `--cwd` use their owning root with a foreign cwd in both directions; local-provider config overrides and applicable env/explicit overrides are preserved. Explicit messages DB mode refuses even with empty transcripts, and no foreign `.ll/history.db` is created.
- [ ] Mixed-project logs stats/dead-skills and workspace activity refuse before aggregation when a selected default target is remote; all-local discovery retains totals, and multiple roots redirected to one env-override file count it once. Stale shadow files are not read.
- [ ] Where a CLI defines `--db`, that explicit path remains local; `LL_HISTORY_DB` keeps its local override at applicable sites.
- [ ] Seeded local conversation data survives the actual ensure/read chain from a foreign remote cwd, with selected `LocalTarget` retained through `conversation_turns` and SQLite setup. Relative/absolute default-shaped explicit `ll-ctx-stats --db` read seeded metrics without reader requests to remote; existing writer/hook precedence is unchanged. This passes without ENH-3700's guard or required-read changes.
- [ ] The support table exists in `CONFIGURATION.md`, refused rows read "not supported with a remote backend" (no follow-up promised), and it includes "context-pressure and handoff rows are not recorded under a remote backend"; epilog exit codes and the two skills describe the refusal exit 1; mirrors regenerated.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3700 (3657b, central guard + serve/degrade; `blocks`, lands after this), ENH-3677 (shared `remote` fixture; `blocked_by`, land first), BUG-3652 (startup/write-path audit; **done**, `62ac0fc89`), ENH-3658 (hand-built paths; `logs` sites deferred here), ENH-3682 (prepatch read budget; independent), FEAT-3535 (remote libSQL backend).
- ENH-3668 / ENH-3684 / ENH-3685 (remote read serving) are deferred indefinitely; no follow-up is promised in docs.
- Consequence to record: remote users lose `ll-history` reader subcommands and MCP `history_search` ("not supported with a remote backend"); `summary` is addressed in ENH-3728 and `ll-harness` in ENH-3700.

## Status

**Open** | Created: 2026-09-29 | Priority: P3 | Split to 3657a 2026-10-02

## Confidence Check Notes

_Cleared 2026-10-02 after the split into 3657a (this issue) and ENH-3700 (3657b). Prior scores (70/48) no longer apply. Re-run `/ll:confidence-check` once ENH-3677 lands._

---

## Scope Boundary

**Ownership:** epilog and CLI.md "Exit codes" edits here cover `ll-ctx-stats` and `ll-history` only. ENH-3700 owns `ll-harness` serving and its existing fail-closed retry/baseline validation behavior; this issue adds no remote-backend refusal there.

## Session Log
- EPIC-3693 review #4 - 2026-10-05 - typed-local reader setup moved here from ENH-3700 to remove an impossible prerequisite ordering; conversation-target forwarding and explicit relative ctx-stats override tests pinned. Fresh Opus consult skipped: existing per-chat budget exhausted; implementation not performed.
- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - current split, selected messages/log roots, multi-project preflight, override precedence and executable design signatures corrected; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:26 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
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
