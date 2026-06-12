---
id: EPIC-1713
title: Pi as full `claude -p` replacement — parity gap tracking
type: epic
status: open
priority: P5
captured_at: "2026-05-26T02:06:59Z"
discovered_date: 2026-05-26
discovered_by: capture-issue
relates_to: [EPIC-1622, EPIC-1463, FEAT-992, FEAT-1480, FEAT-1850]
labels: [epic, captured, pi-adapter, host-compat, tracking, parity]
---

# EPIC-1713: Pi as full `claude -p` replacement — parity gap tracking

## Summary

EPIC-1622 is explicitly a **re-parenting** epic for the 5 Pi-adapter children
left behind when FEAT-992 / FEAT-1474 / FEAT-1477 closed early — its own
text says *"No new scope is added here."* Its scope is hook-compatibility
(2 lifecycle events) plus a `.pi/ll-config.json` probe path plus a wired
`PiRunner` whose `HostCapabilities` are speculative (FEAT-1480 Step 1).

That leaves a substantial gap between "EPIC-1622 done" and the aspirational
goal of **Pi as a first-class `claude -p` replacement**. This epic is the
umbrella tracking those gaps — analogous to EPIC-1463 for Codex — so the
Host Compatibility Matrix and any "Pi parity" prose point at a real issue
link instead of unowned footnotes.

In scope for this epic:

- **Pi CLI headless flag audit** (FEAT-1714) — verify `pi --help` actually
  supports streaming JSON output, bypass-approvals, agent select, tool
  allowlist, and session-resume semantics before `PiRunner.HostCapabilities`
  is set by mirroring Codex. Currently embedded as a one-liner inside
  FEAT-1480 Step 1 with no dedicated tracking.
- **Pi hook-event parity** (FEAT-1715) — Pi's SDK exposes only
  `session_start` and `session_before_compact`. Claude Code wires
  `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`, `SessionEnd`
  and more. context-monitor, optimize-prompt, duplicate-ID checks, and
  related lifecycle automation will not fire on Pi. Likely requires
  upstream pi-mono PRs to expose additional events.
- **Pi conformance test suite** (FEAT-1716) — FEAT-992 candidly says
  commands/skills *"may work via any compatible path fallback Pi supports"*
  — never verified. No test exercises `ll-auto`, `ll-sprint`, `ll-loop`,
  `ll-action` golden paths against Pi to prove behavioral equivalence to
  `claude -p`.

Out of scope (separately owned):

- The 5 EPIC-1622 children themselves (hook compatibility + stub→wired
  `PiRunner`).
- Pi permission-model reconciliation (Pi has no trust dialog; deliberate
  design choice — may warrant a separate ENH if user-facing semantics
  matter).
- Pi MCP server support (no current tracking; capture if/when demand
  arises).

## Children

- **FEAT-1714** — Audit Pi CLI headless flag surface & define `PiRunner` `HostCapabilities`
- **FEAT-1715** — Pi hook-event parity gap (PreToolUse / PostToolUse / UserPromptSubmit / Stop / SessionEnd)
- **FEAT-1716** — Pi `claude -p` conformance test suite (ll-auto / ll-sprint / ll-loop golden paths)
- **FEAT-1850** — Add OmpRunner host runner for oh-my-pi (`omp` CLI)

## Motivation

Without this umbrella, the next time someone asks *"can Pi replace `claude -p`?"*
the honest answer is *"EPIC-1622 closes the plugin-compatibility gap; the
headless-orchestration parity gap is untracked."* That is bad backlog
hygiene: it forces re-discovery of the same gaps in every conversation,
and it leaves FEAT-1480 wiring `PiRunner` speculatively against the Codex
template with no traceable owner for the verification work.

Capturing this epic makes the parity claim measurable. Each child has a
concrete exit criterion; the epic closes when all three children land or
are explicitly closed with rationale recorded in their own files.

## Acceptance Criteria

- All three children have `parent: EPIC-1713` in their frontmatter
- Host Compatibility Matrix Pi column reflects the actual verified
  capability set (no more "may work" prose for commands/skills)
- A `pi` row exists in any "claude -p replacement" docs/decision tables,
  with a status that is either ✓ (capability confirmed), ✗ (capability
  confirmed absent), or a link to a still-open child issue — never
  "unknown"

## Out of Scope

- Implementation of EPIC-1622's 5 children (hook adapter, init skill,
  config probe, docs, `PiRunner` wiring) — those are EPIC-1622's
  authoritative spec
- Re-litigation of the original FEAT-992 plugin-compatibility decisions
- Pi permission-model reconciliation (separate issue if/when warranted)
- Pi MCP server support (separate issue if/when warranted)

## Impact

- **Priority**: P5 — matches the existing Pi-adapter priority tier; no
  signal of urgent user demand for full Pi parity
- **Effort**: Each child is independently small-to-medium; epic as a
  whole is medium (gated on upstream pi-mono PRs for hook event parity)
- **Risk**: Low — additive tracking; no behavioral change until children
  ship
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Authoritative Pi capability matrix; this epic's exit criterion ties to its accuracy |
| `docs/ARCHITECTURE.md` | `PiRunner` component table and `hooks/adapters/` tree listing |

## Labels

`epic`, `pi-adapter`, `tracking`, `parity`, `host-compat`, `captured`

## Status

**Open** | Created: 2026-05-26 | Priority: P5

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: VALID** — Accurate tracking epic:
- All 3 children (FEAT-1714, 1715, 1716) confirmed open ✓
- `docs/reference/HOST_COMPATIBILITY.md` exists and tracks parity ✓
- Pi conformance test suite not created; Pi audit research docs not created ✓

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:49:03 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:18 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-26T02:06:59Z - `3eaac8be-eba9-48b8-a2d9-322df5114921.jsonl`

## Audit Note (2026-06-12)

- **FEAT-1850 detached**: the `omp` (oh-my-pi) runner targets a different
  host CLI than `pi` (pi-mono) and is outside this epic's parity-gap scope;
  it now stands alone in the backlog. Its P3 priority had also inverted the
  epic's P5 children in scheduling order.
- **Discovery-surface coverage**: FEAT-1714's scope was expanded (2026-06-12)
  to add the Pi column to HOST_COMPATIBILITY.md's discovery-surface and
  Runner Capabilities tables — the FEAT-1487-for-Codex equivalent required by
  this epic's third acceptance criterion (no "unknown" Pi cells).
