---
id: EPIC-3563
title: Model Capability Hints
type: EPIC
priority: P2
status: open
captured_at: "2026-09-24T18:44:15Z"
discovered_date: 2026-09-24
discovered_by: link-epics
relates_to: []
---

# EPIC-3563: Model Capability Hints

## Summary

Group of 5 related issues: resolving model capability hints for loop execution, skill/agent frontmatter, dispatch wiring, and validation.

## Motivation

Loop states, and later skills/agents, should be able to declare *what kind* of model they need (`coding`, `reasoning`, `burst`) instead of hard-coding host model IDs, so a loop moves between hosts without edits. Unsupported combinations must fail explicitly, never silently fall back to a default model.

## Goal

A loop can declare `model_hint: coding|reasoning|burst` on a state or its `llm` block. The hint resolves to a model the effective backend can use, on every supported loop dispatch path. An unsupported combination fails explicitly. The same loop runs unedited on hosts with a built-in mapping (`claude-code`, `anthropic-api`); every other supported host needs a one-time `orchestration.model_hints` entry, validated by `ll-doctor` (ENH-3641).

## Scope

In: loop state/`llm` hint declarations, the resolver with built-in `claude-code`/`anthropic-api` (and test-only fake-host) mappings, the `orchestration.model_hints` override, dispatch/lifecycle wiring with selection diagnostics, validate-time warnings, and docs. Deferred: skill/agent frontmatter hints (ENH-3533). Out: new hint vocabulary, run-level hint flags, concrete model IDs for non-Claude hosts, run-time catalog probes or heuristics (e.g. models.dev, `codex debug models` at dispatch), cost routing. Follow-ups: ENH-3641 (doctor-time catalog check, not required for closure); ENH-3642 (Codex effort-based built-in, deferred until a shipped loop declares `model_hint`).

## Impact

- **Priority**: P2 — portability enhancement; no shipped loop declares a model today, so nothing is broken.
- **Effort**: Medium to high — three sequential loop-execution children plus a gated skill/agent follow-up.
- **Risk**: Medium — precedence or backend mismatches can silently select the wrong model; the children guard this with fail-fast errors and argv-level tests.
- **Breaking Change**: No — no-hint loops keep current precedence, argv and defaults.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Children

- **ENH-3527** — Resolve model capability hints for loop execution (open)
- **ENH-3533** — Model capability hints for skill and agent frontmatter (open)
- **ENH-3547** — Wire model hint resolution through loop dispatch and lifecycle (open)
- **ENH-3548** — Validate-time model hint warnings and hint documentation (open)
- **BUG-3541** — Model aliases table maps opus and fable to superseded model IDs (done)
- **ENH-3638** — Show hint-resolved model selection in ll-loop header and info (open)
- **BUG-3640** — Generated host mirrors ship Claude model aliases as the model (open)
- **ENH-3641** — ll-doctor check validates configured model_hints against the host model catalog (open)
- **ENH-3642** — Built-in Codex model_hint mapping via host-default model and reasoning effort (deferred)


## Sequence

1. ~~BUG-3541~~ — done; `MODEL_ALIASES` now holds current IDs
2. ENH-3527 — declaration, resolver, config (including test-only `fake`/`fake-minimal` mappings)
3. ENH-3547 — dispatch, lifecycle, diagnostics
4. ENH-3548 — validate warnings and docs. The warnings half needs only ENH-3527 and can start once it lands; the docs half waits for ENH-3547's tested support matrix
5. BUG-3640 — stop generated host mirrors shipping Claude aliases (`model = "sonnet"`) as the model; independent of the other children, can run any time
6. ENH-3533 — skill/agent frontmatter hints, generation-time only (Option A decided); blocked by BUG-3640 and **not** required for epic closure
7. ENH-3641 — `ll-doctor` model-hints check; independent, can run once ENH-3527 has landed (it has)
8. ENH-3642 — deferred; Codex effort-based built-in, starts with a spike when a shipped loop declares `model_hint`

## Closure Criteria

- [ ] BUG-3541, ENH-3527, ENH-3547 and ENH-3548 are done.
- [ ] ENH-3533 is done, or explicitly deferred/cancelled with a recorded reason.
- [ ] A fixture loop with `coding`/`burst` states runs unedited under the fake host, `claude-code` and `anthropic-api` (ENH-3547 portability proof).

## Verification Notes

Pre-implementation review 2026-09-25 found these gaps and fixed them in the child issues:

- The fake host had no hint mapping. It is excluded from `RUNTIME_HOST_CAPABILITIES`, and `FakeHostRunner` dropped `model` from argv. Fixed in ENH-3527 and ENH-3547.
- Evaluators have no SDK path, so evaluator hints resolve against the CLI host only (ENH-3527, ENH-3547, ENH-3548).
- An ENH-3527 criterion asserted argv behind its own not-yet-supported guard; moved to ENH-3547.
- `validate_fsm` receives no host or `model_hints`; the plumbing is now specified in ENH-3548.
- Resume scope decided in ENH-3547.

Non-Claude mapping review 2026-09-28 (web research plus a second-model consult via `/ll:advise`, Fable 5.1, confidence 0.8): no shared cross-tool role registry exists, and tools that pick models by role (opencode, Crush) still hard-code role lists over their catalogs. A run-time catalog probe or heuristic was rejected as a silent fallback that breaks run reproducibility. Decision: keep config-only for non-Claude hosts, detect stale config values at doctor time (ENH-3641), and pursue only host-owned stable knobs for built-ins, never concrete model IDs (ENH-3642).