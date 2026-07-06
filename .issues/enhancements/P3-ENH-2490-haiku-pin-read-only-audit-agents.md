---
id: ENH-2490
title: Haiku pin + dense-list template + call budget on read-only audit agents (Claude-adapter-only)
type: ENH
priority: P3
status: deferred
captured_at: '2026-07-05T00:00:00Z'
discovered_date: 2026-07-05
discovered_by: scope-epic
parent: EPIC-2456
relates_to:
- FEAT-2470
- ENH-2471
labels:
- token-cost
- agents
- tier-0
decision_needed: false
---

# ENH-2490: Haiku pin on read-only audit agents

## Summary

Extracted from FEAT-2470 (wozcode **P2**). Pin ~4 read-only audit/search agents to
`model: haiku`, add a `dense_list_template` output convention, and declare a 3–5-call
budget in frontmatter. **Deferred** from the Tier 0 roll-up because — unlike the other
four Tier 0 techniques — this one trades answer quality for token cost with **no quality
gate**, and its cross-host safety story is fragile. The other Tier 0 pieces (P6
verbatim-output rule, P1 edit-batch hook, LogCleaner filter, JSON output helpers) ship in
FEAT-2470 without this coupling.

## Why Deferred

1. **No quality gate.** `codebase-analyzer` ("trace the data flow") and
   `codebase-pattern-finder` demand more reasoning than pure file-location. Downgrading
   them from `sonnet` → `haiku` risks shallower traces / missed cross-file logic, and
   FEAT-2470 / ENH-2471 only measure a **token-cost** delta — nothing measures whether
   answer quality regresses. This issue should not ship until a before/after **quality**
   comparison exists (e.g. hold analyzer/pattern-finder answers on the ENH-2471 locked
   trace set to a rubric, not just a cost number).
2. **Cross-host footgun.** The pin is Claude-adapter-only. On Codex/OpenCode/omp/Gemini,
   `CodexAdapter.emit_agent` (`scripts/little_loops/adapters/codex.py:349–374`) passes the
   raw `model:` string straight to that host's resolver — `"haiku"` could silently route
   to *that host's flagship*, inflating spend (the opposite of intent). Requires each
   host's pin primitive to be confirmed first (per EPIC-2456 § cross-host table, which
   defaults this to *defer*).
3. **Inert frontmatter.** `dense_list_template` and `max_calls` have no consumer today
   (`frontmatter.py:30` accepts any top-level key but nothing reads these). Honoring them
   is downstream work (loop-YAML / agent dispatcher); shipping the fields alone delivers
   no behavior.

## Scope

| Source | Technique | Surface |
|---|---|---|
| wozcode P2 | Haiku pin + dense-list template + 3–5-call budget on read-only audit agents | ~4 `agents/*.md` frontmatter |

**Claude-adapter-only** — do not duplicate the pin speculatively for
Codex/OpenCode/omp/Gemini; a wrong `model:` field could silently route a subagent to a
flagship model (see EPIC-2456 § cross-host table).

## Scope Boundaries

**In scope**:
- Pinning `model: haiku` on the ~4 read-only audit/search agents (Claude adapter only).
- Adding the `dense_list_template` output convention + 3–5-call budget frontmatter fields.
- A quality-comparison gate confirming analyzer/pattern-finder answers don't regress vs `sonnet`.
- Flipping the corresponding `docs/reference/API.md` agent-table rows to `haiku`.

**Out of scope**:
- The other four Tier 0 techniques (P6 verbatim rule, P1 edit-batch hook, LogCleaner filter, JSON output helpers) — those ship in FEAT-2470.
- Duplicating the pin to Codex/OpenCode/omp/Gemini adapters — deferred until each host's pin primitive is confirmed.
- Building a consumer for `dense_list_template` / `max_calls` (they remain inert frontmatter; honoring them is downstream loop-YAML / dispatcher work).

## Current Behavior

Read-only audit/search agents run on default (flagship/sonnet) models with no declared
call budget.

## Expected Behavior

The ~4 read-only audit agents pin `haiku`, carry a `dense_list_template` output
convention, and declare a 3–5-call budget in frontmatter — **behind a quality gate** that
confirms analyzer/pattern-finder answer quality does not regress relative to `sonnet`.

## Acceptance Criteria

- Read-only audit agents pin `haiku`, use the dense-list template, and declare a 3–5-call
  budget in frontmatter.
- A quality comparison (not just cost) confirms `codebase-analyzer` /
  `codebase-pattern-finder` answers do not regress on the ENH-2471 locked trace set.
- The pin is applied **only** to the Claude adapter; `.codex/agents/*.toml` for the pinned
  agents remain `sonnet`.
- `docs/reference/API.md` agent table rows updated to `haiku` for the pinned agents.
- `python -m pytest scripts/tests/` exits 0.

## Integration Map

_Carried over from FEAT-2470's refinement/wiring passes (locator + pattern-finder agents,
2026-07-04 / 2026-07-05):_

### Files to Modify

**Read-only audit agents (Claude-adapter-only):**
- `agents/codebase-locator.md` — already `model: haiku` at line 32; add dense-list template + 3–5-call budget
- `agents/codebase-analyzer.md` — change `model: sonnet` (line 30) → `model: haiku` + add dense-list template + 3–5-call budget (read-only)
- `agents/codebase-pattern-finder.md` — same pattern at line 32 (`model: sonnet` → `haiku`)
- `agents/plugin-config-auditor.md` — same pattern at line 30

> ⚠ Haiku pin is per-adapter; do not duplicate the pin for Codex/OpenCode/omp/Gemini (per
> EPIC-2456 § cross-host table). A wrong `model:` field on a non-Claude host could silently
> route a subagent to a flagship.

### Dependent Files (Callers / Importers)

- `scripts/little_loops/host_runner.py:236–282` + `scripts/little_loops/subprocess_utils.py:329–336` — `model:` from agent frontmatter does NOT auto-flow into `build_streaming`; the orchestration layer must pass `model=` explicitly. This issue only changes frontmatter; the dispatch wiring is downstream.
- `scripts/little_loops/adapters/codex.py:349–374` — `CodexAdapter.emit_agent` reads `fm.get("model")` and dispatches it straight to Codex's resolver. This is the concrete evidence for the "Claude-only" warning: a `model: haiku` on a Codex agent routes to whichever model Codex interprets that string as (likely the flagship).
- `scripts/little_loops/frontmatter.py:30` — flat YAML parser; reads `model:` and any other top-level key as a dict value. Verify it doesn't reject the new `dense_list_template` / `max_calls` keys (it accepts any top-level YAML).

### Documentation

- `docs/reference/API.md:8075–8083` — agent table lists `codebase-analyzer` (sonnet), `codebase-locator` (haiku), `codebase-pattern-finder` (sonnet), `plugin-config-auditor` (sonnet). **Three rows must flip to `haiku`** after the pin lands (`codebase-locator` is already `haiku`). `scripts/tests/test_wiring_reference_docs.py` asserts `### /ll:review-epic` and `| review-epic` strings at lines 158–159 — keep those substrings present when editing.
- `.claude-plugin/plugin.json:22–27` — agent manifest entries for the four agents. The agents' `.md` frontmatter is the source of truth for `model:`; verify the manifest doesn't carry stale model hints (read-only check, do NOT modify unless manifest diverges).

### Configuration / Adapter callers (do NOT modify)

- `.codex/agents/codebase-analyzer.toml`, `.codex/agents/codebase-pattern-finder.toml`, `.codex/agents/plugin-config-auditor.toml` — currently `model = "sonnet"`. Per the Claude-adapter-only constraint they MUST remain `sonnet`. Don't regenerate via `ll-adapt --host codex --apply` for these three until Codex-side model support lands. `.codex/agents/codebase-locator.toml` is already `model = "haiku"`.

### Codebase Research Findings (carried from FEAT-2470)

- **`dense_list_template` / `max_calls` frontmatter are inert today**: grep across
  `agents/*.md` and `skills/*/SKILL.md` found no existing consumer or shared convention —
  this issue introduces the keys for the first time. Honoring them is downstream work.
- **Haiku-pin agent scope verified complete**: the 4-agent list (codebase-locator already
  haiku, codebase-analyzer/codebase-pattern-finder/plugin-config-auditor → haiku) is
  complete against all 9 agents in `agents/*.md`; other agents (`consistency-checker`,
  `loop-specialist`, `workflow-pattern-analyzer`, `web-search-researcher`,
  `prompt-optimizer`) are correctly excluded (not read-only-audit-style).

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.issues/epics/P2-EPIC-2456-token-cost-reduction.md` | Parent epic; Tier 0 spec + § cross-host table (defer-until-confirmed default) |
| `.issues/features/P2-FEAT-2470-tier-0-token-cost-behavioral-quick-wins.md` | Origin issue; ships the other four Tier 0 techniques |
| `thoughts/plans/2026-07-02-token-cost-optimal-techniques.md` | Tier prioritization rationale (wozcode P2) |

## Impact

- **Priority**: P3 — deferred; savings are real but gated on a quality-comparison
  prerequisite and per-host pin confirmation that don't exist yet.
- **Effort**: Small — ~4 agent frontmatter edits + doc table flips, once the quality gate
  is in place.
- **Risk**: Medium — silent answer-quality regression on analyzer/pattern-finder with no
  gate; cross-host mis-routing if the Claude-only constraint is violated.
- **Breaking Change**: No

## Status

**Deferred** | Created: 2026-07-05 | Priority: P3

## Session Log
- Extracted from FEAT-2470 (P2 haiku pin) - 2026-07-05
