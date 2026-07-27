---
id: 2878
title: Trace-level assertions in the eval harness, with optional multi-host divergence runs
type: FEAT
parent: EPIC-2856
priority: P1
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
discovered_source: https://github.com/pbakaus/impeccable
labels:
- evals
- ll-harness
---

# FEAT-2878: Trace-level assertions in the eval harness, with optional multi-host divergence runs

Origin: ll-product #FEAT-058

Parent EPIC: EPIC-2856 (rework reduction — design upstream, verify honestly). This issue advances that epic's core premise — make a "verified" signal impossible to fake — by checking a claim against the actual tool-call trace rather than against free-form output the agent authored itself. Sibling to its deterministic pre-patch test-failure check and test-file tamper guard.

## Summary

The current eval surface asserts on **outcomes** and on **recorded** traces: `ll-harness` checks exit codes and semantic criteria, `/ll:create-eval-from-issues` derives tasks from acceptance criteria, and `ll-logs eval-export` plus the trace sets work from logs after the fact. What is missing is assertion on the **live tool-call sequence** a skill produces while it runs — the ability to fail a skill for calling the right tools in the wrong order, or for writing an artifact it should not have touched.

## Source pattern (external, described not copied)

Mined from `pbakaus/impeccable` (Apache-2.0), whose skill-behavior eval tier:

- Inlines the **source** skill file into a real model's system prompt, and gives it bash/read/write/list tools **scoped to a temporary workspace**.
- Asserts on the tool-call trace, not on free-form output — stated flatly as "the trace is the source of truth".
- Pairs this with a workflow-contract test asserting **question order** and **artifact writes** across several end-to-end flows.
- Symlinks the authoring source rather than built output, so edits show up without a rebuild. The trade-off is that unsubstituted build placeholders appear in the reference text — which is acceptable precisely because assertions key on tool calls rather than on content.
- Keeps the scenario list and pass baseline in the suite's own README rather than in the contributor guide, because duplicating it went stale before.
- Is opt-in and separately gated in CI: cheap deterministic suites always run; the paid tier runs only on explicit dispatch.

## Proposed change

Add a trace-assertion mode to the eval harness:

1. Run a skill against a scoped temporary workspace with a restricted tool set.
2. Capture the ordered tool calls — which tool, in what order, against which paths — and assert against a declared expectation.
3. Support contract-style assertions on ordering and on artifact writes, not just on presence of a call.
4. Keep it opt-in and separately gated, alongside the existing deterministic suites rather than inside them.

## Scope constraint (deliberate divergence from the source)

The source runs **four API providers on every eval run**, arguing that "many of the most useful findings come from divergence between providers". Do **not** adopt that as a mandate here. little-loops' provider surface is host CLIs (claude, codex, opencode, pi) through `host_runner`, not raw API providers, and a fixed 4x fan-out on every run is a **cost policy decision, not a feature requirement**.

Instead: make multi-host divergence runs an **opt-in flag**. Hosts that are unavailable or unconfigured must **skip cleanly rather than fail** — the source does get this part right, and an eval suite that hard-fails on a missing host key is unusable in CI.

## Acceptance criteria

- The harness can fail a skill that calls the correct tools in an incorrect order, on a workspace-scoped run.
- The harness can assert that a specific artifact was written, and that an out-of-scope path was not.
- Tool access during a trace eval is confined to the temporary workspace.
- Multi-host divergence is opt-in via a flag; the default run uses one host.
- An unconfigured or unavailable host is skipped with a reported reason, not a failure.
- The scenario list and pass baseline live with the suite, not duplicated into contributor docs.

## Provenance

Pattern mined from `https://github.com/pbakaus/impeccable` (Apache-2.0). Described and re-implemented, not copied.
