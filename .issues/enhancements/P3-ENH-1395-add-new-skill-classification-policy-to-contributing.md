---
captured_at: '2026-05-09T20:48:12Z'
discovered_date: 2026-05-09
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 74
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 21
score_change_surface: 25
decision_needed: false
missing_artifacts: true
---

# ENH-1395: Add New-Skill Classification Policy to CONTRIBUTING.md

## Summary

Add a "New Skill Checklist" section to `CONTRIBUTING.md` that defines when a skill should be LLM-discoverable vs. user-invocable only, enforces a description character limit, and requires a `/doctor` budget check before each release. This prevents the listing budget truncation from recurring as new skills are added.

## Current Behavior

`CONTRIBUTING.md` has no guidance on skill classification. Every new skill defaults to LLM-discoverable (full description in listing budget) because there is no documented policy and no checklist to follow. The listing budget has already been exceeded once and will exceed again as new skills are added.

## Expected Behavior

`CONTRIBUTING.md` includes a "New Skill Checklist" section with:
1. A classification decision tree: "Does the LLM need to discover this skill from natural language? If no, add `disable-model-invocation: true`"
2. Description length cap: ≤ 100 characters for LLM-discoverable skills, no bullet lists
3. A release checklist item: run `/doctor` and confirm 0 skill descriptions dropped before tagging

## Motivation

ENH-1394 fixes the current truncation by tagging 17 existing skills. Without a documented policy, the next batch of new skills will recreate the same problem. The cost of a doc addition is negligible; the cost of rediscovering this issue each release is ongoing session quality degradation.

## Proposed Solution

Add a new section to `CONTRIBUTING.md` between the existing "Skills" and "Testing" sections:

```markdown
### New Skill Checklist

Before adding a new skill, answer:

1. **Will users always type this command explicitly?**
   If yes → add `disable-model-invocation: true` to frontmatter. Examples: `update`, `cleanup-worktrees`, `audit-loop-run`, `analyze-history`.

2. **Should the LLM route to this skill from natural language?**
   If yes → keep default (no flag). Keep the `description` field ≤ 100 characters. No bullet lists in descriptions.

3. **Before release:** run `/doctor` and verify "0 skill descriptions dropped". If any are dropped, tag more skills with `disable-model-invocation: true` or shorten descriptions.
```

## Implementation Steps

1. Open `CONTRIBUTING.md` and locate the "Skills" section
2. Add the "New Skill Checklist" subsection with the decision tree above
3. Add a release checklist item in the existing release process section (if one exists) referencing `/doctor`

## Integration Map

### Files to Modify
- `CONTRIBUTING.md` — add "New Skill Checklist" subsection under Skills

### Dependent Files (Callers/Importers)
- N/A — documentation only

### Similar Patterns
- Existing "New Command Checklist" or similar sections in `CONTRIBUTING.md` (if present)

### Tests
- N/A

### Documentation
- `CONTRIBUTING.md` — the only file changed

### Configuration
- N/A

## Impact

- **Priority**: P3 — prevents recurrence of ENH-1394's root cause
- **Effort**: Very low — documentation addition only
- **Risk**: None
- **Breaking Change**: No

## Labels

`enhancement`, `documentation`, `skills`, `context-engineering`

## Status

**Open** | Created: 2026-05-09 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-11_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Test coverage gap**: `generate_skill_descriptions.py` has no tests specified; failures in skill discovery, API calls, or frontmatter writes will go undetected — add at minimum a smoke test mocking `run_claude_command`
- **New CLI file does not exist**: `scripts/little_loops/cli/generate_skill_descriptions.py` must be created from scratch — ensure it is registered in `pyproject.toml` and installed before testing

## Session Log
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/05b43bc1-4bad-4cee-aaf6-69179c4dd816.jsonl`
- `/ll:decide-issue` - 2026-05-11T05:14:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44ebe857-57a3-4a0b-8ab5-0e68ff9a9869.jsonl`
- `/ll:confidence-check` - 2026-05-11T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db4b4e79-bda6-447b-aee5-e3e1b6b6a142.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:capture-issue` - 2026-05-09T20:48:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c428abc-6b67-47fc-b1a4-d2d8d176f6b7.jsonl`

---

## Scope Addition

**Source**: Merged from ENH-1397 during `/ll:audit-issue-conflicts` conflict resolution.

ENH-1397 proposed a `ll-generate-skill-descriptions` CLI tool that auto-generates minimal (≤100 char) skill descriptions from SKILL.md content using Claude (claude-haiku-4-5). Both issues addressed the same description-bloat problem (ENH-1395 via policy, ENH-1397 via automation), so the tooling scope is absorbed here:

- Add `ll-generate-skill-descriptions` CLI in `scripts/little_loops/cli/` as part of this issue's implementation
- For each `skills/*/SKILL.md`: skip `disable-model-invocation: true` skills; extract trigger keywords and first 500 chars of body; call Claude API to generate a description of ≤100 chars; dry-run by default with `--apply` to write back to frontmatter
- Register CLI entry point in `scripts/pyproject.toml`; mention as optional release utility in `CONTRIBUTING.md`
- Uses `ll-action` infrastructure or direct Anthropic SDK call (claude-haiku-4-5 — cheap, fast, sufficient)

> **Selected:** Subprocess/CLI pattern (`run_claude_command` from `subprocess_utils.py` or `subprocess.run(["claude", "-p", ...])`) — SDK was deliberately removed after FEAT-044; every LLM-calling module routes through the `claude` CLI subprocess; established mock patterns exist

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Subprocess/CLI pattern (`run_claude_command` from `subprocess_utils.py` or `subprocess.run(["claude", "-p", ...])`)

**Reasoning**: The codebase explicitly removed the Anthropic SDK after FEAT-044 replaced the direct SDK call in `evaluate_llm_structured()` (`fsm/evaluators.py`) with `subprocess.run(["claude", "-p", ...])`. All four LLM-calling production modules now route through `run_claude_command` from `subprocess_utils.py`. Reusing this pattern requires no new dependencies, no re-adding of a removed dep, and leverages the established test mock (`patch("little_loops.subprocess_utils.run_claude_command")`) without any new fixture infrastructure.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Subprocess/CLI (`run_claude_command`) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Direct Anthropic SDK | 1/3 | 2/3 | 1/3 | 2/3 | 6/12 |

**Key evidence**:
- **Subprocess/CLI**: `fsm/evaluators.py::evaluate_llm_structured()` is the direct analog — originally used `anthropic.Anthropic()`, then replaced with `subprocess.run(["claude", "-p", ...])`. Mock pattern: `patch("subprocess.run")` or `patch("little_loops.subprocess_utils.run_claude_command")`.
- **Direct Anthropic SDK**: `anthropic>=0.40.0` was deliberately removed from `pyproject.toml`'s `[llm]` extras; zero modules currently import it; no mock fixtures exist anywhere in the test suite.
