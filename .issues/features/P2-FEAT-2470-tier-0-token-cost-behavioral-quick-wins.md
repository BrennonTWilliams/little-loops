---
id: FEAT-2470
title: "Tier 0 token-cost behavioral quick-wins (P6 verbatim-output, haiku pin, edit-batch hook, LogCleaner filter, JSON output helpers)"
type: FEAT
priority: P2
status: open
captured_at: "2026-07-03T00:00:00Z"
discovered_date: 2026-07-03
discovered_by: scope-epic
parent: EPIC-2456
relates_to: [ENH-2471]
labels:
  - token-cost
  - hooks
  - skills
  - agents
  - tier-0
---

# FEAT-2470: Tier 0 token-cost behavioral quick-wins

## Summary

Ship EPIC-2456's Tier 0 layer (~180 LOC): five behavioral techniques that need no
measurement infrastructure and deliver immediate token savings. Per the epic's
prioritization plan (`thoughts/plans/2026-07-02-token-cost-optimal-techniques.md`),
Tier 0 is strictly dominant — it ships before any F-feature.

## Use Case

**Who**: Anyone running `ll-loop` / `ll-auto` / `ll-sprint` on this repo

**Context**: Every loop run pays avoidable token cost from verbose audit output, flagship-model subagents, unbatched edits, noisy tool logs, and unconstrained JSON output

**Goal**: Capture the immediate, infrastructure-free savings tier before any measurement/caching features land

**Outcome**: Lower $/run on every invocation, with the delta measured on ENH-2471's locked trace set

## Scope

| Source | Technique | Surface |
|---|---|---|
| wozcode P6 | Verbatim-output rule in audit skill bodies | ~6 `skills/*/SKILL.md` bodies |
| wozcode P2 | Haiku pin + dense-list template + 3–5-call budget on read-only audit agents | ~4 `agents/*.md` frontmatter |
| wozcode P1 | Edit-batching nudge (`PostToolUse` on Edit/Write/MultiEdit) | `hooks/hooks.json` + new hook module |
| LogCleaner [25] | Anti-event regex + duplicate-window pre-filter on tool/log output | new filter module (~60 LOC) |
| pass-2 #7 | Stop-sequence + prefill JSON output helpers (`extract_between_tags()`, `parse_prefilled_json()`, `rfind('{')` recipe) | new `scripts/little_loops/output/parse.py` (~30 LOC) |

**P2 haiku pin is Claude-adapter-only for now** — do not duplicate the pin
speculatively for Codex/OpenCode/omp/Gemini; a wrong `model:` field could
silently route a subagent to a flagship model (see epic's cross-host table).

## Current Behavior

Audit skills re-summarize instead of quoting verbatim; read-only audit agents run on default (flagship) models with no call budget; edits land one-at-a-time with no batching nudge; tool/log output carries anti-event noise and duplicated windows into context; FSM verdict JSON is emitted unconstrained (no stop-sequence/prefill helpers).

## Expected Behavior

All five Tier 0 techniques active by default: audit skills carry the verbatim-output rule, audit agents pin haiku with a 3–5-call budget, a `PostToolUse` hook nudges edit batching, the anti-event filter trims tool/log output, and `output/parse.py` helpers constrain JSON output.

## Acceptance Criteria

- Verbatim-output rule present in the ~6 audit skill bodies identified during implementation.
- Read-only audit agents pin haiku, use the dense-list template, and declare a 3–5-call budget in frontmatter.
- `PostToolUse` edit-batch hook registered in `hooks/hooks.json`; handler lives under `scripts/little_loops/hooks/` and is covered by `scripts/tests/test_edit_batch_hook.py`.
- LogCleaner-style anti-event/duplicate-window filter module exists with unit tests.
- `scripts/little_loops/output/parse.py` ships `extract_between_tags()` and `parse_prefilled_json()` with `scripts/tests/test_json_output_parse.py`.
- `python -m pytest scripts/tests/` exits 0.

## Verification

Before/after cost delta measured on ENH-2471's locked trace set (measured via
host CLI `usage` block since Tier 1 telemetry isn't online yet). Target: JSON
output helpers deliver 20–40% output-token reduction on FSM verdict strings.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; Tier 0 spec (§ Scope, § Integration Map) |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier prioritization rationale |
| `docs/reference/API.md` | Document `output/parse.py` |

## Impact

- **Priority**: P2 — first-shipped tier of EPIC-2456; strictly dominant (no infra prerequisites, immediate savings)
- **Effort**: Small-Medium — ~180 LOC across skill/agent text edits, one hook module, two small Python modules + tests
- **Risk**: Low — behavioral/additive; no default runtime behavior changes outside automation nudges
- **Breaking Change**: No

## Status

**Open** | Created: 2026-07-03 | Priority: P2

## Session Log

- `/ll:scope-epic` - 2026-07-03T00:00:00Z - filed from EPIC-2456 § Children [TBD-1] (Tier 0 roll-up)
