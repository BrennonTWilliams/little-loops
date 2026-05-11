---
id: ENH-1441
type: ENH
priority: P4
status: open
---

# ENH-1441: README "8 specialized agents" description omits half the agents

## Summary

`README.md:88` describes the 8 agents as being "for codebase analysis, pattern finding, and web research". The Agents table at `README.md:199-208` actually lists 8 agents spanning four additional capability areas not mentioned in the headline description:

- `consistency-checker` — cross-component consistency validation
- `plugin-config-auditor` — plugin configuration auditing
- `prompt-optimizer` — codebase context for prompt enhancement
- `workflow-pattern-analyzer` — workflow pattern and dependency analysis

A new reader scanning "What's Included" gets an inaccurate picture of agent coverage and may not realize plugin-config-auditor, consistency-checker, etc. exist.

## Source

Found by `/ll:audit-docs` on 2026-05-10 (scope=readme). Counts (8 agents) verified correct against `agents/*.md`; the issue is the descriptive copy, not the count.

## Acceptance Criteria

- README.md:88 description mentions all four capability areas covered by the agent list (codebase work, pattern finding, plugin/config auditing, consistency checking, prompt optimization, workflow analysis, web research) — or is rephrased generically to avoid enumerating subset categories.
- Description stays under one line so it doesn't bloat the bullet list.

## Files

- `README.md` (line 88)
- Reference: `README.md:199-208` (Agents table) and `agents/*.md` for authoritative agent list
