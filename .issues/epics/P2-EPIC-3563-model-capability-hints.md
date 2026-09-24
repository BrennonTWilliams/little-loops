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

## Children

- **ENH-3527** — Resolve model capability hints for loop execution (open)
- **ENH-3533** — Model capability hints for skill and agent frontmatter (open)
- **ENH-3547** — Wire model hint resolution through loop dispatch and lifecycle (open)
- **ENH-3548** — Validate-time model hint warnings and hint documentation (open)
- **BUG-3541** — Model aliases table maps opus and fable to superseded model IDs (open)

## Sequence

1. BUG-3541 (blocks ENH-3527)
2. ENH-3527 — declaration, resolver, config
3. ENH-3547 — dispatch, lifecycle, diagnostics
4. ENH-3548 — validate warnings and docs (blocked by ENH-3547)
5. ENH-3533 — skill/agent frontmatter; needs a spike/decision first and is **not** required for epic closure

## Closure Criteria

- [ ] BUG-3541, ENH-3527, ENH-3547 and ENH-3548 are done.
- [ ] ENH-3533 is done, or explicitly deferred/cancelled with a recorded reason.
- [ ] A fixture loop with `coding`/`burst` states runs unedited under `claude-code` and `anthropic-api` (ENH-3547 portability proof).
