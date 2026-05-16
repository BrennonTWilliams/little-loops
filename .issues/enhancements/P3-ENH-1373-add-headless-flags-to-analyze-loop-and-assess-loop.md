---
id: ENH-1373
type: ENH
priority: P3
captured_at: '2026-05-06T17:56:49Z'
completed_at: '2026-05-06T18:14:54Z'
discovered_date: '2026-05-06'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# ENH-1373: Add `--skip-issue-creation` and `--auto` Flags to `/ll:analyze-loop` and `/ll:assess-loop`

## Summary

Both `/ll:analyze-loop` and `/ll:assess-loop` use `AskUserQuestion` at the end of their workflows to ask the user whether to create issues from their findings. When either skill is invoked from a loop state via `action_type: slash_command`, this interactive prompt blocks execution and the loop hangs. Add `--skip-issue-creation` (opt-out of issue creation entirely) and `--auto` (non-interactive mode, auto-declines the prompt) flags so both skills can be called headlessly.

## Current Behavior

- `skills/analyze-loop/SKILL.md` Step 5: uses `AskUserQuestion` to ask whether to create issues from fault/effectiveness signals.
- `skills/assess-loop/SKILL.md` Step 9: uses `AskUserQuestion` to ask whether to create issues from proposal findings.
- Neither skill has a headless mode or flag to suppress the prompt.
- Invoking either skill from `outer-loop-eval.yaml` via `action_type: slash_command` causes the loop to block indefinitely at the question.

## Expected Behavior

- Both skills accept `--skip-issue-creation` to skip the issue-creation step entirely and exit cleanly.
- Both skills accept `--auto` to run non-interactively: suppress all `AskUserQuestion` calls, default to "no" for issue creation.
- When `--skip-issue-creation` or `--auto` is passed, the skill proceeds through all analysis/assessment steps and then exits without prompting.
- Skills remain fully interactive (current behavior) when neither flag is present.

## Motivation

This is a prerequisite for ENH-1328, which refactors `outer-loop-eval.yaml` to delegate its inline analysis states to `/ll:analyze-loop` and `/ll:assess-loop`. Without headless invocation support, ENH-1328 cannot land — the delegated states would immediately block on user input.

More broadly, any future loop that wants to use these skills as sub-steps faces the same problem. Adding these flags makes the skills composable in automation contexts.

## Proposed Solution

Add flag parsing at the top of each skill's argument-handling section (mirroring the `--auto` pattern already used in other skills like `/ll:refine-issue` and `/ll:manage-issue`):

```bash
SKIP_ISSUE_CREATION=false
AUTO_MODE=false
if [[ "$ARGS" == *"--skip-issue-creation"* ]]; then SKIP_ISSUE_CREATION=true; fi
if [[ "$ARGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
# --auto implies --skip-issue-creation
if [[ "$AUTO_MODE" == true ]]; then SKIP_ISSUE_CREATION=true; fi
```

Then at the issue-creation prompt step:
- If `SKIP_ISSUE_CREATION` is true, skip `AskUserQuestion` and print a one-line note: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)`
- Otherwise, behavior is unchanged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Skills use prose guards, not bash blocks.** `commands/refine-issue.md` uses an actual `### 0. Parse Flags` bash block because it is a command. Both `analyze-loop` and `assess-loop` are SKILL files — they use inline prose guards to control behavior, like `assess-loop/SKILL.md:177`: `**Skip this step if `--no-rubric-audit` flag is set.**` The bash pseudo-code in the Proposed Solution above shows the conditional logic to implement; in the SKILL.md files it becomes prose guards and frontmatter declarations, not literal bash.

**Frontmatter changes required (both skills):**
- `argument-hint` (line 4): append `[--skip-issue-creation] [--auto]`
  - `analyze-loop` current: `"[loop-name] [--tail N]"` → add flags
  - `assess-loop` current: `"[loop-name] [--tail N] [--no-rubric-audit]"` → add flags
- `arguments:` block: add two new argument entries following the `no_rubric_audit` style in `assess-loop/SKILL.md:20`

**Canonical prose guard to insert at the issue-creation step:**
```
**Skip this step if `--skip-issue-creation` or `--auto` flag is set.** Print: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` and stop.
```

**Automation context detection:** The canonical `--auto` pattern in `commands/refine-issue.md:49–62` also auto-enables non-interactive mode when `--dangerously-skip-permissions` is detected. Since these are SKILL files (not commands), add a prose note at the top: "Also treat headless mode as active when invoked from a loop (i.e., when `--dangerously-skip-permissions` is in the args or environment)." This prevents blocking in automated slash_command contexts even when `--auto` is omitted.

**Exact insertion points:**
- `skills/analyze-loop/SKILL.md:4` — update `argument-hint`
- `skills/analyze-loop/SKILL.md:13` — extend `arguments:` block
- `skills/analyze-loop/SKILL.md:385` — `## Step 5: Present Proposals and Confirm` — add prose guard before line 410 (`AskUserQuestion` call)
- `skills/assess-loop/SKILL.md:4` — update `argument-hint`
- `skills/assess-loop/SKILL.md:13` — extend `arguments:` block
- `skills/assess-loop/SKILL.md:211` — `## Step 9: Ranked Improvement Proposals` — add prose guard before line 246 (`AskUserQuestion` call)

## Scope Boundaries

- Modifying the analysis or assessment logic in either skill (only flag plumbing changes)
- Adding these flags to skills other than `/ll:analyze-loop` and `/ll:assess-loop`
- Changing the existing interactive behavior when neither flag is present
- Adding flag selection menus or interactive flag discovery

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md` — add flag parsing and conditional skip at Step 5 (issue-creation prompt)
- `skills/assess-loop/SKILL.md` — add flag parsing and conditional skip at Step 9 (issue-creation prompt)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/outer-loop-eval.yaml` — ENH-1328 will invoke both skills with `--skip-issue-creation` once this ships
- Any future loop YAML that invokes these skills headlessly

### Similar Patterns
- `commands/refine-issue.md:49–62` — canonical `### 0. Parse Flags` bash block (note: this is a command; skills use prose guards instead)
- `skills/assess-loop/SKILL.md:177` — existing prose guard for `--no-rubric-audit`: `**Skip this step if `--no-rubric-audit` flag is set.**` — model the new guards after this
- `skills/manage-issue/SKILL.md` — `--gates` flag controls `AskUserQuestion` via inline prose at each gate site

### Tests
- `scripts/tests/test_analyze_loop_synthesis.py` — exists; tests FSM fixture structure in `TestAnalyzeLoopSynthesis`; currently zero flag tests; add new methods following `test_assess_loop_skill.py:72–76` (`test_skill_has_no_rubric_audit_flag`) as the direct template
- `scripts/tests/test_assess_loop_skill.py` — exists; `TestAssessLoopSkill` already has `test_skill_has_no_rubric_audit_flag` at line 72 — add analogous `test_skill_has_skip_issue_creation_flag` and `test_skill_has_auto_flag` methods
- Test Pattern 1 (simple flag presence): `assert "--skip-issue-creation" in SKILL_FILE.read_text()` — mirrors existing tests in `test_assess_loop_skill.py:72–76`
- Test Pattern 3 (AskUserQuestion absence in section): slice to `## Step 5` / `## Step 9` and assert `"AskUserQuestion" not in section_text` when flag is set — modeled after `test_confidence_check_skill.py:48–58` and `test_refine_issue_command.py:66–73`
- Doc-wiring test: add assertions to `scripts/tests/test_enh1268_doc_wiring.py` (or a new file) verifying `--skip-issue-creation` and `--auto` appear in the `/ll:analyze-loop` and `/ll:assess-loop` sections of `docs/reference/COMMANDS.md` — modeled after `TestAssessLoopCommandsWiring` in `test_enh1268_doc_wiring.py:82–125`

### Documentation
- `docs/reference/COMMANDS.md` — add `--skip-issue-creation` and `--auto` to the `/ll:analyze-loop` and `/ll:assess-loop` entries (doc-wiring test in `test_enh1268_doc_wiring.py` checks this for `--no-rubric-audit`; same pattern applies)

### Configuration
- N/A

## Implementation Steps

1. **`skills/analyze-loop/SKILL.md:4`** — Update `argument-hint` from `"[loop-name] [--tail N]"` to `"[loop-name] [--tail N] [--skip-issue-creation] [--auto]"`.
2. **`skills/analyze-loop/SKILL.md:13`** — Add two entries to the `arguments:` block after the `tail` entry, following the `no_rubric_audit` style in `assess-loop/SKILL.md:20`.
3. **`skills/analyze-loop/SKILL.md:385`** (`## Step 5: Present Proposals and Confirm`) — Insert a prose guard before the `AskUserQuestion` call at line 410: `**Skip this step if `--skip-issue-creation` or `--auto` flag is set (or if `--dangerously-skip-permissions` is active).** Print: ℹ️ Issue creation skipped (--skip-issue-creation / --auto) and stop.`
4. **`skills/assess-loop/SKILL.md:4`** — Update `argument-hint` from `"[loop-name] [--tail N] [--no-rubric-audit]"` to add the two new flags.
5. **`skills/assess-loop/SKILL.md:13`** — Add two entries to the `arguments:` block after `no_rubric_audit` at line 20.
6. **`skills/assess-loop/SKILL.md:211`** (`## Step 9: Ranked Improvement Proposals`) — Insert the same prose guard before the `AskUserQuestion` call at line 246 (same wording as step 3 above).
7. Add test methods to `TestAnalyzeLoopSynthesis` in `scripts/tests/test_analyze_loop_synthesis.py` and `TestAssessLoopSkill` in `scripts/tests/test_assess_loop_skill.py`:
   - Simple flag-presence tests (Pattern 1): `assert "--skip-issue-creation" in skill_path.read_text()` — follow `test_skill_has_no_rubric_audit_flag` at `test_assess_loop_skill.py:72`
   - AskUserQuestion-absence tests (Pattern 3): slice to the relevant step section, assert `"AskUserQuestion" not in section_text when skip flag active — follow `test_confidence_check_skill.py:48–58`
8. Update `docs/reference/COMMANDS.md` to document the two new flags in the `/ll:analyze-loop` and `/ll:assess-loop` entries (see `--no-rubric-audit` as a reference; `test_enh1268_doc_wiring.py:TestAssessLoopCommandsWiring` will break if omitted).
9. Run `python -m pytest scripts/tests/test_analyze_loop_synthesis.py scripts/tests/test_assess_loop_skill.py scripts/tests/test_enh1268_doc_wiring.py -v` to verify.

## API/Interface

```
# New flags (both skills)
/ll:analyze-loop <loop_name> --skip-issue-creation   # Skip issue creation, exit cleanly
/ll:analyze-loop <loop_name> --auto                  # Non-interactive; implies --skip-issue-creation
/ll:assess-loop  <loop_name> --skip-issue-creation
/ll:assess-loop  <loop_name> --auto
```

## Impact

- **Priority**: P3 — blocks ENH-1328; low urgency otherwise
- **Effort**: Small — flag parsing + one conditional block per skill
- **Risk**: Low — additive change; no existing behavior altered when flags are absent
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/analyze-loop/SKILL.md` | Primary file to modify |
| `skills/assess-loop/SKILL.md` | Primary file to modify |
| `.issues/enhancements/P4-ENH-1328-outer-loop-eval-delegate-to-analyze-and-assess-loop.md` | Dependent issue that requires these flags |

## Labels

`enhancement`, `skills`, `loops`, `headless`, `captured`

## Resolution

Added `--skip-issue-creation` and `--auto` flags to both `/ll:analyze-loop` (Step 5) and `/ll:assess-loop` (Step 9) via prose guards in the respective SKILL.md frontmatter and issue-creation steps. Documentation and tests updated.

### Changes
- `skills/analyze-loop/SKILL.md`: updated `argument-hint`, added two `arguments:` entries, inserted prose guard before `AskUserQuestion` in Step 5
- `skills/assess-loop/SKILL.md`: updated `argument-hint`, added two `arguments:` entries, inserted prose guard before `AskUserQuestion` in Step 9
- `scripts/tests/test_analyze_loop_synthesis.py`: added three flag/guard tests
- `scripts/tests/test_assess_loop_skill.py`: added three flag/guard tests
- `scripts/tests/test_enh1268_doc_wiring.py`: added four doc-wiring tests
- `docs/reference/COMMANDS.md`: documented new flags in both command entries

## Status

**Completed** | Created: 2026-05-06 | Completed: 2026-05-06 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-06T18:11:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/617c17c5-3d4c-49c3-b7de-be5590f6346b.jsonl`
- `/ll:refine-issue` - 2026-05-06T18:05:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbc40eb3-e3ca-4350-ba0a-67dedf44a51c.jsonl`
- `/ll:format-issue` - 2026-05-06T17:59:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/81732e05-6dae-4a88-848e-c7f2ab988b76.jsonl`
- `/ll:capture-issue` - 2026-05-06T17:56:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/484c72e4-5eaa-4465-a207-cc2a1d3e75ea.jsonl`
- `/ll:confidence-check` - 2026-05-06T18:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f027346-babc-453f-9fe6-f810e69e4a86.jsonl`
- `/ll:manage-issue` - 2026-05-06T18:14:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/617c17c5-3d4c-49c3-b7de-be5590f6346b.jsonl`
