# ENH-456: Add intro context and improve feature descriptions in init wizard

**Created**: 2026-02-23
**Issue**: P3-ENH-456
**Action**: implement

## Research Findings

### File Locations
- `skills/init/interactive.md` — All wizard rounds; intro insertion point at line 26 (before Round 1), Round 3a descriptions at lines 162-170
- `skills/init/SKILL.md` — Top-level skill definition; dispatches to interactive.md at line 81

### Current State
- No intro text exists before Round 1 — wizard jumps straight to "Step 1 of ~7 — Core Settings"
- Round 3a feature descriptions use internal tool names (ll-parallel, /ll:sync-issues, manage-issue) without explanation
- Round 3b automation descriptions also reference tool names (ll-sprint, ll-loop, ll-auto) — in scope per "Round 3 feature option descriptions"

## Implementation Plan

### Phase 1: Add Wizard Intro Text

**File**: `skills/init/interactive.md`
**Location**: After line 24 (end of Progress Tracking Setup), before line 26 (Round 1 heading)

Add a section that outputs intro text before Round 1 begins:

```
## Wizard Introduction

Before starting Round 1, display the following introduction:

> **Welcome to little-loops setup!**
> This wizard creates `.claude/ll-config.json` — the configuration file that controls how little-loops manages your project's issues, code quality checks, and automation tools.
```

### Phase 2: Rewrite Round 3a Feature Descriptions

**File**: `skills/init/interactive.md`
**Lines**: 162-170

| Feature | Current | New |
|---------|---------|-----|
| Parallel processing | "Configure ll-parallel for concurrent issue processing with git worktrees" | "Process multiple issues in parallel using isolated git worktrees (requires ll-parallel CLI)" |
| Context monitoring | "Auto-handoff reminders at 80% context usage (works in all modes)" | "Get automatic reminders to save progress when a session is running low on context" |
| GitHub sync | "Sync issues with GitHub Issues via /ll:sync-issues" | "Keep local issue files and GitHub Issues in sync (two-way push/pull)" |
| Confidence gate | "Block manage-issue implementation when confidence score is below threshold" | "Require a minimum readiness score before automated implementation proceeds" |

### Phase 3: Improve Round 3b Automation Descriptions

**File**: `skills/init/interactive.md`
**Lines**: 186-191

| Feature | Current | New |
|---------|---------|-----|
| Sprint management | "Customize ll-sprint settings for wave-based issue processing" | "Process groups of related issues in coordinated waves (requires ll-sprint CLI)" |
| FSM loops | "Customize ll-loop settings for finite state machine automation" | "Run repeatable multi-step workflows using state machine definitions (requires ll-loop CLI)" |
| Sequential automation | "Customize ll-auto settings for sequential automated processing" | "Process issues one at a time in priority order (requires ll-auto CLI)" |

## Success Criteria

- [ ] Intro text displayed before Round 1
- [ ] Round 3a descriptions are self-explanatory without prior tool knowledge
- [ ] Round 3b descriptions are self-explanatory without prior tool knowledge
- [ ] No changes to wizard logic, question structure, or which features are offered
- [ ] No changes to other rounds

## Risk Assessment

- **Risk**: Low — text-only changes, no behavioral impact
- **Breaking Change**: No
