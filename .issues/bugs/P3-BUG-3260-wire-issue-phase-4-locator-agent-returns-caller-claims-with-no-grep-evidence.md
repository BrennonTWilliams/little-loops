---
id: BUG-3260
type: BUG
title: wire-issue Phase 4 locator agent returns caller claims with no grep evidence
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
testable: true
program_design_not_applicable: true
relates_to:
- ENH-3258
- ENH-2578
captured_at: '2026-08-20T00:20:11Z'
---

# BUG-3260: wire-issue Phase 4 locator agent returns caller claims with no grep evidence

## Summary

In one `/ll:wire-issue` run (ENH-3000, 2026-08-19), the Phase 4 Agent 1
(`ll:codebase-locator`) returned four caller/consumer claims that had **zero** grep hits.
The graph-discovery confirm-before-map rule caught all four, so no bad wiring reached the
issue file — but the agent is presenting fabricated call sites in the same format and with
the same confidence as real ones.

## Current Behavior

The traced symbol set for that run was: build_ref_index, classify_file_ref,
classify_issue_refs, RefIndex, RefStatus, IssuesConfig, qualified_ref_count,
triage_research_axes, check_format_gaps, plus the proposed config key
issues.untracked_by_design.

Four claims, each checked with a targeted grep that returned nothing:

1. **hooks/sweep_stale_refs.py**, reported as calling the classifier for reference
   classification. The file contains no occurrence of any traced symbol.
2. **issue_parser.py**, reported as reading the proposed config key. That key does not
   exist anywhere in the tree — ENH-3000, the issue being wired, *proposes* creating it.
   The claim inverts cause and effect, reporting a not-yet-existent key as already read.
3. **config/core.py**, reported as having a post-init hook on the issues config dataclass
   serving as the merge point. That dataclass defines no such hook.
4. **tests/test_issue_parser.py**, reported as a verdict-literal consumer. No hits for any
   traced symbol.

The pattern: the agent extrapolated from the issue's *proposed* end state and from
plausible module responsibilities, rather than reporting only what it found.

(Symbol and file names are deliberately unlinked above. Pairing them in the usual
`symbol` / `path` form would make this section's own catalogue of fabricated attributions
register as `mislocated_symbol_ref` findings against this issue.)

## Steps to Reproduce

1. Run `/ll:wire-issue ENH-3000 --auto --dry-run` from the repo root.
2. Read Phase 4 Agent 1's returned groups (Direct importers / Callers / Test files /
   Registration files / Config files).
3. For each returned path, grep it for the traced symbols listed above.

**Observed** (2026-08-19): four returned paths yield zero hits for any traced symbol.
**Expected**: every returned path carries at least one matching occurrence, or is marked
as inferred rather than found.

Not deterministic — this is LLM output, so a re-run may return a different set. The four
recorded fabrications are an existence proof, not a fixed reproduction.

## Expected Behavior

Agent 1 returns only paths it has evidence for, and marks anything inferred as
unconfirmed rather than listing it alongside verified hits.

## Motivation

Confirm-before-map is doing its job, so this is not currently producing bad output — but
it is load-bearing in a way the design may not intend. Three consequences:

1. **Cost**: every fabricated claim buys a wasted confirmation grep.
2. **Silent dependence**: if a caller ever skips confirmation for a hit that "looks
   obvious", these land in the Integration Map unchallenged.
3. **Erosion**: the same agent is used by `/ll:refine-issue`, where hits are consumed as
   research leads with a *weaker* confirmation discipline than wire-issue's.

One run is not a rate. This issue records a concrete observation, not a measurement.

## Proposed Solution

Amend the Agent 1 prompt in `skills/wire-issue/SKILL.md` Phase 4 to require evidence per
returned path — the matched line or symbol — and to state explicitly that a path may not
be returned on the basis of what the issue proposes to build. Consider a separate
"inferred, unconfirmed" group so the agent has somewhere to put a genuine hunch.

Before changing the prompt, check whether `agents/codebase-locator.md` or the shared
agent definition is the better place, since `/ll:refine-issue` shares it.

## Integration Map

### Files to Modify
- `skills/wire-issue/SKILL.md` Phase 4 Agent 1 prompt — **or**
  `agents/codebase-locator.md`, depending on where the fix belongs. Decide first: the
  shared agent definition is also used by `/ll:refine-issue`, where the same
  extrapolation is less harmful because hits are consumed as leads
- Host mirrors under `.qwen/`, `.gemini/`, `.kimi-code/` regenerate via `ll-adapt` for
  whichever file changes

### Dependent Files (Callers/Importers)
- `skills/wire-issue/graph-discovery-layer.md` — states the confirm-before-map rule that
  currently absorbs these false positives. Not to be weakened; noted because this issue's
  fix reduces (but must not be assumed to eliminate) reliance on it

### Similar Patterns
- Phase 4 Agents 2 and 3 use the same anchor-based-reference convention; check whether
  they exhibit the same behavior before assuming Agent 1 is unique

### Tests
- `scripts/tests/` has no harness for agent-prompt compliance. Verification is a
  re-run of the ENH-3000 wiring pass, checking that returned paths carry evidence

### Documentation
- None expected

### Configuration
- N/A

## Implementation Steps

1. Decide placement — wire-issue's Phase 4 prompt block vs. the shared
   `agents/codebase-locator.md` definition.
2. Amend the return contract to require a matched line or symbol per returned path, and
   to forbid returning a path on the basis of what the issue *proposes* to build.
3. Add a separate "inferred, unconfirmed" group so genuine hunches have a home and the
   tightening does not suppress real callers.
4. Re-run the ENH-3000 wiring pass and confirm the four recorded fabrications do not
   recur, and that the real hits still do.

## Program Design

N/A — `program_design_not_applicable: true`. This is an agent-prompt (markdown) change:
no types, no signatures, no runtime call path. The only design decision is placement,
covered in Implementation Steps step 1.

## Impact

- **Priority**: P3 - confirm-before-map contains the damage, so no bad wiring is reaching
  issue files today; the cost is wasted confirmation greps and an undocumented dependence
  on that rule
- **Effort**: Small - a prompt amendment, though placement needs deciding first
  (wire-issue's Phase 4 block vs. the shared `agents/` definition that `/ll:refine-issue`
  also uses)
- **Risk**: Low - a stricter return contract can only narrow what the agent reports. The
  cost of over-tightening is a missed real caller, which confirm-before-map does *not*
  protect against, so the prompt should still permit inferred paths in a separate group
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Agent 1's return contract and the evidence it must carry.
- **Out of scope**: the confirm-before-map rule itself, which worked correctly.
- **Out of scope**: `ll-code` accuracy — the graph results in this run were all correct.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3
