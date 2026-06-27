---
id: EPIC-2258
title: oh-my-pi (omp) host adapter — tracking
type: EPIC
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2257
decision_ref: ARCHITECTURE-048
labels: [epic, host-compat, omp, pi-adapter, tracking]
relates_to: [EPIC-2257, EPIC-2178]
---

# EPIC-2258: oh-my-pi (omp) host adapter — tracking

## Summary

First-class host-adapter epic for the [oh-my-pi](https://github.com/can1357/oh-my-pi)
`omp` CLI. Promoted from the lone FEAT-1850 (which now becomes this epic's
runner child) per the 2026-06-24 planning assessment. oh-my-pi is an actively
maintained pi-mono superset fork (MCP support, 40+ providers, richer hook
events, LSP/DAP, subagents, 9.3k stars) and **supersedes vanilla Pi** — the
two Pi epics (EPIC-1622, EPIC-1713) were cancelled and their effort routes
here.

Sequenced **after** Gemini (EPIC-2178) per the host order (ARCHITECTURE-048).

## Goal

omp users can run `ll-auto`, `ll-sprint`, `ll-loop`, `ll-action`, and FSM
loops with `LL_HOST_CLI=omp`, with hook lifecycle events firing correctly, and
a fully-populated `omp` column in `HOST_COMPATIBILITY.md` (no unknown cells).

## 4-layer adapter pattern

Follows the established runner → adapter → config probe → matrix shape proven
by Codex/Gemini:

1. Runner — `OmpRunner` in `host_runner.py` (FEAT-1850).
2. Hook adapter — `hooks/adapters/omp/` (FEAT-2261).
3. Config probe — `.omp` / oh-my-pi config candidate (FEAT-2262).
4. Parity matrix — `omp` column in `HOST_COMPATIBILITY.md` (tracked per child).

Plus hook-event parity (FEAT-2263, absorbing the cancelled FEAT-1715 intent).

## Generic shared infrastructure (NOT duplicated here)

Per ARCHITECTURE-049, omp does **not** get its own conformance suite or
skill/command adapter. Those route through the generic components under
EPIC-2257:

- Conformance → **FEAT-2259** (generic host-parameterized harness; run with
  `--host omp`).
- Skill + command adaptation → **FEAT-2260** (generic `--host omp`).

## Children

- **FEAT-1850** — `OmpRunner` core: headless flag audit + runner wiring + tests
- **FEAT-2261** — omp hook adapter (`hooks/adapters/omp/`)
- **FEAT-2262** — omp config probe (`.omp` config candidate in `_config_candidates()`)
- **FEAT-2263** — omp hook-event parity audit (absorbs cancelled FEAT-1715 intent)

## Acceptance Criteria

- `LL_HOST_CLI=omp` resolves to `OmpRunner`; `omp` on PATH auto-detected.
- `session_start` + at least one tool-lifecycle hook intent fire on omp.
- `ll-auto` processes ≥1 issue end-to-end via omp.
- `omp` column in `HOST_COMPATIBILITY.md` has no unknown cells (✓ / ✗-linked / N/A).
- Conformance + skill/command coverage delivered via FEAT-2259 / FEAT-2260
  (`--host omp`), not bespoke omp-only issues.

## Impact

- **Priority**: P4 — same tier as Gemini, sequenced after it.
- **Effort**: Medium (aggregate) — runner + hook adapter are the bulk.
- **Risk**: Low — additive; no existing runner modified.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
