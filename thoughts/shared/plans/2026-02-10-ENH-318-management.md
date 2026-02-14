# ENH-318: README missing config properties and 2 undocumented sections - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P3-ENH-318-readme-missing-config-properties-and-2-sections.md
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The README.md (lines 225-387) documents 10 config sections in `### Configuration Sections`. Two sections defined in `config-schema.json` are entirely absent: `workflow` (schema lines 296-358) and `prompt_optimization` (schema lines 360-394). Three properties are missing from existing tables: `project.test_dir`, `issues.capture_template`, and `issues.duplicate_detection`.

The Full Configuration Example (lines 119-222) also omits these properties/sections.

### Key Discoveries
- Tables use 3-column format: `| Key | Default | Description |` (README.md:231)
- Nested objects use dot notation in flat tables (e.g., `sync` section at README.md:349-357)
- Enum values shown with quotes in backticks: `"github"` (README.md:352)
- Sections reference commands in description line (README.md:347, 363)
- `workflow` and `prompt_optimization` sit between `scan` and `continuation` in schema ordering

## Desired End State

README has complete documentation for all config sections and properties defined in `config-schema.json`:
1. `project` table includes `test_dir` row
2. `issues` table includes `capture_template` and `duplicate_detection` rows
3. New `workflow` section table with all 7 properties using dot notation
4. New `prompt_optimization` section table with all 5 properties
5. Full Configuration Example includes all missing properties/sections

### How to Verify
- All properties in `config-schema.json` have corresponding README documentation
- Table format matches existing patterns exactly
- Full Configuration Example includes all new entries

## What We're NOT Doing

- Not documenting `commands` section (not called out in ENH-318)
- Not documenting `context_monitor` section (explicitly out of scope per ENH-318)
- Not restructuring existing sections
- Not adding usage examples or guides

## Solution Approach

Make targeted additions to README.md:
1. Add missing rows to existing tables
2. Insert two new section tables between `scan` and `continuation`
3. Update the Full Configuration Example JSON block

## Implementation Phases

### Phase 1: Add missing properties to existing tables

#### Changes Required

**File**: `README.md`

1. Add `test_dir` row to `project` table (after `src_dir` row at line 234):
```
| `test_dir` | `tests` | Test directory path |
```

2. Add `capture_template` and `duplicate_detection` rows to `issues` table (after `templates_dir` row at line 252):
```
| `capture_template` | `"full"` | Default template style for captured issues (`"full"` or `"minimal"`) |
| `duplicate_detection.exact_threshold` | `0.8` | Jaccard similarity threshold for exact duplicates (0.5-1.0) |
| `duplicate_detection.similar_threshold` | `0.5` | Jaccard similarity threshold for similar issues (0.1-0.9) |
```

#### Success Criteria
- [ ] `project` table has 9 rows (was 8)
- [ ] `issues` table has 8 rows (was 5)
- [ ] Dot notation used for `duplicate_detection` nested properties

### Phase 2: Add `workflow` and `prompt_optimization` section tables

#### Changes Required

**File**: `README.md`

Insert between `scan` section (ends at line 319) and `continuation` section (starts at line 321):

```markdown
#### `workflow`

Workflow behavior settings (`/ll:manage-issue`, `/ll:ready-issue`):

| Key | Default | Description |
|-----|---------|-------------|
| `phase_gates.enabled` | `true` | Enable phase gates for manual verification |
| `phase_gates.auto_mode_skip` | `true` | Skip phase gates when --auto flag is used |
| `deep_research.enabled` | `true` | Enable deep research by default |
| `deep_research.quick_flag_skips` | `true` | Allow --quick flag to skip research |
| `deep_research.agents` | 3 sub-agents | Sub-agents to spawn for research |
| `plan_template.sections_recommended` | `true` | Show all template sections as recommended |
| `plan_template.sections_mandatory` | `false` | Require all template sections |

#### `prompt_optimization`

Automatic prompt optimization settings (`/ll:toggle-autoprompt`):

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable automatic prompt optimization |
| `mode` | `"quick"` | Optimization mode (`"quick"` or `"thorough"`) |
| `confirm` | `true` | Show diff and ask for confirmation before applying |
| `bypass_prefix` | `*` | Prefix to bypass optimization |
| `clarity_threshold` | `6` | Minimum clarity score (1-10) to pass through unchanged |
```

#### Success Criteria
- [ ] `workflow` section exists between `scan` and `continuation`
- [ ] `prompt_optimization` section exists between `workflow` and `continuation`
- [ ] Both use dot notation pattern for nested keys
- [ ] Both reference relevant slash commands

### Phase 3: Update Full Configuration Example

#### Changes Required

**File**: `README.md`

1. Add `test_dir` to project block (after `src_dir` line 125)
2. Add `capture_template` and `duplicate_detection` to issues block (after `templates_dir` line 143)
3. Add `workflow` block (after `scan` block, before `continuation`)
4. Add `prompt_optimization` block (after `workflow`, before `continuation`)

#### Success Criteria
- [ ] Full Configuration Example includes all new properties
- [ ] JSON is valid
- [ ] New blocks are in schema order

## Testing Strategy

- Visual inspection of table formatting consistency
- Verify all properties in schema have README coverage (for in-scope sections)
- Verify JSON in Full Configuration Example is valid

## References

- Issue: `.issues/enhancements/P3-ENH-318-readme-missing-config-properties-and-2-sections.md`
- Schema: `config-schema.json:25-29` (test_dir), `config-schema.json:115-141` (capture_template, duplicate_detection), `config-schema.json:296-394` (workflow, prompt_optimization)
- Existing pattern: `README.md:345-357` (sync section with dot notation)
