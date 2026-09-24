---
id: 3549
title: Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam so every reader is host-agnostic
type: ENH
priority: P2
status: open
discovered_date: '2026-09-24'
labels:
- observability
- multi-host
---

# Migrate ll-logs, ll-messages, and ll-ctx-stats onto the session-watcher seam so every reader is host-agnostic

## Summary

The runtime-adapter seam for host log ingestion shipped in v1.162.0 (FEAT-3417, with Codex as the second implementation), and the write-side divergent-fakes acceptance landed in v1.164.0 (ENH-3456/ENH-3459). The migration itself has not: `ll-logs`, `ll-messages`, and `ll-ctx-stats` still reach directly for `~/.claude/projects/<munged-cwd>/`, so every log-derived surface remains Claude-Code-only by construction even though the seam that fixes it is in the tree. The toolkit can write a Codex session's artifacts and then cannot read a single Codex session back.

Migrate all three readers onto the session-watcher seam — detect, watch, emit typed events, stop — with per-host parsers behind it and one shared fan-in above it, so a Codex session reads back as naturally as a Claude Code one. One implementation serves many readers: `ll-logs`, `ll-messages`, `ll-ctx-stats`, and any future dashboard or export consumer attach to the same seam rather than each re-parsing host transcripts directly. Downstream, the dataset export and the quality rollups consume these readers and remain single-host until this lands.

## Design constraints

- The seam stays at the lifecycle only. Per-host parsers live behind it and share nothing above it. Do not introduce a common abstraction over tool-call shapes or token accounting: the runtimes do not overlap enough for a forced common record to beat two honest per-host ones.
- Discovery failure and genuine absence must remain distinguishable after the migration. A workspace whose sessions exist on disk but match nothing renders a named-cause warning, not an empty result; the migration must not regress that behavior where it exists today.
- The Codex parser is tested against a captured real-shape rollout fixture, treated as perishable — vendor shape drift is one re-capture away from detection. The fixture complements, not replaces, the scripted fake hosts.

## Acceptance criteria

- The divergent fakes pass on the **read** side, not only the write side: the composition test drives both fakes' session records through the migrated readers, proving the readers host-agnostic rather than asserting it.
- A Codex session for the current workspace appears in `ll-logs` and `ll-messages` output with the same fidelity as a Claude Code session over the same period.
- `ll-ctx-stats` carries per-observation provenance for the records it counts: where a host exposes authoritative token counts they are read, and where it does not the figure is labeled an estimate (companion work: ENH-3528 and its ingestion splits ENH-3532/ENH-3534).
- No reader in the migrated set reaches for `~/.claude/projects/` directly; a mechanical check (grep or import rule) proves it.
