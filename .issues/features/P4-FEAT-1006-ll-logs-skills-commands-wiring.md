---
id: FEAT-1006
type: FEAT
priority: P4
status: backlog
title: Skills and commands wiring for ll-logs
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 78
testable: false
blocked_by: [FEAT-1002]
---

# FEAT-1006: Skills and commands wiring for ll-logs

## Summary

Wire `ll-logs` into the skills configuration and help command so the tool is authorized during project initialization and visible in `/ll:help` output. Covers `commands/help.md`, `skills/init/SKILL.md`, and `skills/configure/areas.md`.

## Current Behavior

`ll-logs` is not listed in the `commands/help.md` CLI TOOLS block, not authorized in the `skills/init/SKILL.md` permissions allow list, and not included in the CLAUDE.md boilerplate blocks (file-exists or create-new cases). The tool count in `skills/configure/areas.md` is 12 and does not include `ll-logs`.

## Expected Behavior

After implementation:
- `ll-logs` appears in the CLI TOOLS block in `commands/help.md`
- `"Bash(ll-logs:*)"` is in the permissions allow list in `skills/init/SKILL.md`
- `ll-logs` is listed in both CLAUDE.md boilerplate blocks in `skills/init/SKILL.md`
- The tool count in `skills/configure/areas.md` is updated from 12 to 13 with `ll-logs` appended

## Motivation

Without this wiring, `ll-logs` would be built (FEAT-1002) but effectively invisible: not shown in `/ll:help`, not authorized by default during project init, and absent from CLAUDE.md boilerplate. Users would need to manually discover and authorize the tool. This ensures `ll-logs` is a first-class citizen alongside all other `ll-*` CLI tools from day one.

## Use Case

**Who**: Developer setting up little-loops on a new project

**Context**: After running `/ll:init`, all `ll-*` CLI tools should be authorized and visible without additional configuration

**Goal**: Use `ll-logs` immediately after init without needing to manually add permissions or hunt through docs

**Outcome**: `ll-logs` appears in `/ll:help` output, is pre-authorized in `.claude/settings.local.json`, and is documented in the project's CLAUDE.md

## Parent Issue
Decomposed from FEAT-1004: Documentation and wiring updates for ll-logs

## Prerequisites

FEAT-1002 must be implemented first (`ll-logs` must exist). FEAT-1005 (documentation files) can be done in parallel.

## Implementation Steps

1. **Update `commands/help.md:208-221`** — add `ll-logs` to CLI TOOLS block (currently ends at `ll-check-links`). Only add `ll-logs`; do not fix the pre-existing `ll-gitignore` gap.

2. **Update skills configuration** (wiring):
   - `skills/init/SKILL.md:428-443` — add `"Bash(ll-logs:*)"` to canonical `permissions.allow` list written to `.claude/settings.local.json` during init (after `"Bash(ll-check-links:*)"`)
   - `skills/init/SKILL.md:510-522` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (file-exists case)
   - `skills/init/SKILL.md:539-546` — add `ll-logs` to CLAUDE.md CLI Tools boilerplate (create-new case)
   - `skills/configure/areas.md:793` — update count (`12` → `13`) and append `ll-logs` to enumerated list in the "Authorize all N ll- CLI tools" description string

## Integration Map

### Files to Modify
- `commands/help.md:208-221` — CLI TOOLS block (append `ll-logs` after `ll-check-links`)
- `skills/init/SKILL.md:441` — permissions.allow list (add `"Bash(ll-logs:*)"`)
- `skills/init/SKILL.md:522` — CLAUDE.md boilerplate, file-exists case (append `ll-logs` bullet)
- `skills/init/SKILL.md:546` — CLAUDE.md boilerplate, create-new case (append `ll-logs` bullet)
- `skills/configure/areas.md:793` — count 12→13, append `ll-logs` to enumerated list

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md:114-116` — the project's own CLI Tools section lists `ll-check-links` and `ll-gitignore` but not `ll-logs`; this is the live-system equivalent of the boilerplate blocks in `skills/init/SKILL.md` and must be updated in lockstep [Agent 1/2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_logs_wiring.py` — no tests exist for any of the three changed files; new test file needed following pattern in `scripts/tests/test_update_skill.py`:
  - Assert `"ll-logs"` present in `commands/help.md` CLI TOOLS block
  - Assert `"Bash(ll-logs:*)"` present in `skills/init/SKILL.md` permissions allow list
  - Assert `"ll-logs"` appears at least 2 times in `skills/init/SKILL.md` (file-exists and create-new boilerplate blocks)
  - Assert `"Authorize all 13"` present in `skills/configure/areas.md`
  - Assert `"ll-logs"` present in `skills/configure/areas.md` enumerated list [Agent 3 finding]

### Note: pre-existing gap
`ll-gitignore` is also missing from `commands/help.md` CLI TOOLS block (12 entries, ends at `ll-check-links`) and from the `skills/configure/areas.md` enumerated list. When implementing step 1, only add `ll-logs`; do not fix the `ll-gitignore` gap (separate issue). The count `12→13` in `skills/configure/areas.md` is correct for this scope.

### Similar Patterns
- Other `Bash(ll-*:*)` entries in `skills/init/SKILL.md` permissions block — follow same format

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified current state of each insertion point:**

- `commands/help.md:221` — `ll-check-links` is the last entry (confirmed 12 entries total); `ll-gitignore` is absent (pre-existing gap, do not add). Insert `ll-logs` after line 221.
- `skills/init/SKILL.md:441` — `"Bash(ll-check-links:*)",` immediately precedes `"Write(.ll/ll-continue-prompt.md)"` at line 442. Insert `"Bash(ll-logs:*)",` between them.
- `skills/init/SKILL.md:522` — This line is `` - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files `` (the last tool bullet in the file-exists block). Insert `ll-logs` bullet after this line.
- `skills/init/SKILL.md:546` — Same as above for the create-new block; `ll-gitignore` is also at line 546.
- `skills/configure/areas.md:793` — Full current text: `"Authorize all 12 ll- CLI tools and handoff write: ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-history, ll-deps, ll-sync, ll-verify-docs, ll-check-links, Write(.ll/ll-continue-prompt.md)"`. Append `ll-logs,` after `ll-check-links,` and change `12` to `13`.

**Exact description text to use for `ll-logs`:**

```
# commands/help.md — fixed-width two-column format (18-char left column):
ll-logs           Discover and extract ll-relevant log entries from Claude project logs

# skills/init/SKILL.md — both CLAUDE.md boilerplate blocks (bullet format):
- `ll-logs` - Discover and extract ll-relevant log entries from Claude project logs
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `.claude/CLAUDE.md` — append `ll-logs` bullet to the CLI Tools section (after `ll-check-links`) to match the init boilerplate being updated in step 2
4. Create `scripts/tests/test_ll_logs_wiring.py` — follow the pattern in `scripts/tests/test_update_skill.py`; assert that all three changed files contain the expected `ll-logs` strings after implementation

## API/Interface

N/A - No public API changes. Configuration-only updates to command and skill markdown files.

## Acceptance Criteria

- [ ] `commands/help.md` includes `ll-logs` in CLI TOOLS block
- [ ] `skills/init/SKILL.md` includes `"Bash(ll-logs:*)"` in permissions.allow list
- [ ] `skills/init/SKILL.md` includes `ll-logs` in both CLAUDE.md boilerplate blocks (file-exists and create-new cases)
- [ ] `skills/configure/areas.md` count incremented to 13 and `ll-logs` added to enumerated list

## Impact

- **Priority**: P4 - wiring/configuration
- **Effort**: Small - config updates only, no logic changes
- **Risk**: Very low - additive config changes
- **Breaking Change**: No

## Labels

`feature`, `wiring`, `cli`

## Verification Notes

**Verdict**: NEEDS_UPDATE — `ll-gitignore` was added to the codebase after this issue was written. Multiple counts and line references are now stale:

- `skills/configure/areas.md:793` now reads "Authorize all **13** ll- CLI tools" (includes `ll-gitignore`); count must go **13→14** (not 12→13)
- `commands/help.md` now has 13 CLI entries ending at `ll-gitignore` (line 230) — the "pre-existing gap" was fixed; insert `ll-logs` after line 230
- `skills/init/SKILL.md`: `"Bash(ll-gitignore:*)"` already present at line 442; insert `"Bash(ll-logs:*)"` after that (not after `ll-check-links` at 441)
- `skills/init/SKILL.md` boilerplate blocks: `ll-gitignore` is at line 523 (file-exists) and 547 (create-new) — one line later than stated; insert `ll-logs` after those
- `skills/configure/areas.md:793` enumerated list now ends with `ll-gitignore`; append `ll-logs` after it, and update "Authorize all 13" → "Authorize all 14"

— Verified 2026-04-11

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:37:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74f31a92-c105-4f9d-96fe-e1197b28ca78.jsonl`
- `/ll:confidence-check` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c3db3cb3-ebe4-456e-9528-2cdf0057d9ef.jsonl`
- `/ll:wire-issue` - 2026-04-08T22:40:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c7abbb6-2a5d-4619-b357-ee4dba5547bf.jsonl`
- `/ll:refine-issue` - 2026-04-08T22:22:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c7abbb6-2a5d-4619-b357-ee4dba5547bf.jsonl`
- `/ll:format-issue` - 2026-04-08T22:20:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e62cdbf4-324a-40f3-bc53-28315803f0f0.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7158b6b3-d465-4658-9645-8a41be41765d.jsonl`

---

## Status

**Open** | Created: 2026-04-08 | Priority: P4
