---
id: ENH-1615
title: Add disable-model-invocation to all 28 ll-* Codex bridge skills
type: ENH
priority: P3
captured_at: '2026-05-22T19:19:39Z'
discovered_date: 2026-05-22
discovered_by: capture-issue
status: open
parent: EPIC-1463
---

# ENH-1615: Add disable-model-invocation to all 28 ll-* Codex bridge skills

## Summary

The 28 `ll-*` bridge skills (e.g., `ll-align-issues`, `ll-commit`, `ll-help`) are 11-line stubs that bridge `commands/*.md` to the Codex Skills API. They consume 388/720 tokens (54%) of the skill listing budget but provide zero routing value for Claude Code users — Claude Code already routes through the identically-named slash commands. Adding `disable-model-invocation: true` to all 28 would cut the listing budget from 720 to ~332 tokens with no functional impact for Claude Code users.

## Current Behavior

All 28 `ll-*` skills are LLM-discoverable (no `disable-model-invocation`). Their descriptions appear in the listing budget alongside the real Tier 1 skills. Each bridge skill is an 11-line stub referencing its source command file. Six of them have broken `|` descriptions (covered by BUG-1616). Combined, they represent 54% of the total skill listing budget.

## Expected Behavior

All 28 `ll-*` bridge skills have `disable-model-invocation: true`. Claude Code users invoke skills through the existing slash commands (`commands/*.md`) — the bridges are only needed for Codex CLI discovery. The listing budget drops from 720 to ~332 tokens. Codex users are unaffected since Codex discovers skills via the `agents/openai.yaml` sidecar, not via the listing budget.

## Motivation

The 28 `ll-*` bridge skills consume 388 of 720 total listing-budget tokens (54%) despite providing zero routing value for Claude Code users — Claude Code resolves skills through `/ll:<name>` slash commands, not the listing budget. Every skill-listing call pays this overhead. Reducing the budget by ~54% frees headroom for real Tier 1 skills and lowers token cost per listing call.

## Proposed Solution

Add `disable-model-invocation: true` to the YAML frontmatter of all 28 `skills/ll-*/SKILL.md` files. This field already exists in several non-bridge skills (e.g., `cleanup-loops`, `debug-loop-run`). A bulk Python edit is sufficient — no logic changes needed:

```python
import re
from pathlib import Path

for skill_dir in Path("skills").glob("ll-*/SKILL.md"):
    txt = skill_dir.read_text()
    if "disable-model-invocation" not in txt:
        txt = re.sub(r"^(---\n)", r"\1disable-model-invocation: true\n", txt, count=1)
        skill_dir.write_text(txt)
```

## Implementation Steps

1. Enumerate all 28 `skills/ll-*/SKILL.md` files (listed in Integration Map)
2. Insert `disable-model-invocation: true` into each file's frontmatter block (script above)
3. Run `ll-verify-skill-budget` to confirm listing budget drops from ~720 to ~332 tokens
4. Add CHANGELOG "Changed" entry noting the budget reduction

## Scope Boundaries

- **Out of scope**: Fixing broken `|` pipe descriptions in 6 skills (tracked in BUG-1616)
- **Out of scope**: Removing, merging, or deprecating the `ll-*` bridge skills themselves
- **Out of scope**: Changing invocation behavior for Claude Code or Codex users
- **Out of scope**: Modifying source `commands/*.md` files

## Impact

- **Priority**: P3 — structural budget waste, no user-facing bug
- **Effort**: Small — bulk `disable-model-invocation: true` insertion into 28 SKILL.md frontmatter blocks
- **Risk**: Low — additive field only; does not change invocation behavior for Codex users. Note: BUG-1754 demonstrates that `disable-model-invocation: true` prevents Skill tool invocation in pipeline commands (workflow-automation-proposer). The 28 ll-* bridge skills are not themselves pipeline-invoked, so the implementation is safe, but future commands must not invoke ll-* bridge stubs via the Skill tool or they will hit the same failure mode.
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `skills/ll-*/SKILL.md` (all 28 files) — add `disable-model-invocation: true` to frontmatter:
  `ll-align-issues`, `ll-analyze-workflows`, `ll-audit-architecture`, `ll-check-code`,
  `ll-cleanup-worktrees`, `ll-commit`, `ll-create-sprint`, `ll-describe-pr`,
  `ll-find-dead-code`, `ll-handoff`, `ll-help`, `ll-iterate-plan`, `ll-loop-suggester`,
  `ll-manage-release`, `ll-normalize-issues`, `ll-open-pr`, `ll-prioritize-issues`,
  `ll-ready-issue`, `ll-refine-issue`, `ll-resume`, `ll-review-sprint`, `ll-run-tests`,
  `ll-scan-codebase`, `ll-scan-product`, `ll-sync-issues`, `ll-toggle-autoprompt`,
  `ll-tradeoff-review-issues`, `ll-verify-issues`

### Dependent Files (Callers/Importers)
- N/A — frontmatter-only change; no Python imports or callers affected

### Similar Patterns
- `skills/cleanup-loops/SKILL.md`, `skills/debug-loop-run/SKILL.md` — existing use of `disable-model-invocation: true`

### Tests
- N/A — no logic change; verify with `ll-verify-skill-budget` (exit 0 = under budget)

### Documentation
- `CHANGELOG.md` — "Changed" entry noting listing budget reduction

### Configuration
- N/A

## Labels

`enhancement`, `skills`, `context-engineering`, `budget`

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-24T02:24:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11a32bd-ee0b-4bc3-aa81-bbd2c70eaca5.jsonl`
- `/ll:capture-issue` - 2026-05-22T19:19:39Z - conversation analysis

## Status

**Open** | Created: 2026-05-22 | Priority: P3
