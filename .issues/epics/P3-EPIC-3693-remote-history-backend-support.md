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

- **ENH-3678** (P2) and **ENH-3679** (P3) — local-store rebuild gating / lock-wait work; detached so the P2 fix and FEAT-3561 are not held behind P4 remote work by the epic-branch merge rule. Their follow-ons ENH-3698 (size gate, pending notice) and ENH-3699 (single-flight, deferred) hang off ENH-3678.
- **ENH-3668**, **ENH-3684**, **ENH-3685** — remote read serving (strict-read infra, `ll-history` flips, MCP/SFT); deferred, detached (deferred is non-terminal, so keeping them parented would strand the epic branch). Revive when remote read demand exists.
- **ENH-3720** — **done 2026-10-04**; supplied the shared `Deadline`, `connect_readonly(deadline=)` and default-off `HranaStub` fault controls that ENH-3682 consumes. Outside this epic; no dependency on EPIC-3710 or deferred strict-reader work.

## Implementation order

Remote track (revised 2026-10-04): ENH-3677 → {ENH-3657, ENH-3658, ENH-3682, ENH-3729} in parallel → ENH-3728 → ENH-3700. ENH-3728 requires ENH-3677 and ENH-3657 (boundary helper, summary root threading); ENH-3729 requires ENH-3677 only and edits the same `sft-corpus.yaml` states as ENH-3728 (sequence the edits when integrating). ENH-3682 requires ENH-3677 only (ENH-3720 landed 2026-10-04). ENH-3700 requires ENH-3657, ENH-3677 and ENH-3682 (it inherits the sanitized `_connect_readonly` warning); ENH-3728/3729 are independent of it. ENH-3658's temporary CT-0 allowlist is removed by ENH-3728; if ENH-3728 lands first, never introduce it. Each slice merges its own rows into the single support table without discarding siblings' rows.

Local track: ENH-3678 → ENH-3698, with ENH-3679 independent of remote readers. Sequence `cli/doctor.py` / `CLI.md` check-count edits in ENH-3679, ENH-3698 and ENH-3658 when integrating; shared-file ownership is not an additional functional dependency. ENH-3698 must land before any `REBUILD_DERIVE_VERSION` bump. ENH-3699 remains deferred until a spike proves bounded-lock timeout recovery across a newer ingest watermark. Deferred remote serving follows ENH-3700 → ENH-3668 → ENH-3684/3685 if revived.

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

| Surface | Remote verdict at epic closure | Owner |
|---|---|---|
| `ll-history` analyze/activity/rework/quality/collisions/sessions/root; DB-backed logs; `ll-ctx-stats`; explicit messages DB reader | Refuse, named safe stderr, exit 1; preserve applicable explicit local overrides | ENH-3657 |
| MCP `history_search` | Structured `is_error` refusal against the owning project root | ENH-3657 |
| History summary, decisions generation, automatic messages reader, CT-0 | Documented file/JSONL fallback or skip with one note | ENH-3728 |
| `ll-harness` | Remote serving through the unchanged `ensure=True` path for an exact-version stamped store; a behind/ahead/unstamped store is refused cleanly at open (existing policy, not served); advisory history degrades with safe warning, required retry/baseline/compare/pin lookups fail closed through existing validation exits | ENH-3700 |
| Packaged SFT stage/enrich | Auto JSONL and explicit remote unenriched passthrough (ENH-3728); unrelated errors fail the pipeline atomically (ENH-3729) | ENH-3728 / ENH-3729 |
| Artifact snapshot route/dashboard/history panel; loop `--serve`; doctor `--trim` | Named refusal/501/unavailable panel or informational skip; server remains usable | ENH-3658 |
| Prepatch base SHA/dirty reads | Per-invocation telemetry deadline shared by verification/query, otherwise `None`; a read-scoped TTL marker suppresses later advisory reads without silencing telemetry writes and permits recovery | ENH-3682 (ENH-3720 landed) |
| Context-monitor pressure/handoff writes | Documented remote no-op; reminders and exits unchanged | ENH-3680 (cancelled) |
| Existing backend-aware `ll-session recent`/search queries | Existing remote support retained; omission of pressure/handoff writes is documented, not absence of all remote consumers | Existing behavior |

This matrix is the acceptance baseline for the single public table in `docs/reference/CONFIGURATION.md`; link it from CLI/API guides rather than maintaining contradictory promises.

## Acceptance Criteria

- [ ] All active children are `done` or deliberately `cancelled`; deferred/detached work is not required to close the epic.
- [ ] Every matrix row has remote/local tests for its actual entry point; foreign cwd and local override cases preserve owning-project resolution and create no shadow `.ll/history.db`.
- [ ] Unsupported readers return explicit safe refusals; documented advisory fallbacks preserve stdout contracts and emit only their designated safe warning/note channel.
- [ ] Each cold/warm prepatch invocation shares one deadline across verification/query; open/mid-query failures return `None`. Read-marker suppression/recovery is proven, a slow-but-healthy endpoint never suppresses telemetry writes, and ordinary explicit reads are unaltered (no deferred strict-reader APIs).
- [ ] Dashboard 501 is rendered safely and stops polling; initial remote pages skip local snapshot work while serving continues.
- [ ] Stage/enrich failures reach `terminal: true, failure: true`, publish no partial enrichment and never reach filter/publish/success sentinel. (ENH-3729)
- [ ] Required harness retry/baseline/compare/pin lookup failures cannot run the rejected candidate or write candidate rows; advisory rates/admissions cannot change grading. Remote readers keep write-mode access policy at open (behind/ahead/unstamped refused cleanly, never a traceback), and `history_reader` remote mid-query failures degrade through widened catches (AST-gated).
- [ ] The reader importer inventory, hazard gate allowlists, support docs and dependency backlinks agree with the implemented scope. Stale confidence scores are removed; re-run readiness checks on revised issues before implementation, after their prerequisites land.
- [ ] The local authoritative suite (`python -m pytest scripts/tests/`) passes for the implementation; no unsupported reader message promises deferred remote serving.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log

- EPIC-3693 open-child review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - five child plans amended and external ENH-3720 dependency reconciled; implementation not performed
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - split ENH-3700 into ENH-3700/3728/3729; ENH-3720 landed; ENH-3682 marker/ordering fixed; implementation not performed
