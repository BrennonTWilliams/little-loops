---
id: FEAT-2259
title: Generic host-parameterized conformance harness
type: feature
status: open
priority: P4
discovered_date: 2026-06-24
discovered_by: planning-assessment
parent: EPIC-2257
decision_ref: ARCHITECTURE-049
labels: [host-compat, portfolio, conformance, testing]
relates_to: [FEAT-1721, FEAT-2192]
---

# FEAT-2259: Generic host-parameterized conformance harness

## Summary

Build **one** host-parameterized conformance harness that exercises the
`ll-auto` / `ll-sprint` / `ll-loop` / `ll-action` golden paths against a host
passed as an argument (`--host codex|gemini|omp`), instead of a bespoke
conformance suite per host epic.

Per ARCHITECTURE-049, this replaces the independently-specified per-host
conformance children:
- **FEAT-1721** (Codex conformance)
- **FEAT-2192** (Gemini conformance)
- the omp conformance need (now folded here, not re-specified under EPIC-2258)

## Motivation

Each per-host epic re-derived the same conformance suite. A single harness that
takes a host arg means a new host's conformance coverage is a config row, not a
new issue + new test file.

## Acceptance Criteria

- One harness (CLI or pytest-parametrized) runs the four golden paths against
  any registered host via a `--host`/parametrize arg.
- Produces per-host pass/fail rows consumable by `HOST_COMPATIBILITY.md`.
- Codex and Gemini conformance run through this harness (FEAT-1721 / FEAT-2192
  closed as superseded once it lands).
- Adding a host requires no new conformance code — only a host entry.

## Reference

- `ll-harness` — existing one-shot runner evaluation; likely the integration point.
- `resolve_host()` in `host_runner.py` — host registry the harness parametrizes over.
- FEAT-1721 / FEAT-2192 — the bespoke specs this generalizes.

## Impact

- **Effort**: Medium.
- **Risk**: Low — test-only; no runtime behavior change.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-06-24 | Priority: P4
