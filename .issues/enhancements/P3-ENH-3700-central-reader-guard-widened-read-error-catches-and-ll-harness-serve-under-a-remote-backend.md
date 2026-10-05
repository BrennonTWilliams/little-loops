---
id: ENH-3700
type: ENH
title: Central reader guard, widened read-error catches and ll-harness serve under a
  remote backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
blocked_by:
- ENH-3657
- ENH-3677
- ENH-3682
blocks:
- ENH-3668
- ENH-3684
- ENH-3685
relates_to:
- ENH-3658
- BUG-3652
- ENH-3728
- ENH-3729
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3700: Central reader guard, widened read-error catches and ll-harness serve under a remote backend

> **Split from ENH-3657 on 2026-10-02, slimmed again on 2026-10-04.** ENH-3657 owns the refuse boundary. The 2026-10-04 Opus review (`claude-opus-5-5`, confidence 0.78) removed three pieces of this issue's original design: (1) the degrade sites and `sft-corpus` routing moved to **ENH-3728** and **ENH-3729** (they need only the `HistoryUnsupported` the existing pre-resolve already raises, not this seam); (2) the guard **no longer re-raises** through `_connect_readonly` (it maps to `None` plus one fixed-text `remote_telemetry.warn_once`), so there is no contract change across ~67 callers; (3) the read-mode ensure / "serve behind and ahead stores" decision, the shared missing-stamp tightening, the `HranaStub` read-only permission mode and eager same-client verification are **dropped**: the shared `ensure=True` path keeps write-mode `check_access`. Pre-slimming text is in git history.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), a reader that builds the default `<root>/.ll/history.db` path can `ensure_schema`-create an empty shadow local database, and ~65 `history_reader` sites catch only `sqlite3.Error` while a remote query failure raises a `HistoryError`. This issue adds a central guard at the reader seam (no shadow DB, no re-raise), widens the read-error catches so remote failures degrade instead of tracebacking, and lets `ll-harness` serve from the remote store through the unchanged `ensure=True` path.

## Current Behavior

**Load-bearing fact.** `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), so dropping a pre-resolve does not make an absolute-path site read remotely: `open_history_readonly(..., ensure=True)` would create an empty shadow `.ll/history.db`. `cli/harness.py` can serve by retaining relative `DEFAULT_DB_PATH`; existing relative-default session/context readers remain supported.

**Mid-query hole (verified 2026-10-04).** `LibsqlConnection` raises `HistoryUnavailable` / `HistoryOperationError` (`HistoryError`, not `sqlite3.Error`). `history_reader` has ~65 `except sqlite3.Error` sites and only ~4 that also catch `HistoryError`, so a remote mid-query failure (dead endpoint after open, missing column) escapes as a traceback in those readers. `_connect_readonly` (`history_reader/_base.py`) also embeds raw `{exc}` text in its remote `remote_telemetry.warn_once`; ENH-3682 sanitizes that line (this issue is `blocked_by` it).

**Open path stays as is.** `open_history_readonly(ensure=True)` runs `ensure_schema` -> `check_access(write=True)` (metadata SELECTs only), which cleanly refuses a behind/ahead/unstamped store with a message naming `ll-session migrate`; `_connect_readonly` maps that `HistoryUnsupported` to `None` plus one `remote_telemetry.warn_once`. Serving behind/ahead stores through this shared path was rejected on 2026-10-04: queries against a behind schema would surface the mid-query hole above in ~65 sites, replacing today's clean refusal. The process-shared `_VERIFIED` cache already prevents a duplicate cold verification between `ensure_schema` and the first query.

`ll-harness` has 5 pre-resolve sites in `cli/harness.py` (`resolve_history_db(DEFAULT_DB_PATH)` at `_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`) that raise `HistoryBackendNotLocal` under remote.

## Expected Behavior

### Verdicts

| Site | Under remote | Notes |
|---|---|---|
| `ll-harness` x5 sites | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend` via the unchanged `ensure=True` path; an exact-version stamped store is served; a behind/ahead/unstamped store is refused cleanly (existing policy); advisory reads degrade, required retry/baseline lookups fail closed through existing validation paths |
| default-shaped absolute path into the reader seam | **guard** | `HistoryRemoteRefused` -> `_connect_readonly` returns `None` plus one fixed-text `remote_telemetry.warn_once`; no shadow DB |
| remote mid-query failure in any `history_reader` reader | **degrade** to the reader's empty/None result | widened catches; one fixed-text `remote_telemetry.warn_once`, never `str(exc)` |

Degrade sites (`history summary`, `decisions generate`, `reader=auto`, CT-0, `sft-corpus`) are ENH-3728/ENH-3729.

### Central guard (fix the cause once, no re-raise)

In `session_store.backend.open_history_readonly` (the `ensure=True` reader opener): when the configured provider is remote **and** the resolved target is a *default-shaped* absolute local path (`<root>/.ll/history.db`, `LL_HISTORY_DB` unset, no explicit `--db`), raise `HistoryRemoteRefused` (a subclass of `HistoryUnsupported`) instead of `ensure_schema`-creating a shadow DB. It fires only in that case and respects the BUG-3181 absolute-path contract, an explicit `--db` (wrap it in `LocalTarget` at the CLI), `LL_HISTORY_DB`, and first-use local creation when the provider is not remote. Classify "remote" from the root derived from the path (`<root>/.ll/...`), not the cwd, so an MCP call with a foreign cwd is not misclassified.

`_connect_readonly` keeps its single `except HistoryError` handler: `HistoryRemoteRefused` returns `None` with one fixed-text, endpoint-free `remote_telemetry.warn_once` (e.g. key `history-reader-guard`), no traceback. No contract change; update the docstring only to name the guard case.

**Decision reversed 2026-10-04 (Opus):** the earlier plan re-raised `HistoryRemoteRefused` above the `except HistoryError` handler (rejecting a `None` + `remote_telemetry.warn_once` seam as "silent-empty"). Reversed because the re-raise changes the failure contract for ~67 callers and forces the exhaustive audit; the user-facing refusal boundary is ENH-3657's and every reachable default-path caller is covered by the AST gate below. *Dissent:* where stderr is discarded (automation) `None` + `remote_telemetry.warn_once` is effectively silent-empty. If a remote user hits that, revisit as a narrow re-raise for the specific callers.

CLI provenance must survive the reached helper chain: where an explicit local `--db` reaches this ensure-reader seam, retain `LocalTarget` rather than stripping it with `Path(...)` before the guard. Widen only the affected helper annotations and filesystem probes. Audit `ll-session` and `ll-history-context` (both define `--db`) with omitted defaults and explicit absolute default-shaped local paths; preserve their relative-default remote resolution. `ll-ctx-stats --db` uses the separate strict opener and is unaffected. Snapshot CLI provenance belongs to ENH-3658.

### Widened read-error catches

Add `_READ_ERRORS = (sqlite3.Error, HistoryError)` in `history_reader/_base.py` and mechanically replace the `except sqlite3.Error` sites in `history_reader` (keep reasoned exceptions). Remote failures log through a fixed-text `remote_telemetry.warn_once` with a stable operation/category; local SQL diagnostics and fallbacks stay unchanged. Do **not** convert `HistoryError` into `sqlite3.OperationalError`. Add an AST gate: no bare `except sqlite3.Error` in `history_reader` without a recorded reason. Test with a representative reader against `HranaStub` (`fail_next` / killed endpoint after open) returning its empty result with no traceback.

### Importer AST gate (replaces the exhaustive audit)

Instead of a per-importer disposition audit, add an AST regression gate for (a) default-path absolute construction (`<root>/.ll/history.db`-shaped `Path(...)` reaching `open_history_readonly`/`_connect_readonly`) and (b) unaudited new importers of `history_reader`, with reasoned exceptions for explicit local targets, connection-only/pure helpers and remote-gated paths. Seed from the 2026-10-02 inventory (re-run at implementation; it includes function-local imports): external importers `cli/ctx_stats.py`, `cli/harness.py`, `cli/history.py`, `cli/history_context.py`, `cli/logs.py`, `cli/loop/evidence.py`, `cli/session.py`, `fsm/executor.py`, `hooks/session_start.py` (absolute digest path already gated by `not _remote_store`), `issue_history/{agent_quality,collisions,evolution,rework}.py`, `mcp_server/tools.py`, `session_store/queries.py` (connection-only), `user_messages.py`, `work_verification.py` (relative-default prepatch readers). Reader-internal: `_base`, `__init__`, `context`, `digest`, `events`, `formatting`, `harness`, `hooks`, `models`, `runs`, `search`, `sessions`, `subagents`, `summary_dag`, `usage`. Two functions are named `_connect_readonly`: `history_reader/_base.py` (the `ensure=True` opener) and `session_store/queries.py` (a raw `mode=ro` URI opener, unaffected); name the module explicitly in the gate and tests. Dynamic tests assert no shadow DB in the default remote cases. Do not equate every `Path(...)` call with a hazard.

### Harness advisory reads and required validation reads

`_read_target_history` and DSL `admissions_by_reason` are advisory: open/query failure yields the existing absent rate/breakdown and does not alter grading or exit codes (the DSL admissions result is only formatted after execution and does not gate/deduplicate tasks, verified in `cmd_dsl` 2026-10-04). `_retry_gate`, `_resolve_baseline_of`, and `read_baseline` feeding compare/pin gates are required control-flow lookups: failure must never admit a retry or invent a baseline. Preserve the existing missing-attempt/baseline validation messages and exit paths (including exit 1 where already used), with a safe warning for unavailable history and zero subject invocations/new candidate rows for the rejected candidate. Do not infer a successful empty query from a caught error. A behind/ahead/unstamped remote store follows the same dispositions (advisory degrade, required fail closed). Remote configuration itself adds no generic refusal or new harness exit code; this issue owns `ll-harness` exit-code wording.

For remote failures use `remote_telemetry.warn_once` with a stable operation/category and fixed text, never `str(exc)` or `exc_info=True`. Capture logging as well as stderr and inject endpoint/token/SQL canaries on open and mid-query failures (the generic `_connect_readonly` `{exc}` line is sanitized by ENH-3682, a prerequisite).

### Docs wording

Docs and messages say remote readers are "not supported with a remote backend" where refused; they do not promise a follow-up (ENH-3668/3684/3685 are deferred indefinitely). Add the `ll-harness` serve row and the mid-query degrade note to the single support table in `docs/reference/CONFIGURATION.md` (ENH-3657 creates it; merge rows).

## Motivation

A refusal from the boundary helper (ENH-3657) only covers CLIs that pre-resolve. Without the central guard, hand-built absolute paths still create a shadow DB under remote config; without the widened catches, a remote failure after a successful open tracebacks in ~65 readers. `ll-harness` can serve remotely at near-zero cost.

## Scope Boundaries

- **In scope**: central guard (no re-raise), `_connect_readonly` guard mapping, narrow explicit-local provenance in reached helpers, widened read-error catches + gate, importer AST gate, `ll-harness` x5 serve and its advisory/required dispositions, safe remote warnings, support-table rows.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657); degrade sites, CT-0 and mirrors (ENH-3728); `sft-corpus` routing (ENH-3729); hand-built paths (ENH-3658); `context-monitor.sh`; prepatch budget and `_connect_readonly` message sanitization (ENH-3682); **read-mode ensure, serving behind/ahead stores, shared missing-stamp tightening and the `HranaStub` read-only permission mode** (dropped 2026-10-04; revisit as an explicit opt-in only if a remote user needs a behind store served, and with ENH-3668 if revived); remote read serving for `ll-history` subcommands and MCP (ENH-3668/3684/3685, deferred); writers/startup paths (BUG-3652, done).

## Proposed Solution

1. **Seam** (`session_store/backend.py`, `history_reader/_base.py`): guard in `open_history_readonly`; `_connect_readonly` guard mapping + fixed-text warning; `_READ_ERRORS` and the mechanical catch replacement; explicit-local provenance in reached helpers.
2. **Serve** `cli/harness.py` x5 (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`): drop the pre-resolve, pass the relative default; confirm rows round-trip through `HranaStub` and no local `.ll/history.db` is created; widen the reached harness handlers to `(sqlite3.Error, HistoryError)`.
3. **Gates**: AST gate for default-path absolute construction/unaudited importers; AST gate for bare `except sqlite3.Error` in `history_reader`.
4. **Docs**: support-table rows in `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, `docs/reference/API.md` ("SQLite-only prerequisite" `Backend chokepoint` wording), `docs/ARCHITECTURE.md:~758`, `docs/guides/HISTORY_SESSION_GUIDE.md`. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths; do not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (`open_history_readonly`, `HistoryRemoteRefused`), `history_reader/_base.py` (`_connect_readonly`, `_READ_ERRORS`) and the `history_reader/*` modules containing the `except sqlite3.Error` sites, `history_reader/harness.py`, `cli/harness.py` (5 sites), `cli/session.py` / `cli/history_context.py` and only reached helpers that must retain explicit local provenance.
- Anchors drift: re-grep every `resolve_history_db(` site before editing.
- `issue_history/evolution._open_db` (sqlite-only choke point) changes only if made remote-aware.

### Tests
- Guard fires only for the default-shaped case; typed `LocalTarget` for an explicit absolute `<root>/.ll/history.db`, `--db`, `LL_HISTORY_DB`, and non-remote first-use creation are carve-outs.
- `_connect_readonly` returns `None` with exactly one fixed-text `remote_telemetry.warn_once` for the guard (no traceback, no canaries); other `HistoryUnsupported` still maps to `None`; a behind-schema stub store yields the clean migrate-hint refusal, not a traceback.
- Mid-query remote failure in a representative reader returns its empty result without raising.
- `ll-harness` serve returns stub data and creates **no** local `.ll/history.db`; failures: advisory reads degrade, required retry/baseline lookups fail closed with zero subject invocations/new candidate rows.
- Use the hoisted `remote` fixture (ENH-3677; must `delenv("LL_HISTORY_DB")`); test `main_harness([...])`, not `cmd_*`.
- Keep green: `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites and the reader seam, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_evolution_triggers.py`.

## Program Design

### Types
- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)`, and new `HistoryRemoteRefused(HistoryUnsupported)`, in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.
- `LocalTarget` in `little_loops.session_store.targets` carries an explicit local override through only the reached helpers affected by the guard.
- `_READ_ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error, HistoryError)` in `little_loops.history_reader._base`.

### Signatures
- `open_history_readonly(target=None, *, ensure: bool = False)` — gains the default-shaped-local-path guard (raises `HistoryRemoteRefused`); remote `ensure=True` behavior otherwise unchanged (write-mode `check_access`).
- `_connect_readonly(db_path: Path | LocalTarget) -> sqlite3.Connection | None` — preserves explicit local provenance; returns `None` on any `HistoryError` including the guard's, with a fixed-text `remote_telemetry.warn_once` for remote cases.

### Call Path
- `history_reader._connect_readonly` -> `open_history_readonly` -> default-shaped-path guard -> `HistoryRemoteRefused` -> `None` + one `remote_telemetry.warn_once`.
- `main_harness` -> relative `DEFAULT_DB_PATH` -> `LibsqlBackend` (`ensure_schema` write-mode check) -> rows; failure -> advisory empty or required fail-closed.

### Decision Rules
- Serve at the designated `ll-harness` boundary using the relative default. Refuse a plain absolute default-shaped path under remote config; typed explicit `LocalTarget`, applicable `--db`, and `LL_HISTORY_DB` remain local carve-outs.
- Catch class for the guard is `HistoryRemoteRefused`; `"No history.db found"` stays verbatim for local-missing.
- Unreachable endpoint gives advisory empty output plus a safe warning, or a required retry/baseline validation refusal through its existing exit path; it never authorizes a retry or synthesizes a baseline.
- A behind/ahead/unstamped remote store is refused at open with the existing clean message; it is not served.

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture), ENH-3657 (boundary helper and support table) and ENH-3682 (sanitized `_connect_readonly` warning and best-effort seam) landed. ENH-3728 / ENH-3729 are independent of this issue.

1. Seam: guard, `_connect_readonly` mapping, `_READ_ERRORS` replacement, explicit-local provenance; verify against `HranaStub` (including a behind-schema store).
2. `cli/harness.py` serve + advisory/required dispositions.
3. AST gates; docs and support-table rows.
4. Tests per the Integration Map. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium - guard, one mechanical catch replacement, harness serve, two gates.
- **Risk**: Medium - the catch widening touches ~65 sites (mechanical, gated); no reader-contract change.
- **Breaking Change**: No (local behavior unchanged).

## Acceptance Criteria

- [ ] `HistoryRemoteRefused` exists; `_connect_readonly` returns `None` with one fixed-text `remote_telemetry.warn_once` for it (no re-raise, no traceback, no canaries); other `HistoryUnsupported` still maps to `None`.
- [ ] The guard fires only for a remote provider + default-shaped absolute local path with no explicit local intent/`LL_HISTORY_DB`, classifies remote from the path-derived root, and default remote reads create no shadow `.ll/history.db`. Explicit `LocalTarget` stays local through the reached helper chain, including an absolute default-shaped `--db`; local override content is actually read.
- [ ] The importer AST gate (default-path absolute construction + unaudited importers, reasoned exceptions) passes against the re-run inventory, and dynamic tests assert no shadow DB.
- [ ] `history_reader` has no bare `except sqlite3.Error` without a recorded reason (AST gate); a remote mid-query failure in a representative reader returns its empty result with a fixed-text warning and no traceback; local diagnostics unchanged.
- [ ] A behind/ahead/unstamped remote store still yields the clean migrate/upgrade refusal at open (`None` + one warning), not a traceback; no reader-mode ensure, stamp-policy change or stub permission mode is introduced.
- [ ] `ll-harness` serve sites return stub data for an exact-version stamped store and create no local `.ll/history.db`.
- [ ] Non-strict `ll-harness` open/mid-query failures preserve advisory fallbacks and grading; required retry/baseline/compare/pin lookups fail closed with existing validation exits and zero subject invocations/new candidate rows. Actual remote prior attempts/baselines serve successfully. Logs/stderr contain no traceback or endpoint/token/SQL canaries; local failures unchanged.
- [ ] The support table has the `ll-harness` serve and mid-query degrade rows; no message promises deferred remote serving.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3657 (refuse boundary; `blocked_by`), ENH-3677 (shared fixture; `blocked_by`), ENH-3682 (sanitized warning + best-effort seam; `blocked_by`), ENH-3728 (degrade verdicts) and ENH-3729 (SFT routing) (split-out siblings), ENH-3658 (hand-built paths), ENH-3668/3684/3685 (deferred), BUG-3652 (done), FEAT-3535 (remote libSQL backend).

---

## Scope Boundary

**Ownership:** this issue owns `ll-harness` exit-code wording: remote serving adds no generic backend refusal, while its existing fail-closed retry/baseline validation codes remain. ENH-3657's epilog and `CLI.md` exit notes cover `ll-ctx-stats` and `ll-history` only.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Confidence Check Notes

_Updated 2026-10-04 after the second EPIC-3693 review._

Scope narrowed and re-planned; re-run `/ll:confidence-check` after ENH-3677, ENH-3657 and ENH-3682 land. The guard-without-re-raise, catch-widening and harness-serve obligations need implementation evidence; the Opus recommendation is not a passing readiness check.

## Session Log
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.78) - 2026-10-04 - split degrade sites (ENH-3728) and SFT routing (ENH-3729) out; re-raise, read-mode ensure/serve-behind, stamp tightening and stub permission mode dropped; widened catches + AST gates added; implementation not performed
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.74) - 2026-10-04 - stamp enforcement, harness control-flow, safe diagnostics, local provenance and actual SFT failure routing amended; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:05 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
