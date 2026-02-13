# ENH-314: README missing config sections - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-314-readme-missing-config-sections.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The README's "Full Configuration Example" (lines 119-187) and "Configuration Sections" (lines 189-285) document 7 config sections: `project`, `issues`, `automation`, `parallel`, `commands`, `scan`, `context_monitor`. Three actively-used sections are missing: `sync`, `sprints`, `documents`.

### Key Discoveries
- Schema definitions at `config-schema.json:494-524` (documents), `573-597` (sprints), `598-652` (sync)
- Active usage in `.claude/ll-config.json:21-51`
- Existing README sections follow `#### \`section\`` header + description + `| Key | Default | Description |` table pattern

## Desired End State

README includes all three missing config sections in both the Full Configuration Example and Configuration Sections area, following existing documentation patterns.

### How to Verify
- All three sections appear in the Full Configuration Example JSON block
- All three sections have Configuration Section tables
- Format matches existing sections (headers, tables, descriptions)

## What We're NOT Doing

- Not documenting `workflow`, `prompt_optimization`, `continuation`, or other undocumented sections
- Not modifying `config-schema.json`
- Not adding `default_mode` to sprints documentation (exists in ll-config.json but not in schema)

## Implementation Phases

### Phase 1: Add sections to Full Configuration Example

**File**: `README.md`
**Changes**: Insert `sync`, `sprints`, and `documents` JSON blocks after the `context_monitor` section (after line 185) and before the closing `}` brace.

#### Success Criteria
- [ ] JSON in the example is valid
- [ ] All schema-defined properties included with defaults
- [ ] Lint passes: `ruff check scripts/`

### Phase 2: Add Configuration Section tables

**File**: `README.md`
**Changes**: Insert three new `####` sections after `scan` (after line 284) and before `## Commands` (line 286).

Sections to add:
1. `sprints` - Sprint management settings (ll-sprint)
2. `sync` - GitHub Issues sync settings (/ll:sync_issues) — opt-in feature
3. `documents` - Document tracking for /ll:align_issues — opt-in feature with categories sub-explanation

#### Success Criteria
- [ ] Tables follow existing `| Key | Default | Description |` format
- [ ] Opt-in features include enabling instructions
- [ ] `documents` section includes categories sub-explanation with example JSON
