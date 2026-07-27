---
id: 2874
title: Generate degraded-mode agent fallbacks for hosts without subagent support, with mandatory disclosure
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
- agents
---

# ENH-2874: Generate degraded-mode agent fallbacks for hosts without subagent support, with mandatory disclosure

Origin: ll-product #ENH-057

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already owns shared per-host infrastructure including skill/command adapters.

## Summary

little-loops' `agents/*.md` assume the host can spawn a subagent. Codex's invocation model is a known asymmetry, and other hosts lack the capability outright — so for those hosts the role simply does not adapt, and the reasoning the agent encodes is silently unavailable.

## Source pattern (external, described not copied)

Mined from `pbakaus/impeccable` (Apache-2.0), which handles this at build time rather than at run time:

- Where a harness declares no subagent capability, the build emits a **degraded-mode reference file generated from the same agent source**, prefixed with a preamble instructing the model to run the role inline.
- The preamble mandates **disclosure**: the model must "disclose the substitution in one line when you report". A degraded run never silently looks like a delegated one.
- Where a host can spawn subagents only with user permission (Codex's case there), it emits an explicit gate instead: ask once, then stop. No retry loop, no repeated prompting.
- Canonical agent prompts carry frontmatter with `tools`, `model: inherit`, `effort`, and a `max-turns` cap, and the same source emits to each host's native format — markdown for some, TOML for others, degraded-mode inline reference files everywhere else.

## Proposed change

1. Add a `subagents` capability to the host-capability map (values along the lines of: native / permission-gated / none).
2. For hosts with `none`, generate an inline-role reference file from the existing `agents/*.md` source, with a preamble that (a) instructs the model to perform the role inline and (b) requires a one-line disclosure that delegation was substituted.
3. For permission-gated hosts, emit the ask-once-then-stop gate rather than an unguarded spawn.
4. Keep a single authored source per agent. The degraded variant is generated, never hand-maintained in parallel.

## Acceptance criteria

- A host declaring no subagent support produces an inline-role reference file for every agent in `agents/`, from the same source as the native format.
- The generated preamble requires disclosure, and a run that substituted inline execution says so in one line in its report.
- A permission-gated host asks at most once and then stops, rather than retrying or proceeding silently.
- No agent role exists in a native format but is missing from a degraded host's output.

## Dependencies

Depends on the declarative host-capability map issue in the same EPIC — the emission path is selected by the capability flag that map introduces. Sequence it second.

## Provenance

Pattern mined from `https://github.com/pbakaus/impeccable` (Apache-2.0). Described and re-implemented, not copied.
