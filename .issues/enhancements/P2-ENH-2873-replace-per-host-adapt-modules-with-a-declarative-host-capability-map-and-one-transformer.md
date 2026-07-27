---
id: 2873
title: Replace per-host adapt modules with a declarative host-capability map and one transformer
type: ENH
parent: EPIC-2257
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
discovered_source: https://github.com/pbakaus/impeccable
labels:
- multi-host
- ll-adapt
---

# ENH-2873: Replace per-host adapt modules with a declarative host-capability map and one transformer

Origin: ll-product #ENH-056

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already owns shared per-host infrastructure including skill/command adapters.

## Summary

`scripts/little_loops/adapt/` carries a module per host — `codex.py`, `gemini.py`, `omp.py` — and `pyproject.toml` still ships the legacy `ll-adapt-skills-for-codex` / `ll-adapt-agents-for-codex` entry points alongside the generic `ll-adapt --host`. Adding a host therefore means writing code, and each new module is another place host-specific knowledge can drift out of sync with the others.

## Source pattern (external, described not copied)

Mined from `pbakaus/impeccable` (Apache-2.0), which covers 15 harnesses with **zero per-provider code**:

- A flat `PROVIDERS` config map holds one entry per harness (claude-code, cursor, codex, gemini, kiro, opencode, and others). Each entry declares: the harness's config directory, which inline provider tag blocks to keep or strip, which optional frontmatter fields that harness actually reads, the agent file format, whether it emits hooks, and where its hooks manifest lives.
- A single generic `createTransformer(config)` factory consumes an entry. There is no per-provider transformer module.
- Frontmatter emission is likewise data: a field-spec table crossed with each harness's declared readable-fields list.
- A hand-maintained capability matrix document is the human source of truth the config entries are derived from. It carries a **"last verified" date and an explicit point-in-time warning**, on the reasoning that a capability table is a snapshot of other vendors' products and silently goes stale.

## Proposed change

1. Introduce a declarative host-capability map: one entry per host, declaring config dir, output formats, which frontmatter fields the host reads, agent format, and capability flags (hooks, subagents, and so on).
2. Collapse `codex.py` / `gemini.py` / `omp.py` into one generic transformer driven by that map. Host-specific behavior that cannot be expressed as data is the signal that the map needs another field — not that the host needs a module.
3. Reduce the legacy `ll-adapt-skills-for-codex` / `ll-adapt-agents-for-codex` entry points to thin aliases over `ll-adapt --host codex`.
4. Make `docs/reference/HOST_COMPATIBILITY.md` the human-facing matrix the map derives from, and add a "last verified" date plus a point-in-time warning to it. The map and the doc must not be independently maintained sources that can disagree.

## Acceptance criteria

- Adding a new host requires a config-map entry and documentation, and no new module under `scripts/little_loops/adapt/`.
- `codex`, `gemini`, and `omp` adaptation produce byte-identical output to the current per-host modules for the existing skill/agent corpus, or every difference is explained and intentional.
- The legacy per-host entry points still work and dispatch through the generic path.
- `docs/reference/HOST_COMPATIBILITY.md` carries a last-verified date, and the relationship between it and the config map is stated (which one is authored, which derived).

## Notes

Prerequisite for the degraded-mode fallback issue in the same EPIC: that feature selects its emission path from a capability flag this map introduces.

## Provenance

Pattern mined from `https://github.com/pbakaus/impeccable` (Apache-2.0). Described and re-implemented, not copied.
