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
- ENH-3677
- ENH-3682
blocks:
- ENH-3668
confidence_score: 70
outcome_confidence: 48
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 0
---

# ENH-3657: Give history reader CLIs a remote-backend verdict (refuse or degrade)

> **Reconciled 2026-09-30** after three `/ll:advise` (Opus) reviews (the last run after BUG-3652 landed, `62ac0fc89`, and a fourth pass that found a placement bug in the central guard). The body below is the single current design; the earlier per-site design (per-operation `_REMOTE_REFUSALS` keys, `_REJECTED` rows, ~12 per-doc notes, `refuse_on_remote(..., root=)`) is dropped. The confidence score below predates the additional CLI/test corrections in this issue; re-run `/ll:confidence-check` after ENH-3677 lands. The pre-reconcile text is in git history.

## Delivery Slices (2026-09-30 Opus review)

Land as two reviewable slices; the seam alone must never ship, because it turns today's silent-empty reads into tracebacks in every local-editable project.

- **3657a — seam + boundary helper**: central guard in `open_history_readonly`, `_connect_readonly` re-raise, read-mode remote ensure, the one boundary helper wired into `main_history`/`main_logs`/`main_ctx_stats`/`main_messages`, and the non-CLI caller audit (MCP `history_search`, `sft-corpus` `enrich`, CT-0). Seam tests included.
- **3657b — sites, serve, docs**: per-site verdicts, `ll-harness` serve, `history summary`/`decisions`/`--reader auto` degrades, `sft-corpus`/CT-0 changes, skill mirrors, docs and the support table.

**Slicing rationale:** Opus advised two slices, with the boundary helper shipping with the seam (so a refusal is never a traceback) and docs shipping with the sites. An earlier three-way split (seam / helper+refuse sites / serve+docs) was rejected for that reason. This is kept as slices of one issue to avoid re-wiring ENH-3668's `blocked_by`; convert to separate issues only if the slices need independent scheduling.

**Prerequisites:** ENH-3677 (fixture) and ENH-3682 (prepatch reads become `best_effort` and catch `HistoryUnsupported`; without it the re-raise reaches the FSM for `read_base_sha` on a behind/foreign/read-only-token remote store). **Narrow the re-raise** to the guard's own subclass (e.g. `HistoryRemoteRefused(HistoryUnsupported)`) rather than every `HistoryUnsupported`, so remote `ensure_schema` refusals keep degrading to `None` for callers that never opted in.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), user-invoked history reader commands raise an unhandled `HistoryBackendNotLocal` (or, worse, silently create a shadow local `.ll/history.db`). This issue gives each reader site an explicit verdict: **refuse** cleanly, **degrade** to a correct fallback, or (for `ll-harness` only) **serve** from the remote store. Real remote reads for `ll-history` reader subcommands and MCP `history_search` are ENH-3668.

## Current Behavior

These sites pre-resolve through `resolve_history_db()` and raise `HistoryBackendNotLocal` (a `HistoryUnsupported`) unhandled, so the CLI shows a traceback:

- `cli/history.py:main_history` (8 sites: `summary`, `analyze`, `rework`, `quality`, `activity`, `audit-issue-collisions`, `sessions`, `root`), `cli/harness.py` (5 sites), `cli/logs.py` (`_cmd_diff`, `_cmd_eval_export`), `cli/ctx_stats.py`.
- `decisions.py:generate_from_completed`, `user_messages.py:extract_conversation_turns` (reached through `cli/messages.py:main_messages` for SFT output), `mcp_server/tools.py:_tool_history_search` (converted to `is_error` by `handle_call_tool`), and `skills/improve-claude-md` CT-0 (its `python3 -c` ends in `2>/dev/null`, so it emits empty stdout that reads as "no candidates").
- `cli/logs.py` `_cmd_stats` / `_cmd_dead_skills` build `<project>/.ll/history.db` by hand (ENH-3658 defers them here); they can `ensure_schema`-create an empty shadow DB.
- The `except HistoryError` handlers in `logs.py`/`history.py`/`ctx_stats.py` wrap only connect/query calls; the pre-resolves sit outside them.

**Load-bearing fact.** `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), so dropping a pre-resolve does not make a site read remotely: `open_history_readonly(..., ensure=True)` would run `ensure_schema` on that local path and create an empty shadow `.ll/history.db`. Only `cli/harness.py` (relative `DEFAULT_DB_PATH`) can serve.

**Placement bug found in review.** `history_reader/_base.py:_connect_readonly` catches `HistoryError` (parent of `HistoryUnsupported`) and returns `None`, and its ~67 callers all treat `None` as "no data". A refusal raised inside `open_history_readonly` would therefore be swallowed into silent empty output unless `_connect_readonly` re-raises `HistoryUnsupported`.

## Expected Behavior

### Verdicts

| Site | Under remote | Notes |
|---|---|---|
| `history summary` | **degrade** to the file scan, exit 0 | fallback exists (`scan_completed_issues`); one `note:` line on stderr |
| `history analyze`, `activity`, `rework`, `quality`, `audit-issue-collisions`, `sessions`, `root` | **refuse** | boundary helper turns the pre-resolve's `HistoryBackendNotLocal` into `<prog> <sub>: <exc>`, exit 1; real reads are ENH-3668 |
| `ll-harness` ×5 sites | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend`; needs read-mode ensure; never refuses with exit 1 (indistinguishable from a graded FAIL) |
| `logs` `_cmd_diff`, `_cmd_eval_export`, `_cmd_stats`, `_cmd_dead_skills` | **refuse** | keep the literal `"No history.db found"` warning for local-missing (digest loop greps it); refusal is a separate line |
| `ctx_stats` | **refuse** | explicit `--db` skips the pre-resolve and still runs locally; no `refuse_on_remote` needed |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first |
| `ll-messages --sft-format` / `user_messages.extract_conversation_turns` | `reader=auto` → **degrade** to JSONL; `reader=db` → **refuse** | `auto` currently reaches `resolve_history_db`; catch `HistoryUnsupported` before JSONL fallback; explicit `db` gets a clean CLI error |
| CT-0 in `skills/improve-claude-md` | **degrade**: skip with a one-line note | empty stdout must no longer read as "no candidates" |
| MCP `history_search` | **refuse** as a structured `is_error` naming the operation | its pre-resolve already takes `root=project_root`; verify the message names the operation |
| `loops/sft-corpus.yaml` `stage` | switch to `--reader auto` (degrade to JSONL) | a refusal must not become an empty corpus routed to `enrich` as success |
| `loops/sft-corpus.yaml` `enrich` | **degrade**: explicit note, pass records through un-enriched | `lookup_session_metadata` is `.exists()`-gated (`history_reader/sessions.py:358`); serving it is ENH-3668 |

### Central guard (fix the cause once)

In `session_store.backend.open_history_readonly` (the `ensure=True` reader opener): when the configured provider is remote **and** the resolved target is a *default-shaped* absolute local path (`<root>/.ll/history.db`, `LL_HISTORY_DB` unset, no explicit `--db`), raise `HistoryUnsupported` instead of `ensure_schema`-creating a shadow DB. It fires only in that case and must respect the BUG-3181 absolute-path contract, an explicit `--db` (wrap it in `LocalTarget` at the CLI), `LL_HISTORY_DB`, and first-use local creation when the provider is not remote. Classify "remote" from the root derived from the path (`<root>/.ll/...`), not the cwd, so an MCP call with a foreign cwd is not misclassified.

`history_reader/_base.py:_connect_readonly` gains a re-raise of the guard's own `HistoryUnsupported` subclass **above** its `except HistoryError` handler (not every `HistoryUnsupported`; see Delivery Slices). Record the contract change ("`None` on failure, raise on unsupported") in the docstring. Audit every non-CLI caller that passes an absolute default-shaped path and give it a catch or degrade: MCP `history_search`, `sft-corpus` `enrich`, the CT-0 block. (`hooks/session_start` digest is already gated by `not _remote_store`; the executor's `read_base_sha` uses the relative path and is unaffected.)

### One boundary helper

One helper maps `HistoryUnsupported` to `<prog> <sub>: <exc>` on stderr and exit 1, used inside `cli_event_context` by `main_history`, `main_logs`, `main_ctx_stats`, and `main_messages` for explicit DB-backed SFT reads (and `main_harness` only where a refusal can still occur). It replaces ~20 per-site catch blocks. Catch `HistoryUnsupported`, never bare `HistoryError` (which would swallow real store errors). `main_history()` and `main_logs()` take no `argv`; `main_harness(argv=None)` and `main_ctx_stats(argv=None)` do. `reader=auto` handles the unsupported signal in `extract_conversation_turns` and reaches JSONL, not the CLI refusal helper.

### Read-only remote token

`ensure=True` runs `check_access(write=True)` (`remote_schema.check_access`, `libsql.py`), which refuses a behind/ahead store and a read-only token, making every reader return `None`. Make the ensure step of `open_history_readonly` for a `RemoteTarget` a read-mode check (`check_access(write=False)`, no ensure/migrate); a missing remote schema reads as empty, and `ll-harness` serve must treat it as such. Extend `HranaStub` with a read-only permission mode that permits SELECT and rejects writes, or use a controlled equivalent; a token accepted for every SQL statement cannot prove this behavior.

### Notice channel (decided)

Degrade notice = one `note:` line via `print(..., file=sys.stderr)` from the CLI, emitted before touching the seam, only under a remote target, never on stdout, never echoing an endpoint token. The library `remote_telemetry.warn_once` in `_connect_readonly` must **not** also fire for that call: one channel per site, never both.

## Motivation

Remote-backend users hit an unhandled traceback (or a silent shadow DB) from `ll-history`, `ll-harness` and other readers. A clean, named refusal or correct degrade is the achievable fix now; serving the remaining readers safely needs typed-target plumbing (ENH-3668), not a call-site edit.

## Scope Boundaries

- **In scope**: the sites in the verdict table (including `logs` `_cmd_stats`/`_cmd_dead_skills`, deferred here by ENH-3658), the central guard, the `_connect_readonly` re-raise, the read-mode remote ensure, one boundary helper, the CT-0 guard, `sft-corpus` `stage`/`enrich`, and a single reader-support table in `CONFIGURATION.md`.
- **Out of scope**: startup/write-path sites (BUG-3652, done), hand-built paths and `context-monitor.sh` (ENH-3658/3680), `HistoryTarget`-aware readers serving `ll-history` subcommands/MCP (ENH-3668), `ll-session search --fts` (follows ENH-3668; it passes the caller's own `--db` — confirm no unhandled `HistoryBackendNotLocal` path), `ll-doctor` (already handles `HistoryError` with per-site wording; confirm), and writers/runtime callers of `resolve_history_db` (`cli/parallel.py`, `fsm/*`, `hooks/*`, … — BUG-3652 territory).

## Proposed Solution

1. **Session-store seams** (`session_store/backend.py`, `history_reader/_base.py`): central guard in `open_history_readonly`; `_connect_readonly` re-raise; read-mode remote ensure. No new `_REMOTE_REFUSALS` keys, no `_REJECTED` rows, no `refuse_on_remote(root=)`.
2. **Boundary helper** and per-site edits per the verdict table; refusals rely on the existing pre-resolve's `HistoryBackendNotLocal` where present and on the central guard for hand-built paths.
3. **`skills/improve-claude-md/SKILL.md`**: guard CT-0 only (344 lines, cap 500; keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`); then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and `test_improve_claude_md_skill.py`.
4. **`loops/sft-corpus.yaml`**: `stage` → `--reader auto`; `enrich` degrade note.
5. **Docs**: document reader behavior once, as one support table in `docs/reference/CONFIGURATION.md` "Remote history backend", linked from `docs/reference/CLI.md` (ENH-3668 later shrinks it). Also tell the model what a refusal exit 1 means in `skills/analyze-history/SKILL.md` and `skills/create-eval-from-issues/SKILL.md` (regenerate the `.gemini/`, `.qwen/`, `.kimi-code/` mirrors), update the `ll-ctx-stats`/`ll-harness` epilog "Exit codes", and keep `loops/lib/cli.yaml` `ll_history_summary` description non-empty. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (`open_history_readonly`), `history_reader/_base.py` (`_connect_readonly`), `cli/history.py`, `cli/harness.py`, `cli/logs.py`, `cli/ctx_stats.py`, `cli/messages.py`, `decisions.py`, `user_messages.py`, `mcp_server/tools.py`, `skills/improve-claude-md/SKILL.md`, `loops/sft-corpus.yaml`; `scripts/tests/hrana_stub.py` if read-only permissions are modeled there.
- `cli/harness.py` ×5 (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`) is the only serve site: drop the pre-resolve and pass the relative default. `issue_history/evolution._open_db` (sqlite-only choke point shared by `analyze` and CT-0) changes only if made remote-aware.
- Anchors drift: re-grep every `resolve_history_db(` site before editing (`cli/history.py` ~`:501–797`, `cli/logs.py` ~`:1718/1962`, `cli/ctx_stats.py` ~`:1188`, `decisions.py:596`, `user_messages.py` ~`:1227`, `mcp_server/tools.py:172`).

### Loop / digest invariants
- `.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps `"No history.db found"` — keep the string verbatim; add remote notices as separate stderr lines (all its states capture `2> "$ERR"`).
- `evaluation-quality.yaml` and `backlog-flow-optimizer.yaml` (inline `ll-history summary 2>/dev/null || echo`) need no edit. `ll-messages` default-`auto` callers need a regression test because `extract_conversation_turns` currently reaches the remote pre-resolve; `fleet-loop-improve` `fleet-review | tail -n 1` is unaffected by a stderr notice.

### Tests
- New: one **parametrized** refusal test over the refused sites, including `main_messages` under `--sft-format --reader db` (exit 1, `<prog> <sub>:` prefix, `libsql` in stderr, `"Traceback" not in err`, no reader requests). Disable CLI analytics capture for that assertion (`LL_ANALYTICS_CAPTURE=0`), or separate reader requests from legitimate remote `cli_events` writes. Add default-`auto` JSONL fallback coverage. Degrade tests keep stdout unchanged with exactly one `note:` line and no token. `ll-harness` serve returns stub data and creates **no** local `.ll/history.db`; guard fires only for the default-shaped case, with typed `LocalTarget` for an explicit absolute `<root>/.ll/history.db`, `--db`, `LL_HISTORY_DB`, and non-remote first-use creation tested as carve-outs. `_connect_readonly` re-raises `HistoryUnsupported` and does not also `warn_once`; read-only-token serve uses an actual permission-rejecting stub; MCP remote config at `project_root` with foreign cwd; `"No history.db found"` invariant (`test_bug_3216_telemetry_digest_invocations.py`); `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`).
- Use the hoisted `remote` fixture from ENH-3677 (must `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`); test `main_harness([...])`, not `cmd_*` (existing tests call those directly).
- Keep green: `test_enh3549_codex_stored_ctx_stats.py` (`err == ""`), `test_enh3656_stored_cache_rate.py`, `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites and the reader seam, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_feat3410_workspace_quality.py`/`test_feat3445_workspace_activity.py` (literal `"history.db not found"`), `test_cli_decisions.py`/`test_decisions.py` DB-first local branch, `test_ll_logs.py` index-sensitive stderr tests, `test_cli_messages.py`, `test_evolution_triggers.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (single support table), `docs/reference/CLI.md` (link + `ll-history`/`ll-ctx-stats`/`ll-harness` exit notes), `docs/reference/API.md` (`extract_conversation_turns` relationship paragraph; "SQLite-only prerequisite" `Backend chokepoint` wording; `main_ctx_stats` signature is missing `argv=None`), `docs/ARCHITECTURE.md:~758` ("SQLite-only chokepoint"), `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/guides/WORKFLOW_ANALYSIS_GUIDE.md:125`, `docs/reference/loops.md:493`. Reader text is a first mention everywhere; it must not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Program Design

### Types

- `HistoryError(Exception)` ← `HistoryUnsupported(HistoryError)` ← `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.
- `HistoryTarget = LocalTarget | RemoteTarget` in `little_loops.session_store.targets`; no reader signature accepts it (that is ENH-3668).

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False)` — remote-capable reader opener; gains the default-shaped-local-path guard and a read-mode ensure for `RemoteTarget`.
- `_connect_readonly(db_path: Path) -> sqlite3.Connection | None` — returns `None` on ordinary failure but re-raises `HistoryUnsupported`.
- `main_history() -> int` — CLI boundary; maps `HistoryUnsupported` to `<prog> <sub>: <exc>` on stderr and returns 1 (same for `main_logs`, `main_ctx_stats(argv=None)`).
- `generate_from_completed(config: BRConfig) -> int` — degrade site in `little_loops.decisions`; local branch stays DB-first.

### Call Path

- `main_history` → `resolve_history_db` → `HistoryBackendNotLocal` → boundary helper → stderr + `return 1` (refuse verdict).
- `history_reader._connect_readonly` → `open_history_readonly` → default-shaped-path guard → `HistoryUnsupported` re-raised → CLI boundary or MCP `is_error`.
- `cmd_decisions` → `generate_from_completed` → `scan_completed_issues` (degrade verdict, remote only).
- `main_messages` → `extract_conversation_turns(reader="auto")` → JSONL path (degrade); `reader="db"` refuses.

### Decision Rules

- Serve only where the caller passes a relative/default-shaped path (`ll-harness`); an absolute path is a `LocalTarget` and must never reach `ensure=True` under a remote provider.
- Escape hatch: `LL_HISTORY_DB` set, or an explicit `--db` (only `ll-ctx-stats` and `ll-session refresh` define one), runs locally.
- Catch class is `HistoryUnsupported`; notice channel is one CLI `note:` line; `"No history.db found"` stays verbatim for local-missing.
- Unreachable endpoint on a serve site reads as "no data" (`_connect_readonly` maps other `HistoryError` to `None`); accepted for `ll-harness`, documented, and distinguished in ENH-3668.

## Implementation Steps

Prerequisite: ENH-3677 landed (hoisted `remote` fixture). BUG-3652 is done.

1. **Seams**: central guard in `open_history_readonly`; `_connect_readonly` re-raise + docstring; read-mode remote ensure (verify against `HranaStub` first — the one shared-seam edit `ll-harness` serve depends on). Audit non-CLI absolute-path callers.
2. **Serve** `cli/harness.py`: drop the pre-resolve, pass the relative default; verify rows round-trip through `HranaStub` and no local `.ll/history.db` is created.
3. **Boundary helper** and refuse sites: `history` subcommands, `logs`, `ctx_stats` (respect `--db`), `main_messages` for `--sft-format --reader db`, MCP `history_search`.
4. **Degrade** sites: `history summary`, `decisions generate`, `extract_conversation_turns(reader="auto")` to JSONL, CT-0, `sft-corpus` `stage`/`enrich`.
5. **Skills, mirrors, docs** per Proposed Solution 3 and 5.
6. **Tests** per Integration Map → Tests. Run `python -m pytest scripts/tests/`, `ruff check`, `mypy` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium-Large - central guard + boundary helper reduce per-site work, but ~20 sites, several docs, a skill mirror pass and a loop fix remain.
- **Risk**: Medium - the reader contract changes from "`None` on any failure" to "raise on unsupported"; refusals exit 1 and can trip loop gates.
- **Breaking Change**: No (local behavior unchanged).

## Acceptance Criteria

- [ ] Work lands as slices 3657a (seam + boundary helper + caller audit) then 3657b; ENH-3682 has landed first and prepatch `read_base_sha` on a behind/read-only-token remote store still returns `None`.
- [ ] Every site in the verdict table has its verdict implemented; refused sites, including `ll-messages --sft-format --reader db`, are covered by one parametrized remote-stub test (exit 1, `<prog> <sub>:` prefix, `libsql` in stderr, `"Traceback" not in err`, no reader requests when analytics capture is disabled) plus a local twin. Default `reader=auto` reaches JSONL instead of an unhandled refusal.
- [ ] `_connect_readonly` re-raises the guard's `HistoryUnsupported` subclass (documented contract; other `HistoryUnsupported` from remote ensure still map to `None`) so a guard refusal never reads as empty data; non-CLI callers (MCP, `sft-corpus`, CT-0) are audited and handled.
- [ ] The central guard fires only for a remote provider + default-shaped absolute local path with no `--db`/`LL_HISTORY_DB`, classifies remote from the path-derived root (not cwd), and under remote no reader creates a local `.ll/history.db` (assert absence). A caller-supplied absolute local path wrapped as `LocalTarget` stays local.
- [ ] `ll-harness` serve sites return stub data, create no local `.ll/history.db`, and still serve a behind/ahead remote schema and a **read-only token** (`check_access(write=False)`); the test rejects writes with the same token rather than relying on a token-only auth check.
- [ ] Degrade sites (`history summary`, `decisions generate`, `--reader auto`, CT-0, `sft-corpus` `enrich`) keep stdout unchanged, exit 0 (CLI cases), and print exactly one `note:` line on stderr only under a remote target; `warn_once` does not also fire; no endpoint token appears in any notice or refusal.
- [ ] MCP `history_search` refusal names the operation and resolves config against `project_root` (remote config at `project_root` + foreign cwd test).
- [ ] `sft-corpus.yaml` `stage` no longer turns a remote refusal into an empty-success corpus; `"No history.db found"` is unchanged (invariant test).
- [ ] Where a CLI actually defines `--db`, that explicit path remains local; `LL_HISTORY_DB` keeps its local override at applicable sites. With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- BUG-3652 (startup/write-path audit; **done**, `62ac0fc89`); ENH-3677 (shared `remote` fixture; `blocked_by`, land first); FEAT-3535 (remote libSQL backend).
- ENH-3668 (`HistoryTarget`-aware readers; serves what this issue refuses in the interim); ENH-3658 (hand-built paths; coordinate on the shared guard).
- Consequence to record: remote users lose `ll-history` reader subcommands (except `summary`, which degrades) and MCP `history_search` until ENH-3668; `ll-harness` reads work.

## Status

**Open** | Created: 2026-09-29 | Priority: P3

## Confidence Check Notes

_Historical score from before this review; the `ll-messages`, analytics-request, and read-only-stub test corrections above supersede its "only blocker" statement. Re-score after ENH-3677 lands._

_Added by `/ll:confidence-check` on 2026-09-30_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS (Dependencies hard override)
**Outcome Confidence**: 48/100 → LOW

### Concerns
- Design is well-specified and claims check out (`open_history_readonly`, `_connect_readonly`'s `except HistoryError`, `check_access`, 5 `cli/harness.py` + 8 `cli/history.py` `resolve_history_db(` sites, per-file `remote` fixture copies all confirmed); the only blocker is the dependency below.
- Program Design gate, learning tests, parity/claim/decision/structure gaps: all clean.

### Gaps to Address
- `blocked_by: ENH-3677` is `open` (hoisted `remote` fixture not yet landed) — Dependencies hard override forces STOP. Land ENH-3677 first, or drop the edge if the plan is to ship with a per-file fixture copy.

### Outcome Risk Factors
- Broad enumeration across ~20 refuse/degrade sites plus docs, skill mirrors and a loop YAML (16+ change sites).
- Moderate-to-deep per-site complexity: the central guard and `_connect_readonly` re-raise change the reader contract from "`None` on any failure" to "raise on unsupported" for ~67 callers.
- Very wide blast radius on the shared seam (`_connect_readonly` ~67 callers, `open_history_readonly`); a missed non-CLI caller silently swallows a refusal or trips loop gates. Consider landing the seam change (Step 1) as its own reviewable slice first.

## Session Log
- `/ll:confidence-check` - 2026-09-30T01:08:15 - `d09a5e0e-2f2f-4d02-a2fb-345fcc5b2f01.jsonl`
- `/ll:advise` (Opus, placement-bug review) + reconcile rewrite - 2026-09-30
- `/ll:confidence-check` - 2026-09-29T22:09:09 - `c419efbf-94bc-4735-80cf-772ead8ae35e.jsonl` (scores since cleared; re-run)
- `/ll:verify-issues` - 2026-09-29T22:05:34 - `b6e9a962-45bc-4981-a31d-f5f911dc70c3.jsonl`
- `/ll:refine-issue` - 2026-09-29T15:53:17 - `38b577b2-a780-4f13-a766-2b3309027fb9.jsonl`
