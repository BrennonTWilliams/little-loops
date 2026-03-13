# ENH-668: Add `--check` flag to issue prep skills

## Overview

Add `--check` (check-only, non-interactive) flag to 8 issue prep skills/commands so they can serve as FSM loop evaluators that exit non-zero when work remains.

## Implementation Phases

### Phase 1: Skills with $ARGUMENTS pattern (already have --auto)

**1a. `skills/confidence-check/SKILL.md`**
- Add `if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 46)
- Add `--check` to argument docs
- Add check-mode section: run all evaluation logic, collect issues below threshold, print `[ID] check: score N/100 (below threshold)` per failing issue, exit 1 if any fail, exit 0 if all pass

**1b. `skills/issue-size-review/SKILL.md`**
- Add `CHECK_MODE=false` and `if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 49)
- Add `--check` to argument docs
- Add check-mode section: run size scoring, print `[ID] size: score N (oversized)` per failing issue (score >= 5), exit 1 if any fail, exit 0 if all pass

**1c. `skills/map-dependencies/SKILL.md`**
- Add `CHECK_MODE=false` and `if [[ "$ARGUMENTS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 42)
- Add `--check` to argument docs
- Add check-mode section: run dependency analysis, print `[ID] deps: N unmapped dependencies` per issue with unmapped deps, exit 1 if any unmapped, exit 0 if all mapped

**1d. `skills/format-issue/SKILL.md`**
- Add `CHECK_MODE=false` and `if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 63)
- Note: format-issue uses `$FLAGS` not `$ARGUMENTS` (it has frontmatter arguments)
- `--check` acts as dry-run of auto mode: run analysis, print `[ID] format: N gaps found`, exit 1 if gaps, exit 0 if compliant
- Add `--check` implies `--auto` (check is non-interactive)

### Phase 2: Commands with $FLAGS pattern (already have --auto)

**2a. `commands/verify-issues.md`**
- Add `CHECK_MODE=false` and `if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 43)
- Add `--check` to argument docs
- Add check-mode section: run verification, print `[ID] verify: [verdict]` per non-VALID issue, exit 1 if any non-VALID, exit 0 if all valid

**2b. `commands/prioritize-issues.md`**
- Add `CHECK_MODE=false` and `if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi` to parse block (after line 39)
- Add `--check` to argument docs
- Check-mode: scan for unprioritized issues, print `[ID] priority: missing P[0-5] prefix` per issue, exit 1 if any unprioritized, exit 0 if all prioritized

### Phase 3: Commands needing flag parsing from scratch

**3a. `commands/normalize-issues.md`**
- Add frontmatter `arguments` with `flags` parameter
- Add `### 0. Parse Flags` section before Process step 0:
  ```bash
  FLAGS="${flags:-}"
  AUTO_MODE=false
  CHECK_MODE=false
  if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then AUTO_MODE=true; fi
  if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
  if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; fi
  ```
- Add `$ARGUMENTS` section after Examples
- Check-mode: scan for invalid filenames + duplicate IDs + dir violations, print one line per issue, exit 1 if any found, exit 0 if clean

**3b. `commands/ready-issue.md`**
- Already has `flags` in frontmatter with `--deep`
- Add `### 0. Parse Flags` section before Process step 1:
  ```bash
  ISSUE_ID="${issue_id:-}"
  FLAGS="${flags:-}"
  CHECK_MODE=false
  DEEP_MODE=false
  if [[ "$FLAGS" == *"--deep"* ]]; then DEEP_MODE=true; fi
  if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; fi
  ```
- Check-mode: run validation, print `[ID] ready: [verdict]` (READY/CORRECTED → pass, else fail), exit 1 if not ready, exit 0 if ready

### Phase 4: Documentation

**4a. `docs/guides/LOOPS_GUIDE.md`**
- Add a "Prep-Sprint Pattern" example section showing how to use `--check` with `evaluate: type: exit_code` in an FSM loop

### Phase 5: Verification
- [ ] All 8 files modified with --check flag
- [ ] Flag parsing consistent with existing patterns
- [ ] Output format consistent: `[ID] [gate]: [reason]`
- [ ] Exit codes: 0=pass, 1=fail
- [ ] Lint passes
- [ ] Tests pass

## Success Criteria

- [x] Plan created
- [ ] Phase 1: 4 skills updated
- [ ] Phase 2: 2 commands updated
- [ ] Phase 3: 2 commands updated (flag parsing from scratch)
- [ ] Phase 4: LOOPS_GUIDE.md updated
- [ ] Phase 5: Verification passes
