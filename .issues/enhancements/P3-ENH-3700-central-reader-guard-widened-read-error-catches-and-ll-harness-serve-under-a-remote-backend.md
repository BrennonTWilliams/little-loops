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

> **Current scope (reviewed 2026-10-05):** ENH-3657 owns refusal boundaries; ENH-3728 owns degrade sites; ENH-3729 owns SFT failure routing. The guard still returns `None` plus one safe warning for default/advisory callers. Required harness lookups now have a **per-call opt-in** failure channel; this is not the previously dropped universal re-raise or an ambient strict-reader mode. Read-mode ensure/serve-behind, shared stamp-policy changes and a stub permission mode remain dropped. ENH-3682 owns best-effort same-client verification. Earlier scope is in git history.

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), a reader that builds the default `<root>/.ll/history.db` path can create an empty shadow local database, while SQLite-only catches let remote query errors escape. Add the central guard, widen advisory catches and let `ll-harness` serve an exact-version stamped store. Required harness lookups distinguish unavailable history from a successful empty result so measurement, compare, retry and pin decisions cannot proceed on an outage.

## Current Behavior

**Load-bearing fact.** `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), so dropping a pre-resolve does not make an absolute-path site read remotely: `open_history_readonly(..., ensure=True)` would create an empty shadow `.ll/history.db`. `cli/harness.py` can serve by retaining relative `DEFAULT_DB_PATH`; existing relative-default session/context readers remain supported.

**Explicit-local setup hole (verified 2026-10-05; fix moved to ENH-3657 in review #4).** `SqliteBackend.ensure_schema` calls `schema.ensure_db(_local_path(target, ...))`, dropping the selected `LocalTarget`. `schema.ensure_db` then calls `_seam_target(..., reresolve_absolute=True)` and can resolve that plain default-shaped Path against the ambient remote configuration. A temporary-project probe of `open_history_readonly(LocalTarget(<root>/.ll/history.db), ensure=True)` returned `"typed_local_ensure_reader_error": "HistoryBackendNotLocal"` with `"error_operation": "ensure_db"`, despite the local file already existing. ENH-3657 now supplies the narrow setup fix so its own selected-root tests can pass before this dependent issue; consume it here. <!-- ll-evidence-ok: the quoted JSON fields are output of this issue's own 2026-10-05 temp-project probe; ENH-3657 is cited only as the issue the fix moved to -->

**Mid-query hole (verified 2026-10-04).** `LibsqlConnection` raises `HistoryUnavailable` / `HistoryOperationError` (`HistoryError`, not `sqlite3.Error`). `history_reader` has ~65 `except sqlite3.Error` sites and only ~4 that also catch `HistoryError`, so a remote mid-query failure (dead endpoint after open, missing column) escapes as a traceback in those readers. `_connect_readonly` (`history_reader/_base.py`) also embeds raw `{exc}` text in its remote `remote_telemetry.warn_once`; ENH-3682 sanitizes that line (this issue is `blocked_by` it).

**Open path stays as is.** `open_history_readonly(ensure=True)` runs `ensure_schema` -> `check_access(write=True)` (metadata SELECTs only), which cleanly refuses a behind/ahead/unstamped store with a message naming `ll-session migrate`; `_connect_readonly` maps that `HistoryUnsupported` to `None` plus one `remote_telemetry.warn_once`. Serving behind/ahead stores through this shared path was rejected on 2026-10-04: queries against a behind schema would surface the mid-query hole above in ~65 sites, replacing today's clean refusal. The process-shared `_VERIFIED` cache already prevents a duplicate cold verification between `ensure_schema` and the first query.

`ll-harness` has 5 pre-resolve sites in `cli/harness.py` (`resolve_history_db(DEFAULT_DB_PATH)` at `_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`) that raise `HistoryBackendNotLocal` under remote.

## Expected Behavior

### Verdicts

| Site | Under remote | Notes |
|---|---|---|
| `ll-harness` x5 sites | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend` via the unchanged `ensure=True` path; an exact-version stamped store is served; a behind/ahead/unstamped store is refused cleanly (existing policy); advisory reads degrade, required retry/baseline lookups fail closed through existing validation paths |
| default-shaped absolute path into the reader seam | **guard** | `HistoryRemoteRefused` -> `_connect_readonly` returns `None` plus one fixed-text `remote_telemetry.warn_once`; no shadow DB |
| remote mid-query failure in an advisory `history_reader` call | **degrade** to the reader's empty/None result | widened catches; one fixed-text warning, never `str(exc)`; required harness calls use the opt-in failure channel |

Degrade sites (`history summary`, `decisions generate`, `reader=auto`, CT-0, `sft-corpus`) are ENH-3728/ENH-3729.

### Central guard (default/advisory contract retained)

In `session_store.backend.open_history_readonly` (the `ensure=True` reader opener): when the configured provider is remote **and** the original argument is a plain *default-shaped* absolute local path (`<root>/.ll/history.db`) without selected local intent, raise `HistoryRemoteRefused` (a subclass of `HistoryUnsupported`) instead of reading/creating a shadow DB. An explicit `--db` wrapped in `LocalTarget`, an actually selected `LL_HISTORY_DB` target, and first-use local creation when the provider is not remote remain supported. Classify "remote" from the root derived from the path (`<root>/.ll/...`), not the cwd, so an MCP call with a foreign cwd is not misclassified.

Inspect the **original argument** for explicit `LocalTarget` intent before `_resolve_once` automatically wraps a plain absolute path; its synthesized `LocalTarget` must not accidentally exempt the hazard. Consume ENH-3657's typed-local `SqliteBackend.ensure_schema` fix, preventing a second root-less resolution. Keep the schema seam's ordinary writer/hook resolution and `_resolve_once` policy unchanged. Cover both relative and absolute default-shaped explicit CLI paths plus a local owning root under a foreign remote cwd through the actual ensure/read path.

**Env presence is not target provenance (review #4).** A temporary-project probe with a pre-existing shadow and an env override returned `"absolute_default_with_env_reads_shadow": true` and `"reads_override": false`: `_resolve_once` honors the original absolute argument, regardless of a different `LL_HISTORY_DB`. Do not disable the guard merely because that variable is nonempty. For an untyped absolute hazard, the env carve-out applies only when the original path is the actual selected env target (compare normalized absolute locations without creating/opening a DB); otherwise refuse the unrelated shadow path. Root-aware callers that already selected a local target carry `LocalTarget`. A relative default still resolves normally to the env target. Never redirect an already-absolute argument inside this opener; distinguish intentional selection from a global env flag.

For default/advisory calls, `_connect_readonly` maps `HistoryRemoteRefused` to `None` with one fixed-text, endpoint-free `remote_telemetry.warn_once` (e.g. key `history-reader-guard`), preserving the existing contract. Classify that exception **before** the ambient `_is_remote_store` fallback: the latter currently resolves without `root=` and can classify a remote owning path as local from a foreign cwd, selecting `exc_info=True`. Carry only the safe provider/owning-target classification needed by this handler, or use the opener's already-selected target; no endpoint/token is needed on the exception. The guard never reaches the local traceback logger. Required calls instead use the narrow failure channel below; best-effort still wins if both flags are present.

**Decision reversed 2026-10-04 (Opus):** the earlier plan re-raised `HistoryRemoteRefused` above the `except HistoryError` handler (rejecting a `None` + `remote_telemetry.warn_once` seam as "silent-empty"). Reversed because the re-raise changes the failure contract for ~67 callers and forces the exhaustive audit; the user-facing refusal boundary is ENH-3657's and every reachable default-path caller is covered by the AST gate below. *Dissent:* where stderr is discarded (automation) `None` + `remote_telemetry.warn_once` is effectively silent-empty. If a remote user hits that, revisit as a narrow re-raise for the specific callers.

CLI provenance must survive the reached helper chain and SQLite setup: where an explicit local `--db` reaches this ensure-reader seam, retain `LocalTarget` rather than stripping it with `Path(...)` before the guard. Widen only the affected helper annotations and filesystem probes. Audit `ll-session` and `ll-history-context` (both define `--db`) with omitted defaults and explicit relative/absolute default-shaped local paths; distinguish option presence from the parser's default value and preserve omitted-default remote resolution. `ll-ctx-stats --db` uses the separate strict opener and is unaffected. Snapshot CLI provenance belongs to ENH-3658.

### Widened read-error catches

Add `_READ_ERRORS = (sqlite3.Error, HistoryError)` in `history_reader/_base.py` and widen the SQLite-only advisory handlers (keep reasoned local-only exceptions). Include `search.search`, whose handler catches **`sqlite3.OperationalError`**, rather than only the exact `sqlite3.Error` spelling. Preserve its local invalid-FTS-query diagnostic/empty result; its remote branch uses a fixed operation/category warning without the query/exception text. Other local SQL diagnostics and advisory fallbacks stay unchanged. Do not convert `HistoryError` into `sqlite3.OperationalError`.

The AST gate recognizes SQLite `Error` **and subclasses**, import aliases, `from sqlite3 import ...` aliases and tuple handlers; each must also cover `HistoryError` or have an exemption keyed by `(module, qualified function)` with a local-only reason. Required handlers that deliberately re-raise are permitted and tested. Detector tests plant exact Error, OperationalError, module aliases, from-import aliases and tuple variants, plus accepted widened/exempt handlers. Exercise remote open and mid-query failures in a representative reader and FTS reader with sanitized logging; no string-only gate is sufficient.

Catch widening must also replace the reached remote `logger.warning(..., exc_info=True)` branches. Use one module-private diagnostic helper in `_base.py` (or the existing equivalent after prerequisites land), taking a fixed operation label plus the error and selected target/connection classification; remote errors use fixed-text `warn_once`, local SQLite errors keep their current diagnostics. Do not mechanically widen the catch while leaving traceback logging intact. ENH-3682 retains ownership of its existing opener/runs warning edits; reuse those sanitized paths when integrating.

### Importer AST gate (replaces the exhaustive audit)

Instead of a per-importer disposition audit, add an AST regression gate for (a) default-path absolute construction (`<root>/.ll/history.db`-shaped `Path(...)` reaching `open_history_readonly`/`_connect_readonly`) and (b) unaudited new importers of `history_reader`, with reasoned exceptions for explicit local targets, connection-only/pure helpers and remote-gated paths. Seed from the 2026-10-02 inventory (re-run at implementation; it includes function-local imports): external importers `cli/ctx_stats.py`, `cli/harness.py`, `cli/history.py`, `cli/history_context.py`, `cli/logs.py`, `cli/loop/evidence.py`, `cli/session.py`, `fsm/executor.py`, `hooks/session_start.py` (absolute digest path already gated by `not _remote_store`), `issue_history/{agent_quality,collisions,evolution,rework}.py`, `mcp_server/tools.py`, `session_store/queries.py` (connection-only), `user_messages.py`, `work_verification.py` (relative-default prepatch readers). Reader-internal: `_base`, `__init__`, `context`, `digest`, `events`, `formatting`, `harness`, `hooks`, `models`, `runs`, `search`, `sessions`, `subagents`, `summary_dag`, `usage`. Two functions are named `_connect_readonly`: `history_reader/_base.py` (the `ensure=True` opener) and `session_store/queries.py` (a raw `mode=ro` URI opener, unaffected); name the module explicitly in the gate and tests. Dynamic tests assert no shadow DB in the default remote cases. Do not equate every `Path(...)` call with a hazard.

The importer gate is a **syntactic tripwire**, not general interprocedural dataflow analysis. Walk `Import`/`ImportFrom` nodes at module and function scope, attribute them to stable `(module, qualified function)` ownership, and match known construction/call patterns with reasoned exemptions. Plant tests for function-local imports, aliases, new importer functions inside an existing module and known absolute-path hazards. Retain dynamic no-shadow tests; an allowlisted module alone does not prove all future functions safe.

### Harness advisory reads and required validation reads

`_read_target_history` and DSL `admissions_by_reason` remain advisory: unavailable reads yield their absent rate/breakdown and do not alter grading/exit codes. Required lookups include `_retry_gate`, `_resolve_baseline_of` and **every** `read_baseline` used by measure/compare/frozen/pin decisions. Today's `None` loses the distinction between unavailable history and absent rows: `_run_baseline_phase` runs samples after `None`, `_pin_refusal(..., force=True)` permits a pin after `None`, and compare gates validate then fetch again, allowing a failed second read to reach `_run_compare_arm`'s assertion.

Add keyword-only `required: bool = False` to `history_reader.harness.harness_event_by_id` and `baseline_for`, forwarding it through a module-private per-call argument on `_connect_readonly`. With the default, advisory behavior stays unchanged. With `required=True`, successfully queried missing/insufficient rows return `None`; an actual missing **resolved local** file also returns `None` so first-use local measurement works. Classify/guard first: an absent shadow file under remote configuration is not a missing local store. Other open/query/fetch failures raise a `HistoryError` (use an existing typed error with fixed text if wrapping SQLite failures). Do not duplicate the SQL in CLI helpers, reinterpret `HistoryError` as SQLite errors, or add an ambient strict mode. Explicit `best_effort=True` retains its never-raises precedence.

Use this flag at the named required CLI lookups and catch failures at their owning validation boundaries. Emit a fixed safe **history unavailable** reason, distinct from the existing **not found** messages, with the existing retry/recording exit 1 or compare/pin validation exit 2; no new generic backend exit code. Refuse before subjects, candidate rows or pin fragments are written. `--measure-baseline` must refuse an unavailable lookup instead of paying for a new measurement; `--pin-force` bypasses absent/quality evidence only after a successful lookup, never an unavailable store. A behind/ahead/unstamped/foreign remote store is unavailable for this policy, including first remote measurement; setup/migrate remains required.

Normalize reached filesystem/setup `OSError` failures in required mode to a safe typed unavailable result as well; an inaccessible path or a parent that is a regular file is not a genuinely absent local store. Missing-local classification must distinguish `FileNotFoundError` from permission/type errors rather than treating every failed `exists()` probe as absence. Cover required row decoding/tally construction too: invalid stored row data must refuse safely, not escape a `try/finally` that only encloses execute/fetch. Preserve valid rows and successful insufficient-row behavior; do not catch process-control exceptions or hide unrelated programming errors.

Query and validate each incumbent/frozen baseline once, then pass that exact `BaselineResult` into the comparison or pin decision. Remove the validation-then-advisory-read race and avoid re-querying in `_frozen_baseline_refusal`; any unavoidable reread is required and its failure refuses before execution/publication. Successful absence still permits intentional first measurement or force behavior. Local required-read failures also fail closed; this is the deliberate validation correction, while healthy/missing local results and all advisory defaults retain their behavior.

For advisory remote failures use one fixed-text `remote_telemetry.warn_once`; required failures are reported once at the CLI validation boundary without raw reader logging. Capture logging/stderr and inject endpoint/token/SQL canaries on open/query/fetch failures. Sanitize reached loud remote-recording failures in `_run_baseline_phase`, `_run_compare_arm` and retry command catches as well: their current `{exc}` formatting can expose a remote endpoint after a successful lookup followed by a failed write. Preserve local recording diagnostics and exit semantics; no writer/backoff redesign is included. ENH-3682 owns the generic `_connect_readonly` warning.

### Docs wording

Docs and messages say remote readers are "not supported with a remote backend" where refused; they do not promise a follow-up (ENH-3668/3684/3685 are deferred indefinitely). Add the `ll-harness` serve row and the mid-query degrade note to the single support table in `docs/reference/CONFIGURATION.md` (ENH-3657 creates it; merge rows).

## Motivation

A refusal from the boundary helper (ENH-3657) only covers CLIs that pre-resolve. Without the central guard, hand-built absolute paths still create/read a shadow DB under remote config; without the widened catches, a remote failure after a successful open tracebacks in ~65 readers. `ll-harness` can use the existing remote backend; its required validation reads and safe failure paths still need explicit implementation and tests.

## Scope Boundaries

- **In scope**: central guard with retained advisory contract, narrow required harness lookup channel, explicit-local provenance, widened advisory read-error catches + gate, importer tripwire, `ll-harness` serve and advisory/required dispositions (measure/compare/retry/pin-force included), safe remote diagnostics and support-table rows.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657); degrade sites, CT-0 and mirrors (ENH-3728); `sft-corpus` routing (ENH-3729); hand-built paths (ENH-3658); `context-monitor.sh`; prepatch budget and `_connect_readonly` message sanitization (ENH-3682); **read-mode ensure, serving behind/ahead stores, shared missing-stamp tightening and the `HranaStub` read-only permission mode** (dropped 2026-10-04; revisit as an explicit opt-in only if a remote user needs a behind store served, and with ENH-3668 if revived); remote read serving for `ll-history` subcommands and MCP (ENH-3668/3684/3685, deferred); writers/startup paths (BUG-3652, done).

## Proposed Solution

1. **Seam** (`session_store/backend.py`, `history_reader/_base.py`): guard in `open_history_readonly`; `_connect_readonly` guard mapping + fixed-text warning; `_READ_ERRORS` and the mechanical catch replacement; explicit-local provenance in reached helpers.
2. **Serve** `cli/harness.py` x5 (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`): drop the pre-resolve, pass the relative default; add required flags only to validation lookups and retain validated baseline results; confirm rows round-trip through `HranaStub` without a shadow DB. Sanitize the named remote-recording catches.
3. **Gates**: AST gate for default-path absolute construction/unaudited importers; AST gate for bare `except sqlite3.Error` in `history_reader`.
4. **Docs**: support-table rows in `docs/reference/CONFIGURATION.md`, `docs/reference/CLI.md`, `docs/reference/API.md` ("SQLite-only prerequisite" `Backend chokepoint` wording), `docs/ARCHITECTURE.md:~758`, `docs/guides/HISTORY_SESSION_GUIDE.md`. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths; do not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (`open_history_readonly`, `HistoryRemoteRefused`), `history_reader/_base.py` (`_connect_readonly`, `_READ_ERRORS`) and the `history_reader/*` modules containing the `except sqlite3.Error` sites, `history_reader/harness.py`, `cli/harness.py` (5 sites), `cli/session.py` / `cli/history_context.py` and only reached helpers that must retain explicit local provenance.
- Anchors drift: re-grep every `resolve_history_db(` site before editing.
- `issue_history/evolution._open_db` (sqlite-only choke point) changes only if made remote-aware.

### Tests
- Guard fires only for the original plain default-shaped hazard; original typed `LocalTarget`, explicit relative/absolute default-shaped `--db`, the actual selected `LL_HISTORY_DB` target, and non-remote first-use creation are carve-outs. Execute through `SqliteBackend.ensure_schema` to prove the selected local target is not re-resolved; inspect actual override content and both foreign-cwd directions.
- `_connect_readonly` returns `None` with exactly one fixed-text `remote_telemetry.warn_once` for the guard (no traceback, no canaries); other `HistoryUnsupported` still maps to `None`; a behind-schema stub store yields the clean migrate-hint refusal, not a traceback.
- With `LL_HISTORY_DB` set to a different local file, a plain remote-root absolute default path still refuses without reading a stale shadow or creating one. The actual env target (including a default-shaped path), relative default resolution and typed local selection read seeded override content. No already-absolute argument is silently redirected.
- Guard warning classification is exercised from a foreign local cwd against a remote owning path (the current ambient classifier returns false here); no traceback, `exc_info` or canaries appear. Local twins retain their diagnostics.
- Mid-query remote failure in a representative reader returns its empty result without raising.
- `ll-harness` serve returns stub data and creates **no** local `.ll/history.db`; failures: advisory reads degrade, required retry/baseline lookups fail closed with zero subject invocations/new candidate rows.
- Exercise public harness retry, measure-baseline, compare (incumbent and frozen arm), baseline-of, pin and pin-force paths. Inject required open/query/fetch failures; assert their validation exits, fixed unavailable reason and zero subject/candidate/pin writes. Prove compare passes the validated result without a second query, and required rereads (if any) refuse on failure. Genuine empty/insufficient rows and a missing local file still allow intended measure/force behavior. A reached loud-recording failure returns its existing error exit with sanitized remote stderr.
- Add deterministic required filesystem/type/permission and invalid-row decoding failures; all use the same unavailable validation path with zero subject/artifact writes. An explicitly typed local required lookup retains intent through `harness_event_by_id`/`baseline_for` and SQLite setup; `Path(LocalTarget(...))` must not discard/break the override.
- Use the hoisted `remote` fixture (ENH-3677; must `delenv("LL_HISTORY_DB")`); test `main_harness([...])`, not `cmd_*`.
- Keep green: `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites and the reader seam, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_evolution_triggers.py`.

## Program Design

### Types
- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)`, and new `HistoryRemoteRefused(HistoryUnsupported)`, in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.
- `LocalTarget` in `little_loops.session_store.targets` carries an explicit local override through only the reached helpers affected by the guard.
- `_READ_ERRORS: tuple[type[BaseException], ...] = (sqlite3.Error, HistoryError)` in `little_loops.history_reader._base`.

### Signatures
- `open_history_readonly(target=None, *, ensure: bool = False)` — gains the default-shaped-local-path guard (raises `HistoryRemoteRefused`); remote `ensure=True` behavior otherwise unchanged (write-mode `check_access`).
- `_connect_readonly(db_path: Path | LocalTarget, *, best_effort: bool = False, required: bool = False) -> sqlite3.Connection | None` — retain ENH-3682's best-effort parameter. Default/advisory calls return `None` on errors; required calls distinguish actual missing local files from unavailable opens and propagate typed failure. Best-effort wins if both flags are passed.
- `harness_event_by_id(db_path: Path | str | LocalTarget, attempt_id: int, *, required: bool = False) -> HarnessEvent | None` — preserve advisory defaults and selected local intent; required open/query/fetch/invalid-row failure raises a safe typed error.
- `baseline_for(db_path: Path | str | LocalTarget, *, runner: str, target: str, input_hash: str, target_content_hash: str, conditions: BaselineConditions, required: bool = False) -> BaselineResult | None` — add the opt-in flag to the existing keyword arguments, retaining local intent; successful insufficient rows remain `None`.
- `read_baseline(key: BaselineKey, conditions: BaselineConditions, *, required: bool = False) -> BaselineResult | None` — CLI wrapper forwards the flag; all required validation consumers explicitly opt in.

### Call Path
- `history_reader._connect_readonly` -> `open_history_readonly` -> default-shaped-path guard -> `HistoryRemoteRefused` -> `None` + one `remote_telemetry.warn_once`.
- `main_harness` -> relative `DEFAULT_DB_PATH` -> `LibsqlBackend` (`ensure_schema` write-mode check) -> rows; failure -> advisory empty or required fail-closed.

### Decision Rules
- Serve at the designated `ll-harness` boundary using the relative default. Refuse a plain absolute default-shaped path under remote config; typed explicit `LocalTarget`, applicable `--db`, and `LL_HISTORY_DB` remain local carve-outs.
- Catch class for the guard is `HistoryRemoteRefused`; `"No history.db found"` stays verbatim for local-missing.
- Unreachable endpoint gives advisory empty output plus a safe warning, or a required validation refusal through its existing exit path; it never authorizes a retry, new measurement, comparison or forced pin. Successful absence remains distinct.
- A behind/ahead/unstamped remote store is refused at open with the existing clean message; it is not served.

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture), ENH-3657 (boundary helper, support table and typed-local reader setup/forwarding) and ENH-3682 (sanitized `_connect_readonly` warning and best-effort seam) landed. ENH-3728 / ENH-3729 are independent of this issue.

1. Seam: guard with selected-env-target discrimination, `_connect_readonly` mapping, `_READ_ERRORS` replacement plus safe remote query diagnostics, explicit-local provenance; consume ENH-3657's setup fix and verify against `HranaStub` (including a behind-schema store).
2. Required reader flags and CLI validation catches/result reuse; `cli/harness.py` serve + advisory/required dispositions and safe reached recording diagnostics.
3. AST gates; docs and support-table rows.
4. Tests per the Integration Map. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium/Large - guard and local provenance, advisory catch/diagnostic changes across reader modules, required harness validation/result reuse across runner branches, two AST gates and public failure-path tests. Catch widening alone is mechanical; the required lookup and safe diagnostic changes are not.
- **Risk**: Medium - advisory catch widening is gated; narrow required calls intentionally change failure disposition and must retain successful-empty/local-first-use behavior.
- **Breaking Change**: Required harness history failures now refuse instead of being mistaken for absent data; healthy local use and advisory defaults are preserved.

## Acceptance Criteria

- [ ] `HistoryRemoteRefused` exists; default/advisory `_connect_readonly` returns `None` with one fixed-text warning for it and other `HistoryUnsupported`. Required calls propagate typed failure to their CLI boundary. Foreign-cwd guard handling never selects the local traceback logger; no traceback or canaries appear.
- [ ] The guard inspects original intent and fires only for a remote provider + plain default-shaped absolute local path without an override; it classifies from the owning root and creates no shadow DB. Explicit relative/absolute default-shaped `--db` remains local through reached helpers and `SqliteBackend.ensure_schema`; override content is actually read, including from a foreign remote cwd. Ordinary writer/hook resolution is preserved.
- [ ] The importer AST gate (default-path absolute construction + unaudited importers, reasoned exceptions) passes against the re-run inventory, and dynamic tests assert no shadow DB.
- [ ] The catch gate covers SQLite Error/subclasses, aliases and tuples with planted detector tests and qualified-function exemptions. Representative advisory and FTS remote failures degrade safely; local invalid-FTS behavior/diagnostics are retained. Required handlers propagate failure rather than satisfying the gate with an empty fallback.
- [ ] A behind/ahead/unstamped remote store still yields the clean migrate/upgrade refusal at open (`None` + one warning), not a traceback; no reader-mode ensure, stamp-policy change or stub permission mode is introduced.
- [ ] `ll-harness` serve sites return stub data for an exact-version stamped store and create no local `.ll/history.db`.
- [ ] Default/advisory harness failures preserve fallbacks/grading; public retry/baseline-of/measure/compare/frozen/pin/pin-force required failures return existing validation exits with zero subject/candidate/pin writes. Actual remote attempts/baselines serve; genuine empty/insufficient rows and missing local files retain intended measure/force behavior. Required local failures also fail closed.
- [ ] Validated incumbent/frozen baseline objects are reused without advisory rereads; any unavoidable required reread failure refuses before candidate execution. Open/query/fetch and reached loud remote-recording failure tests expose no traceback or endpoint/token/SQL canaries.
- [ ] A different `LL_HISTORY_DB` does not exempt an unselected absolute shadow path; the actual selected env target and typed local required helpers return seeded local content. Required permission/type/setup and invalid-row failures return safe unavailable validation exits with zero subject/artifact writes; only genuine local absence enables first-use behavior. Widened catches use safe remote diagnostics rather than retaining `exc_info=True`.
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
- EPIC-3693 review #4 - 2026-10-05 - setup fix reassigned to prerequisite ENH-3657; env carve-out tied to actual selected target; typed required helper signatures, filesystem/row failure classification and shared safe query diagnostics clarified. Fresh Opus consult skipped: existing per-chat budget exhausted; implementation not performed.
- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - required per-call lookups, measure/pin-force/compare races, SQLite setup/local intent, foreign-cwd guard logging, subclass-aware catch gate and syntactic importer scope corrected; implementation not performed
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.78) - 2026-10-04 - split degrade sites (ENH-3728) and SFT routing (ENH-3729) out; re-raise, read-mode ensure/serve-behind, stamp tightening and stub permission mode dropped; widened catches + AST gates added; implementation not performed
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.74) - 2026-10-04 - stamp enforcement, harness control-flow, safe diagnostics, local provenance and actual SFT failure routing amended; implementation not performed
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:05 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
