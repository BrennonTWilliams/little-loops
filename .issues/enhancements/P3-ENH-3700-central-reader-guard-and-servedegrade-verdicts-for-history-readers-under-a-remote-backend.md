---
id: ENH-3700
type: ENH
title: Central reader guard and serve/degrade verdicts for history readers under a
  remote backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
blocked_by:
- ENH-3657
- ENH-3677
blocks:
- ENH-3668
- ENH-3684
- ENH-3685
relates_to:
- ENH-3658
- ENH-3682
- ENH-3668
- BUG-3652
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3700: Central reader guard and serve/degrade verdicts for history readers under a remote backend

> **Split from ENH-3657 on 2026-10-02** (Opus review of EPIC-3693's children). ENH-3657 (3657a) owns the refuse boundary: one boundary helper plus the refuse sites that fail on the pre-resolve's `HistoryBackendNotLocal`, with no contract change. This issue (3657b) owns the risky seam: the central guard, the `_connect_readonly` re-raise that changes the contract for ~67 callers, the exhaustive caller audit, read-mode remote ensure, `ll-harness` serve, and every degrade site. Isolating it keeps the wide-blast-radius change in one reviewable PR. The design below was moved out of ENH-3657's reconciled body (three prior `/ll:advise` Opus reviews).

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), a reader that builds the default `<root>/.ll/history.db` path can `ensure_schema`-create an empty shadow local database, and `_connect_readonly` maps every `HistoryError` to `None`, so a refusal would read as "no data". This issue adds a central guard at the reader seam, makes the guard's own refusal survive `_connect_readonly`, lets `ll-harness` serve from the remote store, and gives the remaining reader sites a degrade verdict.

## Current Behavior

**Load-bearing fact.** `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), so dropping a pre-resolve does not make an absolute-path site read remotely: `open_history_readonly(..., ensure=True)` would create an empty shadow `.ll/history.db`. Among the newly flipped CLI sites here, `cli/harness.py` can serve by retaining relative `DEFAULT_DB_PATH`; existing relative-default session/context readers remain supported.

**Placement bug.** `history_reader/_base.py:_connect_readonly` catches `HistoryError` (parent of `HistoryUnsupported`) and returns `None`, and its ~67 callers all treat `None` as "no data". A refusal raised inside `open_history_readonly` is swallowed into silent empty output unless `_connect_readonly` re-raises it.

**Read-mode mismatch.** `ensure=True` runs `check_access(write=True)` (`remote_schema.check_access`, `libsql.py`), which refuses a behind/ahead store. It currently sends only metadata SELECTs, so it does **not** establish that a read-only token is rejected on an exact stamped schema; remove that unsupported claim. A permission-rejecting stub is still required to prove the final read path sends no writes/DDL. `LibsqlBackend.ensure_schema` checks policy and never migrates.

**Missing-stamp gap (verified 2026-10-04).** `check_access(write=False)` currently accepts a migrated store with no `project_id` stamp: `_check_project` only rejects a non-null mismatched stamp, and the missing-stamp check is inside `if write:`. A temporary HranaStub probe confirmed a version-58 unstamped read is accepted while a write is refused. This issue must implement the stated read-stamp policy, rather than treat it as existing behavior.

Sites that currently degrade wrongly or silently:
- `decisions.py:generate_from_completed`, `user_messages.py:extract_conversation_turns` (reader `auto` reaches `resolve_history_db`), and `skills/improve-claude-md` CT-0, whose `python3 -c` calls bare `resolve_history_db()` (SKILL.md ~L206-209) and ends in `2>/dev/null`, so the refusal emits empty stdout that reads as "no candidates".
- `scripts/little_loops/loops/sft-corpus.yaml` `stage` and `enrich`: a refusal becomes an empty corpus routed to `enrich` as success; `lookup_session_metadata` is `.exists()`-gated (`history_reader/sessions.py:358`).
- `ll-harness` (5 sites in `cli/harness.py`) pre-resolves and raises.
- `ll-history summary` has a file-scan fallback (`scan_completed_issues`) it does not reach under remote.

## Expected Behavior

### Verdicts

| Site | Under remote | Notes |
|---|---|---|
| `history summary` | **degrade** to the file scan, exit 0 | one `note:` line on stderr |
| `ll-harness` x5 sites | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend`; advisory reads degrade, required retry/baseline lookups fail closed through existing validation paths |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first |
| `ll-messages --sft-format` / `extract_conversation_turns` | `reader=auto` -> **degrade** to JSONL | catch `HistoryUnsupported` before the JSONL fallback; explicit `db` refusal is ENH-3657 |
| CT-0 in `skills/improve-claude-md` | **degrade**: explicit skipped verdict with a one-line note | switch to `resolve_history_store`, branch on `RemoteTarget`, remove the snippet's `2>/dev/null`, and check the skipped verdict before the empty-feedback branch |
| `scripts/little_loops/loops/sft-corpus.yaml` `stage` | `--reader auto` (degrade to JSONL) | a refusal must not become an empty corpus routed to `enrich` as success |
| `scripts/little_loops/loops/sft-corpus.yaml` `enrich` | **degrade**: explicit note, pass records through un-enriched | |

### Central guard (fix the cause once)

In `session_store.backend.open_history_readonly` (the `ensure=True` reader opener): when the configured provider is remote **and** the resolved target is a *default-shaped* absolute local path (`<root>/.ll/history.db`, `LL_HISTORY_DB` unset, no explicit `--db`), raise `HistoryRemoteRefused` (a subclass of `HistoryUnsupported`) instead of `ensure_schema`-creating a shadow DB. It fires only in that case and must respect the BUG-3181 absolute-path contract, an explicit `--db` (wrap it in `LocalTarget` at the CLI), `LL_HISTORY_DB`, and first-use local creation when the provider is not remote. Classify "remote" from the root derived from the path (`<root>/.ll/...`), not the cwd, so an MCP call with a foreign cwd is not misclassified.

CLI provenance must survive the reached helper chain: where an explicit local `--db` reaches this ensure-reader seam, retain `LocalTarget` rather than stripping it with `Path(...)` before the guard. Widen only the affected helper annotations and filesystem probes, not every reader or remote target signature. Audit `ll-session` and `ll-history-context` (both define `--db`) with omitted defaults and explicit absolute default-shaped local paths; preserve their existing relative-default remote resolution. `ll-ctx-stats --db` uses the separate strict opener and remains unaffected. Snapshot CLI provenance belongs to ENH-3658. Record these carve-outs in the AST gate instead of exempting whole modules.

### `_connect_readonly` re-raise (contract change)

`history_reader/_base.py:_connect_readonly` re-raises `HistoryRemoteRefused` **above** its `except HistoryError` handler: only the guard's own subclass, never every `HistoryUnsupported`. Other access-policy refusals (`HistoryUnsupported` for a foreign/unstamped migrated store) keep degrading to `None`. Record the contract change ("`None` on failure, raise on a guard refusal") in the docstring. ENH-3682's regression test (an injected access-policy `HistoryUnsupported` still yields `None`) must pass on either merge order.

**Rejected alternative (2026-09-30 Opus):** a no-re-raise seam (`None` + `warn_once`, refusals only at the CLI boundary) to spare the ~67 callers. Rejected: any CLI the boundary helper misses would print silent-empty output, the failure this work exists to remove. The narrowed subclass confines the blast radius to callers that previously created a shadow DB. The compensating control is the exhaustive non-CLI caller audit below.
*Dissent recorded in the 2026-10-02 review:* with no known remote user, the guard and contract change could be cut in favor of per-site refusals (ENH-3657), ENH-3658's hazard gate and the AST test alone. The guard is kept because a shadow DB is a silent data split that per-site fixes and static tests can miss for future callers. If the audit below proves expensive, cutting the guard is defensible.

### Exhaustive caller audit (required before merge)

**Inventory recorded 2026-10-02.** An AST scan of all Python `Import`/`ImportFrom` nodes (including function-local imports) finds **17 external importer modules**, plus 15 modules inside `history_reader`. A text search finds 41 files because it also matches documentation/comments; `prepatch_check.py`, `token_provenance.py`, `fsm/cost_graph.py`, `session_store/{schema,lifecycle,writers,backend}.py`, and `issue_history/workspace_{activity,quality}.py` have text references but no reader imports. They are not additional importer call sites.

Paths below are relative to `scripts/little_loops/`. These are implementation dispositions, not claims that the planned catches already exist. Re-run the AST inventory at implementation and test every call in each importer, including callers reachable through re-exports.

| Importer | Guard/failure disposition |
|---|---|
| `cli/ctx_stats.py` | ENH-3657 refuses default remote reads; usage selectors receive an existing connection; explicit `--db` stays local. |
| `cli/harness.py` | Serve using relative default; read-mode ensure; quiet open and mid-query fallback (this issue). |
| `cli/history.py` | ENH-3657 refuses reader rows; summary file-scan fallback here. |
| `cli/history_context.py` | Preserve relative-default remote resolution and explicit local path provenance through reached helpers; exercise `--project` and issue/effort paths with local overrides. |
| `cli/logs.py` | ENH-3657 refuses remote DB-backed paths before absolute-path metadata lookup; preserve local missing-data behavior. |
| `cli/loop/evidence.py` | `find_loop_run(run_id)` uses the relative default; guard unaffected. |
| `cli/session.py` | Preserve relative-default remote resolution and explicit local path provenance through reached reader helpers; exercise the absolute default-shaped override without converting omitted defaults to absolute paths. |
| `fsm/executor.py` | Relative `DEFAULT_DB_PATH` advisory prepatch reads; ENH-3682 budgets open/query failure. |
| `hooks/session_start.py` | Absolute digest path is already gated by `not _remote_store`; retain that guard. |
| `issue_history/agent_quality.py` | Called under ENH-3657 refusal; local analysis stays intact; future target propagation is ENH-3684. |
| `issue_history/collisions.py` | Same boundary refusal/local-only analysis; future serving is ENH-3684. |
| `issue_history/evolution.py` | Imports only pure `_stale_cutoff`; local-only opener stays under boundary refusal. |
| `issue_history/rework.py` | Same boundary refusal/local-only analysis; future serving is ENH-3684. |
| `mcp_server/tools.py` | ENH-3657 structured refusal using owning project root before absolute default; future serving is ENH-3685. |
| `session_store/queries.py` | `select_usage_coverage` consumes a caller-owned connection for snapshot export; no reader opener; remote snapshot refusal unchanged. |
| `user_messages.py` | Explicit DB reader refuses via ENH-3657; auto reader catches refusal and falls back to JSONL here. |
| `work_verification.py` | Relative default prepatch readers; ENH-3682 best-effort budget, no absolute coercion. |

Reader-internal inventory: `_base`, `__init__`, `context`, `digest`, `events`, `formatting`, `harness`, `hooks`, `models`, `runs`, `search`, `sessions`, `subagents`, `summary_dag`, `usage`. Audit absolute-path coercions and catches in these reached helpers as well as the external importers. Shell/embedded Python is a separate inventory: CT-0 and packaged SFT states are handled here; `skills/update-docs` and the artifact hazard gate belong to ENH-3658; `context-monitor.sh` is the documented no-op (ENH-3680).

Two different functions are named `_connect_readonly`: `history_reader/_base.py` (the `ensure=True` opener whose `None` mapping this issue changes) and `session_store/queries.py` (a raw `mode=ro` URI opener, unaffected). The audit, the AST gate and every test name the module explicitly so neither is conflated with the other. Add an AST regression gate for default-path absolute construction and unaudited importer additions, with reasoned exceptions for explicit local targets, connection-only/pure helpers and remote-gated paths. Do not equate every `Path(...)` call with a hazard; dynamic tests assert no shadow DB in the default remote cases.

### Read-mode remote ensure

For a `RemoteTarget`, skip writable ensure/migration and use `check_access(write=False)`. In the ordinary `ensure=True` opener, verify eagerly **on the same read-only connection's client before returning it**: replacing the old eager ensure with lazy first-query verification would move auth/project/stamp failures out of `_connect_readonly`'s existing catch into ~67 query callers, many of which catch only `sqlite3.Error`. Preserve that failure timing rather than expanding every caller's catch policy. Close the connection on failed preparation. Cached verification still prevents a second metadata request when the first data query runs; a cold healthy read makes one verification POST plus its data POST. ENH-3682's explicit best-effort seam independently catches open and query failures and uses the same deadline-bound client for any verification it performs. **Stamped-schema rule (decided 2026-10-02):** serve exact, **behind** and **ahead** versions; no ahead-store refusal. Missing queried columns follow the reached caller's query-failure disposition. Extend `HranaStub` with a default-off read-only permission mode permitting metadata/data SELECTs and rejecting writes/DDL; enable it after fixture migration. ENH-3720's fault/deadline controls must compose with it and retain defaults. ENH-3668 must follow this policy if revived.

Enforce missing-stamp rejection in the shared `remote_schema.check_access` **after** state loading/cache lookup: `write=False` plus `state.version > 0` and no store `project_id` raises ordinary `HistoryUnsupported(operation="open")`, never `HistoryRemoteRefused`. Missing configured ID and foreign stamps remain refused. Version 0 keeps the non-strict empty fallback; stamped exact/behind/ahead remain readable. This intentionally tightens migrated-but-unstamped reads for all remote consumers, so test cold, in-process-cache and persisted verification-cache paths and document the migration/stamping requirement. ENH-3682 inherits this shared policy without a duplicate stamp classifier or an extra dependency. The reader maps access-policy errors to its ordinary fallback; the central guard remains the only re-raised refusal.

### Harness advisory reads and required validation reads

`_read_target_history` and DSL `admissions_by_reason` are advisory: open/query failure yields the existing absent rate/breakdown and does not alter grading or exit codes. The DSL admissions result is only formatted after execution and does not gate/deduplicate tasks (verified in `cmd_dsl` 2026-10-04).

`_retry_gate`, `_resolve_baseline_of`, and `read_baseline` feeding compare/pin gates are required control-flow lookups. Failure must never admit a retry or invent a baseline. Preserve the existing missing-attempt/baseline validation messages and exit paths (including exit 1 where already used), with a safe warning for unavailable history and zero subject invocations/new candidate rows for the rejected candidate. Do not infer a successful empty query from a caught error; the library warning distinguishes failure without introducing strict-reader infrastructure. Test successful remote prior-attempt/baseline data and open/query failures at the required gates, plus an advisory representative. Remote configuration itself adds no generic refusal or new harness exit code.

### Non-strict mid-query failures

`HranaError` is a `HistoryError`, but not a `sqlite3.Error`. Widen the reached harness handlers to `(sqlite3.Error, HistoryError)` and retain empty/zero/None with the dispositions above. For remote failures use `warn_once` with a stable operation/category and fixed text, never `str(exc)` or `exc_info=True`; apply the same rule to `_base._connect_readonly`, whose current warning embeds raw exception text. Capture logging as well as stderr and inject endpoint/token/SQL canaries on open and mid-query failures. Keep local SQL diagnostics/fallbacks unchanged. If ENH-3668 is revived, its strict mode must respect explicit best-effort precedence.

### SFT pipeline failure routing (owned here)

In `scripts/little_loops/loops/sft-corpus.yaml`, remove stage's `2>/dev/null || touch "$OUTPUT"` masking and use `--reader auto`. Explicitly propagate the `ll-messages` status (`... > "$OUTPUT" || exit $?`) before the final pathname echo; otherwise that echo returns success and `on_error` never runs. Check other fallible shell commands too, while preserving the optional absent harvest sentinel. On success emit exactly one pathname on stdout, with notices on stderr. A partial run-private raw file may remain on failure but must never be consumed. Add `on_error: corpus_failed` to stage and enrich, with `terminal: true, failure: true`. Remote JSONL/passthrough succeeds with its note; unexpected staging/parsing/serialization errors terminate. Publish `enriched.jsonl` with a unique temporary sibling and atomic replace only after success; clean failed temps and retain the previous final. Test the actual packaged YAML states and FSM failure route (not copied shell snippets), including failure after one record. No failure reaches filter/publish or the harvest success sentinel. ENH-3685 reuses this wiring if revived.

### Notice channel

Degrade notice = one fixed `note:` line on stderr at the human CLI/skill/state boundary, before bypassing the DB, only under a remote target. Libraries such as `generate_from_completed` and `extract_conversation_turns` select their fallback without printing; their CLI callers own the note. Automatic/library callers keep their existing output contract. CT-0 additionally returns parseable JSON with `verdict: skipped` and a fixed reason, then branches before "no candidates". Remove its `2>/dev/null` so the note survives. For packaged stage/enrich, each state owns its designated note; a library warning must not duplicate a deliberate fallback notice. No endpoint/token/SQL or exception text appears in either channel.

### Docs wording

Docs and messages say remote readers are "not supported with a remote backend" where refused; they do not promise a follow-up (remote read serving, ENH-3668/3684/3685, is deferred indefinitely).

## Motivation

A refusal from the boundary helper (ENH-3657) only covers CLIs that pre-resolve. Without the central guard, hand-built absolute paths still create a shadow DB under remote config, and without the re-raise a guard refusal reads as empty data. `ll-harness` can serve remotely at near-zero cost and the degrade sites keep local-only fallbacks working.

## Scope Boundaries

- **In scope**: central guard/re-raise, narrow explicit-local provenance in reached helpers, importer audit/AST test, shared missing read-stamp policy, eager read-mode preparation on the same client and default-off stub permission mode, harness advisory/required-lookups dispositions, safe remote warnings, the degrade sites and boundary-owned notes, CT-0/mirrors, packaged SFT failure routing, and support-table rows.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657), hand-built paths (ENH-3658), `context-monitor.sh`, prepatch budget (ENH-3682), remote read serving for `ll-history` subcommands and MCP (ENH-3668/3684/3685, deferred), writers/startup paths (BUG-3652, done).

## Proposed Solution

1. **Seams** (`session_store/backend.py`, `history_reader/_base.py`): guard in `open_history_readonly`, `_connect_readonly` re-raise + docstring, read-mode remote ensure (verify against `HranaStub` first, since `ll-harness` serve depends on it). Audit non-CLI absolute-path callers.
2. **Serve** `cli/harness.py` x5 (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`): drop the pre-resolve, pass the relative default; confirm rows round-trip through `HranaStub` and no local `.ll/history.db` is created.
3. **Degrade** sites: `history summary`, `decisions generate`, `extract_conversation_turns(reader="auto")`, CT-0, packaged `sft-corpus` stage/enrich. Add failure routing and atomic enrichment publication here; remote passthrough is intentional success, unrelated errors are terminal failures.
4. **Skills, mirrors, docs**: CT-0 only in `skills/improve-claude-md/SKILL.md` (344 lines, cap 500; keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`); then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and `test_improve_claude_md_skill.py`. Support-table rows in `docs/reference/CONFIGURATION.md` "Remote history backend" (ENH-3657 creates the table), `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md:~758`. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths.
5. **Hazard gate**: if ENH-3658 lands first, remove its temporary CT-0 allowlist entry here. If this issue lands first, ENH-3658 adds no CT-0 exception. The context-monitor exception remains intentional; neither order adds a functional dependency.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (`open_history_readonly`), `session_store/remote_schema.py` (missing read stamp policy), `history_reader/_base.py` (`_connect_readonly`), `history_reader/harness.py` (mid-query catches), `cli/harness.py` (5 sites), `cli/history.py` (`summary` degrade), `decisions.py` / `cli/decisions.py` (library fallback / CLI note), `user_messages.py` / `cli/messages.py` (library fallback / CLI note), `cli/session.py` / `cli/history_context.py` and only reached reader helpers that must retain explicit local provenance, `skills/improve-claude-md/SKILL.md`, `scripts/little_loops/loops/sft-corpus.yaml`, `scripts/tests/hrana_stub.py` (read-only permission mode).
- Anchors drift: re-grep every `resolve_history_db(` site before editing (`decisions.py:596`, `user_messages.py` ~`:1227`).
- `issue_history/evolution._open_db` (sqlite-only choke point) changes only if made remote-aware.

### Loop / digest invariants
- `.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps `"No history.db found"`; keep verbatim and add remote notices as separate stderr lines.
- `ll-messages` default-`auto` callers need a regression test because `extract_conversation_turns` currently reaches the remote pre-resolve.

### Tests
- Guard fires only for the default-shaped case; typed `LocalTarget` for an explicit absolute `<root>/.ll/history.db`, `--db`, `LL_HISTORY_DB`, and non-remote first-use creation are carve-outs.
- `_connect_readonly` re-raises `HistoryRemoteRefused` and does not also `warn_once`; other `HistoryUnsupported` still maps to `None`.
- `ll-harness` serve returns stub data and creates **no** local `.ll/history.db`; read-only-token serve uses an actual permission-rejecting stub; behind and ahead stamped stores are served.
- Degrade tests keep stdout unchanged with exactly one `note:` line and no token; default-`auto` JSONL fallback; `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`); `"No history.db found"` invariant (`test_bug_3216_telemetry_digest_invocations.py`).
- Use the hoisted `remote` fixture (ENH-3677; must `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`); test `main_harness([...])`, not `cmd_*`.
- Keep green: `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites and the reader seam, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_cli_decisions.py`/`test_decisions.py` DB-first local branch, `test_cli_messages.py`, `test_evolution_triggers.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (support-table rows), `docs/reference/CLI.md`, `docs/reference/API.md` (`extract_conversation_turns` relationship paragraph; "SQLite-only prerequisite" `Backend chokepoint` wording), `docs/ARCHITECTURE.md:~758`, `docs/guides/HISTORY_SESSION_GUIDE.md`. Must not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Program Design

### Types

- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)`, and new `HistoryRemoteRefused(HistoryUnsupported)`, in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.
- `LocalTarget` in `little_loops.session_store.targets` carries an explicit local override through only the reached helpers affected by the guard. Default remote reads continue to use relative `DEFAULT_DB_PATH`; broad `RemoteTarget` reader propagation is deferred.

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False)` — gains the default-shaped-local-path guard (raises `HistoryRemoteRefused`) and a read-mode ensure for `RemoteTarget`.
- `_connect_readonly(db_path: Path | LocalTarget) -> sqlite3.Connection | None` — preserves explicit local provenance; returns `None` on ordinary failure and re-raises `HistoryRemoteRefused` unless ENH-3682's explicit best-effort mode is selected.
- `generate_from_completed(config: BRConfig) -> int` — degrade site in `little_loops.decisions`; local branch stays DB-first.

### Call Path

- `history_reader._connect_readonly` -> `open_history_readonly` -> default-shaped-path guard -> `HistoryRemoteRefused` re-raised -> CLI boundary helper (ENH-3657) or MCP `is_error`.
- `cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade, remote only).
- `main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade).
- `main_harness` -> relative `DEFAULT_DB_PATH` -> `LibsqlBackend` read-mode check -> rows.

### Decision Rules

- Serve at the designated `ll-harness` boundary using the relative default. Refuse a plain absolute default-shaped path under remote config; typed explicit `LocalTarget`, applicable `--db`, and `LL_HISTORY_DB` remain local carve-outs.
- Escape hatch: `LL_HISTORY_DB` or an applicable explicit local `--db` retains local intent. `ll-session` and `ll-history-context` also define `--db`; do not confuse their omitted relative defaults with explicit absolute local inputs. `ll-ctx-stats` uses the separate strict opener. ENH-3658 owns artifact dashboard overrides.
- Catch class for the guard is `HistoryRemoteRefused`; the notice channel is one CLI `note:` line; `"No history.db found"` stays verbatim for local-missing.
- Unreachable endpoint gives advisory empty output plus a safe warning, or a required retry/baseline validation refusal through its existing exit path; it never authorizes a retry or synthesizes a baseline.
- Stamped remote schema: exact, behind and ahead are all served (`check_access(write=False)`).

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture) and ENH-3657 (boundary helper, so a guard refusal is never a traceback) landed.

1. Seams: guard/re-raise, shared read-stamp predicate, eager same-client read preparation and explicit-local provenance. Verify open-failure timing and permission/request counts against `HranaStub`, then complete the caller audit and recorded per-module verdicts. Coordinate backend/stub edits with external ENH-3720 while preserving its optional deadline and defaults.
2. `cli/harness.py` serve.
3. Degrade sites, CT-0 skill change, `sft-corpus.yaml`.
4. Skills mirrors (`ll-adapt`), docs, remove the CT-0 allowlist entry from ENH-3658's hazard gate.
5. Tests per the Integration Map. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium-Large - guard, re-raise, 17-external/15-internal-module audit, serve and degrade sites, a skill mirror pass and a loop fix.
- **Risk**: Medium-High - the reader contract changes from "`None` on any failure" to "raise on a guard refusal" across ~67 callers.
- **Breaking Change**: No (local behavior unchanged).

## Acceptance Criteria

- [ ] `HistoryRemoteRefused` exists; `_connect_readonly` re-raises it (documented contract) while other `HistoryUnsupported` from remote ensure still map to `None`; ENH-3682's regression test passes on either merge order.
- [ ] The central guard fires only for a remote provider + default-shaped absolute local path with no explicit local intent/`LL_HISTORY_DB`, classifies remote from the path-derived root, and default remote reads create no shadow `.ll/history.db`. Explicit `LocalTarget` stays local through the reached helper chain, including an absolute default-shaped `--db`; local override content is actually read.
- [ ] Re-run and reconcile the recorded 17-external/15-internal importer inventory, covering lazy imports and reached helpers; the AST gate catches new unaudited importers/default-path absolute construction with reasoned exceptions, and dynamic tests assert no shadow DB.
- [ ] `ll-harness` serve sites return stub data, create no local `.ll/history.db`, serve an exact, behind or ahead stamped schema and a read-only token (`check_access(write=False)`, tested with a permission-rejecting stub); no ahead-store refusal is added.
- [ ] Degrade CLI/state sites (`history summary`, `decisions generate`, `--reader auto`, `sft-corpus` `enrich`) preserve data stdout, exit 0 for intentional fallbacks and emit their single safe stderr note only under remote config. Direct/automatic library fallbacks add no stdout/stderr notice. CT-0 emits parseable `verdict: skipped` plus its note and never reports "no candidates" for a remote skip; no duplicate library warning.
- [ ] CT-0 uses `resolve_history_store` and branches on `RemoteTarget`; no bare `resolve_history_db()` remains in `skills/`; mirrors regenerated.
- [ ] Non-strict `ll-harness` open/mid-query failures preserve advisory fallbacks and grading; required retry/baseline/compare/pin lookups fail closed with existing validation exits and zero subject invocations/new candidate rows. Actual remote prior attempts/baselines serve successfully. Logs/stderr contain no traceback or endpoint/token/SQL canaries; local failures remain unchanged.
- [ ] Read-mode access rejects a missing migrated-store stamp with ordinary `HistoryUnsupported`, including cold and cached states; version 0 remains a fallback and exact/behind/ahead stamped stores serve. A permission-rejecting stub proves no reader DDL/write is sent; default-off fault/permission controls compose with ENH-3720.
- [ ] Ordinary remote `ensure=True` access/auth/stamp verification still fails during opening, so `_connect_readonly` returns `None` to existing query callers. Preparation and the data query use the same client, with no duplicate cold verification, and failed preparation closes it; ordinary strict `connect_readonly` defaults are unchanged.
- [ ] Tests execute packaged SFT stage/enrich actions and the FSM route: stage auto fallback works under remote config, a failing `ll-messages` status cannot be overwritten by its pathname echo, and stage/enrich failures reach terminal failure without filter/publish/success sentinel. Success stdout contains only the captured pathname. Remote passthrough succeeds with its note; failed partial enrichment retains the previous final file.
- [ ] `"No history.db found"` is unchanged (invariant test).
- [ ] If ENH-3658's temporary CT-0 allowlist exists, remove it here; if the seam lands first, no CT-0 exception is introduced later. Both orders leave the completed gate without that stale exception.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3657 (3657a, refuse boundary; `blocked_by`, lands first), ENH-3677 (shared `remote` fixture; `blocked_by`), ENH-3658 (hazard gate allowlist entry removed here), ENH-3682 (prepatch budget; independent), ENH-3668 (deferred strict-read infra), BUG-3652 (done), FEAT-3535 (remote libSQL backend).

---

## Scope Boundary

**Ownership:** this issue owns `ll-harness` exit-code wording: remote serving adds no generic backend refusal, while its existing fail-closed retry/baseline validation codes remain. ENH-3657's epilog/CLI.md exit notes cover `ll-ctx-stats` and `ll-history` only.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Updated 2026-10-04 after the code-backed epic review._

Re-run `/ll:confidence-check` after ENH-3677/3657 land. The revised stamp-policy, eager verification timing, explicit-local provenance and harness/SFT obligations need implementation evidence; this review and the Opus recommendation are not passing readiness checks. Coordinate shared backend/stub edits with ENH-3720 without adding a functional dependency.


## Session Log
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.74) - 2026-10-04 - stamp enforcement, harness control-flow, safe diagnostics, local provenance and actual SFT failure routing amended; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:05 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
