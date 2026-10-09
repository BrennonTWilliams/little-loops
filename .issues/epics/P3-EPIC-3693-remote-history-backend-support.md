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
- **ENH-3682** — Budget best-effort remote prepatch history reads (open, P4; off the ENH-3700 critical path since review #7)
- **ENH-3680** — Spool context-monitor.sh history writes (cancelled: remote stays a documented no-op)
- **ENH-3728** — Degrade verdicts for history readers under a remote backend (open)
- **ENH-3729** — Fail-closed failure routing and atomic enrich publish for the sft-corpus loop (open)
- **ENH-3768** — Safe typed decoding of remote marker, verified-cache and live schema-state metadata, with sanitized reader diagnostics (open; extracted from ENH-3682 in review #7)



## Goal

Make the supported remote history surfaces predictable: every entry point serves, refuses or degrades according to the final matrix; no hidden local store, unhandled error or unbounded advisory request obscures that outcome.

## Scope

The eight active children cover the shared test fixture, refusal boundary, central reader guard + `ll-harness` serve, degrade verdicts (ENH-3728), `sft-corpus` failure routing (ENH-3729), shared remote marker/cache/live-state decoding and sanitized reader diagnostics (ENH-3768), hand-built snapshot paths and the advisory prepatch deadline. The cancelled hook spool requires only sibling documentation. Strict CLI/MCP serving and local rebuild/lock work are detached as described below; no implementation of those deferred designs is needed for this epic to close.

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

Remote track (revised 2026-10-07, review #7): **ENH-3677 and ENH-3729 start independently now.** ENH-3768's pure decoder tests need nothing, but its stub-driven cases use the hoisted fixture, so it follows ENH-3677. After ENH-3677, ENH-3657, ENH-3658 and ENH-3768 are independently eligible. ENH-3657 includes the narrow typed-local SQLite reader setup fix (moved from dependent ENH-3700), conversation-target forwarding and explicit relative ctx-stats overrides; its selected-root local tests and intermediate no-shadow-regression test must pass on its own. ENH-3728 requires ENH-3677 + ENH-3657 + ENH-3729 (fixture, selected-root/fallback wiring, and the SFT quality-refusal failure route), and owns direct-schema summary/decisions provenance plus selected-local SFT metadata forwarding. ENH-3700 requires ENH-3657 + ENH-3677 + **ENH-3768** (no longer ENH-3682); it does not wait for ENH-3682, ENH-3728 or ENH-3729. It replaces ENH-3657's compatibility forwarding with the permanent guard and consumes ENH-3768's live-state decoder normalization and sanitized warning. ENH-3682 (P4) requires ENH-3677 + ENH-3768, consumes landed ENH-3720, and is off the critical path; it and ENH-3700 each add one `_connect_readonly` keyword (`best_effort` / `required`) — integrate in either landing order. Sequence ENH-3729 before ENH-3728's edits to the same SFT states, preserving failure routes/atomic publication/path transport. ENH-3658's conditional CT-0 allowlist is removed by ENH-3728; if ENH-3728 lands first, never introduce it, and stale entries fail the gate. Shared backend/base-helper/CLI/docs/mirror edits require integration coordination, not additional artificial dependencies. Merge each slice's rows into the single support table without discarding siblings' rows.

Local track: ENH-3678 → ENH-3698 and independent ENH-3679 are already done; they do not delay remote implementation. Preserve their landed doctor/check-count behavior in ENH-3658. ENH-3699 remains deferred until a spike proves bounded-lock timeout recovery across a newer ingest watermark. Deferred remote serving follows ENH-3700 → ENH-3668 → ENH-3684/3685 if revived.

## Final support matrix

_Current acceptance baseline after review #7 (2026-10-07)._

| Surface | Remote verdict at epic closure | Owner |
|---|---|---|
| `ll-history` analyze/activity/rework/quality/collisions/sessions/root; DB-backed logs; `ll-ctx-stats`; explicit messages DB reader | Refuse, named safe stderr, exit 1; preserve applicable explicit local overrides. Both quality/activity workspace modes preflight all default member targets before aggregation, retaining manifest path precedence and default intent through symlink normalization | ENH-3657 |
| MCP `history_search` | Structured `is_error` refusal against the owning project root | ENH-3657 |
| History summary, decisions generation, automatic messages reader, CT-0 | File/JSONL fallback or skip with one note; summary bypasses all DB metrics/probes and marks loop counts unavailable; messages respects selected `--cwd`, with existing Claude-shaped-only JSONL fallback | ENH-3728 |
| `ll-harness` | Serve an exact-version stamped remote store through existing access policy; advisory reads degrade safely. Per-call required retry/baseline-of/measure/compare/frozen/pin/pin-force reads distinguish successful absence from unavailable history, reuse validated results and fail closed with existing exits | ENH-3700 |
| Packaged SFT stage/enrich | Auto JSONL; remote enrich passes records/metadata through unchanged only when all four DB-quality flags are disabled (packaged defaults); any enabled flag refuses before output and reaches the failure terminal; other stage/enrich failures terminate atomically. Absent stage lineage and later first-record filters are documented limitations, not quality certification | ENH-3728 / ENH-3729 |
| Artifact snapshot route/dashboard/history panel; loop `--serve`; doctor `--trim` | Named refusal/501/unavailable panel or informational skip; server remains usable | ENH-3658 |
| Prepatch base SHA/dirty reads | Per-invocation deadline shared by verification and query on one client (connection-scoped verification completion, no duplicate warm-file-cache request); otherwise `None`. A read-scoped TTL marker suppresses later advisory reads without silencing writes and permits recovery | ENH-3682 (ENH-3720 landed) |
| Shared remote marker/cache/live-state decoding; reader remote diagnostics | Malformed state is a cache miss, inactive marker or fixed typed failure — never a raw conversion error, access evidence or indefinite suppression; remote reader warnings are fixed text with no endpoint/token/SQL | ENH-3768 |
| Context-monitor pressure/handoff writes | Documented remote no-op; reminders and exits unchanged | ENH-3657 (docs; ENH-3680 cancelled) |
| `ll-session recent` / `search` / `redact`; raw ingestion/backfill | Serve (existing behavior). The default relative `--db` reaches the remote store; MCP `history_search` refuses only because its pre-resolve is root-absolute. `redact` landed after review #6 (ENH-3752) and is already documented as supported remotely. Omission of pressure/handoff writes is documented, not absence of all remote consumers | Existing behavior; rows documented by ENH-3657 |

**Rule.** Explicit user-invoked reads refuse under a remote backend; implicit/automatic reads degrade or skip (advisory empty/`None`/file fallback); required harness lookups fail closed. State it once above the public table.

This matrix is the acceptance baseline for the single public table in `docs/reference/CONFIGURATION.md`; link it from CLI/API guides rather than maintaining contradictory promises.

## Plan freeze and review history

**Plan freeze (review #7, 2026-10-07).** Six plan-only reviews (four with an Opus consult) amended the children while no code landed; further plan reviews now cost more than they find. **No review #8.** Start ENH-3677 and ENH-3729 in parallel. Run one `/ll:confidence-check` per child *after its blockers land*, against landed code. Mid-implementation discoveries go to the affected child's Session Log or a follow-up issue — not back into sibling plans or this epic. Reopen planning only if a child's outcome score falls below the 65 gate; ENH-3700's required-lookup phase is the named split candidate.

**Review #7 (code check + `/ll:advise` claude-opus-5-5, confidence 0.80):**

- ENH-3677's planned "exactly one `remote` registration under `scripts/tests`" gate would have failed on landing: two non-copy `remote` fixtures arrived after the audit (`test_raw_redaction.py`, ENH-3752; the BUG-3762 spike). Replaced with a deny-list gate over the root conftest, the six migrated files and nested conftests.
- `ll-session redact` (ENH-3752) landed after the matrix was written and is already documented as supported remotely; matrix and the ENH-3657 support table now carry it with `ll-session recent`/`search`, ingestion and the context-monitor no-op (documentation ownership moved from cancelled ENH-3680 to ENH-3657), plus the explicit-refuse/implicit-degrade rule.
- ENH-3682 (P4) had accreted decoder hardening and sanitized diagnostics that P3 ENH-3700 actually consumed. Extracted to **ENH-3768**; ENH-3700 is `blocked_by` it instead of ENH-3682, so no P3 issue is gated on a P4 one and ENH-3700 no longer waits on the `libsql.py` `_guard` seam.
- Spot-checked and still true: `SqliteBackend.ensure_schema` drops a typed target via `_local_path`; `open_history_readonly` has no guard/best-effort yet; `_connect_readonly` still interpolates raw `{exc}`; ~69 `except sqlite3.*` versus 4 `HistoryError` catches in `history_reader`; `sft-corpus.yaml` still masks stage failure; the five `ll-harness` and eight `ll-history` resolve sites; ENH-3720's `Deadline` and stub fault controls exist. `ll-session refresh` already refuses on remote and `ll-doctor` guards with `_remote_target()`.
- Opus dissent, not adopted: fold ENH-3768 into ENH-3657 (refuse-boundary vs telemetry correctness are distinct); an allowlist-keyed fixture gate (not worth the machinery under closest-fixture semantics). Opus kept ENH-3700 as one issue; it now carries an ordered-commit plan and a confidence-gated split rule.

**Earlier reviews #1–#6 (2026-10-02..06).** Full narrative and probe evidence are in this file's git history before the review #7 commit and in each child's Session Log. Outcomes that still bind:

- #1/#2: narrowed to refusal boundary + reader guard + prepatch budget; cancelled ENH-3680 (documented no-op); detached ENH-3678/3679/3698/3699 and deferred ENH-3668/3684/3685; split ENH-3700 into ENH-3700/3728/3729; ENH-3720 landed.
- #3: required harness lookups use a per-call opt-in failure channel (no ambient strict mode); warm-file-cache single verification seam; SFT quality refusal; selected-root coverage.
- #4: typed-local reader setup moved into ENH-3657; direct-schema summary/decisions provenance in ENH-3728; env presence never exempts an unrelated absolute shadow path; malformed marker/cache state is advisory.
- #5: workspace quality **and** activity share one remote-member preflight in ENH-3657; verified-cache payload validation.
- #6: ENH-3657's setup fix must not create an intermediate shadow-file regression (legacy untyped-default path retained until ENH-3700's guard); live-metadata decode errors normalized; selected SFT metadata target; sentinel/run_dir transport in ENH-3729; CT-0 stale-exemption gate in ENH-3658.

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
- [ ] Malformed/future/nonfinite marker/cache timestamps, invalid verified-cache version/project/stamp payloads and expected bookkeeping/setup failures preserve the advisory read contract. Malformed cache evidence cannot authorize access by numeric coercion; normal bounded verification still applies. Required filesystem/invalid-row failures produce safe validation refusal. Wrong-shape SFT records and non-regular sentinel paths reach the failure terminal without raw-record output, traceback or partial publication. (ENH-3768 owns the shared decoders; ENH-3682 consumes them.)
- [ ] Remote reader warnings and the shared marker/cache/live-state decoders are safe and advisory (ENH-3768): fixed-text diagnostics with no endpoint/token/SQL, and malformed state never raises a raw conversion error or suppresses indefinitely.
- [ ] ENH-3657's setup fix introduces no intermediate shadow-file regression before ENH-3700; the final guard replaces its compatibility forwarding. Malformed live metadata remains a typed failure before cache admission, with no raw value or transport marker. Backend success/suppression contracts stay distinct from advisory `None`. (The live-metadata clause is ENH-3768's.)
- [ ] Source-bearing local SFT enrichment reads real env/config-selected metadata with a missing or stale default DB; ordinary stage output's absent lineage and later filter limitations are documented. Present malformed/dangling sentinels fail safely before invocation with a recovery reason; valid timestamps are single quoted arguments and touched stage/enrich paths tolerate spaces/quotes/metacharacters.
- [ ] The reader importer inventory, hazard gate allowlists, support docs and dependency backlinks agree with the implemented scope. Stale confidence scores are removed; re-run readiness checks on revised issues before implementation, after their prerequisites land. The public support table carries the existing `ll-session recent`/`search`/`redact`, ingestion and context-monitor rows and the refuse-explicit/degrade-implicit rule.
- [ ] The local authoritative suite (`python -m pytest scripts/tests/`) passes for the implementation; no unsupported reader message promises deferred remote serving.

## Status

**Open** | Created: 2026-10-02 | Priority: P3

## Session Log

- EPIC-3693 open-child review #7 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-07 - code drift check: ENH-3677 fixture gate fixed (two new non-copy `remote` fixtures); `ll-session redact`/search/ingestion/context-monitor rows added to the matrix; decoder hardening + sanitized diagnostics extracted from ENH-3682 into ENH-3768 so P3 ENH-3700 no longer waits on a P4 issue; plan freeze declared (no review #8; ENH-3677 + ENH-3729 start now); review history compacted (full text in git history). Implementation not performed.
- EPIC-3693 open-child review #6 + `/ll:advise` (opus, user_requested, confidence 0.62) - 2026-10-06 - all seven children reviewed; six plans amended for safe intermediate setup, live decoder errors, selected SFT metadata, sentinel/path handling and exemption/client ordering. Fixture plan retained; no new child/dependency or implementation. Follow-up consult skipped at the existing task budget; ENH-3729 stale scores cleared.
- EPIC-3693 open-child review #5 - 2026-10-05 - seven open children reviewed; workspace quality/activity preflight with manifest provenance and complete verified-cache validation added to ENH-3657/3682, scope/risk estimates synchronized on ENH-3657/3682/3700/3728. No new child/dependency or implementation; fresh Opus consult skipped at existing 3/3 session budget.
- EPIC-3693 open-child review #4 - 2026-10-05 - five child plans amended for prerequisite ordering/local provenance, actual env selection, malformed marker/cache state and safe SFT input failures; ENH-3677/3658 retained. Fresh Opus consult skipped at the existing 3/3 chat budget; no new advisor score or implementation.
- EPIC-3693 open-child review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - all seven child files and epic acceptance/order updated; required-read gaps, cache seam, SFT quality refusal, selected-root coverage and dependency cleanup; implementation not performed

- EPIC-3693 open-child review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - five child plans amended and external ENH-3720 dependency reconciled; implementation not performed
- EPIC-3693 review #2 + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - split ENH-3700 into ENH-3700/3728/3729; ENH-3720 landed; ENH-3682 marker/ordering fixed; implementation not performed
