---
id: ENH-1441
type: ENH
priority: P4
status: open
---

# ENH-1441: README "8 specialized agents" description omits half the agents

## Summary

`README.md:160` describes the 8 agents as being for "codebase analysis, pattern finding, consistency checking, web research". `agents/*.md` actually contains 8 agents spanning capability areas not mentioned in the headline description:

- `plugin-config-auditor` — plugin configuration auditing
- `prompt-optimizer` — codebase context for prompt enhancement
- `workflow-pattern-analyzer` — workflow pattern and dependency analysis

A new reader scanning "What's Included" gets an inaccurate picture of agent coverage and may not realize plugin-config-auditor, prompt-optimizer, etc. exist.

## Source

Found by `/ll:audit-docs` on 2026-05-10 (scope=readme). Counts (8 agents) verified correct against `agents/*.md`; the issue is the descriptive copy, not the count.

## Acceptance Criteria

- `README.md:160` description mentions all capability areas covered by the agent list (codebase work, pattern finding, plugin/config auditing, consistency checking, prompt optimization, workflow analysis, web research) — or is rephrased generically to avoid enumerating subset categories.
- Description stays under one line so it doesn't bloat the bullet list.

## Files

- `README.md` (line 160 — was line 88 before commit `4fb5ffcd` README rewrite)
- Reference: `agents/*.md` for authoritative agent list (8 files)

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-05-14

- README was rewritten (commit `4fb5ffcd`); the cited line 88 is now line 160. Current text reads: `**8 specialized agents** — codebase analysis, pattern finding, consistency checking, web research`. Still omits plugin-config-auditor, prompt-optimizer, workflow-pattern-analyzer.
- The previously cited "Agents table at README.md:199-208" no longer exists in the README; sole reference is now the one-line bullet at line 160. Removed the stale reference.


## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
