---
id: EPIC-3693
title: Remote History Backend Support
type: EPIC
priority: P3
status: open
captured_at: "2026-10-02T17:30:24Z"
discovered_date: 2026-10-02
discovered_by: link-epics
relates_to:
  - ENH-3678
  - ENH-3679
  - ENH-3668
  - ENH-3684
  - ENH-3685
  - ENH-3720
---

# EPIC-3693: Remote History Backend Support

## Summary

Make an opt-in remote (libSQL) history backend fail cleanly instead of silently: reader CLIs refuse with a named verdict instead of a traceback, no reader creates a shadow local `.ll/history.db`, hand-built `history.db` paths classify against the project root, and best-effort prepatch reads are time-budgeted. Narrowed 2026-10-02 after an Opus pre-implementation review (BUG-3652's follow-ups).

**Closure criterion:** each audited entry point has a documented serve/refuse/degrade verdict, creates no unintended shadow local DB, and exposes no endpoint/token/SQL or unhandled traceback. Applicable explicit local overrides remain supported. Intentional advisory empty results and skipped writes remain permitted where stated below; unsupported user-facing readers must not look like successful empty queries, and required harness retry/baseline lookups must fail closed. Broader strict read serving (ENH-3668/3684/3685) stays deferred; limited `ll-harness` serving is in scope. Refused rows say "not supported with a remote backend" and promise no follow-up.

## Children

- **ENH-3677** — Hoist the shared remote history-backend test fixture into conftest.py (open)
- **ENH-3657** — Reader CLI refusal boundary and refuse sites (3657a) (open)
- **ENH-3700** — Central reader guard, widened read-error catches and ll-harness serve (3657b, slimmed 2026-10-04) (open)
- **ENH-3658** — Handle hand-built history.db paths under a remote history backend (open)
- **ENH-3682** — Budget best-effort remote prepatch history reads (open)
- **ENH-3680** — Spool context-monitor.sh history writes (cancelled: remote stays a documented no-op)
- **ENH-3728** — Degrade verdicts for history readers under a remote backend (open)
- **ENH-3729** — Fail-closed failure routing and atomic enrich publish for the sft-corpus loop (open)



## Goal

Make the supported remote history surfaces predictable: every entry point serves, refuses or degrades according to the final matrix; no hidden local store, unhandled error or unbounded advisory request obscures that outcome.

## Scope

The seven active children cover the shared test fixture, refusal boundary, central reader guard + `ll-harness` serve, degrade verdicts (ENH-3728), `sft-corpus` failure routing (ENH-3729), hand-built snapshot paths and the advisory prepatch deadline. The cancelled hook spool requires only sibling documentation. Strict CLI/MCP serving and local rebuild/lock work are detached as described below; no implementation of those deferred designs is needed for this epic to close.

## Impact

- **Priority:** P3 — correctness of opt-in remote history support.
- **Effort:** Multiple independently reviewable reader, artifact and advisory slices.
- **Risk:** The central guard changes the reader failure contract; recorded importer coverage and local override tests constrain the blast radius.
- **Breaking Change:** Unsupported remote readers acquire explicit refusal output; local behavior remains unchanged.

## Detached / deferred (not children; `relates_to` this epic)

- **ENH-3678** (P2), **ENH-3679** (P3) and follow-on **ENH-3698** — local-store rebuild gating / lock-wait / size-gate work; **done 2026-10-03**, detached from this epic. Consume their landed doctor/check-count behavior when integrating ENH-3658. ENH-3699 (single-flight) remains deferred and detached.
- **ENH-3668**, **ENH-3684**, **ENH-3685** — remote read serving (strict-read infra, `ll-history` flips, MCP/SFT); deferred, detached (deferred is non-terminal, so keeping them parented would strand the epic branch). Revive when remote read demand exists.
- **ENH-3720** — **done 2026-10-04**; supplied the shared `Deadline`, `connect_readonly(deadline=)` and default-off `HranaStub` fault controls that ENH-3682 consumes. Outside this epic; no dependency on EPIC-3710 or deferred strict-reader work.

## Implementation order

Remote track (revised 2026-10-06, review #6): **ENH-3677 and ENH-3729 can start independently**, after fresh readiness checks on their current plans. After ENH-3677, ENH-3657, ENH-3658 and ENH-3682 are independently eligible. ENH-3657 includes the narrow typed-local SQLite reader setup fix (moved from dependent ENH-3700), conversation-target forwarding and explicit relative ctx-stats overrides; its selected-root local tests and intermediate no-shadow-regression test must pass on its own. ENH-3728 requires ENH-3677 + ENH-3657 + ENH-3729 (fixture, selected-root/fallback wiring, and the SFT quality-refusal failure route), and owns direct-schema summary/decisions provenance plus selected-local SFT metadata forwarding. ENH-3700 requires ENH-3657 + ENH-3677 + ENH-3682; it does not wait for ENH-3728 or ENH-3729. It replaces ENH-3657's compatibility forwarding with the permanent guard and consumes ENH-3682's live-state decoder normalization. ENH-3682 consumes landed ENH-3720 without an unresolved prerequisite. Sequence ENH-3729 before ENH-3728's edits to the same SFT states, preserving failure routes/atomic publication/path transport. ENH-3658's conditional CT-0 allowlist is removed by ENH-3728; if ENH-3728 lands first, never introduce it, and stale entries fail the gate. Shared backend/base-helper/CLI/docs/mirror edits require integration coordination, not additional artificial dependencies. Merge each slice's rows into the single support table without discarding siblings' rows.

Local track: ENH-3678 → ENH-3698 and independent ENH-3679 are already done; they do not delay remote implementation. Preserve their landed doctor/check-count behavior in ENH-3658. ENH-3699 remains deferred until a spike proves bounded-lock timeout recovery across a newer ingest watermark. Deferred remote serving follows ENH-3700 → ENH-3668 → ENH-3684/3685 if revived.

## Composition Review

_Reviewed 2026-10-02 against the code and Opus/Sonnet critiques; issue-plan amendments applied before implementation._

Retain ENH-3677, ENH-3657, ENH-3700, ENH-3658 and ENH-3682 as the active remote-support slices. The refusal boundary and risky reader seam are separate reviews; the fixture is their test prerequisite. Cancel ENH-3680's spool and document the existing remote omission, acknowledging that remote recent/search consumers already exist but no live control-flow dependency was found. Detach ENH-3678/3679 and the rebuild follow-ons from this epic's branch; retain their local-store value. ENH-3699 stays deferred until its watermark/restart recovery spike is proven. Defer/detach ENH-3668/3684/3685 until demonstrated strict remote-read demand; their retained plans specify safe error, target and atomic SFT contracts if revived.

Revised issues with cleared/missing confidence scores require a new confidence check before implementation; planned tests are not passing evidence. No child is claimed implementation-ready merely because its prose now validates.

_Re-reviewed 2026-10-04 against current code, a temporary HranaStub missing-stamp probe and `/ll:advise` with `claude-opus-5-5` (confidence 0.74). No extra child issue is needed._

Amendments: ENH-3657 now pins owning-root resolution and tests the real CLI/MCP boundaries. ENH-3700 implements the previously assumed missing-stamp read predicate, preserves eager ensure-reader access failures on the same client, separates advisory output from required retry/baseline refusals, sanitizes diagnostics and propagates SFT shell failures before the pathname echo. ENH-3658 preserves explicit local snapshot provenance through export, supplies a real renderer skip path and doctor-trim DB override, and regenerates skill mirrors. ENH-3677 fixes variant ownership/setup-failure cleanup and clears stale 100/67 scores. ENH-3682 consumes external ENH-3720, clarifies per-read budgeting/marker recovery and does not require deferred `strict_reads()` infrastructure.

Opus agreed with the core corrections and favored the shared stamp predicate. Its dissent favored refusing some default-shaped explicit local paths to reduce signature changes; the plan retains the epic's local-override promise through narrowly reached helpers and the snapshot seam. Opus's possible-remote-migration concern was checked: `LibsqlBackend.ensure_schema` currently verifies policy and does not migrate. Required gates use existing validation exits; no new strict-reader subsystem or harness exit code is added.

_Re-reviewed a second time 2026-10-04 (after ENH-3720 landed) against current code and `/ll:advise` with `claude-opus-5-5` (confidence 0.78)._

Amendments: ENH-3700 was slimmed — the `HistoryRemoteRefused` re-raise, read-mode ensure / serving behind and ahead stores, the shared missing-stamp tightening, the `HranaStub` read-only permission mode and eager same-client verification were **dropped** (serving behind stores through the shared path would turn today's clean migrate-hint refusal into a traceback in ~65 `except sqlite3.Error`-only reader sites); it now owns the guard (maps to `None` + one fixed-text `warn_once`), widened `(sqlite3.Error, HistoryError)` catches with an AST gate, an importer AST gate (replacing the exhaustive audit) and `ll-harness` serve. The degrade sites moved to ENH-3728 and `sft-corpus` failure routing to ENH-3729 (neither needs the seam). ENH-3682 dropped its ENH-3720 `blocked_by` (landed), uses `connect_readonly(deadline=)` plus a read-scoped marker so deadline expiry cannot silence telemetry writes, skips `ensure_schema`, verifies once on the same client and owns `_connect_readonly` message sanitization; ENH-3700 is now `blocked_by` ENH-3682. Opus's dissent: where stderr is discarded `None` + `warn_once` is effectively silent-empty — revisit as a narrow re-raise if a remote user hits it. Revised issues have cleared scores; re-run `/ll:confidence-check` starting with ENH-3677.

## Final support matrix

_Current acceptance baseline after review #6 (2026-10-06); historical composition notes above describe earlier plans._

| Surface | Remote verdict at epic closure | Owner |
|---|---|---|
| `ll-history` analyze/activity/rework/quality/collisions/sessions/root; DB-backed logs; `ll-ctx-stats`; explicit messages DB reader | Refuse, named safe stderr, exit 1; preserve applicable explicit local overrides. Both quality/activity workspace modes preflight all default member targets before aggregation, retaining manifest path precedence and default intent through symlink normalization | ENH-3657 |
| MCP `history_search` | Structured `is_error` refusal against the owning project root | ENH-3657 |
| History summary, decisions generation, automatic messages reader, CT-0 | File/JSONL fallback or skip with one note; summary bypasses all DB metrics/probes and marks loop counts unavailable; messages respects selected `--cwd`, with existing Claude-shaped-only JSONL fallback | ENH-3728 |
| `ll-harness` | Serve an exact-version stamped remote store through existing access policy; advisory reads degrade safely. Per-call required retry/baseline-of/measure/compare/frozen/pin/pin-force reads distinguish successful absence from unavailable history, reuse validated results and fail closed with existing exits | ENH-3700 |
| Packaged SFT stage/enrich | Auto JSONL; remote enrich passes records/metadata through unchanged only when all DB-quality flags are disabled (packaged defaults). Any enabled DB-quality flag refuses before output and reaches the failure terminal; other stage/enrich failures also terminate atomically. Validated sentinel/path transport and selected local metadata overrides are covered. Existing absent stage lineage and later first-record filters are documented limitations, not full-corpus quality certification | ENH-3728 / ENH-3729 |
| Artifact snapshot route/dashboard/history panel; loop `--serve`; doctor `--trim` | Named refusal/501/unavailable panel or informational skip; server remains usable | ENH-3658 |
| Prepatch base SHA/dirty reads | Per-invocation deadline shared by verification/query on one client, with connection-scoped verification completion (no duplicate warm-file-cache request); otherwise `None`. Backend opener retains connection-or-typed-error; advisory wrappers own `None`. A read-scoped TTL marker suppresses later advisory reads without silencing writes and permits recovery. Malformed cache/marker or live verification metadata and expected setup/bookkeeping failures cannot escape this fallback, authorize access by coercion, or suppress indefinitely | ENH-3682 (ENH-3720 landed) |
| Context-monitor pressure/handoff writes | Documented remote no-op; reminders and exits unchanged | ENH-3680 (cancelled) |
| Existing backend-aware `ll-session recent`/search queries | Existing remote support retained; omission of pressure/handoff writes is documented, not absence of all remote consumers | Existing behavior |

This matrix is the acceptance baseline for the single public table in `docs/reference/CONFIGURATION.md`; link it from CLI/API guides rather than maintaining contradictory promises.

## Pre-implementation Review #3 (2026-10-05)

Seven open children remain on-theme; no additional child is needed. Progress output: `"total": 8`, `"open": 7`, `"cancelled": 1`, `"percent_done": 12.5`. No child is stalled: session-log/mtime activity is within one day (14-day default threshold). Closure: **No** — the seven open children still require implementation and their revised confidence checks.

Applied fixes after code inspection and `/ll:advise` with `claude-opus-5-5` (`user_requested`, confidence **0.80**):

- **ENH-3657:** correct stale split ownership and local-provider-only `history.db_path` precedence; classify selected messages/log roots before empty-data exits; preflight mixed-project logs/workspace sources and deduplicate returned local override paths. Add real helper/root signatures so the issue is structurally executable.
- **ENH-3700:** preserve advisory defaults but add a narrow required lookup flag; include measure-baseline and pin-force, reuse validated incumbent/frozen results, and sanitize reached remote recording failures. Preserve original local intent through SQLite setup as well as helpers; a typed target alone currently fails after setup drops it. Root-independent guard warning classification and subclass/alias-aware catch gates close missed traceback paths. Importer gate is explicitly syntactic, with dynamic no-shadow tests.
- **ENH-3682:** add the actual `LibsqlConnection` verification-completion seam. A warm file-cache hit must not trigger lazy re-verification or contaminate process cache; readonly/deadline checks remain active. Keep `write=True` access policy because its checks issue metadata SELECTs, not writes.
- **ENH-3728:** skip the summary's secondary DB count query, retain date/source semantics and unavailable metrics; define exact remote SFT passthrough and fail closed when quality flags need unavailable metadata; document the existing host-parser limitation. Add the functional ENH-3729 edge.
- **ENH-3729 / ENH-3677:** remove the artificial fixture prerequisite from backend-independent SFT failure routing and synchronize its backlink. ENH-3658 retains its scope, with same-server usability after 501 made an explicit test.

Read-only probes support the harness/diagnostic findings: `"baseline_lookup_none_reaches_sample_loop": true`, `"pin_force_with_lookup_none_is_allowed": true`, and `"root_aware_target_is_remote": true` alongside `"ambient_warning_classifier_is_remote": false`. These describe current defects, not implementation success.

A further explicit-local probe returned `"typed_local_ensure_reader_error": "HistoryBackendNotLocal"`, `"error_operation": "ensure_db"`; ENH-3700 now owns preserving the selected local target through `SqliteBackend.ensure_schema`. ENH-3658 similarly carries every classified local snapshot target through export, including a default local owning root under a foreign remote cwd.

Opus favored per-call required flags over duplicate CLI SQL, connection-scoped verification and remote quality refusal. Its dissent offered lazy-only verification (loses warm file-cache benefit) and documentation-only SFT semantics (leaves unchecked correction filters passing); neither is adopted. Its warning that `write=True` might need write-token privileges was checked against `check_access`: the policy uses metadata SELECTs, so the exact-version/stamp rule is retained. No broad strict-reader subsystem, serving-behind policy, new host parser or filter redesign is added. Planned tests and the advisor verdict do not certify implementation readiness.

## Pre-implementation Review #4 (2026-10-05)

All seven open children remain on-theme. ENH-3677's fixture and ENH-3658's snapshot plans were retained; no extra child, hard dependency or reopening of deferred serving is needed. Existing progress remains `"open": 7`, `"cancelled": 1`; implementation and fresh readiness checks are still outstanding.

Five child plans were amended from code inspection and temporary deterministic probes:

- **ENH-3657:** the selected-root local tests relied on a setup fix scheduled in dependent ENH-3700. Move only typed-local `SqliteBackend.ensure_schema` preservation into this prerequisite and forward selected conversation targets through the reached helpers. Explicit relative default-shaped ctx-stats DB paths must be anchored to remain local.
- **ENH-3700:** env presence alone cannot exempt an unrelated absolute shadow path. Tie the carve-out to the actual selected env target or typed local intent, without redirecting absolute arguments. Clarify typed required helper signatures, expected filesystem/invalid-row failure handling and shared safe query diagnostics alongside catch widening.
- **ENH-3682:** reached existing marker/cache timestamp casts can throw or suppress indefinitely; validate malformed/nonfinite/future timestamps and make expected marker I/O/local setup failures advisory. Successful data must survive failed marker cleanup, and unavailable configuration must not throw again while forming a marker key.
- **ENH-3728:** summary/decisions helpers call `schema.connect` directly; carry optional selected-local provenance through those three helpers so foreign remote cwd cannot cause a remote query or a misleading file fallback. This is separate from the reader setup fix.
- **ENH-3729:** add safe wrong-shape/source JSON and non-regular sentinel cases to the actual-state failure tests; permit correctly checked shell conditionals while requiring failure status propagation.

Probe evidence: `"root_resolved_local_under_foreign_remote_ensure": "HistoryBackendNotLocal"`, followed by `"only_typed_ensure_fix_resolved_local": true`; `"absolute_default_with_env_reads_shadow": true`, `"reads_override": false`; malformed marker timestamps returned `ValueError`/`TypeError`, and `Infinity` yielded active suppression; local prepatch setup returned `"prepatch_setup_escaped": "FileExistsError"`; the local direct-schema summary probe from a remote cwd returned `"local_summary_probe_escaped": "HistoryDbUnavailable"`. Temporary projects were removed; no production code was changed.

A fresh `/ll:advise --signal user_requested --host claude-code --model opus` consult was attempted but did not run: `advisor consult budget exhausted for this task (advisor.max_consults_per_task)` (3/3 spent in this chat). This review has no new Opus verdict or confidence score; earlier reviews remain historical evidence. Planned regression tests and structural checks do not certify implementation readiness.

Review validation: `ll-issues format-check` and `ll-issues check-design` exit 0 for all seven open children; `ll-issues epic-consistency EPIC-3693` reports empty drift lists; the edited-file `git diff --check` exits 0. Existing non-blocking advisory symbol notes concern the fixture plan and the planned guard exception. The implementation test suite was not run for these issue-only edits.

## Pre-implementation Review #5 (2026-10-05)

All seven open children were checked against their current contracts and code paths. They remain on-theme; no additional child or dependency edge is needed. No child is stalled (all have 2026-10-05 activity), and the epic remains 7 open / 1 cancelled, not ready to close.

Two further code-backed corrections are owned by existing children:

- **ENH-3657:** workspace quality was missing from the member preflight specified for activity. Both public commands returned exit 0 against a local owning root with a remote member's pre-existing shadow DB; quality included `remote (source)` without a skip, and activity marked both members `ok`. Require one quality/activity preflight before either local aggregator. Keep manifest members' existing isolation from global env/member config DB redirection, and retain default intent before discovery resolves symlinks. This raw SQLite path is outside ENH-3700's reader guard.
- **ENH-3682:** timestamp hardening alone leaves malformed verified-cache versions unsafe. Decoder probes showed `Infinity` escaping as `OverflowError`, `47.9` coercing to `47`, and `true` coercing to `1`. Validate the complete written cache payload before access evidence is accepted; invalid entries trigger normal bounded verification, while well-formed warm-cache behavior stays unchanged.

ENH-3657's obsolete "no seam change" effort description, ENH-3682/3700 effort estimates and ENH-3728's low-risk wording were corrected to reflect their already-expanded scope. ENH-3677's fixture and ENH-3658/3729's implementation plans need no additional scope from this pass. Preserve the fresh 2026-10-05 confidence results on ENH-3677 and ENH-3729; issues whose plans changed or scores are absent still need the normal readiness checks after prerequisites land. No planned test or temporary probe is implementation certification.

A fresh `/ll:advise --signal user_requested --host claude-code --model opus` attempt did not run: `advisor consult budget exhausted for this task (advisor.max_consults_per_task)` (existing session 3/3). No new Opus verdict is claimed and the limit was not changed. Probes used temporary projects and removed them; only issue files were edited. Start order remains ENH-3677 and ENH-3729 independently, followed by the existing dependency graph; coordinate edits to shared helpers/docs and SFT states.

Validation: all seven child `ll-issues format-check` commands exit 0 with no blocking findings; four existing symbol-reference advisories remain in ENH-3677/3700 (planned symbols and environment/loader references). `epic-consistency` reports no membership drift, the open-child dependency graph is acyclic, and `git diff --check` is clean. The production test suite was not run for this issue-only review; implementation acceptance gates remain outstanding.

## Pre-implementation Review #6 (2026-10-06)

All seven open children remain on-theme and recently active; no additional child or dependency is needed. Structural progress output remains `"total": 8`, `"open": 7`, `"cancelled": 1`, `"percent_done": 12.5`. Closure: **No** — implementation and current-plan readiness checks remain outstanding. ENH-3677's prior scores were already cleared by its later standalone review; ENH-3729's 100/82 scores are cleared in this pass after its plan changed.

One completed `/ll:advise --signal user_requested --host claude-code --model opus` consult returned confidence **0.62**. Its recommendation was `"No new child is needed. Keep ENH-3700 as one issue."` Its dissent stated `"I could not see the code; this review rests only on the summarized plans."` The following amendments use code inspection and temporary probes in addition to that critique:

- **ENH-3657 / ENH-3700:** unconditional typed-local setup would introduce a shadow-file regression before the dependent guard lands. Preserve original intent and the legacy untyped remote-default setup path in ENH-3657, with an independent no-regression gate. ENH-3700 replaces that compatibility handling after guarding original intent, then forwards allowed local targets without ambient resolution. Keep its guard/error and required-harness work as two ordered review phases within one issue.
- **ENH-3682:** malformed live `meta.schema_version` escapes the typed error boundary even after file-cache validation. Normalize reached live-state decoding before cache admission, using the live decimal-TEXT contract separately from the JSON cache contract. Retain unmigrated/version/stamp policy; metadata errors create no transport marker. Clarify that the backend returns a connection or raises a typed error and only advisory wrappers return `None`.
- **ENH-3728:** pass the selected local metadata target through `lookup_session_metadata`, whose default `.exists()` gate otherwise ignores a populated env/config override. Document absent source/session lineage in ordinary formatter output and unchanged later filters; source-bearing enrich tests prove only the stated stage/enrich contract.
- **ENH-3729:** validate readable sentinel contents against the actual writer's UTC format, give a fixed recovery message without echoing contents, and use quoted optional arguments. Transport run_dir safely through the environment in the two touched actions. Malformed sentinels are retained, never silently reset into a full harvest.
- **ENH-3658:** make both CT-0 landing orders executable through a stale-exemption gate, and explicitly handle 501 before generic retryable 5xx logic. ENH-3677's already-reviewed fixture plan is retained. Detached ENH-3678/3679/3698 are already done; their completed work is no longer presented as a pending integration sequence.

Probe evidence: `"current_plain_absolute": "HistoryBackendNotLocal"`, `"current_file_exists": false`, followed under the temporary proposed setup patch by `"unconditional_typed_fix": "opened"`, `"shadow_created": true`; live malformed metadata yielded `"live_meta_read_escaped": "ValueError"`, `"raw_metadata_in_error": true`; a populated selected local DB with no default file yielded `"default_metadata": {}` but selected metadata contained `"tool_count": 1`. Temporary projects and patches were removed; no production code changed.

Opus's requested required-harness catch sites and legacy `db_path_is_default=None` behavior were already specified and remain in place; no duplicate classifier is added. Its suggested canonical target keyword and rejection of combined best-effort/required flags are not adopted: reached typed arguments versus direct-schema `db_target` serve distinct seams, and best-effort precedence is already an explicit scoped contract. No broad cache-policy change, remote serving revival, SFT lineage/filter redesign or new dependency is introduced. A follow-up consult did not run: `advisor consult budget exhausted for this task (advisor.max_consults_per_task)`; no follow-up verdict is claimed.

Validation: all seven child `format-check` and `check-design` commands exited 0 with no blocking findings; existing fixture/planned-symbol advisories remain. `epic-consistency` reports empty drift lists, the epic-scoped dependency check has no broken references/backlinks/stale prerequisite findings, the graph has no cycles, and `git diff --check` is clean. Repository-wide dependency warnings outside this epic are unchanged by this review. Planned regressions and the advisor's opinion do not certify implementation readiness; the authoritative implementation suite was not run for these issue-only edits and remains required when code lands.

## Acceptance Criteria

- [ ] All active children are `done` or deliberately `cancelled`; deferred/detached work is not required to close the epic.
- [ ] Every matrix row has remote/local tests for its actual entry point; foreign cwd and local override cases preserve owning-project resolution and create no shadow `.ll/history.db`.
- [ ] Unsupported readers return explicit safe refusals; documented advisory fallbacks preserve stdout contracts and emit only their designated safe warning/note channel.
- [ ] Each cold/warm prepatch invocation shares one deadline across verification/query; open/mid-query failures return `None`. Read-marker suppression/recovery is proven, a slow-but-healthy endpoint never suppresses telemetry writes, and ordinary explicit reads are unaltered (no deferred strict-reader APIs).
- [ ] Dashboard 501 is rendered safely and stops polling; initial remote pages skip local snapshot work while serving continues.
- [ ] Stage/enrich failures reach `terminal: true, failure: true`, publish no partial enrichment and never reach filter/publish/success sentinel. (ENH-3729)
- [ ] Required harness retry/baseline-of/measure/compare/frozen/pin/pin-force lookup failures cannot run subjects or write candidate/pin artifacts; genuine absent/insufficient rows and first-use missing local stores retain intended behavior. Validated baselines are reused without advisory rereads; remote recording errors are safe. Advisory rates/admissions cannot change grading. Behind/ahead/unstamped remote stores keep existing refusal policy; advisory mid-query errors degrade through subclass-aware catches (AST-gated).
- [ ] Remote summary never consults a stale shadow DB or its secondary count helper; loop metrics remain unavailable. Messages/logs use selected project roots, mixed-project default readers cannot return misleading partial aggregates, and local config overrides obey existing provider precedence. Both workspace quality/activity refuse remote default members before aggregation; all-local manifest paths retain their existing env/config isolation, and symlink normalization cannot erase default intent.
- [ ] Remote SFT enrich with disabled DB-quality flags preserves records/metadata with one note; each enabled DB-quality flag fails before publication through the actual terminal route. Local override enrichment still works. Cold-process warm-file-cache prepatch reads make one data POST with no duplicate verification and no process-cache contamination.
- [ ] ENH-3657's local selected-root tests pass independently of ENH-3700, with local intent preserved through conversation reads/setup; explicit relative ctx-stats DB overrides read actual local metrics. Local summary/decisions carry selected provenance through direct schema helpers under foreign remote cwd. Env presence never exempts an unrelated absolute shadow path.
- [ ] Malformed/future/nonfinite marker/cache timestamps, invalid verified-cache version/project/stamp payloads and expected bookkeeping/setup failures preserve the advisory read contract. Malformed cache evidence cannot authorize access by numeric coercion; normal bounded verification still applies. Required filesystem/invalid-row failures produce safe validation refusal. Wrong-shape SFT records and non-regular sentinel paths reach the failure terminal without raw-record output, traceback or partial publication.
- [ ] ENH-3657's setup fix introduces no intermediate shadow-file regression before ENH-3700; the final guard replaces its compatibility forwarding. Malformed live metadata remains a typed failure before cache admission, with no raw value or transport marker. Backend success/suppression contracts stay distinct from advisory `None`.
- [ ] Source-bearing local SFT enrichment reads real env/config-selected metadata with a missing or stale default DB; ordinary stage output's absent lineage and later filter limitations are documented. Present malformed/dangling sentinels fail safely before invocation with a recovery reason; valid timestamps are single quoted arguments and touched stage/enrich paths tolerate spaces/quotes/metacharacters.
- [ ] The reader importer inventory, hazard gate allowlists, support docs and dependency backlinks agree with the implemented scope. Stale confidence scores are removed; re-run readiness checks on revised issues before implementation, after their prerequisites land.
- [ ] The local authoritative suite (`python -m pytest scripts/tests/`) passes for the implementation; no unsupported reader message promises deferred remote serving.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log

- EPIC-3693 open-child review #6 + `/ll:advise` (opus, user_requested, confidence 0.62) - 2026-10-06 - all seven children reviewed; six plans amended for safe intermediate setup, live decoder errors, selected SFT metadata, sentinel/path handling and exemption/client ordering. Fixture plan retained; no new child/dependency or implementation. Follow-up consult skipped at the existing task budget; ENH-3729 stale scores cleared.
- EPIC-3693 open-child review #5 - 2026-10-05 - seven open children reviewed; workspace quality/activity preflight with manifest provenance and complete verified-cache validation added to ENH-3657/3682, scope/risk estimates synchronized on ENH-3657/3682/3700/3728. No new child/dependency or implementation; fresh Opus consult skipped at existing 3/3 session budget.
- EPIC-3693 open-child review #4 - 2026-10-05 - five child plans amended for prerequisite ordering/local provenance, actual env selection, malformed marker/cache state and safe SFT input failures; ENH-3677/3658 retained. Fresh Opus consult skipped at the existing 3/3 chat budget; no new advisor score or implementation.
- EPIC-3693 open-child review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - all seven child files and epic acceptance/order updated; required-read gaps, cache seam, SFT quality refusal, selected-root coverage and dependency cleanup; implementation not performed

- EPIC-3693 open-child review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - five child plans amended and external ENH-3720 dependency reconciled; implementation not performed
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - split ENH-3700 into ENH-3700/3728/3729; ENH-3720 landed; ENH-3682 marker/ordering fixed; implementation not performed
