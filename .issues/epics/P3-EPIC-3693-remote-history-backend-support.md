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
---

# EPIC-3693: Remote History Backend Support

## Summary

Make an opt-in remote (libSQL) history backend fail cleanly instead of silently: reader CLIs refuse with a named verdict instead of a traceback, no reader creates a shadow local `.ll/history.db`, hand-built `history.db` paths classify against the project root, and best-effort prepatch reads are time-budgeted. Narrowed 2026-10-02 after an Opus pre-implementation review (BUG-3652's follow-ups).

**Closure criterion:** each audited entry point has a documented serve/refuse/degrade verdict, creates no shadow local DB, and exposes no endpoint/token or unhandled traceback. Intentional advisory empty results and skipped writes remain permitted where stated below; an unsupported user-facing reader must not look like a successful empty query. Broader strict read serving (ENH-3668/3684/3685) is deferred; the limited `ll-harness` best-effort serving in ENH-3700 is in scope. Refused rows say "not supported with a remote backend" and promise no follow-up.

## Children

- **ENH-3677** — Hoist the shared remote history-backend test fixture into conftest.py (open)
- **ENH-3657** — Reader CLI refusal boundary and refuse sites (3657a) (open)
- **ENH-3700** — Central reader guard and serve/degrade verdicts (3657b) (open)
- **ENH-3658** — Handle hand-built history.db paths under a remote history backend (open)
- **ENH-3682** — Budget best-effort remote prepatch history reads (open)
- **ENH-3680** — Spool context-monitor.sh history writes (cancelled: remote stays a documented no-op)

## Goal

Make the supported remote history surfaces predictable: every entry point serves, refuses or degrades according to the final matrix; no hidden local store, unhandled error or unbounded advisory request obscures that outcome.

## Scope

The five active children cover the shared test fixture, refusal boundary, central reader guard and selected fallbacks, hand-built snapshot paths and advisory prepatch deadline. The cancelled hook spool requires only sibling documentation. Strict CLI/MCP serving and local rebuild/lock work are detached as described below; no implementation of those deferred designs is needed for this epic to close.

## Impact

- **Priority:** P3 — correctness of opt-in remote history support.
- **Effort:** Multiple independently reviewable reader, artifact and advisory slices.
- **Risk:** The central guard changes the reader failure contract; recorded importer coverage and local override tests constrain the blast radius.
- **Breaking Change:** Unsupported remote readers acquire explicit refusal output; local behavior remains unchanged.

## Detached / deferred (not children; `relates_to` this epic)

- **ENH-3678** (P2) and **ENH-3679** (P3) — local-store rebuild gating / lock-wait work; detached so the P2 fix and FEAT-3561 are not held behind P4 remote work by the epic-branch merge rule. Their follow-ons ENH-3698 (size gate, pending notice) and ENH-3699 (single-flight, deferred) hang off ENH-3678.
- **ENH-3668**, **ENH-3684**, **ENH-3685** — remote read serving (strict-read infra, `ll-history` flips, MCP/SFT); deferred, detached (deferred is non-terminal, so keeping them parented would strand the epic branch). Revive when remote read demand exists.

## Implementation order

Remote track: ENH-3677 → ENH-3657 → ENH-3700. ENH-3658 and ENH-3682 each require ENH-3677; they can proceed independently of the refusal slice, but prefer ENH-3682 after ENH-3700 because both edit the reader seam. ENH-3658's CT-0 allowlist exists only until ENH-3700 lands; if the seam lands first, do not introduce that temporary entry.

Local track: ENH-3678 → ENH-3698, with ENH-3679 independent of remote readers. Sequence `cli/doctor.py` / `CLI.md` check-count edits in ENH-3679, ENH-3698 and ENH-3658 when integrating; shared-file ownership is not an additional functional dependency. ENH-3698 must land before any `REBUILD_DERIVE_VERSION` bump. ENH-3699 remains deferred until a spike proves bounded-lock timeout recovery across a newer ingest watermark. Deferred remote serving follows ENH-3700 → ENH-3668 → ENH-3684/3685 if revived.

## Composition Review

_Reviewed 2026-10-02 against the code and Opus/Sonnet critiques; issue-plan amendments applied before implementation._

Retain ENH-3677, ENH-3657, ENH-3700, ENH-3658 and ENH-3682 as the active remote-support slices. The refusal boundary and risky reader seam are separate reviews; the fixture is their test prerequisite. Cancel ENH-3680's spool and document the existing remote omission, acknowledging that remote recent/search consumers already exist but no live control-flow dependency was found. Detach ENH-3678/3679 and the rebuild follow-ons from this epic's branch; retain their local-store value. ENH-3699 stays deferred until its watermark/restart recovery spike is proven. Defer/detach ENH-3668/3684/3685 until demonstrated strict remote-read demand; their retained plans specify safe error, target and atomic SFT contracts if revived.

Revised issues with cleared/missing confidence scores require a new confidence check before implementation; planned tests are not passing evidence. No child is claimed implementation-ready merely because its prose now validates.

## Final support matrix

| Surface | Remote verdict at epic closure | Owner |
|---|---|---|
| `ll-history` analyze/activity/rework/quality/collisions/sessions/root; DB-backed logs; `ll-ctx-stats`; explicit messages DB reader | Refuse, named safe stderr, exit 1; preserve applicable explicit local overrides | ENH-3657 |
| MCP `history_search` | Structured `is_error` refusal against the owning project root | ENH-3657 |
| History summary, decisions generation, automatic messages reader, CT-0 | Documented file/JSONL fallback or skip with one note | ENH-3700 |
| `ll-harness` | Best-effort remote serving; exact/behind/ahead stamped schema and read-only token (`check_access(write=False)` policy); foreign/auth/uninitialized/unavailable/query failure degrades as documented | ENH-3700 |
| Packaged SFT stage/enrich | Auto JSONL and explicit remote unenriched passthrough; unrelated errors fail the pipeline atomically | ENH-3700 |
| Artifact snapshot route/dashboard/history panel; loop `--serve`; doctor `--trim` | Named refusal/501/unavailable panel or informational skip; server remains usable | ENH-3658 |
| Prepatch base SHA/dirty reads | Best-effort remote data within one cumulative telemetry deadline, otherwise `None`; TTL marker suppresses repeat requests | ENH-3682 |
| Context-monitor pressure/handoff writes | Documented remote no-op; reminders and exits unchanged | ENH-3680 (cancelled) |
| Existing backend-aware `ll-session recent`/search queries | Existing remote support retained; omission of pressure/handoff writes is documented, not absence of all remote consumers | Existing behavior |

This matrix is the acceptance baseline for the single public table in `docs/reference/CONFIGURATION.md`; link it from CLI/API guides rather than maintaining contradictory promises.

## Acceptance Criteria

- [ ] All active children are `done` or deliberately `cancelled`; deferred/detached work is not required to close the epic.
- [ ] Every matrix row has remote/local tests for its actual entry point; foreign cwd and local override cases preserve owning-project resolution and create no shadow `.ll/history.db`.
- [ ] Unsupported readers return explicit safe refusals; documented advisory fallbacks preserve stdout contracts and emit only their designated safe warning/note channel.
- [ ] Cold and warm prepatch reads share one cumulative deadline; open and mid-query failures never escape the advisory path.
- [ ] Dashboard 501 is rendered safely and stops polling; initial remote pages skip local snapshot work while serving continues.
- [ ] Stage/enrich failures reach `terminal: true, failure: true`, publish no partial enrichment and never reach filter/publish/success sentinel.
- [ ] The reader importer inventory, hazard gate allowlists, support docs and dependency backlinks agree with the implemented scope. Stale confidence scores are removed; re-run readiness checks on revised issues before implementation, after their prerequisites land.
- [ ] The local authoritative suite (`python -m pytest scripts/tests/`) passes for the implementation; no unsupported reader message promises deferred remote serving.

## Status

**Open** | Created: 2026-10-02 | Priority: P3
