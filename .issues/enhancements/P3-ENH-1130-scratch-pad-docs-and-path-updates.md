---
id: ENH-1130
type: ENH
priority: P3
status: done
parent: ENH-1111
size: Small
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
completed_at: '2026-04-22T20:11:55Z'
---

# ENH-1130: Documentation and Path Updates for Scratch-Pad Hook

## Summary

Update all documentation and inline references for the scratch-pad enforcement feature: correct `/tmp/ll-scratch/` → `.loops/tmp/scratch/` everywhere, update CLAUDE.md to describe automatic enforcement, document new `scratch_pad` config properties in CONFIGURATION.md and ARCHITECTURE.md. Independent of ENH-1128/ENH-1129 — can be done in any order.

## Current Behavior

- `.claude/CLAUDE.md:122-130` (`## Automation: Scratch Pad`) still instructs Claude to write scratch files to `/tmp/ll-scratch/`, the path that BUG-817 migrated away from. Live misdirection at session-start time.
- `docs/guides/LOOPS_GUIDE.md:569` CLI override example shows `--context scratch_dir=/tmp/ll-scratch`, also the old path.
- `docs/reference/CONFIGURATION.md:162-165` JSON example block shows only 2 of 6 `scratch_pad` keys (`enabled`, `threshold_lines`), making the other four keys (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) undiscoverable from the example.

## Expected Behavior

- `.claude/CLAUDE.md:122-130` references `.loops/tmp/scratch/` as the active scratch path, notes the `scratch-pad-redirect` PreToolUse hook auto-enforces when `scratch_pad.enabled: true`, and points at the `scratch_pad` config keys.
- `docs/guides/LOOPS_GUIDE.md:569` CLI override example shows `--context scratch_dir=.loops/tmp` (the FSM default per `context-health-monitor.yaml`).
- `docs/reference/CONFIGURATION.md:162-165` JSON example block includes all 6 `scratch_pad` keys with their schema defaults.

## Parent Issue

Decomposed from ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Motivation

BUG-817 migrated the active scratch path to `.loops/tmp/scratch/` but CLAUDE.md still references `/tmp/ll-scratch/`. Additionally, once the hook ships (ENH-1129), the prose convention text in CLAUDE.md can be replaced with a pointer to the `scratch_pad` config keys.

## Acceptance Criteria

- `.claude/CLAUDE.md:122-130` (`## Automation: Scratch Pad` section) updated to:
  - Describe automatic enforcement via the hook
  - Correct path from `/tmp/ll-scratch/` → `.loops/tmp/scratch/`
  - Point at `scratch_pad` config keys (`enabled`, `threshold_lines`, `automation_contexts_only`, etc.)
  - Remove prose instructions the hook now enforces
- `docs/reference/CONFIGURATION.md:155,474-481` updated with the four new `scratch_pad` properties (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) and their defaults
- `docs/ARCHITECTURE.md:90-95` (hook scripts directory listing) gains `scratch-pad-redirect.sh` entry
- `docs/guides/LOOPS_GUIDE.md:569` — correct `/tmp/ll-scratch` → `.loops/tmp` in `scratch_dir` CLI override example (FSM default is `.loops/tmp`, not `.loops/tmp/scratch`)
- After editing CLAUDE.md, run `python -m pytest scripts/tests/test_create_extension_wiring.py -v` to confirm `"ll-create-extension"` and `"ll-generate-schemas"` string assertions still pass (low-risk but verify; test reads CLAUDE.md at `scripts/tests/test_create_extension_wiring.py:83-87,162-166`)

## Files to Modify

- `.claude/CLAUDE.md:122-130`
- `docs/reference/CONFIGURATION.md:162-165`
- `docs/guides/LOOPS_GUIDE.md:569`
- `docs/ARCHITECTURE.md:90-95` — already satisfied; do not modify

## Integration Map

### Files to Modify
- `.claude/CLAUDE.md:122-130` — Replace `/tmp/ll-scratch/` on lines 126-127 with `.loops/tmp/scratch/`; add sentence noting `scratch-pad-redirect` PreToolUse hook auto-enforces when `scratch_pad.enabled: true`; add pointer to `scratch_pad` config keys (`enabled`, `threshold_lines`, `automation_contexts_only`, `tail_lines`); condense manual prose
- `docs/guides/LOOPS_GUIDE.md:568` — Change `--context scratch_dir=/tmp/ll-scratch` to `--context scratch_dir=.loops/tmp` (actual FSM default per `context-health-monitor.yaml:10`)
- `docs/reference/CONFIGURATION.md:162-165` — JSON example block shows only 2 of 6 `scratch_pad` keys (`enabled`, `threshold_lines`); expand to include all six (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) with their schema defaults

### Already Satisfied — Do Not Modify
- `docs/reference/CONFIGURATION.md:489-500` — AC2 **prose table** complete; all six `scratch_pad` properties documented (by prior commit `d50560d0`); note: the JSON example block at lines 162-165 is NOT satisfied — see "Files to Modify" above
- `docs/ARCHITECTURE.md:93` — AC3 `scratch-pad-redirect.sh` entry already present (by prior commit `61a2cd66`)

### Reference (Read-Only)
- `hooks/scripts/scratch-pad-redirect.sh:81-82,116` — Source of truth; hook writes to `.loops/tmp/scratch/`
- `scripts/little_loops/loops/context-health-monitor.yaml:10` — Confirms `scratch_dir` FSM default is `.loops/tmp` (parent dir, not the hook subdirectory)
- `config-schema.json:609-651` — All six `scratch_pad` properties already defined

### Tests
- `scripts/tests/test_create_extension_wiring.py:83-87,162-166` — Run after CLAUDE.md edit to confirm `ll-create-extension` and `ll-generate-schemas` substring assertions still pass (per AC5); scratch pad changes won't affect them but verify anyway

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1130_doc_wiring.py` — new test file needed; follow `test_enh1138_doc_wiring.py` pattern; assert `.loops/tmp/scratch/` appears in `.claude/CLAUDE.md` and `.loops/tmp` appears in `docs/guides/LOOPS_GUIDE.md:568` (and `/tmp/ll-scratch` no longer appears in either)

## Implementation Steps

1. Edit `.claude/CLAUDE.md:122-130`: replace `/tmp/ll-scratch/` with `.loops/tmp/scratch/` on lines 126-127; add hook-enforcement note; add `scratch_pad` config key pointers; condense manual prose
2. Edit `docs/guides/LOOPS_GUIDE.md:568`: change `scratch_dir=/tmp/ll-scratch` to `scratch_dir=.loops/tmp`
3. Edit `docs/reference/CONFIGURATION.md:162-165`: expand the `scratch_pad` JSON example block from 2 keys to all 6 (`enabled`, `threshold_lines`, `automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) using schema defaults from `config-schema.json:609-651`
4. Skip `docs/ARCHITECTURE.md` — AC3 already satisfied by prior commit `61a2cd66`
5. Run `python -m pytest scripts/tests/test_create_extension_wiring.py -v` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Create `scripts/tests/test_enh1130_doc_wiring.py` — new wiring test file asserting: (a) `.loops/tmp/scratch/` appears in `.claude/CLAUDE.md`, (b) `/tmp/ll-scratch` no longer appears in `.claude/CLAUDE.md`, (c) `.loops/tmp` appears in `docs/guides/LOOPS_GUIDE.md` at the `scratch_dir` override example; follow pattern from `scripts/tests/test_enh1138_doc_wiring.py`

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-04-22_ — **NO-GO (REFINE)**

**Deciding Factor**: AC4 specifies an objectively wrong target path (`.loops/tmp/scratch` vs the actual FSM default `.loops/tmp` confirmed at `context-health-monitor.yaml:10`). The issue must be updated to reflect current codebase state and resolve the correct path before implementation proceeds.

### Key Arguments For
- CLAUDE.md lines 126-127 actively instruct Claude to write scratch files to `/tmp/ll-scratch/`, the exact path BUG-817 identified as causing silent data corruption across concurrent sessions — live misdirection at session-start time.
- The CONFIGURATION.md JSON example block at lines 162-165 shows only two `scratch_pad` keys while the config schema defines six, making four config keys (`automation_contexts_only`, `tail_lines`, `command_allowlist`, `file_extension_filters`) undiscoverable.

### Key Arguments Against
- AC4's "correction" (`/tmp/ll-scratch` → `.loops/tmp/scratch`) introduces a semantic error: `context-health-monitor.yaml:10` confirms `scratch_dir` defaults to `.loops/tmp` (the parent), not `.loops/tmp/scratch`. The correct fix would be `.loops/tmp`, making the override example redundant rather than corrective.
- AC3 (`docs/ARCHITECTURE.md:93` — `scratch-pad-redirect.sh` entry) and AC2's prose table (`docs/reference/CONFIGURATION.md:489-500` — all six `scratch_pad` properties) are already fully satisfied by prior commits (`61a2cd66`, `d50560d0`); the issue has not been audited against the current codebase.

### Rationale
The issue contains at least one demonstrably incorrect acceptance criterion: AC4 specifies correcting `scratch_dir=/tmp/ll-scratch` to `scratch_dir=.loops/tmp/scratch`, but `context-health-monitor.yaml:10` confirms the actual FSM default is `scratch_dir: .loops/tmp`. Changing the example to `.loops/tmp/scratch` would introduce a semantic error — the monitor watches all loop output files under `.loops/tmp/`, not just the hook's subdirectory. Additionally, AC3 and AC2's prose table are already satisfied by prior commits, meaning the issue has not been audited against current codebase state. The CLAUDE.md correction (AC1) is real and valid, but implementing the issue as written bundles a valid fix with a wrong one.

## Scope Boundaries

- Only updating documentation and inline reference strings — no code logic changes.
- `docs/ARCHITECTURE.md` (AC3) and `docs/reference/CONFIGURATION.md` prose table (AC2) are explicitly out of scope — already satisfied by prior commits `61a2cd66` and `d50560d0`.
- No changes to hook scripts or config schema.

## Impact

- **Priority**: P3 — Live documentation misdirection; not breaking but causes confusion in automation sessions
- **Effort**: Small — Three targeted text edits plus a new wiring test file
- **Risk**: Low — Documentation-only; no runtime behavior changes; verified by wiring test
- **Breaking Change**: No

## Labels

`documentation`, `enhancement`, `scratch-pad`

## Status

**Open** | Created: 2026-04-22 | Priority: P3

## Session Log
- `ll-auto` - 2026-04-22T20:11:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b845b2b2-cee1-4d01-8790-c3b7599dd1ce.jsonl`
- `/ll:ready-issue` - 2026-04-22T20:09:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44738150-1e95-485b-b9de-efb28cd3a773.jsonl`
- `/ll:wire-issue` - 2026-04-22T20:00:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11e2d49e-b581-4771-8622-7d23334f2839.jsonl`
- `/ll:refine-issue` - 2026-04-22T19:57:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d97b3fc-442b-4215-a0e1-e7e88115a06e.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7d6ff545-eb89-4060-969d-7b25e3f9974e.jsonl`


---

## Resolution

- **Action**: improve
- **Completed**: 2026-04-22
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
