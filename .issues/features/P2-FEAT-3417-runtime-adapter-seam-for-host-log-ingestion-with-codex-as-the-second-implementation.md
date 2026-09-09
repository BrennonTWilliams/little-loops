---
id: 3417
title: Runtime-adapter seam for host log ingestion, with Codex as the second implementation
type: FEAT
priority: P2
status: open
discovered_date: '2026-09-08'
labels:
- multi-host
- observability
- testing
---

## Summary

`ll-logs`, `ll-messages`, and `ll-ctx-stats` all reach directly for `~/.claude/projects/<munged-cwd>/`, and nothing in the tree parses a Codex rollout file. That is the observability half of goal 2 going unbuilt while the generation half is already done: `ll-adapt --host codex` ships today, so little-loops writes artifacts for Codex and then cannot read a single Codex session back. Every log-derived capability downstream — goal 6's dataset export, goal 7's quality rollups — silently covers one host while claiming to generalize.

Introduce a session-watcher seam, not a Codex feature. The interface is small and covers the lifecycle only: detect a session for a workspace, watch it, emit typed events, stop. Per-host parsers live behind it and share nothing above it. One implementation then serves `ll-logs`, `ll-ctx-stats`, and any future dashboard, the same way one extension point can serve a CLI and a UI without either knowing about the other.

## The seam is at the lifecycle, and is refused on content

Deliberately keep the seam at the lifecycle and refuse it on content. Tool-call shapes and token accounting do not overlap enough between hosts to justify a common abstraction, and forcing one produces a lowest-common-denominator record that is worse than two honest per-host ones.

Evidence from a visualizer that independently shipped two host integrations against the same two runtimes supports exactly this split. It introduced a four-method session-watcher interface *and* explicitly refused a shared tool summarizer in the same release, recording the reason in a header comment: the two runtimes' tool shapes don't overlap enough. Token counting followed the same rule in the other direction — Codex exposes authoritative token counts, so the estimator was deleted there; Claude Code exposes no equivalent field, so estimation stayed. Two runtimes, two strategies, no forced uniformity.

This is a real counterweight to the standing proposal for a declarative host-adapter schema — a host described as a YAML stanza with capability booleans. That proposal assumes hosts are uniform enough for one schema to describe them. The evidence from two hosts actually implemented is that the *lifecycle* generalizes cleanly and the *content* does not, which suggests the seam belongs at the watcher with per-host content code behind it, rather than at a schema that tries to describe the content. Weigh it when that design decision is actually made; it is not a refutation.

## Sequencing

Sequencing matters and should be stated in the issue rather than discovered during review: build the seam when the second implementation makes the duplication concrete, not in anticipation of it. Codex is that second implementation, so the seam is now earned. The reference implementation followed the same order — the first host was built with no abstraction at all, and the interface arrived only once the second host made the duplication real.

Keeping the Codex watcher free of any UI-framework dependency is what lets one implementation serve `ll-logs`, `ll-ctx-stats`, and a future dashboard without modification.

## Testing

Test the Codex parser against a captured real-shape rollout fixture — actual JSONL from a real session, committed alongside the parser — not hand-minimized stubs. This is complementary to, not a substitute for, the scripted fake-host work: a fake host tests our handling of a sequence we chose, a captured fixture tests our parser against a record shape the vendor chose and can change under us without telling us.

Treat the fixture as perishable and re-capture it periodically. The concrete precedent: a vendor started inlining full base instructions into the first line of its rollout file, that line blew past a consumer's fixed 64KB read buffer, `cwd` extraction failed, and sessions were silently skipped — an empty panel with no error. Neither a scripted fake host nor the existing unit tests would have caught it; re-capturing the fixture would have.

## Relations

Relates to the session-id minting work, which fixes run↔transcript pairing precision above this layer, and to the declarative host-adapter schema proposal discussed above.

## Acceptance Criteria

- A session-watcher interface exists covering the lifecycle only: detect a session for a workspace, watch it, emit typed events, stop.
- Per-host parsers live behind the interface and share no content-level code above it; tool-call shapes and token accounting stay per-host, with the refusal recorded in the code.
- Codex rollout files are parsed as the second implementation, exercising the seam.
- `ll-logs` and `ll-ctx-stats` are served by the one implementation rather than reaching for `~/.claude/projects/` directly.
- The Codex parser is tested against a captured real-shape rollout fixture committed alongside it, with the fixture marked as perishable and a re-capture expectation stated.
