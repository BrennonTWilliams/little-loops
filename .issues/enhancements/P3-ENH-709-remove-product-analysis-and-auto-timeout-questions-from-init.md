---
discovered_date: "2026-03-12"
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-709: Remove Product Analysis and Auto-Timeout Questions from Init Interactive

## Summary

Remove two unnecessary interactive questions from `/ll:init --interactive`:
1. **"Enable product-focused issue analysis? (Optional)"** (Round 4) — the recommended answer is "No, skip", making the question low-value friction.
2. **"What timeout should ll-auto use per issue (seconds)? → 3600 (Recommended)"** (Round 5a) — the recommended default (3600) is almost always correct; users who need a different value can edit `ll-config.json` directly.

Both questions add interaction rounds without meaningful decision value for most users.

## Current Behavior

Both questions are always shown during `/ll:init --interactive`, requiring user input even though the recommended defaults are appropriate for nearly all projects.

## Expected Behavior

- Product analysis question removed; default to disabled (current recommended answer).
- Auto-timeout question removed; default to 3600 seconds (current recommended answer).
- Users who need non-default values can configure them in `.claude/ll-config.json` after init.

## Motivation

These questions add cognitive load and interaction rounds to the init wizard without proportional value. ENH-613 previously removed other low-value questions but retained these two — this completes that effort.

## Proposed Solution

Edit `skills/init/interactive.md`:
1. Remove the `## Round 4: Product Analysis` section and its conditional config application block (through the "proceed to Round 5" instruction).
2. Remove the `auto_timeout` question from `### Round 5a: Advanced Settings` (the "Auto Timeout" header/question block) and hardcode the 3600 default in the Round 5 configuration output.
3. Update round numbering, `TOTAL` count, and the Round Reference Table to reflect the removed content.

## Integration Map

### Files to Modify
- `skills/init/interactive.md` — remove question definitions and conditional logic

### Dependent Files (Callers/Importers)
- `skills/init/SKILL.md` — references interactive rounds (may need round count update)

### Similar Patterns
- N/A

### Tests
- N/A (skill definition, not Python code)

### Documentation
- N/A

### Configuration
- N/A

## API/Interface

N/A - No public API changes (skill definition file edit only)

## Success Metrics

- Interaction rounds reduced: `/ll:init --interactive` completes with 2 fewer prompts
- No config regression: `product_analysis` defaults to disabled, `auto_timeout` defaults to 3600 (same as current recommended answers)

## Scope Boundaries

- **Not** removing or changing any other init interactive rounds (Rounds 1–3, 5 parallel questions, Round 6 docs)
- **Not** changing non-interactive mode (`/ll:init` without `--interactive`)
- **Not** altering the default config values — just skipping the prompts and applying the same defaults silently
- **Not** removing the underlying config keys (`product_analysis`, `auto_timeout`) from `ll-config.json` — they remain settable via direct edit

## Implementation Steps

1. Remove product analysis question and its config-writing logic from `interactive.md`
2. Remove auto-timeout question and hardcode 3600 default in `interactive.md`
3. Adjust round numbering/comments if subsequent rounds reference removed ones

## Impact

- **Priority**: P3 - Quality-of-life improvement
- **Effort**: Small - Two question block removals in a single file
- **Risk**: Low - Removing optional questions, defaults already match recommended answers
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0f02fc6-1ba7-4fc8-9e31-5f723e7e51ef.jsonl`
- `/ll:format-issue` - 2026-03-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4b6ece1e-87fe-49b2-b766-58bab5968326.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `skills/init/interactive.md` confirms Round 4 (Product Analysis) exists at line 230, and `auto_timeout` is still in Round 5a (lines 224, 381, 398). Both questions are still present. Enhancement not yet applied.

## Status

**Open** | Created: 2026-03-12 | Priority: P3
