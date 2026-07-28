---
id: ENH-2874
title: Generate degraded-mode agent fallbacks for hosts without subagent support, with mandatory disclosure
type: ENH
parent: EPIC-2257
priority: P2
status: open
discovered_date: 2026-07-27
blocked_by:
- ENH-2873
labels:
- multi-host
- ll-adapt
- agents
---

# ENH-2874: Generate degraded-mode agent fallbacks for hosts without subagent support, with mandatory disclosure

Origin: ll-product #ENH-057

Parent EPIC: EPIC-2257 (multi-host generalization — portfolio coordination), which already
owns shared per-host infrastructure including skill/command adapters.

## Summary

little-loops' `agents/*.md` encode roles the host is expected to spawn as subagents. Where
a host cannot spawn one, the role does not adapt at all and the reasoning it encodes is
silently unavailable on that host. Generate a degraded-mode inline-role file from the same
agent source, with a preamble that mandates one-line disclosure so a degraded run never
reads like a delegated one.

## Current Behavior

`adapters/gemini.py` hard-stubs agent emission behind `_AGENT_STUB_MSG` ("gemini agent
emission not yet stable — Gemini agents are a preview feature; open a PR when they exit
preview"), so no Gemini artifact exists for any role in `agents/`. `adapters/omp.py` raises
for every artifact kind. `adapters/codex.py` emits agent TOML with derived sandbox mode and
MCP servers. There is no fallback path anywhere: a host either gets native agent artifacts
or gets nothing, and nothing in the generated output tells a model that a role it cannot
delegate should be run inline.

## Expected Behavior

Every host with a working emitter gets an artifact for every role in `agents/`: the native
format where the host supports subagents, a generated inline-role reference file where it
does not. The degraded file is generated from the same authored source as the native one —
never a hand-maintained parallel copy — and its preamble instructs the model to perform the
role inline **and** to disclose the substitution in one line when it reports.

## Proposed Change

1. **`subagents` capability flag** on ENH-2873's capability map. Start with two values —
   `native` and `none` — and add a third only if step 2 below finds a host that genuinely
   needs it (see Open Question).

2. **Verify the permission-gated premise before building for it.** The origin write-up
   asserts Codex needs an "ask once, then stop" gate. Codex has first-class custom agents;
   the known asymmetry with Claude Code is that invocation is *spawn-based rather than
   flag-based*, which is not the same thing as a permission gate. Confirm against the
   current Codex CLI before implementing a tri-state; if no host needs it, ship the
   two-value flag and drop the gate entirely. Building an ask-once gate for a constraint
   that does not exist is worse than not building it.

3. **Degraded emitter path in `adapters/core.py`** — for a host whose entry declares
   `subagents: none`, `process_agents` writes an inline-role file per `agents/*.md`:
   authored body verbatim, prefixed with a generated preamble. Selected by the capability
   flag, not by a host name check.

4. **The preamble** — a single template (one authored string, not per-host) that (a)
   instructs the model to perform the role inline rather than delegate, and (b) requires a
   one-line disclosure in the report that inline substitution was used.

5. **Output location and discoverability — decide this before implementing.** A generated
   file nothing references is dead weight. Specify, in the capability-map entry: the output
   directory, the filename convention, and how the model reaches the file (referenced from
   the adapted skills? a generated index? the host's own config dir?). Record the choice in
   `HOST_COMPATIBILITY.md`.

## Acceptance Criteria

- [ ] The capability map carries a `subagents` flag, and `process_agents` selects native
      vs. degraded emission from that flag alone — no host-name branches in `core.py`.
- [ ] For a host declaring `subagents: none` **and having a working emitter**, every file in
      `agents/` produces exactly one inline-role output file. A test enumerates `agents/`
      and asserts one-to-one coverage, so a newly added agent cannot silently miss the
      degraded host. `omp` is excluded while its emitter raises, and the exclusion is named
      in the test rather than implicit.
- [ ] The generated preamble contains the inline-execution instruction and the
      one-line-disclosure requirement — asserted **structurally** on the generated file.
      (The behavioral claim "a degraded run actually says so in its report" is model
      behavior at runtime; the local pytest suite cannot gate it. If it is worth checking,
      it belongs in an `ll-harness` eval, tracked separately — not as an AC here.)
- [ ] The degraded file's role content derives from the authored `agents/*.md` source; a
      test asserts the body matches the source, so the two cannot drift.
- [ ] The output path and discovery mechanism are declared in the capability map and
      documented in `HOST_COMPATIBILITY.md`.
- [ ] If step 2 confirms a permission-gated host exists: it asks at most once and then
      stops — no retry loop, no repeated prompting — and a test asserts the generated
      artifact contains no retry construct. If step 2 finds none, the issue closes with
      the two-value flag and this AC is marked N/A with the finding recorded.

## Scope Boundaries

- **In scope**: the `subagents` flag, the degraded emission path in `core.py`, the preamble
  template, the coverage test, and the output-location decision.
- **Out of scope**: implementing the `omp` emitter (ENH-2873 leaves it a stub; this issue
  does not change that); the capability map itself (ENH-2873); runtime enforcement that a
  model actually discloses.
- **Supersedes the Gemini stub deliberately**: `_AGENT_STUB_MSG` in `adapters/gemini.py`
  goes away for degraded emission — Gemini stops raising and starts producing inline-role
  files. That is intended, not a regression of the preview-feature rationale: if Gemini
  agents exit preview later, the host's flag flips to `native` and the native path takes
  over with no change to this work.

## Open Question

Does any supported host actually need permission-gated subagent spawning? Resolve in
step 2 before implementing the tri-state. Default assumption if unresolved: two values
(`native` / `none`).

## Dependencies

Blocked by ENH-2873 (Phase A alone is sufficient — the capability map and its
`subagents` field). Sequence second.

## Impact

- **Priority**: P2 — without it, entire agent roles are invisible on non-Claude-Code hosts,
  and the failure is silent (no artifact, no error, no note).
- **Effort**: Small-to-Medium once ENH-2873 Phase A lands — one emission branch, one
  preamble template, one coverage test. The output-location decision is the long pole.
- **Risk**: Low — purely additive output; the native path is untouched.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-07-27 | Priority: P2
