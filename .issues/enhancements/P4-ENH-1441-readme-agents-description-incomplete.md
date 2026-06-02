---
id: ENH-1441
type: ENH
priority: P4
status: done
completed_at: 2026-05-22T18:52:27Z
decision_needed: true
testable: false
confidence_score: 95
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1441: README "9 specialized agents" description omits several agents

## Summary

`README.md:160` describes the 8 agents as being for "codebase analysis, pattern finding, consistency checking, web research". `agents/*.md` actually contains 8 agents spanning capability areas not mentioned in the headline description:

- `plugin-config-auditor` — plugin configuration auditing
- `prompt-optimizer` — codebase context for prompt enhancement
- `workflow-pattern-analyzer` — workflow pattern and dependency analysis

A new reader scanning "What's Included" gets an inaccurate picture of agent coverage and may not realize plugin-config-auditor, prompt-optimizer, etc. exist.

## Current Behavior

`README.md:164` reads: `**9 specialized agents** — codebase analysis, pattern finding, consistency checking, loop diagnosis, web research`. Three agent capability areas are omitted from the headline description: plugin configuration auditing (`plugin-config-auditor`), prompt optimization (`prompt-optimizer`), and workflow pattern analysis (`workflow-pattern-analyzer`). A reader scanning "What's Included" gets an incomplete picture of agent coverage.

## Expected Behavior

The README agent description should cover all capability areas present in `agents/*.md`, or be phrased generically (e.g., "codebase analysis, quality assurance, automation, and research") to avoid enumerating subset categories that drift out of date as agents change.

## Motivation

This enhancement would:
- Improve new-user onboarding by accurately representing agent capabilities
- Prevent readers from overlooking `plugin-config-auditor`, `prompt-optimizer`, and `workflow-pattern-analyzer`
- Reduce maintenance burden if phrased generically (won't need updates when agents change)

## Scope Boundaries

- **In scope**: Updating `README.md` line ~164 agent description to accurately cover all capability areas
- **Out of scope**: Adding/removing agents, restructuring the README layout, changing agent functionality

## Success Metrics

- README description covers all capability areas in `agents/*.md`, or uses generic phrasing that doesn't enumerate subset categories
- Description stays under one line (per acceptance criteria)

## API/Interface

N/A — documentation-only change with no API or interface modifications.

## Source

Found by `/ll:audit-docs` on 2026-05-10 (scope=readme). Counts (8 agents) verified correct against `agents/*.md`; the issue is the descriptive copy, not the count.

## Acceptance Criteria

- `README.md:160` description mentions all capability areas covered by the agent list (codebase work, pattern finding, plugin/config auditing, consistency checking, prompt optimization, workflow analysis, web research) — or is rephrased generically to avoid enumerating subset categories.
- Description stays under one line so it doesn't bloat the bullet list.

## Proposed Solution

Option A (specific): Expand the description to include all categories: "codebase analysis, pattern finding, plugin/config auditing, consistency checking, prompt optimization, workflow analysis, loop diagnosis, web research."

Option B (generic — preferred): Rephrase to a category-neutral summary: "codebase analysis, quality assurance, automation, and research." This avoids future drift as agents change, per the acceptance criteria's "or is rephrased generically" clause.

### Research-Informed Notes

_Added by `/ll:refine-issue`:_

- **Option B is consistent with README conventions**: Every other bullet in the "What's in the box" section already uses non-exhaustive, drift-proof phrasing (broad domains for 28 slash commands, parenthetical examples for 30 skills and 51 loops, `and more`/`and generic` catch-alls for CLI tools and config templates). Option B aligns the agents bullet with this established pattern.
- **Option A would still need maintenance**: If a 10th agent is added, the explicit enumeration in Option A would drift out of date again. Option B's category groups accommodate new agents without text changes.
- **Option A coverage note**: The draft in Option A lists 8 capability descriptors. If chosen, `codebase-locator` should be considered under "codebase analysis" (it finds WHERE code lives vs. codebase-analyzer which traces HOW code works), and the list should verify all 9 agents map to a listed category.

## Implementation Steps

1. Read current `README.md` line ~164 to confirm exact text
2. Draft updated description covering all agent capability areas (prefer generic phrasing from Option B)
3. Update `README.md` line 164
4. Verify the description covers all agents listed in `agents/*.md`
5. Run `python -m pytest scripts/tests/test_feat1532_doc_wiring.py scripts/tests/test_doc_counts.py -v` to confirm substring assertions and dynamic count extraction still pass
6. Run `/ll:verify-issues ENH-1441` to confirm the fix resolves the verification findings

## Files

- `README.md` (line 160 — was line 88 before commit `4fb5ffcd` README rewrite)
- Reference: `agents/*.md` for authoritative agent list (9 files)

## Integration Map

### Files to Modify
- `README.md` (line ~164)

### Tests
- N/A — documentation change

### Documentation
- `README.md` (the fix itself)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Pattern anomaly**: Every other bullet in the "What's in the box" section (lines 163-168) uses non-exhaustive patterns — broad category groups, parenthetical examples, or `and more`/`and generic` catch-alls. The agents bullet at line 164 is the **only** one that enumerates specific capability categories without a catch-all mechanism, making it uniquely drift-prone.
- **4 agents lack explicit coverage** (not 3 as originally scoped): `codebase-locator` (super Grep/Glob — WHERE code lives) is also absent from the current description, though it can arguably fold under "codebase analysis." The other three (`plugin-config-auditor`, `prompt-optimizer`, `workflow-pattern-analyzer`) have no umbrella category at all.
- **Precedent ENH-437**: A resolved P4 enhancement that fixed the same class of problem in the same section (config template coverage). The fix chose specific expansion over generic rephrasing, adding missing items and a trailing catch-all. See `.issues/enhancements/P4-ENH-437-readme-template-coverage-understated.md`.
- **Tests safe**: `scripts/tests/test_feat1532_doc_wiring.py:72` only asserts the substring `"9 specialized agents"` — any description rephrasing that preserves the count will pass. `scripts/tests/test_doc_counts.py:90` dynamically extracts the count pattern, so that will also work unchanged.

## Impact

- **Priority**: P4 — cosmetic/docs improvement, no functional impact
- **Effort**: Small — single-line text change
- **Risk**: Low — documentation-only, no code changes
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`

## Verification Notes

**Verdict**: NEEDS_UPDATE — Re-verified 2026-05-22

- `README.md:164` reads: `**9 specialized agents** — codebase analysis, pattern finding, consistency checking, loop diagnosis, web research`
- Agent count confirmed at 9. Title updated from "8" to "9".
- Core problem persists: `plugin-config-auditor`, `prompt-optimizer`, `workflow-pattern-analyzer` still omitted from description.
- No fix applied.

**Verdict**: NEEDS_UPDATE — Re-verified 2026-05-17 (this pass)

- `README.md:164` reads: `**9 specialized agents** — codebase analysis, pattern finding, consistency checking, loop diagnosis, web research`
- Agent count confirmed at 9 (`agents/*.md` has 9 files).
- Issue title says "8 specialized agents" — must be updated to "9 specialized agents".
- Core problem persists: `plugin-config-auditor`, `prompt-optimizer`, `workflow-pattern-analyzer` still omitted from description.
- No fix applied.

**Verdict**: NEEDS_UPDATE — Re-verified 2026-05-17

- README now reads: `**9 specialized agents** — codebase analysis, pattern finding, consistency checking, loop diagnosis, web research` (count bumped from 8→9; "loop diagnosis" added for loop-specialist agent)
- Still omits plugin-config-auditor, prompt-optimizer, workflow-pattern-analyzer from the description.
- Issue title and summary reference "8 agents" — update to reflect 9 agents now present.
- No fix applied; issue remains open.

**Verdict**: NEEDS_UPDATE — Re-verified 2026-05-17 (earlier)

- `README.md:164` still reads: `**8 specialized agents** — codebase analysis, pattern finding, consistency checking, web research`
- Still omits plugin-config-auditor, prompt-optimizer, workflow-pattern-analyzer from the description.
- No fix applied; issue remains open.

**Verdict**: NEEDS_UPDATE — Verified 2026-05-14

- README was rewritten (commit `4fb5ffcd`); the cited line 88 is now line 160. Current text reads: `**8 specialized agents** — codebase analysis, pattern finding, consistency checking, web research`. Still omits plugin-config-auditor, prompt-optimizer, workflow-pattern-analyzer.
- The previously cited "Agents table at README.md:199-208" no longer exists in the README; sole reference is now the one-line bullet at line 160. Removed the stale reference.


## Session Log
- `/ll:ready-issue` - 2026-05-22T18:50:29 - `5efbefd7-1e7e-4313-93e5-cb518b43d9a0.jsonl`
- `/ll:confidence-check` - 2026-05-22T18:30:00 - `3c58564f-6b57-4320-9585-5e1198e38eee.jsonl`
- `/ll:refine-issue` - 2026-05-22T17:54:26 - `261f5d45-e076-411a-ba2a-36d1d1fe75d1.jsonl`
- `/ll:format-issue` - 2026-05-22T17:44:52 - `b54d6f76-2311-48be-b480-66a4968220d3.jsonl`
- `/ll:verify-issues` - 2026-05-22T16:11:38 - `d87b546d-fad7-425c-a8f4-8246f0ea8de8.jsonl`
- `/ll:verify-issues` - 2026-05-18T04:53:51 - `2807bd8b-4e79-4b76-994d-e6f6cae14245.jsonl`
- `/ll:verify-issues` - 2026-05-17T17:04:58 - `907d2d29-7e38-4120-a77d-deb597ac2df4.jsonl`
- `/ll:verify-issues` - 2026-05-17T05:54:38 - `9fb51237-8283-40d3-94ce-bda6ff4b1b33.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
