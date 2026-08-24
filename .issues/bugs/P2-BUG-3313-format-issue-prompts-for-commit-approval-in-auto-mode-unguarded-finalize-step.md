---
id: BUG-3313
type: BUG
title: format-issue prompts for commit approval in --auto mode (unguarded Finalize
  step)
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-24'
captured_at: '2026-08-24T16:20:58Z'
completed_at: '2026-08-24T16:32:16Z'
---

# BUG-3313: format-issue prompts for commit approval in --auto mode (unguarded Finalize step)

## Summary

`/ll:format-issue` presents an interactive commit-approval question even when
`--auto` is explicitly passed, breaking the non-interactive contract that
automation contexts (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM loop states)
depend on.

## Current Behavior

Flag parsing in `skills/format-issue/SKILL.md` § "0. Parse Flags" correctly sets
`AUTO_MODE=true` for `--auto`, `--all`, `--check`, and for detected automation
env (`LL_NON_INTERACTIVE`, `DANGEROUSLY_SKIP_PERMISSIONS`).

§ "4. Interactive Refinement" is explicitly gated — its heading reads
"(Skip in Auto Mode)" and its body says "Skip this entire section if
`AUTO_MODE` is true."

§ "6. Finalize" carries **no such guard**. It unconditionally instructs:

```
3. Offer to commit changes:

questions:
  - question: "Commit the formatted issue?"
    header: "Commit"
    ...
```

So an `--auto` run skips §4, falls through to §6, and fires an
`AskUserQuestion`. It is the only interactive prompt in the skill missing the
auto guard — `grep -rn 'question: "Commit'` over `skills/` and `commands/`
matches this file alone.

Secondary defect in the same section: the `git add "[issue-file-path]"` step
does not check `DRY_RUN`, so `--auto --dry-run` (and therefore `--check`, which
implies both) would offer to stage a file it never modified.

## Expected Behavior

With `AUTO_MODE` true, §6 emits the Auto Mode / Batch Mode output block from
`skills/format-issue/templates.md` and returns without any question. Those
templates already specify the intended behavior: both end with
`## NEXT STEPS — Run /ll:commit to commit changes`, i.e. auto mode *reports*
the commit as a caller follow-up and never performs or requests it. Only the
interactive-mode template pairs with a commit question.

With `DRY_RUN` true, nothing is staged or committed.

## Motivation

An unattended `--auto` run that stops on an `AskUserQuestion` hangs until it
times out or is killed. That makes `/ll:format-issue [ID] --auto` unsafe as a
step inside `ll-auto` / `ll-parallel` / `ll-sprint` and inside FSM loop states —
exactly the integration the skill's own "Automation integration" section
advertises ("Enables automated issue formatting without user interaction").
The failure is silent from the caller's side: the run looks stalled, not
broken.

## Proposed Solution

Add the guard to §6 (source of truth: `skills/format-issue/SKILL.md`), then
propagate to the three `ll-adapt`-generated host mirrors
(`.qwen/`, `.gemini/`, `.kimi-code/`) via `ll-adapt --host <h> --apply`:

- Lead §6 with "**Skip steps 3-4 entirely if `AUTO_MODE` is true.**" plus the
  rationale that auto mode is non-interactive by contract, pointing at the
  templates' `NEXT STEPS` block as the auto-mode substitute.
- Mark the commit question and the `git add` step "(interactive mode only)".
- Add "**Never stage or commit when `DRY_RUN` is true**".

## Integration Map

### Files to Modify
- `skills/format-issue/SKILL.md` — § "6. Finalize" guard (source of truth)
- `.qwen/skills/format-issue/SKILL.md` — `ll-adapt` mirror
- `.gemini/skills/format-issue/SKILL.md` — `ll-adapt` mirror
- `.kimi-code/skills/format-issue/SKILL.md` — `ll-adapt` mirror

### Dependent Files (Callers/Importers)
- Any FSM loop YAML invoking `/ll:format-issue ... --auto` or `--check`
- `ll-auto` / `ll-parallel` / `ll-sprint` automation paths that pre-format
  issues before implementation

### Similar Patterns
- § "4. Interactive Refinement (Skip in Auto Mode)" in the same file is the
  correct guard pattern to mirror.

### Tests
- No existing test asserts skill-body interactivity guards. `ll-verify-skills`
  checks the 500-line cap only; the MR-8 evidence lint operates on FSM YAML
  `evaluate.prompt` text, not skill markdown bodies.

### Documentation
- None — behavior already documented as non-interactive; the skill body was
  the thing out of sync with the docs.

### Configuration
- N/A

## Implementation Steps

1. Add the `AUTO_MODE` skip directive and `DRY_RUN` staging guard to
   § "6. Finalize" of `skills/format-issue/SKILL.md`.
2. Propagate to host mirrors with `ll-adapt --host {qwen,gemini,kimi-code} --apply`.
3. Verify: guard text present in all four files; SKILL.md under the 500-line
   cap; `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Blocks unattended automation, but a documented workaround
  exists (answer the prompt) and no data is lost.
- **Effort**: Small - Prose-only change to one skill body plus regenerated mirrors.
- **Risk**: Low - Narrows behavior in auto mode only; interactive mode unchanged.
- **Breaking Change**: No

## Root Cause

Missing `AUTO_MODE` guard on § "6. Finalize" in
`skills/format-issue/SKILL.md`. The guard convention was applied to §4 when
auto mode was added but not extended to §6, which predates it.

## Files to Modify

- `skills/format-issue/SKILL.md` — § "6. Finalize" guard
- `.qwen/skills/format-issue/SKILL.md` — regenerated mirror
- `.gemini/skills/format-issue/SKILL.md` — regenerated mirror
- `.kimi-code/skills/format-issue/SKILL.md` — regenerated mirror

## Acceptance Criteria

- [ ] § "6. Finalize" in `skills/format-issue/SKILL.md` carries an explicit
      `AUTO_MODE` skip directive covering the commit question.
- [ ] The `git add` step is conditioned on `DRY_RUN` being false.
- [ ] All three host mirrors contain the same guard text (verify:
      `grep -c "Skip steps 3-4 entirely if" .{qwen,gemini,kimi-code}/skills/format-issue/SKILL.md`
      returns 1 for each).
- [ ] `skills/format-issue/SKILL.md` remains under the 500-line SKILL cap
      enforced by `ll-verify-skills`.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Notes

Class of defect worth a sweep: any skill with a documented `--auto` /
non-interactive mode should have every `questions:` block in it gated. Only
this one was found, but the audit was scoped to the `"Commit` prompt string.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-24T16:32:16 - `561d686d-886b-4568-adc4-51983884773a.jsonl`
